"""Calendar-only selection and evidence guards for the November weekday view."""

from copy import deepcopy
from concurrent.futures import Future
from contextlib import ExitStack
from datetime import datetime
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from algo.scripts import report_november_weekdays as weekdays


DATES = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06",
         "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13",
         "2026-11-16", "2026-11-17", "2026-11-18"]


def timestamp(value):
    return datetime.fromisoformat(value).timestamp()


def case(identity, at, *, corridor="corridor", incident="publisher-family", timing=False):
    return {"id": identity, "decision_at": timestamp(at), "corridor_id": corridor,
            "incident_ids": [incident], "reference_route_id": "stay",
            "asof_mta_prediction": {"routes": [{"id": "stay", "timing_eligible": timing}]},
            "official_text_review": {"status": "CONFIRMED", "confirmed_impact": "DISRUPTION"}}


class WeekdaySelectionTests(unittest.TestCase):
    def test_explicit_thirteen_local_dates_exclude_weekends_and_boundary_day(self):
        rows = [case("day-{:02d}".format(day), "2026-11-{:02d}T12:00:00-05:00".format(day),
                     incident="incident-{:02d}".format(day)) for day in range(1, 20)]
        original = deepcopy(rows)
        selected, primary = weekdays.select_view(rows, DATES)
        expected = ["day-" + day[-2:] for day in DATES]
        self.assertEqual([c["id"] for c in selected], expected)
        self.assertEqual([c["id"] for c in primary], expected)
        self.assertEqual(len(selected), 13)
        self.assertNotIn("day-19", expected)
        self.assertEqual(rows, original)

    def test_filter_uses_new_york_date_at_utc_midnight_boundary(self):
        sunday = case("sunday", "2026-11-16T04:59:59+00:00")
        monday = case("monday", "2026-11-16T05:00:00+00:00")
        final = case("final", "2026-11-19T04:59:59+00:00", incident="last")
        boundary = case("boundary-only", "2026-11-19T05:00:00+00:00", incident="outside")
        selected, _ = weekdays.select_view([sunday, monday, final, boundary], DATES)
        self.assertEqual([c["id"] for c in selected], ["monday", "final"])

    def test_primary_is_literal_earliest_qualified_weekday_even_without_stay_timing(self):
        early = case("initial-closure", "2026-11-03T08:00:00-05:00", timing=False)
        early["official_text_review"].update(confirmed_impact="SEVERE",
            severity_basis="COMPLETE_FIXED_PATH_INTERRUPTION")
        later = case("later-timed", "2026-11-03T08:05:00-05:00", timing=True)
        # These deliberately conflicting outcome hints are irrelevant to selection.
        early["outcomes"] = {"stay": {"status": "UNAVAILABLE"}}
        later["outcomes"] = {"stay": {"status": "INFERRED", "saving_seconds": 1000}}
        selected, primary = weekdays.select_view([later, early], DATES)
        self.assertEqual(len(selected), 2)
        self.assertEqual([c["id"] for c in primary], ["initial-closure"])
        self.assertFalse(primary[0]["asof_mta_prediction"]["routes"][0]["timing_eligible"])
        for row in (early, later):
            row["outcomes"] = {"arbitrary": "changed"}
            row["recommendation"] = "SWITCH"
        self.assertEqual([c["id"] for c in weekdays.select_view([later, early], DATES)[1]],
                         ["initial-closure"])

    def test_weekend_origin_family_receives_new_weekday_representative(self):
        weekend = case("sunday-origin", "2026-11-08T23:30:00-05:00", timing=True)
        monday = case("monday-first", "2026-11-09T00:20:00-05:00", timing=False)
        later = case("monday-later", "2026-11-09T00:25:00-05:00", timing=True)
        selected, primary = weekdays.select_view([weekend, later, monday], DATES)
        self.assertEqual([c["id"] for c in selected], ["monday-later", "monday-first"])
        self.assertEqual([c["id"] for c in primary], ["monday-first"])

    def test_primary_grouping_keeps_corridors_and_publisher_families_distinct(self):
        at = "2026-11-03T08:00:00-05:00"
        rows = [case("z-tie", at), case("a-tie", at),
                case("second-corridor", at, corridor="another"),
                case("second-family", at, incident="another-family")]
        _, primary = weekdays.select_view(rows, DATES)
        self.assertEqual({c["id"] for c in primary}, {"a-tie", "second-corridor", "second-family"})
        self.assertEqual(len(primary), 3)


class PlannedClosureTimingTests(unittest.TestCase):
    def test_case_specific_active_and_inactive_membership_override_generic_text(self):
        review = {"planned_closure_active_case_ids": ["active"],
                  "planned_closure_inactive_case_ids": ["inactive"],
                  "planned_closure_mentioned": True,
                  "planned_through_service_unavailable": True}
        original = deepcopy(review)
        self.assertEqual(weekdays.planned_timing({"id": "active", "official_text_review": review}),
                         "CONFIRMED_ACTIVE")
        self.assertEqual(weekdays.planned_timing({"id": "inactive", "official_text_review": review}),
                         "CONFIRMED_INACTIVE")
        self.assertEqual(review, original)

    def test_mentioned_closure_without_timing_evidence_remains_unknown(self):
        row = {"id": "unresolved-time", "official_text_review": {"planned_closure_mentioned": True},
               "outcomes": {"stay": {"status": "UNAVAILABLE"}},
               "asof_mta_prediction": {"routes": [{"id": "stay", "timing_eligible": False}]}}
        self.assertEqual(weekdays.planned_timing(row), "MENTIONED_TIMING_UNKNOWN")
        row["outcomes"] = {"stay": {"status": "INFERRED"}}
        row["asof_mta_prediction"]["routes"][0]["timing_eligible"] = True
        self.assertEqual(weekdays.planned_timing(row), "MENTIONED_TIMING_UNKNOWN")

    def test_explicit_input_reviewed_unavailability_and_no_mention_are_distinct(self):
        self.assertEqual(weekdays.planned_timing({"id": "a", "official_text_review": {
            "planned_through_service_unavailable": True}}), "CONFIRMED_ACTIVE")
        self.assertEqual(weekdays.planned_timing({"id": "a", "official_text_review": {}}),
                         "NO_PLANNED_CLOSURE_MENTION")

    def test_conflicting_case_membership_fails_even_for_another_current_case(self):
        row = {"id": "current", "official_text_review": {
            "planned_closure_active_case_ids": ["conflict"],
            "planned_closure_inactive_case_ids": ["conflict"]}}
        with self.assertRaisesRegex(ValueError, "conflicting"):
            weekdays.planned_timing(row)


class WeekdayPolicyTests(unittest.TestCase):
    def policy_files(self, root):
        policy = {"stage": "DECLARED_BEFORE_NOVEMBER_OUTCOME_SCORING",
                  "selection_uses_outcomes": False, "analysis_dates": list(DATES),
                  "analysis_date_count": 13, "original_analysis_bounds": ["2026-11-01", "2026-11-18"],
                  "timezone": "America/New_York", "training_dates": ["2026-10-01", "2026-10-31"]}
        for key in ("addendum", "inherited_base_protocol"):
            filename = key + ".md"
            content = ("Frozen input-only " + key + "\n").encode()
            (root / filename).write_bytes(content)
            policy[key] = {"path": filename, "sha256": hashlib.sha256(content).hexdigest()}
        path = root / "weekday-policy.json"
        path.write_text(json.dumps(policy))
        return policy, path

    def test_reads_valid_policy_with_both_protocol_hashes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            policy, path = self.policy_files(root)
            with patch.object(weekdays, "ROOT", root), patch.object(weekdays, "POLICY_PATH", path):
                self.assertEqual(weekdays.read_policy(), policy)

    def test_modified_addendum_or_inherited_protocol_is_rejected(self):
        for key in ("addendum", "inherited_base_protocol"):
            with self.subTest(key=key), TemporaryDirectory() as directory:
                root = Path(directory)
                policy, path = self.policy_files(root)
                (root / policy[key]["path"]).write_text("Changed after declaration\n")
                with patch.object(weekdays, "ROOT", root), patch.object(weekdays, "POLICY_PATH", path):
                    with self.assertRaisesRegex(ValueError, "Reporting protocol changed"):
                        weekdays.read_policy()

    def test_invalid_calendar_or_outcome_selection_flags_are_rejected(self):
        for defect in ("stage", "outcomes", "count", "duplicate", "weekend", "unsorted",
                       "boundary", "timezone", "training"):
            with self.subTest(defect=defect), TemporaryDirectory() as directory:
                root = Path(directory)
                policy, path = self.policy_files(root)
                if defect == "stage":
                    policy["stage"] = "AFTER_OUTCOME_SCORING"
                elif defect == "outcomes":
                    policy["selection_uses_outcomes"] = True
                elif defect == "count":
                    policy["analysis_date_count"] -= 1
                elif defect == "duplicate":
                    policy["analysis_dates"][1] = policy["analysis_dates"][0]
                elif defect == "weekend":
                    policy["analysis_dates"][0] = "2026-11-01"
                elif defect == "boundary":
                    policy["analysis_dates"][-1] = "2026-11-19"
                elif defect == "timezone":
                    policy["timezone"] = "UTC"
                elif defect == "training":
                    policy["training_dates"][-1] = "2026-11-01"
                else:
                    policy["analysis_dates"].reverse()
                path.write_text(json.dumps(policy))
                with patch.object(weekdays, "ROOT", root), patch.object(weekdays, "POLICY_PATH", path):
                    with self.assertRaisesRegex(ValueError, "valid input-only calendar selection"):
                        weekdays.read_policy()


class WeekdayFreezeTests(unittest.TestCase):
    def test_weekday_freeze_uses_separate_outputs_and_never_opens_outcomes(self):
        weekend = case("weekend", "2026-11-08T23:30:00-05:00", timing=True)
        early = case("first-weekday-unknown", "2026-11-09T00:20:00-05:00", timing=False)
        later = case("later-weekday-timed", "2026-11-09T00:25:00-05:00", timing=True)
        rows = [weekend, later, early]
        prepared = {"provenance": {"old_source": "unchanged"}}
        review = {"audit_sources": [{"path": "input-only-audit.json", "sha256": "audit-hash"}]}
        policy = {"analysis_dates": list(DATES)}
        selection = {"all_date_fixed_window_cases": 3}
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            output_directory = root / "weekday-output"
            frozen_path = root / "weekday-freeze.json"
            stack.enter_context(patch.object(weekdays, "read_policy", return_value=policy))
            stack.enter_context(patch.object(weekdays, "qualified_inputs", return_value=(
                prepared, review, rows, selection, [], [{"first_applicable_receipt": weekend["decision_at"]}])))
            stack.enter_context(patch.object(weekdays, "provenance", return_value={"weekday_view": "bound"}))
            stack.enter_context(patch.object(weekdays, "artifact", return_value={"path": "review.json", "sha256": "review-hash"}))
            stack.enter_context(patch.object(weekdays, "FREEZE", frozen_path))
            stack.enter_context(patch.object(weekdays, "LOCAL", output_directory))
            stack.enter_context(patch.object(weekdays.base, "LOCAL", root / "original-output"))
            stack.enter_context(patch.object(weekdays.base, "training_provenance", return_value={"profile": "frozen-october"}))
            no_outcomes = stack.enter_context(patch.object(weekdays.base, "read_outcomes",
                side_effect=AssertionError("A weekday freeze must not open outcomes.")))

            def forecasts(actual_prepared, selected):
                self.assertIs(actual_prepared, prepared)
                self.assertEqual(weekdays.base.LOCAL, output_directory)
                self.assertEqual([c["id"] for c in selected], ["later-weekday-timed", "first-weekday-unknown"])
                return ({"path": "weekday-output/forecasts.json.gz", "sha256": "forecast-hash"},
                        {"path": "weekday-output/execution.json", "sha256": "execution-hash"})

            def sensitivity(actual_prepared, primary, review_artifact):
                self.assertIs(actual_prepared, prepared)
                self.assertEqual(weekdays.base.LOCAL, output_directory)
                self.assertEqual([c["id"] for c in primary], ["first-weekday-unknown"])
                return {"path": "weekday-output/sensitivity.json.gz", "sha256": "sensitivity-hash"}

            stack.enter_context(patch.object(weekdays, "prepare_parallel_forecasts", side_effect=forecasts))
            stack.enter_context(patch.object(weekdays.base, "prepare_sensitivity", side_effect=sensitivity))
            writer = stack.enter_context(patch.object(weekdays, "dump"))
            stack.enter_context(patch("builtins.print"))
            weekdays.freeze_view()
            no_outcomes.assert_not_called()
            writer.assert_called_once()
            written_path, frozen = writer.call_args.args
            self.assertEqual(written_path, frozen_path)
            self.assertEqual(frozen["provenance"], {"weekday_view": "bound"})
            self.assertEqual(frozen["primary_case_ids"], ["first-weekday-unknown"])
            self.assertEqual(frozen["excluded_weekend_case_ids"], ["weekend"])
            self.assertEqual(frozen["forecast_execution"],
                             {"path": "weekday-output/execution.json", "sha256": "execution-hash"})
            self.assertFalse(frozen["selection_uses_outcomes"])
            self.assertFalse(frozen["weekend_three_mode_predictions_generated"])


class ParallelForecastTests(unittest.TestCase):
    def test_date_workers_merge_in_frozen_order_with_serial_parity_and_no_outcomes(self):
        calls = []
        first = timestamp("2026-11-02T08:00:00-05:00")
        second = timestamp("2026-11-03T08:00:00-05:00")

        def prediction(at, mode="mta"):
            return {"cutoff": at, "mode": mode, "routes": [{"id": "stay", "timing_eligible": True,
                    "total_duration_seconds": 1000 + (0 if mode == "mta" else 60),
                    "selected_legs": [{"trip_id": "train-at-" + str(at)}]}]}

        rows = [case("second-day", "2026-11-03T08:00:00-05:00"),
                case("z-first-day", "2026-11-02T08:00:00-05:00"),
                case("a-first-day", "2026-11-02T08:00:00-05:00", incident="another-publisher")]
        for row in rows:
            row["asof_mta_prediction"] = prediction(row["decision_at"])
        original = deepcopy(rows)
        prepared = {"corridors": [{"id": "corridor", "reference_route_id": "stay"}]}

        def snapshots(actual_prepared, requested):
            self.assertIs(actual_prepared, prepared)
            return iter({"cutoff": at, "snapshots": [{"captured_at": at - 5}]}
                        for at in sorted(requested))

        def predict(snapshots, corridor, at, index, estimator, mode):
            calls.append((at, mode))
            return prediction(at, mode)

        class ImmediateExecutor:
            def __init__(self, **kwargs):
                self.worker_count = kwargs["max_workers"]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def submit(self, function, argument):
                future = Future()
                future.set_result(function(argument))
                return future

        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            local = root / "weekday-output"
            for filename in ("prepared.json", "review.json", "wrapper.py"):
                (root / filename).write_text("Input-only fixture " + filename)

            def artifact(path):
                return {"path": str(path.relative_to(root)), "sha256": weekdays.sha(path)}

            stack.enter_context(patch.object(weekdays, "ROOT", root))
            stack.enter_context(patch.object(weekdays, "LOCAL", local))
            stack.enter_context(patch.object(weekdays, "SELF", root / "wrapper.py"))
            stack.enter_context(patch.object(weekdays, "artifact", side_effect=artifact))
            stack.enter_context(patch.object(weekdays.base, "PREPARED", root / "prepared.json"))
            stack.enter_context(patch.object(weekdays.base, "REVIEW", root / "review.json"))
            stack.enter_context(patch.object(weekdays.base, "training_provenance", return_value={"seal": "october-only"}))
            stack.enter_context(patch.object(weekdays.base, "source_days", return_value=({}, {})))
            stack.enter_context(patch.object(weekdays.base, "incident_index", return_value=object()))
            stack.enter_context(patch.object(weekdays.base, "ProfileEstimator", return_value=object()))
            stack.enter_context(patch.object(weekdays.base, "selected_snapshots", side_effect=snapshots))
            stack.enter_context(patch.object(weekdays.base, "predict", side_effect=predict))
            no_outcomes = stack.enter_context(patch.object(weekdays.base, "read_outcomes",
                side_effect=AssertionError("Forecast workers must not read outcomes.")))
            stack.enter_context(patch.object(weekdays, "ProcessPoolExecutor", ImmediateExecutor))
            stack.enter_context(patch.object(weekdays, "as_completed", side_effect=lambda futures: reversed(list(futures))))
            stack.enter_context(patch("builtins.print"))
            output_artifact, execution_artifact = weekdays.prepare_parallel_forecasts(prepared, rows, workers=3)
            saved = weekdays.load(root / output_artifact["path"])
            execution = weekdays.load(root / execution_artifact["path"])
            no_outcomes.assert_not_called()
            self.assertEqual([r["id"] for r in saved["cases"]], [r["id"] for r in original])
            self.assertEqual([{k: v for k, v in r.items() if k != "predictions"} for r in saved["cases"]], original)
            self.assertEqual(execution["worker_count"], 2)
            self.assertEqual([s["date"] for s in execution["shards"]], ["2026-11-02", "2026-11-03"])
            self.assertEqual(execution["serial_parity_case_ids"], ["a-first-day", "second-day"])
            self.assertEqual(execution["serial_mode_parity_checks"], 6)
            self.assertFalse(execution["outcomes_read"])
            self.assertTrue(execution["all_selected_stay_forecasts_match_input_scope"])
            self.assertIsNone(weekdays._FORECAST_RUNTIME)
            # Two date/corridor snapshots x three modes, then six serial checks.
            # Repeated publisher cases at one cutoff share the worker cache.
            self.assertEqual(len(calls), 12)
            self.assertEqual(set(calls), {(at, mode) for at in (first, second) for mode in weekdays.MODES})

    def test_worker_rejects_missing_selected_snapshot_before_writing(self):
        row = case("missing-snapshot", "2026-11-02T08:00:00-05:00")
        runtime = {"by_day": {"2026-11-02": [row]}, "prepared": {},
                   "corridors": {"corridor": {"id": "corridor"}},
                   "index": object(), "estimator": object(), "binding": {"input": "fixed"}}
        with patch.object(weekdays, "_FORECAST_RUNTIME", runtime), \
                patch.object(weekdays.base, "selected_snapshots", return_value=iter([])), \
                patch.object(weekdays, "dump") as writer:
            with self.assertRaisesRegex(ValueError, "missing exact selected snapshots"):
                weekdays._forecast_day("2026-11-02")
            writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
