"""Evidence separation and fixed-reference regressions for supplemental replay."""

from copy import deepcopy
import unittest

from stayorswitch.affected_replay import (
    REFERENCE_POLICY, apply_text_review, re_reference, select_affected, selection_view,
    summarize_affected, unknown_switch_reasons,
)
from stayorswitch.october_evaluation import MODES


CONFIG = {"switch_margin_seconds": 300, "tie_margin_seconds": 180}
CUTOFF = 1793041582.0


def inferred(seconds):
    return {"status": "INFERRED", "total_duration_seconds": seconds}


def route(identifier, duration, *, severe=False, fresh=True, eligible=True, family=None):
    incident_ids = ["affected-incident"] if severe else []
    context = {"state": "SEVERE" if severe else "NORMAL", "applicable": severe,
               "evidence_status": "FRESH" if fresh else "LAST_OBSERVED",
               "severe_incident_ids": incident_ids, "incident_ids": incident_ids,
               "ambiguous_scope": False,
               "alerts": [{"incident_id": "affected-incident", "version_id": "v1",
                           "header": "R trains are running with severe delays.",
                           "captured_at": CUTOFF - 1}] if severe else []}
    return {"id": identifier, "name": identifier, "family": family or identifier,
            "timing_eligible": eligible, "comparison_eligible": eligible and fresh,
            "total_duration_seconds": duration, "eta": CUTOFF + duration if eligible else None,
            "context": deepcopy(context), "severe_incident_ids": incident_ids,
            "reason_codes": [] if eligible else ["NO_USABLE_CATCHABLE_TRAIN"],
            "rejected": [] if eligible else [{"reason": "EXPIRED_BASELINE_FORECAST"}],
            "selected_legs": [{"trip_id": identifier + "-train",
                               "incident_context": context}] if eligible else []}


def case():
    routes = [route("a", 1000), route("b", 2000, severe=True), route("c", 1300)]
    routes += [route("unavailable-" + str(i), None, eligible=False) for i in range(8)]
    outcomes = {"a": inferred(1100), "b": inferred(2300), "c": inferred(900)}
    outcomes.update({r["id"]: {"status": "UNAVAILABLE", "reason": "NO_COMPLETE_FORECAST_SELECTED_JOURNEY"}
                     for r in routes if not r["timing_eligible"]})
    modes = {}
    for mode in MODES:
        modes[mode] = {"mode": mode, "routes": deepcopy(routes), "outcomes": deepcopy(outcomes),
                       "strict_decision": {"action": "STAY", "recommended_itinerary_id": "a"},
                       "conditional_timing_decision": {"action": "STAY", "recommended_itinerary_id": "a"},
                       "scores": {}, "current_route_id": "a"}
    return {"id": "checkpoint", "split": "test", "date": "2026-10-26",
            "local_time": "2026-10-26T15:06:22-04:00", "decision_at": CUTOFF,
            "period": "AFTERNOON", "day_type": "WEEKDAY",
            "incident_ids": ["unrelated-checkpoint-trigger"], "reference_route_id": "a",
            "reference": deepcopy(routes[0]), "reference_outcome": inferred(1100), "modes": modes}


def select(source):
    return select_affected([selection_view({"kind": "BASELINE_REPLAY", "case": source})])


class SelectionEvidenceTests(unittest.TestCase):
    def test_selection_does_not_depend_on_outcomes_decisions_or_forecast_magnitudes(self):
        original = case()
        changed = deepcopy(original)
        changed["reference_outcome"] = {"status": "UNAVAILABLE"}
        for value in changed["modes"].values():
            value["outcomes"] = {"poison": "not outcome data"}
            value["strict_decision"] = {"action": "SWITCH", "estimated_savings_seconds": 100000}
            value["conditional_timing_decision"] = {"action": "UNDETERMINED"}
            value["scores"] = {"classification": "MEANINGFUL_LOSS"}
            for candidate in value["routes"]:
                candidate["total_duration_seconds"] = -9999
                candidate["eta"] = 9999999999
        self.assertEqual(select(original), select(changed))

    def test_selection_can_run_without_any_outcomes_or_prior_decisions(self):
        source = case()
        del source["reference_outcome"]
        del source["reference"]
        source["modes"] = {"mta": {"routes": source["modes"]["mta"]["routes"]}}
        selected = select(source)
        self.assertEqual([row["reference_route_id"] for row in selected["cases"]], ["b"])

    def test_sensitivity_and_margin_replays_are_not_primary_cases(self):
        for kind in ("WALKING_SENSITIVITY", "VALIDATION_DECISION_MARGIN"):
            self.assertIsNone(selection_view({"kind": kind, "case": case()}))

    def test_last_observed_exposure_remains_selected_but_strict_advice_abstains(self):
        source = case()
        for value in source["modes"].values():
            affected = value["routes"][1]
            affected["comparison_eligible"] = False
            affected["context"]["evidence_status"] = "LAST_OBSERVED"
            affected["selected_legs"][0]["incident_context"]["evidence_status"] = "LAST_OBSERVED"
        selected = select(source)["cases"]
        self.assertEqual(len(selected), 1)
        result = re_reference(source, selected[0], CONFIG)
        for value in result["modes"].values():
            self.assertEqual(value["strict_decision"]["action"], "UNDETERMINED")
            self.assertEqual(value["conditional_timing_decision"]["action"], "SWITCH")

    def test_not_applicable_severe_text_does_not_select_a_route(self):
        source = case()
        source["modes"]["mta"]["routes"][1]["selected_legs"][0]["incident_context"]["applicable"] = False
        self.assertEqual(select(source)["cases"], [])

    def test_unavailable_routes_are_kept_in_coverage_with_rejection_reasons(self):
        selected = select(case())
        self.assertEqual(selected["input_coverage"]["candidate_route_observations"], 11)
        self.assertEqual(len(selected["unavailable_candidates"]), 8)
        self.assertEqual(selected["unavailable_candidates"][0]["rejection_reasons"], ["EXPIRED_BASELINE_FORECAST"])

    def test_example_selection_is_chronological_by_incident_and_family(self):
        first = case()
        first["modes"]["mta"]["routes"].append(route("bb", 2100, severe=True, family="b"))
        later = deepcopy(first)
        later["id"] = "later"
        later["decision_at"] += 300
        selected = select_affected([selection_view({"kind": "BASELINE_REPLAY", "case": c})
                                    for c in (later, first)])
        self.assertEqual(len(selected["cases"]), 4)
        self.assertEqual(selected["example_ids"], ["checkpoint--stay-b"])


class FixedAffectedReferenceTests(unittest.TestCase):
    def test_only_reference_changes_forecasts_trains_and_outcomes_are_preserved(self):
        source = case()
        before = deepcopy(source)
        result = re_reference(source, select(source)["cases"][0], CONFIG)
        self.assertEqual(source, before)
        self.assertEqual(result["reference_route_id"], "b")
        self.assertEqual(result["original_reference_route_id"], "a")
        for mode in MODES:
            self.assertEqual(result["modes"][mode]["routes"], source["modes"][mode]["routes"])
            self.assertEqual(result["modes"][mode]["outcomes"], source["modes"][mode]["outcomes"])
            self.assertEqual(len(result["modes"][mode]["routes"]), 11)
            self.assertFalse(result["modes"][mode]["strict_decision"]["comparison_complete"])

    def test_switch_gain_uses_affected_stay_and_strategy_gain_uses_original_mta(self):
        source = case()
        corrected = source["modes"]["incident_profile"]
        corrected["routes"][0]["total_duration_seconds"] = 1600
        corrected["routes"][2]["total_duration_seconds"] = 1000
        corrected["outcomes"]["b"] = inferred(2600)
        result = re_reference(source, select(source)["cases"][0], CONFIG)
        mta = result["modes"]["mta"]
        adjusted = result["modes"]["incident_profile"]
        self.assertEqual(mta["strict_decision"]["recommended_itinerary_id"], "a")
        self.assertEqual(mta["scores"]["strict_decision"]["inferred_switch_savings_seconds"], 1200)
        self.assertEqual(mta["scores"]["strict_decision"]["inferred_strategy_gain_vs_original_mta_seconds"], 0)
        self.assertEqual(adjusted["strict_decision"]["recommended_itinerary_id"], "c")
        self.assertEqual(adjusted["scores"]["strict_decision"]["inferred_switch_savings_seconds"], 1700)
        self.assertEqual(adjusted["scores"]["strict_decision"]["inferred_strategy_gain_vs_original_mta_seconds"], 200)

    def test_summary_groups_actual_affected_incident_and_replaces_reference_policy(self):
        source = case()
        result = re_reference(source, select(source)["cases"][0], CONFIG)
        self.assertEqual(result["incident_ids"], ["affected-incident"])
        self.assertEqual(result["checkpoint_incident_ids"], ["unrelated-checkpoint-trigger"])
        summary = summarize_affected([result])
        self.assertEqual(list(summary["by_incident"]), ["affected-incident"])
        self.assertEqual(summary["unique_primary_checkpoints"], 1)
        for item in (summary, summary["by_split"]["test"], summary["by_incident"]["affected-incident"]):
            self.assertTrue(item["reference_service_context"]["policy"].startswith(REFERENCE_POLICY))

    def test_missing_stay_and_missed_switch_are_unknown_not_success_or_tie(self):
        source = case()
        for value in source["modes"].values():
            value["outcomes"]["b"] = {"status": "UNAVAILABLE", "reason": "MISSING_OR_UNUSABLE_ENDPOINT_LABEL",
                                       "endpoint_flags": {"boarding": ["CSV_SCHEDULE_CHANGED"]}}
            value["outcomes"]["a"] = {"status": "MISSED_SELECTED_TRAIN",
                                       "reason": "INFERRED_DEPARTURE_BEFORE_PLATFORM_READY"}
        result = re_reference(source, select(source)["cases"][0], CONFIG)
        reasons = unknown_switch_reasons([result])
        for mode in MODES:
            self.assertEqual(result["modes"][mode]["scores"]["strict_decision"]["classification"], "UNKNOWN")
            entry = reasons[mode]["strict_decision"]
            self.assertEqual(entry["unknown_switch_count"], 1)
            self.assertEqual(entry["side_reason_counts"], {
                "stay:MISSING_OR_UNUSABLE_ENDPOINT_LABEL": 1,
                "switch:INFERRED_DEPARTURE_BEFORE_PLATFORM_READY": 1})
            self.assertEqual(entry["endpoint_flag_counts"], {"stay:boarding:CSV_SCHEDULE_CHANGED": 1})

    def test_changed_exposure_fails_closed(self):
        source = case()
        selected = select(source)["cases"][0]
        selected["reference_service_context"]["evidence_status"] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "exposure"):
            re_reference(source, selected, CONFIG)

    def test_five_minute_threshold_and_three_minute_tie_are_unchanged(self):
        source = case()
        for value in source["modes"].values():
            value["routes"][1]["total_duration_seconds"] = 1300
            value["outcomes"]["b"] = inferred(1280)
        result = re_reference(source, select(source)["cases"][0], CONFIG)
        for value in result["modes"].values():
            self.assertEqual(value["strict_decision"]["action"], "SWITCH")
            self.assertEqual(value["strict_decision"]["estimated_savings_seconds"], 300)
            self.assertEqual(value["scores"]["strict_decision"]["classification"], "PRACTICAL_TIE")


class OfficialTextReviewTests(unittest.TestCase):
    def review(self, row, status="CONFIRMED"):
        return {"split": row["split"], "source_case_id": row["checkpoint_id"],
                "reference_route_id": row["reference_route_id"], "decision_at": row["decision_at"],
                "classifier_incident_ids": deepcopy(row["incident_ids"]), "status": status,
                "confirmed_incident_ids": deepcopy(row["incident_ids"]) if status == "CONFIRMED" else []}

    def test_only_confirmed_pairs_remain_without_erasing_classifier_inventory(self):
        source = case()
        source["modes"]["mta"]["routes"].append(route("d", 2300, severe=True))
        selected = select(source)
        reviews = [self.review(row, "CONFIRMED" if row["reference_route_id"] == "b" else "DIRECTION_MISMATCH")
                   for row in selected["cases"]]
        before = deepcopy(selected)
        result = apply_text_review(selected, reviews, "test")
        self.assertEqual(selected, before)
        self.assertEqual(len(result["classifier_candidates"]), 2)
        self.assertEqual([row["reference_route_id"] for row in result["cases"]], ["b"])
        self.assertEqual([row["reference_route_id"] for row in result["excluded_classifier_candidates"]], ["d"])
        self.assertEqual(result["example_ids"], ["checkpoint--stay-b"])

    def test_missing_extra_or_wrong_split_reviews_fail_closed(self):
        selected = select(case())
        valid = self.review(selected["cases"][0])
        extra = dict(valid, reference_route_id="extra")
        wrong_split = dict(valid, split="validation")
        for reviews in ([], [valid, extra], [wrong_split]):
            with self.subTest(reviews=reviews), self.assertRaisesRegex(ValueError, "exactly"):
                apply_text_review(selected, reviews, "test")

    def test_review_cannot_change_cutoff_or_invent_an_affected_incident(self):
        selected = select(case())
        valid = self.review(selected["cases"][0])
        for changed in (dict(valid, decision_at=valid["decision_at"] + 1),
                        dict(valid, classifier_incident_ids=["future-incident"]),
                        dict(valid, confirmed_incident_ids=[]),
                        dict(valid, confirmed_incident_ids=["future-incident"])):
            with self.subTest(review=changed), self.assertRaises(ValueError):
                apply_text_review(selected, [changed], "test")

    def test_duplicate_reviews_do_not_silently_override_each_other(self):
        selected = select(case())
        valid = self.review(selected["cases"][0])
        with self.assertRaisesRegex(ValueError, "[Dd]uplicate"):
            apply_text_review(selected, [valid, deepcopy(valid)], "test")

    def test_confirmed_summary_ids_narrow_without_modifying_prediction_contexts(self):
        source = case()
        for value in source["modes"].values():
            affected = value["routes"][1]
            affected["severe_incident_ids"].append("false-positive-incident")
            affected["context"]["severe_incident_ids"].append("false-positive-incident")
        selected = select(source)
        review = self.review(selected["cases"][0])
        review["confirmed_incident_ids"] = ["affected-incident"]
        narrowed = apply_text_review(selected, [review], "test")
        result = re_reference(source, narrowed["cases"][0], CONFIG)
        self.assertEqual(result["reference_service_context"]["severe_incident_ids"], ["affected-incident"])
        self.assertEqual(result["classifier_reference_service_context"]["severe_incident_ids"],
                         ["affected-incident", "false-positive-incident"])
        for mode in MODES:
            self.assertEqual(result["modes"][mode]["routes"], source["modes"][mode]["routes"])
        self.assertEqual(summarize_affected([result])["reference_service_context"]["distinct_definite_severe_incidents"], 1)


if __name__ == "__main__":
    unittest.main()
