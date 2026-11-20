"""Test unchanged advice and honest evidence accounting in feed replay."""

from copy import deepcopy
from contextlib import ExitStack, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from algo.scripts import evaluate_november_feed_replay as replay
from stayorswitch.severe import MODES


POLICY = {
    "boarding_margin_seconds": 120,
    "execution_horizon_seconds": 7200,
    "switch_margin_seconds": 300,
    "tie_margin_seconds": 180,
    "max_feed_gap_seconds": 120,
    "max_endpoint_age_seconds": 180,
    "retrain": False,
    "regenerate_forecasts": False,
    "initial_recommendation_uses_future_outcomes": False,
    "execution_selects_on_final_destination_arrival": False,
    "unknown_unselected_trains_block_execution": False,
    "boarding_margin_sensitivity_seconds": [60, 180],
}

QUALITY_POLICY = {
    "max_straight_line_speed_kmh": 300.0,
    "scope": "POST_SELECTION_SELECTED_TRAIN_OUTCOME_ONLY",
    "changes_forecasts_or_candidate_selection": False,
    "applies_to_all_routes_modes_and_comparison_signs": True,
    "retain_raw_endpoint_values": True,
}


def outcome(status="INFERRED", duration=1200, **extra):
    result = {"status": status, **extra}
    if status == "INFERRED":
        result["total_duration_seconds"] = duration
    return result


def paired_case(identity="one", old_class="UNKNOWN", new_class="MEANINGFUL_GAIN",
                old_outcome=None, new_outcome=None, action="SWITCH"):
    common = {"id": identity, "corridor_id": "corridor", "decision_at": 1000,
              "reference_route_id": "stay"}
    selected = "switch" if action == "SWITCH" else "stay" if action == "STAY" else None
    decision = {"action": action, "recommended_itinerary_id": selected,
                "estimated_savings_seconds": 600 if action == "SWITCH" else None}
    old_outcome = old_outcome if old_outcome is not None else outcome("UNAVAILABLE", reason="UNRESOLVED_EARLIER_BOARDING")
    new_outcome = new_outcome if new_outcome is not None else outcome()
    before, after = dict(common, modes={}), dict(common, modes={})
    for mode in MODES:
        before["modes"][mode] = {
            "strict_decision": deepcopy(decision),
            "scores": {"classification": old_class},
            "selected_routes": [{"id": selected, "route_execution_outcome": deepcopy(old_outcome)}] if selected else [],
        }
        after["modes"][mode] = {
            "strict_decision": deepcopy(decision),
            "scores": {"strict_decision": {"classification": new_class}},
            "outcomes": {selected: deepcopy(new_outcome)} if selected else {},
        }
    return before, after


class FeedReplayPolicyTests(unittest.TestCase):
    def test_preserved_policy_loads_without_reading_outcomes_or_predicting(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(POLICY))
            with patch.object(replay, "POLICY_PATH", path), patch.object(
                    replay.repair.base, "read_outcomes", side_effect=AssertionError("No outcome access")), patch.object(
                    replay.repair, "prepare_forecasts", side_effect=AssertionError("No new forecasts")):
                self.assertEqual(replay.read_policy(), POLICY)

    def test_replay_cannot_change_forecasts_margins_or_use_future_selection(self):
        replacements = (
            ("retrain", True), ("regenerate_forecasts", True),
            ("boarding_margin_seconds", 0), ("execution_horizon_seconds", 3600),
            ("switch_margin_seconds", 60), ("tie_margin_seconds", 0),
            ("max_feed_gap_seconds", 600), ("max_endpoint_age_seconds", 600),
            ("initial_recommendation_uses_future_outcomes", True),
            ("execution_selects_on_final_destination_arrival", True),
            ("unknown_unselected_trains_block_execution", True),
            ("boarding_margin_sensitivity_seconds", [30, 60]),
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            for key, value in replacements:
                with self.subTest(key=key):
                    path.write_text(json.dumps(dict(POLICY, **{key: value})))
                    with patch.object(replay, "POLICY_PATH", path), self.assertRaises(ValueError):
                        replay.read_policy()


class FeedReplayAdviceTests(unittest.TestCase):
    def test_changed_outcomes_do_not_change_frozen_advice(self):
        before, after = paired_case()
        original = deepcopy((before, after))
        replay.assert_advice_unchanged([before], [after])
        self.assertEqual((before, after), original)

    def test_any_mode_advice_or_savings_change_is_rejected(self):
        for mode in MODES:
            for key, value in (("action", "STAY"), ("recommended_itinerary_id", "another"),
                               ("estimated_savings_seconds", 650)):
                with self.subTest(mode=mode, key=key):
                    before, after = paired_case()
                    after["modes"][mode]["strict_decision"][key] = value
                    with self.assertRaises(ValueError):
                        replay.assert_advice_unchanged([before], [after])

    def test_changed_case_membership_order_or_metadata_is_rejected(self):
        first, current_first = paired_case("one")
        second, current_second = paired_case("two")
        for current in ([current_first], [current_second, current_first]):
            with self.subTest(ids=[row["id"] for row in current]), self.assertRaises(ValueError):
                replay.assert_advice_unchanged([first, second], current)
        for key, value in (("corridor_id", "elsewhere"), ("decision_at", 1001),
                           ("reference_route_id", "another-stay")):
            with self.subTest(key=key):
                changed = deepcopy(current_first)
                changed[key] = value
                with self.assertRaises(ValueError):
                    replay.assert_advice_unchanged([first], [changed])

    def test_duplicate_cases_cannot_inflate_evaluator_denominators(self):
        before, after = paired_case()
        with self.assertRaises(ValueError):
            replay.assert_advice_unchanged([before, deepcopy(before)], [after, deepcopy(after)])


class FeedReplayFreezeTests(unittest.TestCase):
    def exercise_freeze(self, mutation=None, verify_overrides=None):
        identities = ["case-" + str(index) for index in range(2306)]
        prior = {
            "training": {"seal": "unchanged-training"},
            "forecast_cases": {"path": "prior/main.json.gz", "sha256": "expected"},
            "margin_sensitivity": {"path": "prior/sensitivity.json.gz", "sha256": "expected"},
            "old_forecast_cases": {"path": "prior/original.json.gz", "sha256": "expected"},
            "selected_case_ids": identities, "primary_case_ids": identities[:197],
        }
        cases = [{"id": identity} for identity in identities]
        prepared = {"corridors": []}
        variants = [{"case_id": "variant-" + str(index)} for index in range(394)]
        quality = {key: {"path": "quality/" + key, "sha256": "expected"}
                   for key in ("config", "addendum", "station_source")}
        initial_run = {key: {"path": "initial/" + key, "sha256": "expected"}
                       for key in ("preservation_manifest", "selection_freeze", "result",
                                   "shared_route_execution", "archive_manifest")}
        with TemporaryDirectory() as directory, ExitStack() as stack:
            path = Path(directory) / "freeze.json"
            stack.enter_context(patch.object(replay, "FREEZE", path))
            stack.enter_context(patch.object(replay, "read_policy", return_value=deepcopy(POLICY)))
            stack.enter_context(patch.object(replay, "producers", return_value={"executor": "same-code"}))
            stack.enter_context(patch.object(replay, "quality_binding", return_value=quality))
            stack.enter_context(patch.object(replay, "initial_run_binding", return_value=initial_run))
            stack.enter_context(patch.object(replay.repair, "verify", return_value=(prior, prepared, cases, cases, variants)))
            stack.enter_context(patch.object(replay, "artifact", side_effect=lambda p: {"path": str(p), "sha256": "expected"}))
            stack.enter_context(patch.object(replay, "sha", return_value="expected"))
            stack.enter_context(redirect_stdout(StringIO()))
            replay.freeze()
            if mutation:
                frozen = json.loads(path.read_text())
                mutation(frozen)
                path.write_text(json.dumps(frozen))
            for helper, replacement in (verify_overrides or {}).items():
                stack.enter_context(patch.object(replay, helper, return_value=replacement))
            return replay.verify()

    def test_freeze_roundtrip_reuses_complete_prior_forecasts_and_cohort(self):
        frozen, _, _, cases, variants = self.exercise_freeze()
        self.assertTrue(frozen["forecasts_reused_byte_for_byte"])
        self.assertFalse(frozen["model_retrained"])
        self.assertEqual(len(cases), 2306)
        self.assertEqual(len(variants), 394)
        self.assertEqual(frozen["forecast_cases"]["path"], "prior/main.json.gz")

    def test_quality_followup_discloses_prior_visible_feed_results(self):
        frozen, *_ = self.exercise_freeze()
        self.assertTrue(frozen["initial_visible_feed_results_known"])
        self.assertTrue(frozen["outcome_quality_followup_after_initial_score"])
        self.assertTrue(frozen["new_executor_scoring_started"])
        self.assertFalse(frozen["corrected_outcome_scoring_started"])
        self.assertEqual(set(frozen["initial_visible_feed_run"]), {
            "preservation_manifest", "selection_freeze", "result",
            "shared_route_execution", "archive_manifest"})
        for key, value in (("initial_visible_feed_results_known", False),
                           ("outcome_quality_followup_after_initial_score", False),
                           ("new_executor_scoring_started", False),
                           ("corrected_outcome_scoring_started", True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.exercise_freeze(lambda row: row.__setitem__(key, value))

    def test_quality_and_preserved_initial_artifacts_are_exactly_bound(self):
        for group, keys in (
            ("outcome_quality", ("config", "addendum", "station_source")),
            ("initial_visible_feed_run", ("preservation_manifest", "selection_freeze",
                                         "result", "shared_route_execution", "archive_manifest")),
        ):
            for key in keys:
                for replacement in ({"path": "other/hash-valid.json", "sha256": "expected"},
                                    {"path": group + "/" + key, "sha256": "changed"}):
                    with self.subTest(group=group, key=key, replacement=replacement), self.assertRaises(ValueError):
                        self.exercise_freeze(lambda row: row[group].__setitem__(key, replacement))

    def test_quality_or_preservation_binding_cannot_drift_after_freeze(self):
        for helper in ("quality_binding", "initial_run_binding"):
            with self.subTest(helper=helper), self.assertRaises(ValueError):
                self.exercise_freeze(verify_overrides={helper: {"changed": "after freeze"}})
        with self.assertRaises(ValueError):
            self.exercise_freeze(verify_overrides={"producers": {
                "executor": "same-code", "data/route_outcome_sanity.py": "changed-quality-code"}})

    def test_frozen_forecast_reference_cannot_point_to_another_valid_artifact(self):
        for key in ("forecast_cases", "margin_sensitivity", "old_forecast_cases"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.exercise_freeze(lambda value: value.__setitem__(key,
                    {"path": "other/also-hash-valid.json.gz", "sha256": "expected"}))

    def test_case_order_and_training_are_bound_to_prior_freeze(self):
        for mutation in (
            lambda value: value["selected_case_ids"].reverse(),
            lambda value: value["primary_case_ids"].pop(),
            lambda value: value.__setitem__("training", {"seal": "different-training"}),
        ):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.exercise_freeze(mutation)


class FeedReplayQualityProvenanceTests(unittest.TestCase):
    def test_quality_policy_preserves_the_declared_symmetric_post_selection_rule(self):
        changes = (("max_straight_line_speed_kmh", 500.0), ("scope", "BEFORE_SELECTION"),
                   ("changes_forecasts_or_candidate_selection", True),
                   ("applies_to_all_routes_modes_and_comparison_signs", False),
                   ("retain_raw_endpoint_values", False))
        for key, replacement in changes:
            for value in (replacement, None):
                with self.subTest(key=key, value=value), patch.object(
                        replay, "load", return_value=dict(QUALITY_POLICY, **{key: value})), patch.object(
                        replay, "artifact", side_effect=AssertionError("Reject policy before source binding")):
                    with self.assertRaisesRegex(ValueError, "symmetric post-selection screen"):
                        replay.quality_binding()

    def test_quality_binding_checks_the_independent_station_source_hash(self):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            stations, config, addendum = (root / name for name in ("stations.csv", "quality.json", "quality.md"))
            stations.write_text("stop_id,latitude,longitude\nA,40.7,-73.9\n")
            source = {"path": "stations.csv", "sha256": replay.sha(stations)}
            config.write_text(json.dumps(dict(QUALITY_POLICY, station_source=source)))
            addendum.write_text("The quality rule was declared after the initial score.\n")
            stack.enter_context(patch.object(replay, "ROOT", root))
            stack.enter_context(patch.object(replay, "QUALITY_CONFIG", config))
            stack.enter_context(patch.object(replay, "QUALITY_ADDENDUM", addendum))
            stack.enter_context(patch.object(replay, "artifact", side_effect=lambda path: {
                "path": str(path.relative_to(root)), "sha256": replay.sha(path)}))
            bound = replay.quality_binding()
            self.assertEqual(bound["station_source"], source)
            self.assertEqual(bound["config"]["sha256"], replay.sha(config))
            self.assertEqual(bound["addendum"]["sha256"], replay.sha(addendum))
            stations.write_text("stop_id,latitude,longitude\nA,0,0\n")
            with self.assertRaisesRegex(ValueError, "station source"):
                replay.quality_binding()

    def test_initial_run_binding_reads_preserved_copies_and_checks_every_file(self):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            local = root / "algo/local/replay"
            initial = local / "superseded/initial-v3"
            original_paths = {
                "selection_freeze": root / "algo/reports/freeze.json",
                "result": root / "algo/reports/result.json",
                "shared_route_execution": local / "shared-route-execution.json.gz",
                "archive_manifest": root / "data/manifests/archive.json",
                "archived_source": root / "data/archived_source.py",
            }
            files = []
            before = {}
            for key, original in original_paths.items():
                saved = initial / original.relative_to(root)
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_text("Preserved " + key)
                files.append({"path": str(original.relative_to(root)), "sha256": replay.sha(saved)})
                before[saved] = saved.read_bytes()
            manifest = initial / "preservation-manifest.json"
            manifest.write_text(json.dumps({"files": files}))
            before[manifest] = manifest.read_bytes()
            for name, value in (("ROOT", root), ("LOCAL", local), ("INITIAL_RUN", initial),
                                ("FREEZE", original_paths["selection_freeze"]),
                                ("RESULT", original_paths["result"]),
                                ("ARCHIVE_MANIFEST", original_paths["archive_manifest"])):
                stack.enter_context(patch.object(replay, name, value))
            stack.enter_context(patch.object(replay, "artifact", side_effect=lambda path: {
                "path": str(path.relative_to(root)), "sha256": replay.sha(path)}))
            bound = replay.initial_run_binding()
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            for key in ("selection_freeze", "result", "shared_route_execution", "archive_manifest"):
                self.assertIn("superseded/initial-v3/", bound[key]["path"])
                self.assertEqual(bound[key]["sha256"], replay.sha(root / bound[key]["path"]))
            archived_source = initial / original_paths["archived_source"].relative_to(root)
            archived_source.write_text("Changed source outside the four result references")
            with self.assertRaisesRegex(ValueError, "Superseded initial feed replay changed"):
                replay.initial_run_binding()


class FeedReplayComparisonTests(unittest.TestCase):
    def test_recovered_and_lost_outcome_evidence_are_separate_from_advice(self):
        old_one, new_one = paired_case("one")
        old_two, new_two = paired_case("two", old_class="MEANINGFUL_LOSS", new_class="UNKNOWN",
            old_outcome=outcome(duration=2000), new_outcome=outcome("UNAVAILABLE", reason="SELECTED_TRAIN_MISSING"))
        compared = replay.evaluator_comparison([old_one, old_two], [new_one, new_two])
        for mode in MODES:
            row = compared[mode]
            self.assertTrue(row["advice_unchanged"])
            self.assertEqual(row["case_count"], 2)
            self.assertEqual(row["unknown_comparison_recovered"], 1)
            self.assertEqual(row["previous_comparison_now_unknown"], 1)
            self.assertEqual(row["classification_transitions"], {
                "MEANINGFUL_LOSS -> UNKNOWN": 1, "UNKNOWN -> MEANINGFUL_GAIN": 1})
            self.assertIsNone(row["records"][0]["old_selected_duration_seconds"])
            self.assertIsNone(row["records"][1]["new_selected_duration_seconds"])
            self.assertNotIn("new_policy_wins", row)

    def test_censored_outcome_keeps_its_status_and_has_no_invented_horizon_duration(self):
        before, after = paired_case(new_class="UNKNOWN",
            new_outcome=outcome("CENSORED", reason="EXECUTION_HORIZON"))
        result = replay.evaluator_comparison([before], [after])["incident_profile"]
        self.assertEqual(result["selected_status_transitions"], {"UNAVAILABLE -> CENSORED": 1})
        self.assertEqual(result["unknown_comparison_recovered"], 0)
        self.assertIsNone(result["records"][0]["new_selected_duration_seconds"])

    def test_undetermined_advice_has_no_selected_journey(self):
        before, after = paired_case(action="UNDETERMINED", old_class="NOT_A_DECISION", new_class="NOT_A_DECISION")
        row = replay.evaluator_comparison([before], [after])["incident_profile"]
        self.assertEqual(row["selected_status_transitions"], {"NO_SELECTED_JOURNEY -> NO_SELECTED_JOURNEY": 1})
        self.assertEqual(row["unknown_comparison_recovered"], 0)


class FeedReplayTraceTests(unittest.TestCase):
    def test_quality_rejections_preserve_selected_routes_and_separate_reference_failures(self):
        reason = "SELECTED_OUTCOME_IMPLAUSIBLE_TRAVEL_TIME"
        rejected = outcome("UNAVAILABLE", reason=reason, leg_index=0,
            event={"canonical_trip_id": "C:one", "from_stop_id": "A", "to_stop_id": "B"},
            outcome_quality={"reason": "IMPLAUSIBLE_LEG_TRAVEL_TIME", "observed_seconds": 10})
        _, first = paired_case("one", new_class="UNKNOWN", new_outcome=deepcopy(rejected))
        _, second = paired_case("two", new_class="UNKNOWN")
        _, inactive = paired_case("three", action="UNDETERMINED", new_class="NOT_A_DECISION")
        shared = {"one": {"stay": outcome(), "switch": deepcopy(rejected)},
                  "two": {"stay": deepcopy(rejected), "switch": outcome()},
                  "three": {"stay": outcome("UNAVAILABLE", reason="OTHER_REASON")}}
        for case in (first, second, inactive):
            for value in case["modes"].values():
                value["outcomes"] = shared[case["id"]]
        for case in (first, second):
            case["modes"]["mta"]["strict_decision"].update(action="STAY", recommended_itinerary_id="stay")
        cases = [first, second, inactive]
        before = deepcopy((shared, cases))
        result = replay.quality_summary(shared, cases)
        self.assertEqual((shared, cases), before)
        self.assertEqual(result["selected_route_queries_rejected"], 2)
        self.assertEqual(result["unique_selected_legs_rejected"], 1)
        self.assertFalse(result["rejected_outcomes_trigger_alternate_selection"])
        self.assertEqual(result["by_mode"]["mta"], {"chosen_route_rejected": 1})
        for mode in ("time_profile", "incident_profile"):
            self.assertEqual(result["by_mode"][mode], {
                "chosen_route_rejected": 1, "switch_route_rejected": 1,
                "switch_comparison_stay_rejected": 1,
                "switch_comparison_either_route_rejected": 2})
        self.assertTrue(all(row["status"] == "UNAVAILABLE" for row in result["records"]))
        self.assertEqual([(row["case_id"], row["route_id"]) for row in result["records"]],
                         [("one", "switch"), ("two", "stay")])

    def test_trace_summary_retains_unavailable_events_and_ignores_boolean_counters(self):
        complete = outcome(trace_counters={"feed_updates": 2, "chosen_train_updates": 1, "flag": True},
                           update_trace=[{"event": "SELECT"}, {"event": "BOARD"}])
        missing = outcome("UNAVAILABLE", reason="SELECTED_DEPARTURE_UNVERIFIED",
                          trace_counters={"feed_updates": 3, "selected_unknown": 1},
                          update_trace=[{"event": "SELECT"}, {"event": "MISSING"}])
        result = replay.trace_summary(iter([complete, missing]))
        self.assertEqual(result["route_query_count"], 2)
        self.assertEqual(result["status_counts"], {"INFERRED": 1, "UNAVAILABLE": 1})
        self.assertEqual(result["trace_counters"], {"chosen_train_updates": 1, "feed_updates": 5, "selected_unknown": 1})
        self.assertEqual(result["trace_event_counts"], {"BOARD": 1, "MISSING": 1, "SELECT": 2})
        self.assertEqual(result["reason_counts"], {"SELECTED_DEPARTURE_UNVERIFIED": 1})

    def test_shared_routes_are_counted_once_and_selected_denominators_are_separate(self):
        _, active = paired_case()
        _, inactive = paired_case("two", action="UNDETERMINED", old_class="NOT_A_DECISION", new_class="NOT_A_DECISION")
        complete = outcome(trace_counters={"feed_updates": 2})
        missing = outcome("UNAVAILABLE", reason="SELECTED_ARRIVAL_UNVERIFIED")
        shared = {"one": {"stay": complete, "switch": complete},
                  "two": {"stay": missing, "switch": missing}}
        for value in active["modes"].values():
            value["outcomes"] = shared["one"]
        active["modes"]["mta"]["strict_decision"].update(action="STAY", recommended_itinerary_id="stay")
        result = replay.execution_summaries(shared, [active, inactive])
        self.assertEqual(result["all_supplied_paths"]["route_query_count"], 4)
        self.assertEqual(result["all_supplied_paths"]["trace_counters"], {"feed_updates": 4})
        for mode in MODES:
            self.assertEqual(result["selected_routes_by_mode"][mode]["route_query_count"], 1)
        self.assertEqual(result["switch_routes_by_mode"]["mta"]["route_query_count"], 0)
        self.assertEqual(result["switch_routes_by_mode"]["incident_profile"]["route_query_count"], 1)

    def test_report_row_preserves_explicit_zero_counts(self):
        self.assertEqual(replay._table_row(["Severe", 51, 0, 0, 0, 51]),
                         "| Severe | 51 | 0 | 0 | 0 | 51 |")


def conditional_case(identity="one"):
    _, value = paired_case(identity)
    for mode in MODES:
        value["modes"][mode]["outcomes"] = {
            "stay": outcome(duration=1800, conditional_on_unverified_selected_wait=False),
            "switch": outcome(duration=1200, conditional_on_unverified_selected_wait=False),
        }
    value["paired_policies"] = {key: {"comparable": True, "classification": "PRACTICAL_TIE"}
        for key in ("incident_vs_mta", "time_vs_mta", "incident_vs_time")}
    return value


class FeedReplayConditionalEvidenceTests(unittest.TestCase):
    def test_conditional_stay_qualifies_switch_comparison_but_not_chosen_route(self):
        value = conditional_case()
        value["modes"]["incident_profile"]["outcomes"]["stay"]["conditional_on_unverified_selected_wait"] = True
        result = replay.conditional_evidence_summary([value])
        model = result["by_mode"]["incident_profile"]
        self.assertEqual(model["inferred_chosen_routes"], {"without_unverified_selected_wait": 1})
        self.assertEqual(model["comparable_switch_vs_stay"], {"conditional_on_unverified_selected_wait": 1})
        self.assertEqual(model["conditional_switch_classes"], {"MEANINGFUL_GAIN": 1})
        self.assertEqual(model["switch_classes_without_unverified_selected_wait"], {})
        self.assertEqual(result["paired_policies"]["incident_vs_mta"]["comparable"],
                         {"without_unverified_selected_wait": 1})

    def test_either_selected_policy_can_make_paired_comparison_conditional(self):
        value = conditional_case()
        for route in ("stay", "switch"):
            value["modes"]["incident_profile"]["outcomes"][route]["conditional_on_unverified_selected_wait"] = True
        result = replay.conditional_evidence_summary([value])
        model = result["by_mode"]["incident_profile"]
        self.assertEqual(model["comparable_switch_vs_stay"], {"conditional_on_unverified_selected_wait": 1})
        for comparison in ("incident_vs_mta", "incident_vs_time"):
            self.assertEqual(result["paired_policies"][comparison]["comparable"],
                             {"conditional_on_unverified_selected_wait": 1})
            self.assertEqual(result["paired_policies"][comparison]["conditional_classes"],
                             {"PRACTICAL_TIE": 1})
        self.assertEqual(result["paired_policies"]["time_vs_mta"]["comparable"],
                         {"without_unverified_selected_wait": 1})

    def test_unknown_outcome_is_not_promoted_to_conditional_complete_evidence(self):
        value = conditional_case()
        for mode in MODES:
            value["modes"][mode]["outcomes"]["switch"] = outcome("UNAVAILABLE",
                reason="SELECTED_ARRIVAL_UNVERIFIED", conditional_on_unverified_selected_wait=True)
            value["modes"][mode]["scores"]["strict_decision"]["classification"] = "UNKNOWN"
        for pair in value["paired_policies"].values():
            pair.update(comparable=False, classification="UNKNOWN")
        result = replay.conditional_evidence_summary([value])
        self.assertTrue(result["conditional_is_not_an_independent_observed_passenger_outcome"])
        for mode in MODES:
            self.assertEqual(result["by_mode"][mode]["inferred_chosen_routes"], {})
            self.assertEqual(result["by_mode"][mode]["comparable_switch_vs_stay"], {})
        for comparison in result["paired_policies"].values():
            self.assertEqual(comparison["comparable"], {})


if __name__ == "__main__":
    unittest.main()
