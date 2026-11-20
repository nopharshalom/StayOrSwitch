"""Keep repaired advice, route execution and exact-train evidence separate."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from algo.scripts import evaluate_november_repair as repair
from stayorswitch.severe import MODES


def case():
    return {"id": "one", "corridor_id": "corridor", "decision_at": 1000,
        "local_time": "2026-11-03T08:00:00-05:00", "reference_route_id": "stay",
        "incident_ids": ["notice"], "incident_origin": "NEW",
        "official_text_review": {"confirmed_impact": "DISRUPTION"}, "exposure": []}


def prediction():
    return {"routes": [{"id": key, "name": key, "timing_eligible": True,
        "comparison_eligible": True, "total_duration_seconds": duration,
        "selected_legs": [{"trip_id": key + "-forecast-train"}]} for key, duration in
        (("stay", 1800), ("switch", 1200))]}


def inferred(duration, train="actual-train"):
    return {"status": "INFERRED", "total_duration_seconds": duration,
        "selected_legs": [{"trip_id": train}]}


def decisions(_prediction, _reference, **_kwargs):
    value = {"action": "SWITCH", "recommended_itinerary_id": "switch"}
    return {"strict_decision": value, "conditional_timing_decision": deepcopy(value)}


POLICY = {"switch_margin_seconds": 300, "tie_margin_seconds": 180}


class RepairScoringTests(unittest.TestCase):
    def score(self, outcomes, fixed, original_case=None):
        predictions = {mode: prediction() for mode in MODES}
        with patch.object(repair, "decide", side_effect=decisions), patch.object(repair, "outcome_for",
                side_effect=lambda route, labels, cutoff: deepcopy(fixed[route["id"]])), patch(
                "stayorswitch.repair_metrics.boarding_diagnostic", return_value={"status": "UNVERIFIABLE"}, create=True):
            result = repair.score_policy(original_case or case(), predictions, outcomes, {}, POLICY)
        return result

    def test_later_route_completion_does_not_erase_missed_recommended_train(self):
        outcomes = {"stay": inferred(1800), "switch": inferred(1200)}
        fixed = {"stay": inferred(1800), "switch": {"status": "MISSED_SELECTED_TRAIN"}}
        result = self.score(outcomes, fixed)
        self.assertEqual(result["modes"]["incident_profile"]["scores"]["strict_decision"]["classification"], "MEANINGFUL_GAIN")
        self.assertEqual(result["fixed_train_diagnostics"]["incident_profile"]["switch"]["status"], "MISSED_SELECTED_TRAIN")
        self.assertEqual(result["modes"]["incident_profile"]["outcomes"]["switch"], outcomes["switch"])

    def test_execution_gap_is_not_filled_with_exact_train_time(self):
        outcomes = {"stay": inferred(1800), "switch": {"status": "UNAVAILABLE", "reason": "UNRESOLVED_EARLIER_BOARDING"}}
        result = self.score(outcomes, {"stay": inferred(1800), "switch": inferred(1000)})
        self.assertEqual(result["modes"]["incident_profile"]["scores"]["strict_decision"]["classification"], "UNKNOWN")
        self.assertIsNone(result["policy_comparison"]["gain_seconds"])

    def test_censored_route_is_not_assigned_horizon_as_duration(self):
        outcomes = {"stay": inferred(1800), "switch": {"status": "CENSORED", "reason": "HORIZON"}}
        result = self.score(outcomes, {"stay": inferred(1800), "switch": inferred(1000)})
        self.assertEqual(result["modes"]["mta"]["scores"]["strict_decision"]["classification"], "UNKNOWN")
        self.assertNotIn("total_duration_seconds", result["modes"]["mta"]["outcomes"]["switch"])

    def test_identical_selected_route_has_identical_outcome_for_all_modes(self):
        outcomes = {"stay": inferred(1800), "switch": inferred(1200)}
        result = self.score(outcomes, outcomes)
        self.assertEqual(result["paired_policies"]["incident_vs_mta"]["classification"], "PRACTICAL_TIE")
        self.assertEqual(result["paired_policies"]["incident_vs_mta"]["gain_seconds"], 0)

    def test_three_minute_boundary_remains_a_practical_tie(self):
        outcomes = {"stay": inferred(1380), "switch": inferred(1200)}
        result = self.score(outcomes, outcomes)
        self.assertEqual(result["modes"]["incident_profile"]["scores"]["strict_decision"]["classification"], "PRACTICAL_TIE")

    def test_future_executable_but_forecast_ineligible_path_is_not_a_missed_opportunity(self):
        predictions = {mode: prediction() for mode in MODES}
        for value in predictions.values():
            value["routes"].append({"id": "hidden", "name": "hidden", "timing_eligible": False,
                                    "comparison_eligible": False, "selected_legs": []})
        outcomes = {"stay": inferred(1800), "switch": inferred(2200), "hidden": inferred(100)}
        advice = {key: {"action": "STAY", "recommended_itinerary_id": "stay"}
                  for key in ("strict_decision", "conditional_timing_decision")}
        with patch.object(repair, "decide", return_value=advice), patch.object(repair, "outcome_for",
                side_effect=lambda route, labels, cutoff: outcomes[route["id"]]), patch(
                "stayorswitch.repair_metrics.boarding_diagnostic", return_value={"status": "UNVERIFIABLE"}, create=True):
            result = repair.score_policy(case(), predictions, outcomes, {}, POLICY)
        self.assertEqual(result["modes"]["incident_profile"]["scores"]["strict_decision"]["classification"], "ACCEPTABLE_STAY")
        self.assertIn("hidden", result["modes"]["incident_profile"]["outcomes"])

    def test_case_specific_inactive_planned_closure_is_preserved(self):
        original = case()
        original["official_text_review"].update(planned_through_service_unavailable=True,
            planned_closure_mentioned=True, planned_closure_inactive_case_ids=["one"])
        outcomes = {"stay": inferred(1800), "switch": inferred(1200)}
        result = self.score(outcomes, outcomes, original)
        self.assertEqual(result["planned_closure_timing"], "CONFIRMED_INACTIVE")
        self.assertFalse(result["official_text_review"]["planned_through_service_unavailable"])
        self.assertTrue(original["official_text_review"]["planned_through_service_unavailable"])

    def test_input_outcomes_are_not_mutated_and_compact_report_keeps_both_evidence_types(self):
        outcomes = {"stay": inferred(1800), "switch": inferred(1200)}
        original = deepcopy(outcomes)
        result = self.score(outcomes, outcomes)
        self.assertEqual(outcomes, original)
        compact = repair.compact_case(result, {"one"})
        self.assertTrue(compact["primary"])
        route = next(r for r in compact["modes"]["incident_profile"]["selected_routes"] if r["id"] == "switch")
        self.assertEqual(route["forecast_selected_train_ids"], ["switch-forecast-train"])
        self.assertEqual(route["route_execution_outcome"]["selected_legs"][0]["trip_id"], "actual-train")
        self.assertIn("fixed_train_outcome", route)


class RepairPolicyTests(unittest.TestCase):
    def test_policy_cannot_retrain_use_future_choices_or_change_main_parameters(self):
        policy = json.loads(repair.POLICY_PATH.read_text())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            for key, value in (("retrain", True), ("boarding_margin_seconds", 0),
                ("execution_horizon_seconds", 3600), ("tie_margin_seconds", 0),
                ("execution_selects_on_final_destination_arrival", True),
                ("same_executor_for_old_and_new_policies", False),
                ("boarding_margin_sensitivity_seconds", [30, 60]),
                ("max_feed_gap_seconds", 600)):
                with self.subTest(key=key):
                    altered = dict(policy, **{key: value})
                    path.write_text(json.dumps(altered))
                    with patch.object(repair, "POLICY_PATH", path), self.assertRaises(ValueError):
                        repair.read_policy()

    def test_authorized_policy_loads_without_outcome_access(self):
        with patch.object(repair.base, "read_outcomes", side_effect=AssertionError("No outcomes allowed")):
            self.assertEqual(repair.read_policy()["boarding_margin_seconds"], 120)


if __name__ == "__main__":
    unittest.main()
