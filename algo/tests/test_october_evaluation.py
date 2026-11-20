"""Synthetic checks for October replay evidence, arithmetic, and denominators."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stayorswitch.october_evaluation import (
    MODES, _decision_scores, decision_margin_case, evaluate_case, latest_at_cutoffs, outcome_for,
    project_snapshot, reference_service_context, select_incident_checkpoints, sensitivity_selection,
    summarize, summary_case, walking_variations,
)
from data.delay_profiles.incidents import IncidentIndex
from data.delay_profiles.common import digest
from stayorswitch.severe import decide as actual_decide, predict_routes


CUTOFF = datetime(2026, 10, 19, 16, tzinfo=timezone.utc).timestamp()
CONFIG = {
    "timezone": "America/New_York",
    "periods": [{"id": "DAY", "start_hour": 0, "end_hour": 24}],
    "splits": {"train": ["2026-10-01", "2026-10-17"],
               "validation": ["2026-10-18", "2026-10-24"],
               "test": ["2026-10-25", "2026-10-31"]},
    "train_max_age_seconds": 180,
    "alerts_max_age_seconds": 300,
    "switch_margin_seconds": 300,
    "tie_margin_seconds": 180,
}


def endpoint(arrival, departure):
    return {"arrival_at": CUTOFF + arrival, "departure_at": CUTOFF + departure,
            "arrival_usable": True, "departure_usable": True,
            "quality_flags": [], "arrival_quality_flags": [],
            "departure_quality_flags": []}


def labels_for(train, arrival, departure=100, start="A", end="B"):
    return {train: {start: endpoint(departure, departure),
                    end: endpoint(arrival, arrival)}}


def route(identifier="stay", train="train-a", duration=1000, *, family="DIRECT"):
    return {"id": identifier, "family": family, "name": identifier,
            "status": "ESTIMATED", "timing_eligible": True,
            "comparison_eligible": True, "eta": CUTOFF + duration,
            "total_duration_seconds": duration,
            "selected_legs": [{"trip_id": train, "route_id": "F", "feed_id": "bdfm",
                               "from_stop_id": "A", "to_stop_id": "B",
                               "departure_at": CUTOFF + 100,
                               "arrival_at": CUTOFF + duration}],
            "access_walk_seconds": 0, "transfer_walk_seconds": [],
            "egress_walk_seconds": 0}


def snapshot(feed, offset, payload="a", status="OK"):
    return {"feed_id": feed, "captured_at": CUTOFF + offset, "sha256": payload,
            "status": status, "trips": [{"id": payload}], "alerts": []}


def incident_alert(header="F trains have severe delays.", identifier="lmm:alert:1:30",
                   route_id="F", **extra):
    return {"id": identifier, "header": header, "description": None,
            "active_periods": [{"start": CUTOFF - 3600}],
            "informed_entities": [{"route_id": route_id}],
            "cause": None, "effect": None, "extensions": {}, **extra}


def alert_snapshot(offset, alerts=(), **extra):
    at = CUTOFF + offset
    return {"feed_id": "subway-alerts", "kind": "alerts", "captured_at": at,
            "fetched_at": at, "source_updated_at": at - 1, "requested_at": at,
            "status": "AVAILABLE", "alerts": list(alerts), **extra}


def checkpoint_config():
    return {**deepcopy(CONFIG), "start_date": "2026-10-01", "end_date": "2026-10-31",
            "incident_checkpoint_seconds": 300, "route_ids": ["F", "FX", "G"],
            "routes": [{"id": "f_direct", "legs": [{"route_id": "F", "route_ids": ["F", "FX"]}]},
                       {"id": "g_direct", "legs": [{"route_id": "G", "route_ids": ["G"]}]}]}


def decision(action, recommended):
    return {"action": action, "recommended_itinerary_id": recommended}


def inferred(duration):
    return {"status": "INFERRED", "total_duration_seconds": duration}


def scored_value(outcomes, *, action="STAY", chosen="stay", strict=None):
    return {"routes": [{"id": identifier, "timing_eligible": True}
                       for identifier in outcomes],
            "outcomes": outcomes, "strict_decision": strict or decision(action, chosen),
            "conditional_timing_decision": decision(action, chosen)}


def fake_decide(prediction, current_route_id, *, switch_margin_seconds, require_severe):
    assert require_severe is True
    candidates = [item for item in prediction["routes"] if item["timing_eligible"]]
    current = next((item for item in candidates if item["id"] == current_route_id), None)
    if current is None or len(candidates) < 2:
        value = decision("UNDETERMINED", None)
    else:
        best = min(candidates, key=lambda item: (item["total_duration_seconds"], item["id"]))
        if (best["id"] != current_route_id and
                current["total_duration_seconds"] - best["total_duration_seconds"] >= switch_margin_seconds):
            value = decision("SWITCH", best["id"])
        else:
            value = decision("STAY", current_route_id)
    strict = value if prediction.get("strict_available", True) else decision("UNDETERMINED", None)
    return {"strict_decision": deepcopy(strict), "conditional_timing_decision": deepcopy(value)}


def fake_predictor(by_mode, calls=None, *, stale_mode=None):
    def predict(snapshots, templates, cutoff, *, mode, estimator, incident_index,
                train_max_age_seconds, alerts_max_age_seconds):
        if calls is not None:
            calls.append({"mode": mode, "cutoff": cutoff, "snapshots": deepcopy(snapshots)})
        return {"mode": mode, "routes": deepcopy(by_mode[mode]),
                "strict_available": mode != stale_mode}
    return predict


class SelectedJourneyOutcomeTests(unittest.TestCase):
    def test_exact_platform_ready_departure_is_catchable(self):
        candidate = route()
        candidate["access_walk_seconds"] = 100
        result = outcome_for(candidate, labels_for("train-a", 1000), CUTOFF)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["components"]["waiting_seconds"], 0)

    def test_missed_first_train_is_unknown_without_replacement(self):
        candidate = route()
        candidate["access_walk_seconds"] = 101
        labels = labels_for("train-a", 1000)
        labels.update(labels_for("later-train", 1200, departure=200))
        result = outcome_for(candidate, labels, CUTOFF)
        self.assertEqual(result["status"], "MISSED_SELECTED_TRAIN")
        self.assertEqual(result["trip_id"], "train-a")
        self.assertEqual(result["completed_legs"], [])

    def two_leg_route(self):
        candidate = route()
        candidate.update(access_walk_seconds=60, transfer_walk_seconds=[120], egress_walk_seconds=60)
        candidate["selected_legs"].append({"trip_id": "train-b", "from_stop_id": "C", "to_stop_id": "D"})
        return candidate

    def test_transfer_readiness_and_component_totals_use_inferred_arrival(self):
        labels = labels_for("train-a", 300)
        labels.update(labels_for("train-b", 800, departure=480, start="C", end="D"))
        result = outcome_for(self.two_leg_route(), labels, CUTOFF)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][1]["platform_ready_at"], CUTOFF + 420)
        self.assertEqual(result["components"], {"walking_seconds": 240, "waiting_seconds": 100,
                                                "riding_seconds": 520})
        self.assertEqual(result["total_duration_seconds"], 860)
        self.assertEqual(sum(result["components"].values()), result["total_duration_seconds"])

    def test_missed_transfer_never_uses_another_train(self):
        labels = labels_for("train-a", 300)
        labels.update(labels_for("train-b", 800, departure=419, start="C", end="D"))
        labels.update(labels_for("later-train", 900, departure=600, start="C", end="D"))
        result = outcome_for(self.two_leg_route(), labels, CUTOFF)
        self.assertEqual(result["status"], "MISSED_SELECTED_TRAIN")
        self.assertEqual(result["trip_id"], "train-b")
        self.assertEqual(result["leg_index"], 1)
        self.assertEqual(len(result["completed_legs"]), 1)

    def test_field_specific_validity_does_not_require_unused_endpoint(self):
        labels = labels_for("train-a", 1000)
        labels["train-a"]["A"].update(arrival_usable=False, arrival_quality_flags=["BAD_UNUSED_ARRIVAL"])
        labels["train-a"]["B"].update(departure_usable=False, departure_quality_flags=["BAD_UNUSED_DEPARTURE"])
        self.assertEqual(outcome_for(route(), labels, CUTOFF)["status"], "INFERRED")

    def test_unusable_boarding_departure_is_not_replaced_with_arrival(self):
        labels = labels_for("train-a", 1000)
        labels["train-a"]["A"].update(departure_usable=False,
                                          departure_quality_flags=["MISSING_DEPARTURE"])
        result = outcome_for(route(), labels, CUTOFF)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIn("MISSING_DEPARTURE", result["endpoint_flags"]["boarding"])

    def test_missing_selected_identity_does_not_match_similar_trip(self):
        result = outcome_for(route(train="service-date-one:train"),
                             labels_for("service-date-two:train", 1000), CUTOFF)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIn("MISSING_LABEL_RECORD", result["endpoint_flags"]["boarding"])

    def test_common_quality_flag_invalidates_endpoint(self):
        labels = labels_for("train-a", 1000)
        labels["train-a"]["B"]["quality_flags"] = ["SCHEDULE_CHANGED"]
        self.assertEqual(outcome_for(route(), labels, CUTOFF)["status"], "UNAVAILABLE")

    def test_nonmonotonic_endpoints_remain_unavailable(self):
        result = outcome_for(route(), labels_for("train-a", 99, departure=100), CUTOFF)
        self.assertEqual(result["reason"], "NONMONOTONIC_ENDPOINT_LABEL")

    def test_nonfinite_endpoint_is_unavailable(self):
        labels = labels_for("train-a", 1000)
        labels["train-a"]["B"]["arrival_at"] = float("nan")
        self.assertEqual(outcome_for(route(), labels, CUTOFF)["status"], "UNAVAILABLE")

    def test_missing_journey_and_invalid_walks(self):
        candidate = route()
        candidate["timing_eligible"] = False
        self.assertEqual(outcome_for(candidate, {}, CUTOFF)["status"], "UNAVAILABLE")
        for invalid in (-1, True, float("inf")):
            with self.subTest(invalid=invalid):
                candidate = route()
                candidate["access_walk_seconds"] = invalid
                with self.assertRaises(ValueError):
                    outcome_for(candidate, labels_for("train-a", 1000), CUTOFF)
        candidate = self.two_leg_route()
        candidate["transfer_walk_seconds"] = []
        with self.assertRaises(ValueError):
            outcome_for(candidate, {}, CUTOFF)


class SnapshotSelectionTests(unittest.TestCase):
    def test_feed_grouped_input_uses_independent_latest_captures(self):
        records = [snapshot("a", 100), snapshot("a", 200, "b"),
                   snapshot("b", 110, "c"), snapshot("b", 190, "d")]
        selected, carry = latest_at_cutoffs(records, [CUTOFF + 150, CUTOFF + 200])
        self.assertEqual({x["feed_id"]: x["sha256"] for x in selected[CUTOFF + 150]}, {"a": "a", "b": "c"})
        self.assertEqual({x["feed_id"]: x["sha256"] for x in selected[CUTOFF + 200]}, {"a": "b", "b": "d"})
        self.assertEqual(carry["a"]["captured_at"], CUTOFF + 200)

    def test_previous_day_carry_and_future_exclusion(self):
        initial = {"a": snapshot("a", -10), "b": snapshot("b", -5, "b")}
        selected, _ = latest_at_cutoffs([snapshot("a", 200, "c"), snapshot("b", 210, "d")],
                                        [CUTOFF, CUTOFF + 205], initial=initial)
        self.assertEqual({x["feed_id"]: x["sha256"] for x in selected[CUTOFF]}, {"a": "a", "b": "b"})
        self.assertEqual({x["feed_id"]: x["sha256"] for x in selected[CUTOFF + 205]}, {"a": "c", "b": "b"})

    def test_future_only_snapshot_does_not_appear_at_cutoff(self):
        selected, _ = latest_at_cutoffs([snapshot("a", 1)], [CUTOFF])
        self.assertEqual(selected[CUTOFF], [])

    def test_latest_missing_capture_does_not_revive_valid_snapshot(self):
        records = [snapshot("a", 0), snapshot("a", 60, "b", status="MISSING")]
        selected, _ = latest_at_cutoffs(records, [CUTOFF + 60])
        self.assertEqual(selected[CUTOFF + 60][0]["status"], "MISSING")

    def test_equal_capture_conflict_is_sticky_until_newer_capture(self):
        records = [snapshot("a", 0, "a"), snapshot("a", 0, "b"),
                   snapshot("a", 0, "b"), snapshot("a", 60, "c")]
        selected, _ = latest_at_cutoffs(records, [CUTOFF, CUTOFF + 60])
        self.assertEqual(selected[CUTOFF][0]["status"], "MISSING")
        self.assertEqual(selected[CUTOFF][0]["trips"], [])
        self.assertEqual(selected[CUTOFF + 60][0]["status"], "OK")

    def test_identical_equal_capture_duplicate_is_usable(self):
        selected, _ = latest_at_cutoffs([snapshot("a", 0), snapshot("a", 0)], [CUTOFF])
        self.assertEqual(selected[CUTOFF][0]["status"], "OK")

    def test_backwards_timestamp_within_feed_is_rejected(self):
        with self.assertRaises(ValueError):
            latest_at_cutoffs([snapshot("a", 60), snapshot("a", 0)], [CUTOFF + 100])


class DecisionScoringTests(unittest.TestCase):
    def score(self, value, original=None, scope="strict_decision"):
        return _decision_scores(value, "stay", original or inferred(1000), scope, 180, 300)

    def test_switch_gain_and_original_strategy_gain_are_different(self):
        value = scored_value({"stay": inferred(800), "alternative": inferred(1100)},
                             action="SWITCH", chosen="alternative")
        result = self.score(value, original=inferred(1500))
        self.assertEqual(result["inferred_switch_savings_seconds"], -300)
        self.assertEqual(result["inferred_strategy_gain_vs_original_mta_seconds"], 400)
        self.assertEqual(result["classification"], "MEANINGFUL_LOSS")

    def test_practical_tie_boundaries_are_inclusive(self):
        for saving, expected in [(180, "PRACTICAL_TIE"), (-180, "PRACTICAL_TIE"),
                                 (181, "MEANINGFUL_GAIN"), (-181, "MEANINGFUL_LOSS")]:
            with self.subTest(saving=saving):
                value = scored_value({"stay": inferred(1000), "alternative": inferred(1000 - saving)},
                                     action="SWITCH", chosen="alternative")
                self.assertEqual(self.score(value)["classification"], expected)

    def test_missed_opportunity_threshold_is_strict(self):
        for saving, missed in [(300, False), (300.01, True)]:
            value = scored_value({"stay": inferred(1000), "alternative": inferred(1000 - saving)})
            result = self.score(value)
            self.assertEqual(result["missed_more_than_switch_margin"], missed)

    def test_missing_alternative_does_not_make_stay_acceptable(self):
        value = scored_value({"stay": inferred(1000), "alternative": {"status": "UNAVAILABLE"}})
        result = self.score(value)
        self.assertEqual(result["classification"], "UNKNOWN")
        self.assertIsNone(result["complete_candidate_regret_seconds"])

    def test_one_faster_known_alternative_proves_missed_opportunity(self):
        value = scored_value({"stay": inferred(1000), "faster": inferred(600),
                              "unknown": {"status": "UNAVAILABLE"}})
        result = self.score(value)
        self.assertEqual(result["classification"], "MEANINGFUL_MISSED_ALTERNATIVE")
        self.assertTrue(result["missed_more_than_switch_margin"])
        self.assertEqual(result["known_candidate_regret_seconds"], 400)
        self.assertIsNone(result["complete_candidate_regret_seconds"])

    def test_unknown_selected_outcome_is_not_a_tie(self):
        value = scored_value({"stay": inferred(1000), "alternative": {"status": "MISSED_SELECTED_TRAIN"}},
                             action="SWITCH", chosen="alternative")
        result = self.score(value)
        self.assertEqual(result["classification"], "UNKNOWN")
        self.assertIsNone(result["inferred_switch_savings_seconds"])


class CaseEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.case = {"id": "synthetic-case", "decision_at": CUTOFF,
                     "incident_ids": ["incident-1"], "snapshots": [{"as_of": "synthetic"}]}
        baseline = [route("stay", "train-a", 1000), route("alternative", "train-b", 1200, family="TRANSFER")]
        corrected = [route("stay", "train-a", 1400), route("alternative", "train-b", 900, family="TRANSFER")]
        self.predictions = {"mta": baseline, "time_profile": corrected, "incident_profile": corrected}

    def evaluate(self, labels, **kwargs):
        return evaluate_case(self.case, [], labels, CONFIG,
                             predict=fake_predictor(self.predictions, **kwargs), decide=fake_decide)

    def test_changed_labels_cannot_change_prediction_reference_or_decision(self):
        first_labels = labels_for("train-a", 1500)
        first_labels.update(labels_for("train-b", 1000))
        second_labels = labels_for("train-a", 900)
        second_labels.update(labels_for("train-b", 1400))
        calls = []
        first = self.evaluate(first_labels, calls=calls)
        second = self.evaluate(second_labels)
        self.assertEqual(first["reference_route_id"], "stay")
        self.assertEqual(second["reference_route_id"], "stay")
        self.assertEqual([item["mode"] for item in calls], list(MODES))
        self.assertTrue(all(item["cutoff"] == CUTOFF for item in calls))
        for mode in MODES:
            self.assertEqual(first["modes"][mode]["routes"], second["modes"][mode]["routes"])
            self.assertEqual(first["modes"][mode]["strict_decision"], second["modes"][mode]["strict_decision"])
        self.assertNotEqual(first["modes"]["incident_profile"]["scores"],
                            second["modes"]["incident_profile"]["scores"])

    def test_missing_baseline_outcome_does_not_substitute_reference(self):
        result = self.evaluate(labels_for("train-b", 1000))
        self.assertEqual(result["reference_route_id"], "stay")
        self.assertEqual(result["reference_outcome"]["status"], "UNAVAILABLE")
        self.assertIsNone(result["modes"]["incident_profile"]["scores"]["strict_decision"]
                          ["inferred_strategy_gain_vs_original_mta_seconds"])

    def test_mode_can_choose_another_stay_train_without_conflating_switch_gain(self):
        self.predictions["incident_profile"] = [route("stay", "other-stay-train", 1200),
                                                 route("alternative", "train-b", 700)]
        labels = labels_for("train-a", 1500)
        labels.update(labels_for("other-stay-train", 800))
        labels.update(labels_for("train-b", 1100))
        result = self.evaluate(labels)
        scores = result["modes"]["incident_profile"]["scores"]["strict_decision"]
        self.assertEqual(scores["inferred_strategy_gain_vs_original_mta_seconds"], 400)
        self.assertEqual(scores["inferred_switch_savings_seconds"], -300)

    def test_conditional_success_never_counts_as_strict_success(self):
        labels = labels_for("train-a", 1500)
        labels.update(labels_for("train-b", 1000))
        result = self.evaluate(labels, stale_mode="incident_profile")
        summary = summarize([result])
        strict = summary["modes"]["incident_profile"]["strict_decision"]
        conditional = summary["modes"]["incident_profile"]["conditional_timing_decision"]
        self.assertEqual(strict["actions"], {"UNDETERMINED": 1})
        self.assertEqual(strict["switches"], 0)
        self.assertIsNone(strict["meaningful_switch_gain_rate"])
        self.assertEqual(conditional["switches"], 1)
        self.assertEqual(conditional["meaningful_switch_gain_rate"], 1)

    def test_summary_preserves_unknown_switch_and_route_coverage_denominators(self):
        complete_labels = labels_for("train-a", 1500)
        complete_labels.update(labels_for("train-b", 1000))
        complete = self.evaluate(complete_labels)
        unknown = self.evaluate(labels_for("train-a", 1500))
        summary = summarize([complete, unknown])
        scores = summary["modes"]["incident_profile"]["strict_decision"]
        self.assertEqual(summary["case_count"], 2)
        self.assertEqual(summary["incident_count"], 1)
        self.assertEqual(scores["switches"], 2)
        self.assertEqual(scores["switches_with_comparable_outcomes"], 1)
        self.assertEqual(scores["switches_without_comparable_outcomes"], 1)
        self.assertEqual(scores["outcome_classes"], {"MEANINGFUL_GAIN": 1, "UNKNOWN": 1})
        self.assertEqual(summary["route_families"]["TRANSFER"]["outcome_UNAVAILABLE"], 1)
        self.assertEqual(summary["by_period"]["DAY"]["case_count"], 2)

    def test_tied_baseline_uses_stable_route_identity(self):
        self.predictions["mta"] = [route("z", "train-z", 1000), route("a", "train-a", 1000)]
        result = self.evaluate({})
        self.assertEqual(result["reference_route_id"], "a")


class IncidentCheckpointTests(unittest.TestCase):
    def select(self, snapshots, config=None):
        return select_incident_checkpoints(IncidentIndex(snapshots), config or checkpoint_config())

    def offsets(self, selected):
        return [item["decision_at"] - CUTOFF for item in selected["cases"]]

    def test_first_visible_severe_version_never_backdates_to_mild_notice(self):
        mild = incident_alert("F trains have delays.", "lmm:alert:1:26")
        severe = incident_alert()
        recovered = incident_alert("F trains are on or close to schedule.", "lmm:alert:1:20")
        selected = self.select([alert_snapshot(0, [mild]), alert_snapshot(100, [severe]),
                                alert_snapshot(1050, [recovered])])
        self.assertEqual(self.offsets(selected), [100, 400, 700, 1000, 1050])
        self.assertEqual(selected["incident_candidates"], 1)
        self.assertEqual(selected["cases"][0]["incident_ids"], ["lmm:alert:1"])
        self.assertEqual(selected["cases"][0]["checkpoint_reasons"],
                         {"lmm:alert:1": ["FIRST_SEVERE_VISIBILITY"]})
        self.assertEqual(selected["cases"][-1]["checkpoint_reasons"],
                         {"lmm:alert:1": ["OBSERVED_RECOVERY_OR_NOTICE_END"]})
        self.assertEqual(selected["right_censored_active_incidents"], [])
        self.assertFalse(selected["selection_uses_outcomes"])
        self.assertFalse(selected["selection_uses_model_predictions"])

    def test_severity_change_keeps_original_fixed_interval_anchor(self):
        mild = incident_alert("F trains have delays.", "lmm:alert:1:26")
        selected = self.select([alert_snapshot(100, [incident_alert()]),
                                alert_snapshot(550, [mild]), alert_snapshot(1050)])
        self.assertEqual(self.offsets(selected), [100, 400, 550, 700, 1000, 1050])
        changed = selected["cases"][2]
        self.assertEqual(changed["checkpoint_reasons"],
                         {"lmm:alert:1": ["OBSERVED_SEVERITY_CHANGE"]})

    def test_failed_capture_is_not_evidence_of_recovery(self):
        selected = self.select([alert_snapshot(100, [incident_alert()]),
                                alert_snapshot(500, status="MISSING"), alert_snapshot(1050)])
        self.assertEqual(self.offsets(selected), [100, 400, 700, 1000, 1050])
        self.assertNotIn(500, self.offsets(selected))
        self.assertEqual(selected["right_censored_active_incidents"], [])

    def test_equal_capture_conflict_is_not_evidence_of_recovery(self):
        selected = self.select([alert_snapshot(100, [incident_alert()]),
                                alert_snapshot(500), alert_snapshot(500, [incident_alert()]),
                                alert_snapshot(1050)])
        self.assertEqual(self.offsets(selected), [100, 400, 700, 1000, 1050])

    def test_successful_empty_snapshot_ends_incident_off_grid(self):
        selected = self.select([alert_snapshot(100, [incident_alert()]), alert_snapshot(650)])
        self.assertEqual(self.offsets(selected), [100, 400, 650])
        self.assertEqual(selected["cases"][-1]["checkpoint_reasons"]["lmm:alert:1"],
                         ["OBSERVED_RECOVERY_OR_NOTICE_END"])

    def test_route_alias_is_included_even_when_primary_route_differs(self):
        selected = self.select([alert_snapshot(100, [incident_alert("FX severe delays.", route_id="FX")]),
                                alert_snapshot(650)])
        self.assertEqual(self.offsets(selected), [100, 400, 650])
        self.assertEqual(selected["incident_candidates"], 1)

    def test_stop_scoped_and_ambiguous_notices_are_retained_for_input_only_selection(self):
        for selector in ({"route_id": "F", "stop_id": "INTERMEDIATE_STOP"},
                         {"route_id": "F", "direction_id": 1}):
            with self.subTest(selector=selector):
                severe = incident_alert(informed_entities=[selector])
                selected = self.select([alert_snapshot(100, [severe]), alert_snapshot(650)])
                self.assertEqual(self.offsets(selected), [100, 400, 650])

    def test_unrelated_route_never_enters_selection(self):
        selected = self.select([alert_snapshot(100, [incident_alert("B severe delays.", route_id="B")]),
                                alert_snapshot(650)])
        self.assertEqual(selected["cases"], [])
        self.assertEqual(selected["incident_candidates"], 0)

    def test_shared_route_incident_is_not_duplicated(self):
        value = incident_alert(informed_entities=[{"route_id": "F"}, {"route_id": "G"}])
        selected = self.select([alert_snapshot(100, [value]), alert_snapshot(650)])
        self.assertEqual(self.offsets(selected), [100, 400, 650])
        self.assertTrue(all(item["incident_ids"] == ["lmm:alert:1"] for item in selected["cases"]))

    def test_explicit_recovery_version_across_split_purges_whole_family(self):
        boundary = datetime(2026, 10, 18, 4, tzinfo=timezone.utc).timestamp() - CUTOFF
        recovered = incident_alert("F trains are on or close to schedule.", "lmm:alert:1:20")
        selected = self.select([alert_snapshot(boundary - 60, [incident_alert(active_periods=[])]),
                                alert_snapshot(boundary + 60, [recovered])])
        self.assertEqual(selected["cases"], [])
        self.assertEqual(selected["purged_cross_split_incident_ids"], ["lmm:alert:1"])

    def test_removal_across_split_purges_whole_family(self):
        boundary = datetime(2026, 10, 18, 4, tzinfo=timezone.utc).timestamp() - CUTOFF
        selected = self.select([alert_snapshot(boundary - 60, [incident_alert(active_periods=[])]),
                                alert_snapshot(boundary + 60)])
        self.assertEqual(selected["cases"], [])
        self.assertEqual(selected["purged_cross_split_incident_ids"], ["lmm:alert:1"])

    def test_right_censored_event_across_split_is_purged(self):
        boundary = datetime(2026, 10, 18, 4, tzinfo=timezone.utc).timestamp() - CUTOFF
        selected = self.select([alert_snapshot(boundary - 60, [incident_alert(active_periods=[])]),
                                alert_snapshot(boundary + 60, status="MISSING")])
        self.assertEqual(selected["cases"], [])
        self.assertEqual(selected["purged_cross_split_incident_ids"], ["lmm:alert:1"])


class SensitivitySelectionTests(unittest.TestCase):
    def case(self, identity, offset, incident, split="validation", **extra):
        return {"id": identity, "decision_at": CUTOFF + offset,
                "incident_ids": [incident], "split": split, **extra}

    def test_first_chronological_incidents_and_first_checkpoint_are_fixed_before_outcomes(self):
        cases = [self.case("second-event", 200, "second"),
                 self.case("first-later", 300, "first"),
                 self.case("first-earliest", 100, "first"),
                 self.case("third", 400, "third"),
                 self.case("training", 0, "train", "train"),
                 self.case("test-event", 1000, "test-first", "test")]
        config = {"sensitivity_incident_limit_per_split": 2}
        selected = sensitivity_selection(cases, config)
        self.assertEqual([item["case_id"] for item in selected],
                         ["first-earliest", "second-event", "test-event"])
        poisoned = deepcopy(cases)
        for item in poisoned:
            item.update(outcomes={"status": "UNAVAILABLE"},
                        modes={"incident_profile": {"success": item["id"] == "third"}},
                        score=999999 if item["id"] == "third" else -999999)
        self.assertEqual(selected, sensitivity_selection(list(reversed(poisoned)), config))

    def test_one_shared_checkpoint_can_represent_multiple_prespecified_incidents(self):
        case = self.case("shared", 100, "b")
        case["incident_ids"].append("a")
        selected = sensitivity_selection([case], {"sensitivity_incident_limit_per_split": 2})
        self.assertEqual([item["incident_id"] for item in selected], ["a", "b"])
        self.assertEqual([item["case_id"] for item in selected], ["shared", "shared"])

    def test_walking_variations_change_one_component_and_preserve_originals(self):
        templates = [{"id": "a", "access_walk_seconds": 60, "egress_walk_seconds": 180,
                      "transfer_walk_seconds": [30, 240]},
                     {"id": "b", "access_walk_seconds": 300, "egress_walk_seconds": 240,
                      "transfer_walk_seconds": []}]
        original = deepcopy(templates)
        variants = list(walking_variations(templates, {"walking_sensitivity_seconds": [-120, 120]}))
        self.assertEqual(len(variants), 12)
        self.assertEqual(templates, original)
        for metadata, changed in variants:
            with self.subTest(metadata=metadata):
                expected = deepcopy(original)
                target = next(item for item in expected if item["id"] == metadata["route_id"])
                component, index = metadata["component"], metadata["transfer_index"]
                before = target[component] if index is None else target[component][index]
                after = max(0, before + metadata["requested_delta_seconds"])
                if index is None:
                    target[component] = after
                else:
                    target[component][index] = after
                self.assertEqual(changed, expected)
                self.assertEqual(metadata["actual_delta_seconds"], after - before)
        variants[0][1][0]["transfer_walk_seconds"].append(999)
        self.assertEqual(templates, original)
        self.assertEqual(variants[1][1][0]["transfer_walk_seconds"], [30, 240])

    def test_margin_sensitivity_matches_independent_decisions_with_fixed_predictions(self):
        case = {"id": "margin-case", "decision_at": CUTOFF, "incident_ids": ["incident"], "snapshots": []}
        predictions = {"mta": [route("stay", "a", 1000), route("alternative", "b", 1200)],
                       "time_profile": [route("stay", "a", 1050), route("alternative", "b", 900)],
                       "incident_profile": [route("stay", "a", 1050), route("alternative", "b", 900)]}
        labels = {**labels_for("a", 1400), **labels_for("b", 800)}
        baseline = evaluate_case(case, [], labels, CONFIG, predict=fake_predictor(predictions), decide=fake_decide)
        original = deepcopy(baseline)
        for margin in (120, 180, 300):
            with self.subTest(margin=margin):
                changed = decision_margin_case(baseline, CONFIG, margin, decide=fake_decide)
                independent = evaluate_case(case, [], labels, {**CONFIG, "switch_margin_seconds": margin},
                                            predict=fake_predictor(predictions), decide=fake_decide)
                self.assertEqual(changed["modes"], independent["modes"])
                self.assertEqual(changed["reference_route_id"], baseline["reference_route_id"])
                self.assertEqual(changed["predicted_switch_margin_seconds"], margin)
                self.assertEqual(changed["modes"]["incident_profile"]["strict_decision"]["action"],
                                 "SWITCH" if margin == 120 else "STAY")
        self.assertEqual(baseline, original)

    def test_margin_sensitivity_keeps_prespecified_missed_opportunity_threshold(self):
        case = {"id": "fixed-metric", "decision_at": CUTOFF, "incident_ids": ["incident"], "snapshots": []}
        predictions = {mode: [route("stay", "a", 1000), route("alternative", "b", 1100)] for mode in MODES}
        labels = {**labels_for("a", 1000), **labels_for("b", 750)}
        result = evaluate_case(case, [], labels, CONFIG, predict=fake_predictor(predictions), decide=fake_decide)
        changed = decision_margin_case(result, CONFIG, 180, decide=fake_decide)
        self.assertFalse(changed["modes"]["incident_profile"]["scores"]["strict_decision"]
                         ["missed_more_than_switch_margin"])


class SyntheticProfile:
    def estimate(self, target, route_id, from_stop_id, to_stop_id, cutoff,
                 horizon_seconds, context):
        correction = 0
        if target == "arrival" and route_id in ("F", "FX"):
            correction = 250 if route_id == "F" else 20
            if context.get("state") == "SEVERE":
                correction += 100
        return {"correction_seconds": correction, "supported": True,
                "level": "SYNTHETIC", "event_count": 50, "incident_count": 4,
                "statistics": {}, "reason": None}


class SnapshotProjectionParityTests(unittest.TestCase):
    def setUp(self):
        first = {"route_id": "F", "route_ids": ["F", "FX"], "feed_id": "bdfm",
                 "from_stop_id": "P1S", "to_stop_id": "P2S"}
        second = {"route_id": "G", "feed_id": "g", "from_stop_id": "P2S", "to_stop_id": "P3S"}
        self.templates = [{"id": "current", "family": "TRANSFER", "name": "Synthetic transfer",
                           "access_walk_seconds": 60, "egress_walk_seconds": 60,
                           "transfer_walk_seconds": [60], "legs": [first, second]},
                          {"id": "direct", "family": "DIRECT", "name": "Synthetic direct",
                           "access_walk_seconds": 60, "egress_walk_seconds": 60,
                           "transfer_walk_seconds": [], "legs": [deepcopy(first)]}]
        self.alerts = alert_snapshot(-5, [incident_alert()])

    def train(self, identity, line, departure, arrival, start="P1S", end="P2S"):
        feed = "g" if line == "G" else "bdfm"
        return {"id": "MTA:" + feed + ":20261019:" + line + ":" + identity,
                "trip_id": identity, "route_id": line, "feed_id": feed,
                "start_date": "20261019", "start_time": "12:00:00", "direction_id": 1,
                "timestamp": CUTOFF - 10, "schedule_relationship": "SCHEDULED", "reason_codes": [],
                "stop_updates": [{"stop_id": start, "stop_sequence": 1,
                                  "arrival_time": CUTOFF + departure, "departure_time": CUTOFF + departure,
                                  "schedule_relationship": "SCHEDULED"},
                                 {"stop_id": end, "stop_sequence": 3,
                                  "arrival_time": CUTOFF + arrival, "departure_time": CUTOFF + arrival,
                                  "schedule_relationship": "SCHEDULED"}]}

    def feed(self, trains, feed_id="bdfm"):
        value = alert_snapshot(-5)
        value.update(kind="train", feed_id=feed_id, trips=trains)
        return value

    def feeds(self):
        return [self.feed([self.train("fast", "F", 120, 300),
                           self.train("express", "FX", 180, 420),
                           self.train("elsewhere", "F", 120, 200, "Q1S", "Q2S")]),
                self.feed([self.train("early", "G", 400, 800, "P2S", "P3S"),
                           self.train("later", "G", 650, 1000, "P2S", "P3S")], "g"),
                self.alerts]

    def assert_parity(self, snapshots, *, modes=MODES):
        projected = [project_snapshot(item, self.templates) for item in snapshots]
        results = {}
        for mode in modes:
            with self.subTest(mode=mode):
                kwargs = {"mode": mode, "estimator": SyntheticProfile(),
                          "incident_index": IncidentIndex([self.alerts])}
                complete = predict_routes(snapshots, self.templates, CUTOFF, **kwargs)
                compact = predict_routes(projected, self.templates, CUTOFF, **kwargs)
                self.assertEqual(complete["feed_states"], compact["feed_states"])
                for before, after in zip(complete["routes"], compact["routes"]):
                    # The retained diagnostics may omit irrelevant rejected trains.
                    for key in set(before) - {"rejected"}:
                        self.assertEqual(before[key], after[key], key)
                self.assertEqual(actual_decide(complete, "current"), actual_decide(compact, "current"))
                results[mode] = complete
        return projected, results

    def test_projection_preserves_mta_and_corrected_transfer_selections(self):
        feeds = self.feeds()
        original = deepcopy(feeds)
        compact, results = self.assert_parity(feeds)
        self.assertEqual(feeds, original)
        self.assertEqual(len(compact[0]["trips"]), 2)
        baseline = results["mta"]["routes"][0]["selected_legs"]
        corrected = results["time_profile"]["routes"][0]["selected_legs"]
        self.assertTrue(baseline[0]["trip_id"].endswith(":fast"))
        self.assertTrue(baseline[1]["trip_id"].endswith(":early"))
        self.assertTrue(corrected[0]["trip_id"].endswith(":express"))
        self.assertTrue(corrected[1]["trip_id"].endswith(":later"))

    def test_conflicting_duplicate_without_endpoint_still_invalidates_train(self):
        first = self.train("duplicate", "F", 120, 300)
        conflict = deepcopy(first)
        conflict["stop_updates"] = conflict["stop_updates"][:1]
        feeds = [self.feed([first, conflict]), self.feeds()[1], self.alerts]
        compact, results = self.assert_parity(feeds)
        self.assertEqual(len(compact[0]["trips"]), 2)
        self.assertTrue(all(not route["timing_eligible"] for route in results["mta"]["routes"]))

    def test_same_physical_train_alias_without_endpoint_stays_ambiguous_after_projection(self):
        self.templates.append({"id": "unrelated", "family": "G_DIRECT", "name": "Unaffected G",
                               "access_walk_seconds": 60, "egress_walk_seconds": 60,
                               "transfer_walk_seconds": [],
                               "legs": [deepcopy(self.templates[0]["legs"][1])]})
        first = self.train("normalized-start-a", "F", 120, 300)
        first["trip_id"] = "060000_F..S"
        alias = deepcopy(first)
        alias.update(id=first["id"] + ":different-start", start_time="12:00:05")
        alias["stop_updates"] = alias["stop_updates"][:1]
        feeds = [self.feed([first, alias]), self.feeds()[1], self.alerts]
        compact, results = self.assert_parity(feeds)
        self.assertEqual(len(compact[0]["trips"]), 2)
        self.assertNotEqual(compact[0]["trips"][0]["id"], compact[0]["trips"][1]["id"])
        for mode, result in results.items():
            with self.subTest(mode=mode):
                by_id = {route["id"]: route for route in result["routes"]}
                self.assertFalse(by_id["current"]["timing_eligible"])
                self.assertFalse(by_id["direct"]["timing_eligible"])
                self.assertTrue(by_id["unrelated"]["timing_eligible"])

    def test_full_intermediate_path_is_retained_for_incident_scope(self):
        train = self.train("affected", "F", 120, 300)
        train["stop_updates"].insert(1, {"stop_id": "MIDPOINTS", "stop_sequence": 2,
                                         "arrival_time": CUTOFF + 200, "departure_time": CUTOFF + 200})
        self.alerts = alert_snapshot(-5, [incident_alert(informed_entities=[
            {"route_id": "F", "stop_id": "MIDPOINTS"}])])
        compact, results = self.assert_parity([self.feed([train]), self.feeds()[1], self.alerts])
        self.assertEqual(compact[0]["trips"][0]["stop_updates"], train["stop_updates"])
        self.assertEqual(results["incident_profile"]["routes"][0]["context"]["state"], "SEVERE")

    def test_repeated_boarding_stop_stays_ambiguous(self):
        train = self.train("repeated", "F", 120, 300)
        repeated = deepcopy(train["stop_updates"][0])
        repeated.update(stop_sequence=2, departure_time=CUTOFF + 150)
        train["stop_updates"].insert(1, repeated)
        _, results = self.assert_parity([self.feed([train]), self.feeds()[1], self.alerts])
        self.assertTrue(all(not route["timing_eligible"] for route in results["mta"]["routes"]))

    def test_original_snapshot_hash_keeps_equal_capture_conflicts_visible(self):
        first = self.feed([self.train("fast", "F", 120, 300)])
        second = deepcopy(first)
        second["trips"].append(self.train("irrelevant", "F", 120, 200, "Q1S", "Q2S"))
        first["sha256"], second["sha256"] = "original-a", "original-b"
        _, results = self.assert_parity([first, second, self.feeds()[1], self.alerts])
        self.assertTrue(all(not route["timing_eligible"] for route in results["mta"]["routes"]))


class ReferenceServiceExposureTests(unittest.TestCase):
    def reference(self, state="SEVERE", evidence="FRESH", *, applicable=True, ids=None,
                  ambiguous=False, comparison_eligible=None):
        value = route()
        context = {"state": state, "evidence_status": evidence, "applicable": applicable,
                   "severe_incident_ids": list(ids if ids is not None else ["severe-1"] if state == "SEVERE" else []),
                   "ambiguous_scope": ambiguous}
        value["selected_legs"][0]["incident_context"] = deepcopy(context)
        value["context"] = deepcopy(context)
        value["comparison_eligible"] = (evidence == "FRESH" and not ambiguous
                                        if comparison_eligible is None else comparison_eligible)
        return value

    def evaluate_reference(self, reference, identifier="exposure", alternate_mode_reference=None):
        case = {"id": identifier, "decision_at": CUTOFF, "incident_ids": ["selection-event"], "snapshots": []}
        routes = [reference] if reference is not None else []
        predictions = {mode: deepcopy(routes) for mode in MODES}
        if alternate_mode_reference is not None:
            predictions["time_profile"] = [alternate_mode_reference]
            predictions["incident_profile"] = [alternate_mode_reference]
        return evaluate_case(case, [], {}, CONFIG, predict=fake_predictor(predictions), decide=fake_decide)

    def test_definite_severe_keeps_stale_evidence_separate(self):
        for evidence in ("FRESH", "LAST_OBSERVED"):
            with self.subTest(evidence=evidence):
                value = reference_service_context(self.reference(evidence=evidence, ids=["b", "a", "a"]))
                self.assertEqual(value, {"category": "DEFINITE_APPLICABLE_SEVERE",
                                         "evidence_status": evidence,
                                         "comparison_eligible": evidence == "FRESH",
                                         "severe_incident_ids": ["a", "b"]})

    def test_definite_leg_survives_unknown_other_leg_and_aggregate(self):
        value = self.reference()
        other = deepcopy(value["selected_legs"][0])
        other["incident_context"] = {"state": "UNKNOWN", "evidence_status": "UNKNOWN"}
        value["selected_legs"].append(other)
        value["transfer_walk_seconds"] = [0]
        value["context"].update(state="UNKNOWN", evidence_status="UNKNOWN", scope_ambiguous=True)
        value["comparison_eligible"] = False
        result = reference_service_context(value)
        self.assertEqual(result["category"], "DEFINITE_APPLICABLE_SEVERE")
        self.assertEqual(result["evidence_status"], "UNKNOWN")
        self.assertFalse(result["comparison_eligible"])
        self.assertEqual(result["severe_incident_ids"], ["severe-1"])

    def test_severe_needs_definite_applicability_and_incident_identity(self):
        for kwargs in ({"applicable": None}, {"applicable": False}, {"ids": []}):
            with self.subTest(kwargs=kwargs):
                result = reference_service_context(self.reference(**kwargs))
                self.assertEqual(result["category"], "UNKNOWN_OR_AMBIGUOUS")
                self.assertEqual(result["severe_incident_ids"], [])

    def test_ambiguous_severe_without_definite_identity_stays_unknown(self):
        for key in ("ambiguous_scope", "scope_ambiguous", "scope_uncertain"):
            with self.subTest(flag=key):
                value = self.reference(ids=[])
                value["selected_legs"][0]["incident_context"][key] = True
                self.assertEqual(reference_service_context(value)["category"], "UNKNOWN_OR_AMBIGUOUS")

    def test_known_severe_plus_other_possible_notice_keeps_definite_hit_but_not_comparability(self):
        value = self.reference(ambiguous=True, comparison_eligible=False)
        value["selected_legs"][0]["incident_context"]["possible_alerts"] = [
            {"incident_id": "uncertain-other", "state": "SEVERE"}]
        result = reference_service_context(value)
        self.assertEqual(result["category"], "DEFINITE_APPLICABLE_SEVERE")
        self.assertEqual(result["severe_incident_ids"], ["severe-1"])
        self.assertFalse(result["comparison_eligible"])

    def test_aggregate_severe_alone_does_not_invent_selected_path_applicability(self):
        value = self.reference()
        del value["selected_legs"][0]["incident_context"]
        self.assertEqual(reference_service_context(value)["category"], "UNKNOWN_OR_AMBIGUOUS")

    def test_fresh_normal_and_other_known_non_severe_remain_distinct(self):
        expected = {"NORMAL": "UNAFFECTED_FRESH_NORMAL", "PLANNED": "OTHER_KNOWN_NON_SEVERE",
                    "DISRUPTION": "OTHER_KNOWN_NON_SEVERE", "UNKNOWN": "UNKNOWN_OR_AMBIGUOUS"}
        for state, category in expected.items():
            with self.subTest(state=state):
                result = reference_service_context(self.reference(state, applicable=False))
                self.assertEqual(result["category"], category)
                self.assertEqual(result["severe_incident_ids"], [])

    def test_stale_or_ambiguous_nonsevere_evidence_is_unknown(self):
        for state in ("NORMAL", "PLANNED", "DISRUPTION"):
            for kwargs in ({"evidence": "LAST_OBSERVED"}, {"ambiguous": True}):
                with self.subTest(state=state, kwargs=kwargs):
                    self.assertEqual(reference_service_context(self.reference(state, **kwargs))["category"],
                                     "UNKNOWN_OR_AMBIGUOUS")

    def test_no_usable_reference_is_unavailable_even_if_partial_path_is_severe(self):
        partial = self.reference()
        partial["timing_eligible"] = False
        for value in (None, partial):
            with self.subTest(value=value):
                self.assertEqual(reference_service_context(value),
                                 {"category": "REFERENCE_UNAVAILABLE", "evidence_status": "UNKNOWN",
                                  "comparison_eligible": False, "severe_incident_ids": []})

    def test_exposure_uses_original_mta_reference_not_corrected_mode_context(self):
        result = self.evaluate_reference(self.reference("NORMAL", applicable=False),
                                         alternate_mode_reference=self.reference())
        self.assertEqual(result["reference_service_context"]["category"], "UNAFFECTED_FRESH_NORMAL")
        self.assertEqual(result["modes"]["incident_profile"]["routes"][0]["context"]["state"], "SEVERE")

    def test_exposure_denominators_and_compact_summary_preserve_every_checkpoint(self):
        unknown_leg = self.reference(comparison_eligible=False)
        unknown_leg["context"].update(state="UNKNOWN", evidence_status="UNKNOWN", scope_ambiguous=True)
        references = [self.reference(ids=["severe-1", "severe-2"]),
                      self.reference(evidence="LAST_OBSERVED"), unknown_leg,
                      self.reference("NORMAL", applicable=False), self.reference("PLANNED"),
                      self.reference(ambiguous=True, ids=[]), None]
        cases = [self.evaluate_reference(value, "exposure-" + str(index)) for index, value in enumerate(references)]
        full = summarize(cases)
        exposure = full["reference_service_context"]
        self.assertEqual(exposure["checkpoints_by_category"],
                         {"DEFINITE_APPLICABLE_SEVERE": 3, "UNAFFECTED_FRESH_NORMAL": 1,
                          "OTHER_KNOWN_NON_SEVERE": 1, "UNKNOWN_OR_AMBIGUOUS": 1, "REFERENCE_UNAVAILABLE": 1})
        self.assertEqual(sum(exposure["checkpoints_by_category"].values()), full["case_count"])
        self.assertEqual(exposure["checkpoints_by_evidence_status"], {"FRESH": 4, "LAST_OBSERVED": 1, "UNKNOWN": 2})
        self.assertEqual(exposure["definite_severe_checkpoints_by_evidence_status"],
                         {"FRESH": 1, "LAST_OBSERVED": 1, "UNKNOWN": 1})
        self.assertEqual(exposure["definite_severe_comparison_eligible_checkpoints"], 1)
        self.assertEqual(exposure["distinct_definite_severe_incidents"], 2)
        self.assertEqual(summarize([summary_case(case) for case in cases]), full)
        without_precomputed = deepcopy(cases)
        for case in without_precomputed:
            del case["reference_service_context"]
        self.assertEqual(summarize([summary_case(case) for case in without_precomputed]), full)


class EvaluationFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts/evaluate_october.py"
        spec = importlib.util.spec_from_file_location("october_evaluation_runner_test", path)
        cls.runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.runner)

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="october-evaluation-test-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        root_patch = patch.object(self.runner, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.config = self.root / "config.json"
        self.config.write_text('{"synthetic": true}\n')
        self.code = self.root / "tracked.py"
        self.code.write_text('"""Synthetic frozen source."""\n')
        self.source = self.root / "training-input.json"
        self.source.write_text('{"synthetic_training_source": true}\n')
        source_hashes = {"training-input.json": self.runner.sha256(self.source)}
        self.profile_path = self.root / "profile.json"
        self.manifest_path = self.root / "manifest.json"
        self.profile = {"schema_version": "delay-profiles-v1", "configuration": {},
                        "groups": {}, "fit_split": "train", "complete_month_inputs": True,
                        "source_hashes": source_hashes}
        self.profile["seal"] = digest(self.profile)
        self.profile_path.write_text(json.dumps(self.profile))
        self.manifest = {"complete_month_inputs": True,
                         "config_sha256": self.runner.sha256(self.config),
                         "code_sha256": {"tracked.py": self.runner.sha256(self.code)},
                         "source_sha256": deepcopy(source_hashes),
                         "train_profile": {"path": "profile.json", "sha256": self.runner.sha256(self.profile_path)},
                         "profile_seal": self.profile["seal"]}
        self.write_manifest()

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def reseal_profile(self):
        self.profile["seal"] = digest({key: value for key, value in self.profile.items() if key != "seal"})
        self.profile_path.write_text(json.dumps(self.profile))
        self.manifest["train_profile"]["sha256"] = self.runner.sha256(self.profile_path)
        self.manifest["profile_seal"] = self.profile["seal"]
        self.write_manifest()

    def test_evaluation_freeze_requires_explicit_creation(self):
        path = self.root / "freeze.json"
        fingerprint = {"source": "synthetic", "code": {"file": "hash"}}
        with self.assertRaises(ValueError):
            self.runner.verify_evaluation_freeze(path, fingerprint)
        self.assertFalse(path.exists())
        self.runner.verify_evaluation_freeze(path, fingerprint, create=True)
        self.assertEqual(json.loads(path.read_text()), fingerprint)
        self.runner.verify_evaluation_freeze(path, fingerprint)

    def test_existing_freeze_is_immutable_even_with_creation_flag(self):
        path = self.root / "freeze.json"
        fingerprint = {"code_sha256": {"file": "original"}, "input_sha256": {"source": "original"},
                       "config_sha256": "original", "profile_frozen_manifest_sha256": "original",
                       "selection_sha256": "original"}
        self.runner.verify_evaluation_freeze(path, fingerprint, create=True)
        original = path.read_bytes()
        for key in fingerprint:
            for create in (False, True):
                with self.subTest(key=key, create=create):
                    changed = dict(fingerprint, **{key: "modified"})
                    with self.assertRaises(ValueError):
                        self.runner.verify_evaluation_freeze(path, changed, create=create)
                    self.assertEqual(path.read_bytes(), original)

    def test_matching_train_only_profile_is_accepted(self):
        estimator = self.runner.verify_frozen_profile(self.config, self.manifest_path)
        self.assertEqual(estimator.fit_split, "train")
        self.assertEqual(estimator.seal, self.profile["seal"])

    def test_incomplete_month_manifest_is_rejected(self):
        self.manifest["complete_month_inputs"] = False
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_descriptive_month_profile_is_rejected_even_when_resealed(self):
        self.profile["fit_split"] = "month_descriptive"
        self.reseal_profile()
        with self.assertRaises(ValueError):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_incomplete_train_profile_is_rejected_even_when_resealed(self):
        self.profile["complete_month_inputs"] = False
        self.reseal_profile()
        with self.assertRaises(ValueError):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_modified_configuration_is_rejected(self):
        self.config.write_text('{"synthetic": false}\n')
        with self.assertRaises(ValueError):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_modified_profile_code_is_rejected(self):
        self.code.write_text('"""Changed frozen source."""\n')
        with self.assertRaises(ValueError):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_missing_profile_artifact_is_rejected(self):
        self.profile_path.unlink()
        with self.assertRaises(ValueError):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_modified_profile_artifact_is_rejected(self):
        self.profile_path.write_text(self.profile_path.read_text() + "\n")
        with self.assertRaises(ValueError):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_bad_internal_profile_seal_is_rejected_with_matching_file_hash(self):
        self.profile["seal"] = "bad-internal-seal"
        self.profile_path.write_text(json.dumps(self.profile))
        self.manifest["train_profile"]["sha256"] = self.runner.sha256(self.profile_path)
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_manifest_profile_seal_mismatch_is_rejected(self):
        self.manifest["profile_seal"] = "different-frozen-seal"
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_manifest_source_hashes_must_match_sealed_profile(self):
        self.manifest["source_sha256"]["training-input.json"] = "different-source-hash"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "source provenance"):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_mutated_training_source_is_rejected(self):
        self.source.write_text('{"synthetic_training_source": "changed"}\n')
        with self.assertRaisesRegex(ValueError, "source changed"):
            self.runner.verify_frozen_profile(self.config, self.manifest_path)

    def test_source_artifacts_cover_all_daily_outputs_metadata_and_labels(self):
        directory = self.root / "normalized"
        directory.mkdir()
        manifest = {"days": [], "daily_labels": {}}
        expected = {}
        for day in ("2026-10-18", "2026-10-19"):
            outputs = {}
            for kind in ("snapshots", "alerts", "trips", "receipts"):
                path = directory / (day + "." + kind + ".json")
                path.write_text(json.dumps({"synthetic_date": day, "kind": kind}))
                relative, checksum = str(path.relative_to(self.root)), self.runner.sha256(path)
                outputs[kind] = {"path": relative, "sha256": checksum}
                expected[relative] = checksum
            manifest["days"].append({"date": day, "outputs": outputs})
            metadata = directory / (day + ".source.json")
            metadata.write_text(json.dumps({"date": day, "synthetic_metadata": True}))
            expected[str(metadata.relative_to(self.root))] = self.runner.sha256(metadata)
            labels = self.root / (day + ".labels.json")
            labels.write_text('{"synthetic_labels": true}\n')
            relative, checksum = str(labels.relative_to(self.root)), self.runner.sha256(labels)
            manifest["daily_labels"][day] = {"path": relative, "sha256": checksum}
            expected[relative] = checksum
        self.assertEqual(self.runner.source_artifacts(manifest), expected)
        metadata.write_text('{"changed_metadata": true}\n')
        changed = self.runner.source_artifacts(manifest)
        relative = str(metadata.relative_to(self.root))
        self.assertNotEqual(changed[relative], expected[relative])
        self.assertEqual({key: value for key, value in changed.items() if key != relative},
                         {key: value for key, value in expected.items() if key != relative})


if __name__ == "__main__":
    unittest.main()
