"""Behavioral regressions for conservative boarding without ETA penalties."""

from copy import deepcopy
import math
import unittest

from algo.tests.test_severe import (
    IncidentFake, NOW, ProfileFake, context, leg, route, snapshot, train,
)
from stayorswitch.boarding_safe import evaluate_modes, predict_routes
from stayorswitch.severe import predict_routes as original_predict_routes


def prediction(templates=None, snapshots=None, *, mode="mta", profiles=None,
               incidents=None, margin=120):
    templates = templates if templates is not None else [route()]
    snapshots = list(snapshots) if snapshots is not None else [
        snapshot([train(departure=240)])]
    if not any(item["feed_id"] == "subway-alerts" for item in snapshots):
        snapshots.append(snapshot(feed="subway-alerts"))
    return predict_routes(
        snapshots, templates, NOW, mode=mode, estimator=profiles,
        incident_index=incidents or IncidentFake(), boarding_margin_seconds=margin)


class BoardingEligibilityTests(unittest.TestCase):
    def test_positive_average_delay_cannot_make_an_uncatchable_train_eligible(self):
        templates = [route(access=120)]
        feeds = [snapshot([train(departure=90, arrival=600)])]
        profiles = ProfileFake({("F", "departure"): 180})
        original = original_predict_routes(
            feeds, templates, NOW, mode="time_profile", estimator=profiles,
            incident_index=IncidentFake())["routes"][0]
        self.assertTrue(original["timing_eligible"])
        for margin in (0, 60, 120, 180):
            with self.subTest(margin=margin):
                safe = prediction(templates, feeds, mode="time_profile",
                                  profiles=profiles, margin=margin)["routes"][0]
                self.assertFalse(safe["timing_eligible"])
                rejected = safe["rejected"][0]
                self.assertEqual(rejected["reason"], "INSUFFICIENT_BOARDING_MARGIN")
                self.assertEqual(rejected["boarding_gate"]["slack_seconds"], -30)

    def test_rejected_optimistic_train_is_replaced_by_a_safe_later_option(self):
        feeds = [snapshot([train("too-tight", departure=90, arrival=600),
                           train("later", departure=360, arrival=900)])]
        profiles = ProfileFake({("F", "departure"): 180})
        result = prediction([route(access=120)], feeds, mode="time_profile",
                            profiles=profiles)["routes"][0]
        self.assertTrue(result["timing_eligible"])
        self.assertTrue(result["selected_legs"][0]["trip_id"].endswith(":later"))

    def test_exact_margin_boundary_is_admitted_but_less_is_not(self):
        for departure, expected in ((180, True), (179.999, False)):
            with self.subTest(departure=departure):
                result = prediction(snapshots=[snapshot([train(departure=departure)])])["routes"][0]
                self.assertEqual(result["timing_eligible"], expected)

    def test_positive_departure_correction_does_not_reduce_required_margin(self):
        profiles = ProfileFake({("F", "departure"): 180})
        result = prediction(snapshots=[snapshot([train(departure=179)])],
                            mode="incident_profile", profiles=profiles)["routes"][0]
        self.assertFalse(result["timing_eligible"])
        self.assertEqual(result["rejected"][0]["boarding_gate"]["slack_seconds"], 119)

    def test_negative_departure_correction_can_tighten_the_gate(self):
        feeds = [snapshot([train(departure=240)])]
        raw = prediction(snapshots=feeds)["routes"][0]
        safe = prediction(snapshots=feeds, mode="time_profile",
                          profiles=ProfileFake({("F", "departure"): -61}))["routes"][0]
        self.assertTrue(raw["timing_eligible"])
        self.assertFalse(safe["timing_eligible"])
        self.assertEqual(safe["rejected"][0]["boarding_gate"]["slack_seconds"], 119)

    def test_expired_raw_forecast_is_not_revived_by_large_delay(self):
        safe = prediction(snapshots=[snapshot([train(departure=-10)])],
                          mode="time_profile",
                          profiles=ProfileFake({("F", "departure"): 300}))["routes"][0]
        self.assertFalse(safe["timing_eligible"])
        self.assertEqual(safe["rejected"][0]["reason"], "EXPIRED_BASELINE_FORECAST")

    def test_all_modes_receive_the_same_margin(self):
        result = evaluate_modes(
            [snapshot([train(departure=150)])], [route()], NOW, "current",
            estimator=ProfileFake({("F", "departure"): 300}),
            incident_index=IncidentFake(), boarding_margin_seconds=120,
            require_severe=False)
        for mode, value in result.items():
            with self.subTest(mode=mode):
                self.assertFalse(value["routes"][0]["timing_eligible"])
                self.assertEqual(value["policy"]["boarding_margin_seconds"], 120)
                self.assertEqual(value["strict_decision"]["action"], "UNDETERMINED")

    def test_invalid_margin_is_rejected(self):
        for margin in (-1, True, None, "120", math.inf, math.nan):
            with self.subTest(margin=margin), self.assertRaises(ValueError):
                prediction(margin=margin)


class TransferAndDurationTests(unittest.TestCase):
    def test_early_arrival_correction_does_not_create_a_tight_transfer(self):
        template = route(legs=[leg(), leg("G", "P2S", "P3S")], transfers=[60])
        feeds = [snapshot([train(departure=240, arrival=600)]),
                 snapshot([train("too-early", "G", 650, 900, "P2S", "P3S"),
                           train("later", "G", 900, 1200, "P2S", "P3S")], feed="g")]
        result = prediction([template], feeds, mode="time_profile",
                            profiles=ProfileFake({("F", "arrival"): -180}))["routes"][0]
        transfer = result["selected_legs"][1]
        self.assertTrue(transfer["trip_id"].endswith(":later"))
        self.assertEqual(transfer["platform_ready_at"], NOW + 480)
        self.assertEqual(transfer["boarding_gate"]["conservative_platform_ready_at"], NOW + 660)
        self.assertEqual(result["total_duration_seconds"], 1260)
        self.assertEqual(sum(result["components"].values()), 1260)

    def test_late_arrival_correction_delays_both_transfer_timelines(self):
        template = route(legs=[leg(), leg("G", "P2S", "P3S")], transfers=[60])
        feeds = [snapshot([train(departure=240, arrival=600)]),
                 snapshot([train("too-tight", "G", 900, 1200, "P2S", "P3S"),
                           train("later", "G", 1080, 1400, "P2S", "P3S")], feed="g")]
        result = prediction([template], feeds, mode="time_profile",
                            profiles=ProfileFake({("F", "arrival"): 180}))["routes"][0]
        transfer = result["selected_legs"][1]
        self.assertTrue(transfer["trip_id"].endswith(":later"))
        self.assertEqual(transfer["platform_ready_at"], NOW + 840)
        self.assertEqual(transfer["boarding_gate"]["conservative_platform_ready_at"], NOW + 840)

    def test_positive_next_train_delay_cannot_rescue_a_missed_transfer(self):
        template = route(legs=[leg(), leg("G", "P2S", "P3S")], transfers=[60])
        feeds = [snapshot([train(departure=240, arrival=600)]),
                 snapshot([train("too-tight", "G", 700, 1400, "P2S", "P3S"),
                           train("later", "G", 1100, 1500, "P2S", "P3S")], feed="g")]
        result = prediction([template], feeds, mode="time_profile",
                            profiles=ProfileFake({("G", "departure"): 300}))["routes"][0]
        self.assertTrue(result["selected_legs"][1]["trip_id"].endswith(":later"))
        self.assertEqual(result["rejected"][0]["boarding_gate"]["slack_seconds"], 40)

    def test_margin_does_not_add_walking_waiting_or_riding_penalties(self):
        profiles = ProfileFake({("F", "departure"): 60, ("F", "arrival"): 120})
        results = [prediction(snapshots=[snapshot([train(departure=300)])],
                              mode="time_profile", profiles=profiles, margin=margin)["routes"][0]
                   for margin in (60, 120, 180)]
        for result in results:
            self.assertEqual(result["total_duration_seconds"], 780)
            self.assertEqual(result["components"],
                             {"walking_seconds": 120, "waiting_seconds": 300, "riding_seconds": 360})
        self.assertEqual([r["eta"] for r in results], [NOW + 780] * 3)

    def test_zero_walk_transfer_is_allowed_without_an_invented_walk_penalty(self):
        template = route(legs=[leg(), leg("G", "P2S", "P3S")], transfers=[0])
        feeds = [snapshot([train(departure=240, arrival=600)]),
                 snapshot([train("connection", "G", 720, 1000, "P2S", "P3S")], feed="g")]
        result = prediction([template], feeds)["routes"][0]
        self.assertTrue(result["timing_eligible"])
        self.assertEqual(result["components"]["walking_seconds"], 120)
        self.assertEqual(result["total_duration_seconds"], 1060)
        self.assertEqual(sum(result["components"].values()), 1060)

    def test_nonmonotonic_corrected_endpoints_remain_unavailable(self):
        result = prediction(mode="time_profile",
                            profiles=ProfileFake({("F", "departure"): 500}))["routes"][0]
        self.assertFalse(result["timing_eligible"])
        self.assertEqual(result["rejected"][0]["reason"], "NONMONOTONIC_CORRECTED_ENDPOINTS")

    def test_missing_provider_transfer_timing_is_not_invented(self):
        template = route(legs=[leg(), leg("G", "P2S", "P3S")], transfers=[None])
        with self.assertRaises(ValueError):
            prediction([template])


class PreservedInputSafeguardsTests(unittest.TestCase):
    def test_future_capture_and_outcome_hints_do_not_change_asof_forecast(self):
        asof = snapshot([train("asof", departure=240, arrival=600)])
        future = snapshot([train("future", departure=240, arrival=400)], fetched=1, source=0)
        poisoned = deepcopy(asof)
        poisoned["trips"][0]["later_outcome"] = {"arrival_at": NOW + 99999}
        expected = prediction(snapshots=[asof])
        actual = prediction(snapshots=[poisoned, future])
        self.assertEqual(expected, actual)

    def test_stale_or_failed_feed_does_not_use_an_old_valid_train(self):
        old = snapshot([train(departure=240)], fetched=-200, source=-205)
        failure = snapshot([], status="MISSING")
        for feeds in ([old], [old, failure]):
            with self.subTest(feeds=len(feeds)):
                result = prediction(snapshots=feeds)["routes"][0]
                self.assertFalse(result["timing_eligible"])

    def test_duplicate_identity_is_not_repaired_by_cherry_picking(self):
        first = train(departure=240)
        second = deepcopy(first)
        second["stop_updates"][-1]["arrival_time"] += 300
        result = prediction(snapshots=[snapshot([first, second])])["routes"][0]
        self.assertFalse(result["timing_eligible"])
        self.assertEqual({r["reason"] for r in result["rejected"]}, {"AMBIGUOUS_TRIP_IDENTITY"})

    def test_no_service_notice_still_excludes_timed_train(self):
        alerts = snapshot(feed="subway-alerts")
        alerts["alerts"] = [{"id": "closure", "effect": "NO_SERVICE",
            "active_periods": [{"start": NOW - 60, "end": NOW + 3600}],
            "informed_entities": [{"route_id": "F"}]}]
        result = prediction(snapshots=[snapshot([train(departure=240)]), alerts])["routes"][0]
        self.assertFalse(result["timing_eligible"])
        self.assertEqual(result["rejected"][0]["reason"], "NO_SERVICE_ALERT_CONFLICT")

    def test_unverified_service_evidence_does_not_become_formal_advice(self):
        result = prediction(incidents=IncidentFake({"F": context(evidence="LAST_OBSERVED")}))["routes"][0]
        self.assertTrue(result["timing_eligible"])
        self.assertFalse(result["comparison_eligible"])

    def test_input_objects_are_not_mutated(self):
        templates = [route()]
        feeds = [snapshot([train(departure=240)])]
        before = deepcopy((templates, feeds))
        prediction(templates, feeds)
        self.assertEqual((templates, feeds), before)


if __name__ == "__main__":
    unittest.main()
