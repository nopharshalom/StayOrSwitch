"""Pre-problem reference selection and exact-train replay regressions."""

from copy import deepcopy
from datetime import datetime
import unittest
from unittest.mock import patch

from stayorswitch.preincident_replay import (
    POLICY, choose_anchor, plan_incidents, score_modes, select_delayed,
)
from stayorswitch.severe import MODES


BASE = datetime.fromisoformat("2026-10-30T10:00:00-04:00").timestamp()
IDS = [route["id"] for route in POLICY["routes"]]


def route(identifier, duration, *, at=BASE, state="NORMAL", fresh=True,
          timing=True, comparison=True, incident=None, outcome=None):
    return {
        "id": identifier, "family": identifier, "name": identifier,
        "eta": at + duration, "total_duration_seconds": duration,
        "timing_eligible": timing, "comparison_eligible": comparison,
        "components": {"walking_seconds": 240, "waiting_seconds": 120,
                       "riding_seconds": duration - 360},
        "context": {"state": state, "evidence_status": "FRESH" if fresh else "LAST_OBSERVED",
                    "incident_ids": [incident] if incident else []},
        "severe_incident_ids": [incident] if incident and state == "SEVERE" else [],
        "selected_legs": [{"trip_id": identifier + "-chosen-train"}],
        "fixture_outcome": {"status": "INFERRED", "total_duration_seconds":
                            duration if outcome is None else outcome},
    }


def prediction(durations=(1000, 1400, 1600), *, at=BASE, affected=False):
    routes = [route(identifier, duration, at=at) for identifier, duration in zip(IDS, durations)]
    if affected:
        routes[0]["context"].update(state="DISRUPTION", incident_ids=["problem"])
    return {"cutoff": at, "routes": routes}


def plan():
    return {"incident_id": "problem", "anchor_boundary": BASE,
            "first_problem_receipt": BASE + 60,
            "anchor_times": [BASE - 60, BASE - 300],
            "decision_times": [BASE + 60, BASE + 360]}


def anchor():
    return choose_anchor(plan(), {BASE - 60: prediction(at=BASE - 60)})


def family(identifier="problem", *, first=BASE, state="DISRUPTION", line="7"):
    return {"incident_id": identifier, "first_observed_at": first, "route_ids": [line],
            "versions": [{"first_observed_at": first, "state": state,
                          "alert": {"active_periods": [{"start": first - 120}]}}]}


class IncidentTimingTests(unittest.TestCase):
    def test_anchor_precedes_initial_declared_problem_not_later_severe_escalation(self):
        incident = family()
        incident["versions"].append({"first_observed_at": BASE + 3600, "state": "SEVERE",
                                     "alert": {"active_periods": [{"start": BASE}]}})
        row = plan_incidents({"incidents": [incident]})[0]
        self.assertEqual(row["first_problem_receipt"], BASE)
        self.assertEqual(row["anchor_boundary"], BASE - 120)
        self.assertTrue(all(t < BASE - 120 for t in row["anchor_times"]))
        self.assertIn(BASE + 3600, row["decision_times"])

    def test_earlier_unknown_family_receipt_is_not_backdated_to_first_severe(self):
        incident = family(state="UNKNOWN")
        incident["versions"].append({"first_observed_at": BASE + 1800, "state": "SEVERE",
                                     "alert": {"active_periods": [{"start": BASE + 1700}]}})
        row = plan_incidents({"incidents": [incident]})[0]
        self.assertEqual(row["first_problem_receipt"], BASE + 1800)
        self.assertEqual(row["anchor_boundary"], BASE - 120)

    def test_non_test_families_unrelated_routes_and_planned_only_notices_are_excluded(self):
        earlier = datetime.fromisoformat("2026-10-24T23:59:00-04:00").timestamp()
        inventory = {"incidents": [family("old", first=earlier), family("other", line="R"),
                                    family("planned", state="PLANNED"), family("eligible")]}
        self.assertEqual([row["incident_id"] for row in plan_incidents(inventory)], ["eligible"])

    def test_test_week_end_limits_future_decision_grid(self):
        late = datetime.fromisoformat("2026-10-31T23:45:00-04:00").timestamp()
        row = plan_incidents({"incidents": [family(first=late)]})[0]
        midnight = datetime.fromisoformat("2026-11-01T00:00:00-04:00").timestamp()
        self.assertTrue(all(t < midnight for t in row["decision_times"]))
        self.assertEqual(max(row["decision_times"]), late + 600)


class PreProblemAnchorTests(unittest.TestCase):
    def test_latest_eligible_anchor_defines_fastest_without_later_route_rankings(self):
        newest = prediction((1700, 1200, 1500), at=BASE - 60)
        older = prediction((1000, 1400, 1500), at=BASE - 300)
        chosen = choose_anchor(plan(), {BASE - 60: newest, BASE - 300: older})
        self.assertEqual(chosen["decision_at"], BASE - 60)
        self.assertEqual(chosen["reference_route_id"], IDS[1])
        self.assertEqual(chosen["winner_lead_seconds"], 300)

    def test_anchor_at_onset_is_rejected_even_if_fast_and_normal(self):
        event = plan()
        event["anchor_times"] = [BASE, BASE - 300]
        chosen = choose_anchor(event, {BASE: prediction(), BASE - 300: prediction(at=BASE - 300)})
        self.assertEqual(chosen["decision_at"], BASE - 300)
        self.assertEqual(chosen["attempts"][0]["reason"], "ANCHOR_NOT_BEFORE_FIRST_PROBLEM_BOUNDARY")

    def test_cannot_claim_fastest_when_a_supplied_alternative_is_missing_or_unverified(self):
        for defect in ("missing", "timing_eligible", "comparison_eligible"):
            source = prediction(at=BASE - 60)
            if defect == "missing":
                source["routes"].pop()
            else:
                source["routes"][-1][defect] = False
            with self.subTest(defect=defect):
                self.assertEqual(choose_anchor(plan(), {BASE - 60: source})["status"], "UNAVAILABLE")

    def test_fastest_route_needs_fresh_normal_evidence(self):
        for state, evidence in (("DISRUPTION", "FRESH"), ("NORMAL", "LAST_OBSERVED"),
                                ("UNKNOWN", "FRESH")):
            source = prediction(at=BASE - 60)
            source["routes"][0]["context"].update(state=state, evidence_status=evidence)
            with self.subTest(state=state, evidence=evidence):
                rejected = choose_anchor(plan(), {BASE - 60: source})
                self.assertEqual(rejected["status"], "UNAVAILABLE")
                self.assertEqual(rejected["attempts"][0]["reason"], "FASTEST_ROUTE_NOT_FRESH_NORMAL")

    def test_near_tie_is_disclosed_without_changing_fastest_reference(self):
        chosen = choose_anchor(plan(), {BASE - 60: prediction((1000, 1180, 1600), at=BASE - 60)})
        self.assertEqual(chosen["reference_route_id"], IDS[0])
        self.assertTrue(chosen["baseline_near_tie"])
        self.assertEqual(chosen["winner_lead_seconds"], 180)


class DelayedCaseSelectionTests(unittest.TestCase):
    def test_original_fastest_stay_is_frozen_when_another_route_becomes_fastest(self):
        before = anchor()
        after = prediction((1700, 1100, 1300), at=BASE + 360, affected=True)
        selected, reason = select_delayed(plan(), before, after, BASE + 360)
        self.assertIsNone(reason)
        self.assertEqual(selected["reference_route_id"], IDS[0])
        self.assertEqual(selected["duration_deterioration_seconds"], 700)
        self.assertEqual(selected["component_deterioration_seconds"]["riding_seconds"], 700)
        self.assertEqual(selected["asof_mta_prediction"], after)

    def test_clock_advance_alone_does_not_count_as_delay(self):
        after = prediction((1000, 1400, 1600), at=BASE + 3600, affected=True)
        selected, reason = select_delayed(plan(), anchor(), after, BASE + 3600)
        self.assertIsNone(selected)
        self.assertEqual(reason, "REMAINING_DURATION_DID_NOT_INCREASE_FIVE_MINUTES")

    def test_exact_five_minute_deterioration_is_included_without_requiring_a_switch(self):
        # The old route is still fastest, so this is not a winner-only sample.
        after = prediction((1300, 1500, 1700), at=BASE + 360, affected=True)
        selected, reason = select_delayed(plan(), anchor(), after, BASE + 360)
        self.assertIsNone(reason)
        self.assertEqual(selected["duration_deterioration_seconds"], 300)
        after["routes"][0]["total_duration_seconds"] -= 1
        self.assertIsNone(select_delayed(plan(), anchor(), after, BASE + 360)[0])

    def test_post_problem_notice_must_match_frozen_stay_and_this_incident(self):
        after = prediction((1700, 1100, 1300), at=BASE + 360, affected=True)
        for state, incident_ids in (("NORMAL", ["problem"]), ("DISRUPTION", ["unrelated"])):
            changed = deepcopy(after)
            changed["routes"][0]["context"].update(state=state, incident_ids=incident_ids)
            with self.subTest(state=state, incident_ids=incident_ids):
                self.assertEqual(select_delayed(plan(), anchor(), changed, BASE + 360)[1],
                                 "NO_APPLICABLE_CURRENT_PROBLEM_NOTICE")

    def test_decision_cannot_precede_problem_or_exceed_declared_window(self):
        for at in (BASE + 59, BASE + 60 + POLICY["decision_window_seconds"] + 1):
            with self.subTest(at=at):
                after = prediction((1700, 1100, 1300), at=at, affected=True)
                self.assertEqual(select_delayed(plan(), anchor(), after, at)[1],
                                 "OUTSIDE_PREDECLARED_DECISION_WINDOW")

    def test_unusable_stay_timing_is_not_silently_replaced_with_new_fastest(self):
        after = prediction((1700, 1100, 1300), at=BASE + 360, affected=True)
        after["routes"][0]["timing_eligible"] = False
        self.assertEqual(select_delayed(plan(), anchor(), after, BASE + 360)[1],
                         "FROZEN_STAY_HAS_NO_COMPLETE_TIMING")

    def test_labels_and_recommendations_do_not_change_selection(self):
        original = prediction((1700, 1100, 1300), at=BASE + 360, affected=True)
        changed = deepcopy(original)
        changed["outcomes"] = {"irrelevant": "future labels"}
        changed["strict_decision"] = {"action": "STAY"}
        for candidate in changed["routes"]:
            candidate["fixture_outcome"] = {"status": "MISSED_SELECTED_TRAIN"}
        first, reason1 = select_delayed(plan(), anchor(), original, BASE + 360)
        second, reason2 = select_delayed(plan(), anchor(), changed, BASE + 360)
        self.assertEqual(reason1, reason2)
        for key in ("id", "reference_route_id", "duration_deterioration_seconds",
                    "component_deterioration_seconds", "selection_uses_outcomes"):
            self.assertEqual(first[key], second[key])


class ExactTrainScoringTests(unittest.TestCase):
    def score(self, case, predictions):
        def observed(candidate, labels, cutoff):
            self.assertEqual(cutoff, case["decision_at"])
            self.assertEqual(labels, {"separate": "labels"})
            return deepcopy(candidate["fixture_outcome"])
        with patch("stayorswitch.preincident_replay.outcome_for", side_effect=observed):
            return score_modes(case, predictions, {"separate": "labels"})

    def fixture(self):
        after = prediction((1700, 1100, 1300), at=BASE + 360, affected=True)
        selected, _ = select_delayed(plan(), anchor(), after, BASE + 360)
        return selected, {mode: deepcopy(after) for mode in MODES}

    def test_stay_remains_original_route_and_same_cutoff_mta_is_separate_baseline(self):
        selected, predictions = self.fixture()
        predictions["mta"]["routes"][1]["fixture_outcome"]["total_duration_seconds"] = 1400
        adjusted = predictions["incident_profile"]
        adjusted["routes"][2]["total_duration_seconds"] = 900
        adjusted["routes"][0]["fixture_outcome"]["total_duration_seconds"] = 2000
        adjusted["routes"][2]["fixture_outcome"]["total_duration_seconds"] = 1200
        original = deepcopy(predictions)
        result = self.score(selected, predictions)
        self.assertEqual(predictions, original)
        self.assertEqual(result["reference_route_id"], IDS[0])
        self.assertEqual(result["same_cutoff_fastest_mta_route_id"], IDS[1])
        scored = result["modes"]["incident_profile"]
        self.assertEqual(scored["current_route_id"], IDS[0])
        self.assertEqual(scored["strict_decision"]["recommended_itinerary_id"], IDS[2])
        self.assertEqual(scored["scores"]["strict_decision"]["inferred_switch_savings_seconds"], 800)
        self.assertEqual(scored["scores"]["strict_decision"]["inferred_strategy_gain_vs_original_mta_seconds"], 200)
        for mode in MODES:
            self.assertEqual(result["modes"][mode]["routes"], original[mode]["routes"])

    def test_ordinary_delay_can_trigger_switch_without_being_relabelled_severe(self):
        selected, predictions = self.fixture()
        result = self.score(selected, predictions)
        for value in result["modes"].values():
            self.assertEqual(value["routes"][0]["context"]["state"], "DISRUPTION")
            self.assertEqual(value["strict_decision"]["action"], "SWITCH")

    def test_stale_notice_withholds_strict_advice_but_preserves_timing_diagnostic(self):
        selected, predictions = self.fixture()
        for value in predictions.values():
            value["routes"][0]["comparison_eligible"] = False
            value["routes"][0]["context"]["evidence_status"] = "LAST_OBSERVED"
        result = self.score(selected, predictions)
        for value in result["modes"].values():
            self.assertEqual(value["strict_decision"]["action"], "UNDETERMINED")
            self.assertEqual(value["conditional_timing_decision"]["action"], "SWITCH")

    def test_missed_selected_train_remains_unknown_without_substitution(self):
        selected, predictions = self.fixture()
        for value in predictions.values():
            value["routes"][1]["fixture_outcome"] = {
                "status": "MISSED_SELECTED_TRAIN", "reason": "INFERRED_DEPARTURE_BEFORE_PLATFORM_READY"}
        result = self.score(selected, predictions)
        for value in result["modes"].values():
            self.assertEqual(value["strict_decision"]["recommended_itinerary_id"], IDS[1])
            self.assertEqual(value["scores"]["strict_decision"]["classification"], "UNKNOWN")
            self.assertIsNone(value["scores"]["strict_decision"]["inferred_switch_savings_seconds"])

    def test_counterfactual_uses_forecast_best_alternative_even_when_hindsight_prefers_another(self):
        selected, predictions = self.fixture()
        for value in predictions.values():
            value["routes"][1]["fixture_outcome"]["total_duration_seconds"] = 1500
            value["routes"][2]["fixture_outcome"]["total_duration_seconds"] = 800
        result = self.score(selected, predictions)
        for value in result["modes"].values():
            comparison = value["alternative_counterfactual"]
            self.assertFalse(comparison["selection_uses_outcomes"])
            self.assertEqual(comparison["predicted_alternative_route_id"], IDS[1])
            self.assertEqual(comparison["predicted_savings_seconds"], 600)
            self.assertEqual(comparison["inferred_savings_seconds"], 200)
            self.assertEqual(comparison["hindsight_best_known_alternative_route_id"], IDS[2])
            self.assertEqual(comparison["hindsight_best_known_savings_seconds"], 900)
            self.assertTrue(comparison["hindsight_values_are_not_recommendations"])
            self.assertEqual(value["strict_decision"]["recommended_itinerary_id"], IDS[1])

    def test_stay_decision_still_compares_an_actual_alternative_instead_of_stay_with_itself(self):
        after = prediction((1300, 1500, 1700), at=BASE + 360, affected=True)
        selected, _ = select_delayed(plan(), anchor(), after, BASE + 360)
        predictions = {mode: deepcopy(after) for mode in MODES}
        for value in predictions.values():
            value["routes"][0]["fixture_outcome"]["total_duration_seconds"] = 1400
        result = self.score(selected, predictions)
        for value in result["modes"].values():
            self.assertEqual(value["strict_decision"]["action"], "STAY")
            self.assertEqual(value["strict_decision"]["recommended_itinerary_id"], IDS[0])
            comparison = value["alternative_counterfactual"]
            self.assertEqual(comparison["predicted_alternative_route_id"], IDS[1])
            self.assertNotEqual(comparison["predicted_alternative_route_id"], selected["reference_route_id"])
            self.assertEqual(comparison["predicted_savings_seconds"], -200)
            self.assertTrue(comparison["outcomes_comparable"])
            self.assertEqual(comparison["inferred_savings_seconds"], -100)

    def test_unknown_forecast_best_alternative_is_not_replaced_with_known_hindsight_winner(self):
        selected, predictions = self.fixture()
        unavailable = {"status": "UNAVAILABLE", "reason": "MISSING_OR_UNUSABLE_ENDPOINT_LABEL"}
        for value in predictions.values():
            value["routes"][1]["fixture_outcome"] = deepcopy(unavailable)
            value["routes"][2]["fixture_outcome"]["total_duration_seconds"] = 800
        result = self.score(selected, predictions)
        for value in result["modes"].values():
            comparison = value["alternative_counterfactual"]
            self.assertEqual(comparison["predicted_alternative_route_id"], IDS[1])
            self.assertEqual(comparison["alternative_outcome"], unavailable)
            self.assertFalse(comparison["outcomes_comparable"])
            self.assertIsNone(comparison["inferred_savings_seconds"])
            self.assertEqual(comparison["hindsight_best_known_alternative_route_id"], IDS[2])
            self.assertEqual(comparison["hindsight_best_known_savings_seconds"], 900)
            self.assertEqual(value["strict_decision"]["recommended_itinerary_id"], IDS[1])
            self.assertEqual(value["scores"]["strict_decision"]["classification"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
