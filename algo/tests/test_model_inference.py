"""Synthetic model-component composition checks, not passenger accuracy tests."""

import math
import itertools
import random
import unittest

from stayorswitch.model_training.inference import (
    choose_catchable, compose_candidate, evaluate_supplied_path,
)


def train(identifier="train", departure=100, arrival=300, departure_delta=0, segment_delta=0):
    return {"trip_id": identifier, "departure_at": departure, "arrival_at": arrival,
            "departure_correction_seconds": departure_delta,
            "segment_correction_seconds": segment_delta}


class ComponentCompositionTests(unittest.TestCase):
    def compose(self, candidate, ready=50, decision=0):
        return compose_candidate(candidate, decision_at=decision, ready_at=ready)

    def test_departure_and_segment_residuals_are_applied_once(self):
        result = self.compose(train(departure_delta=40, segment_delta=20))
        self.assertEqual(result["departure_at"], 140)
        self.assertEqual(result["riding_seconds"], 220)
        self.assertEqual(result["arrival_at"], 360)
        self.assertEqual(result["waiting_seconds"], 90)

    def test_arrival_residual_is_explicitly_rejected(self):
        candidate = train()
        candidate["arrival_correction_seconds"] = 30
        result = self.compose(candidate)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason_code"], "ARRIVAL_RESIDUAL_NOT_APPLICABLE_TO_COMPOSITION")

    def test_delayed_departure_can_become_catchable(self):
        self.assertEqual(self.compose(train(), ready=120)["status"], "UNAVAILABLE")
        self.assertEqual(self.compose(train(departure_delta=30), ready=120)["status"], "USABLE")

    def test_earlier_corrected_departure_can_be_missed(self):
        result = self.compose(train(departure_delta=-30), ready=80)
        self.assertEqual(result["reason_code"], "NOT_CATCHABLE_AT_READY_TIME")

    def test_departure_exactly_at_readiness_is_catchable(self):
        self.assertEqual(self.compose(train(), ready=100)["status"], "USABLE")

    def test_negative_corrected_duration_is_not_silently_clipped(self):
        result = self.compose(train(segment_delta=-201))
        self.assertEqual(result["reason_code"], "NEGATIVE_CORRECTED_RIDING_TIME")

    def test_departure_before_decision_is_unavailable(self):
        result = self.compose(train(departure_delta=-101))
        self.assertEqual(result["reason_code"], "CORRECTED_DEPARTURE_BEFORE_DECISION")

    def test_nonfinite_missing_and_boolean_inputs_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf, None, True, "10", 10 ** 400):
            with self.subTest(value=value):
                candidate = train()
                candidate["segment_correction_seconds"] = value
                self.assertEqual(self.compose(candidate)["reason_code"], "INVALID_COMPONENT_VALUE")
        candidate = train()
        del candidate["departure_at"]
        self.assertEqual(self.compose(candidate)["reason_code"], "INVALID_COMPONENT_VALUE")

    def test_baseline_order_and_arithmetic_overflow_are_rejected(self):
        self.assertEqual(self.compose(train(departure=300, arrival=100))["reason_code"],
                         "INVALID_BASELINE_TIME_ORDER")
        self.assertEqual(self.compose(train(departure=1e308, arrival=1e308,
                                            departure_delta=1e308))["reason_code"],
                         "COMPONENT_ARITHMETIC_OVERFLOW")

    def test_invalid_global_readiness_raises(self):
        with self.assertRaises(ValueError):
            self.compose(train(), ready=-1)
        with self.assertRaises(ValueError):
            self.compose(train(), decision=math.nan)

    def test_candidate_selection_uses_arrival_not_departure_order(self):
        result = choose_catchable([train("slow", 100, 500), train("fast", 120, 300)],
                                  decision_at=0, ready_at=50)
        self.assertEqual(result["selected"]["trip_id"], "fast")

    def test_exact_ties_preserve_input_order(self):
        result = choose_catchable([train("first"), train("second")], decision_at=0, ready_at=50)
        self.assertEqual(result["selected"]["trip_id"], "first")

    def test_empty_or_uncatchable_candidates_do_not_create_a_train(self):
        for candidates in ([], [train(departure=10, arrival=100)]):
            self.assertIsNone(choose_catchable(candidates, decision_at=0, ready_at=50)["selected"])


class SuppliedPathTests(unittest.TestCase):
    def evaluate(self, legs, access=50, egress=20):
        return evaluate_supplied_path(decision_at=0, access_walk_seconds=access,
                                      transit_legs=legs, egress_walk_seconds=egress)

    def test_upstream_correction_rechecks_connection_and_selects_next_train(self):
        legs = [{"candidates": [train("first", 100, 200, segment_delta=100)],
                 "transfer_walk_seconds_after": 30},
                {"candidates": [train("missed", 250, 400), train("next", 350, 500)]}]
        result = self.evaluate(legs)
        self.assertEqual(result["legs"][1]["selected"]["trip_id"], "next")
        self.assertEqual(result["arrival_at"], 520)
        self.assertEqual(result["components"],
                         {"walking_seconds": 100, "waiting_seconds": 70, "riding_seconds": 350})
        self.assertEqual(sum(result["components"].values()), result["total_duration_seconds"])

    def test_no_next_connection_returns_unavailable(self):
        legs = [{"candidates": [train("first", 100, 300)], "transfer_walk_seconds_after": 30},
                {"candidates": [train("missed", 250, 400)]}]
        result = self.evaluate(legs)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIsNone(result["arrival_at"])
        self.assertIsNone(result["components"])

    def test_walking_only_path_is_supported(self):
        result = self.evaluate([], access=150, egress=100)
        self.assertEqual(result["arrival_at"], 250)
        self.assertEqual(result["components"]["walking_seconds"], 250)

    def test_negative_walk_and_double_counted_final_transfer_raise(self):
        with self.assertRaises(ValueError):
            self.evaluate([], access=-1)
        with self.assertRaises(ValueError):
            self.evaluate([{"candidates": [train()], "transfer_walk_seconds_after": 10}])

    def test_zero_riding_time_is_nonnegative(self):
        result = self.evaluate([{"candidates": [train(segment_delta=-200)]}])
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["components"]["riding_seconds"], 0)

    def test_fixed_path_matches_exhaustive_corrected_connections(self):
        generator = random.Random(5900)
        for case in range(100):
            legs = []
            for index in range(3):
                candidates = []
                for option in range(3):
                    departure = generator.randint(0, 1000)
                    candidates.append(train("{}-{}".format(index, option), departure,
                                            departure + generator.randint(0, 400),
                                            generator.randint(-80, 100),
                                            generator.randint(-80, 100)))
                legs.append({"candidates": candidates,
                             "transfer_walk_seconds_after": generator.randint(0, 90) if index < 2 else 0})
            access, egress = generator.randint(0, 150), generator.randint(0, 90)
            outcomes = []
            for combination in itertools.product(*(leg["candidates"] for leg in legs)):
                cursor = access
                for leg, candidate in zip(legs, combination):
                    departure = candidate["departure_at"] + candidate["departure_correction_seconds"]
                    duration = (candidate["arrival_at"] - candidate["departure_at"]
                                + candidate["segment_correction_seconds"])
                    if departure < cursor or duration < 0:
                        break
                    cursor = departure + duration + leg["transfer_walk_seconds_after"]
                else:
                    outcomes.append(cursor + egress)
            result = self.evaluate(legs, access=access, egress=egress)
            with self.subTest(case=case):
                self.assertEqual(result["arrival_at"], min(outcomes) if outcomes else None)


if __name__ == "__main__":
    unittest.main()
