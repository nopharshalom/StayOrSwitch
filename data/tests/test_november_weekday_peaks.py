"""Protect the calendar-only weekday view of the unchanged peak input freeze."""

from collections import Counter
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.november_peak_analysis import mark_representatives, scheduled_grid
from data.november_weekday_peaks import (
    MODEL_FREEZE, ROOT, SOURCE, score, select_weekday_rows, summarize_weekdays, weekday_dates,
)


DATES = ["2026-11-" + suffix for suffix in (
    "02", "03", "04", "05", "06", "09", "10", "11", "12", "13", "16", "17", "18")]
CORRIDORS = [{"id": "corridor-" + str(i)} for i in range(5)]


def prepared_rows():
    """Generate synthetic inputs only; no archived forecasts or labels are read."""
    rows = []
    for corridor in CORRIDORS:
        for checkpoint in scheduled_grid():
            sequence = [["synthetic:" + corridor["id"] + ":" + checkpoint["date"], "A", "B"]]
            rows.append(dict(checkpoint, id=corridor["id"] + "--" + str(checkpoint["decision_at"]),
                             corridor_id=corridor["id"],
                             forecast={"timing_eligible": False, "selected_legs": []},
                             duration_band="UNAVAILABLE", physical_sequence=sequence))
    return mark_representatives(rows)


def scored_unknown_rows(rows):
    values = deepcopy(rows)
    for row in values:
        row["outcome"] = {"status": "UNAVAILABLE", "reason": "SYNTHETIC_MISSING_FEED"}
        row["eta_error_seconds"] = None
    return values


class WeekdayCalendarTests(unittest.TestCase):
    def test_exact_thirteen_approved_dates(self):
        self.assertEqual(weekday_dates(), DATES)

    def test_selects_2860_checkpoints_without_mutating_3960_inputs(self):
        rows = prepared_rows()
        before = deepcopy(rows)
        selected = select_weekday_rows(rows)
        self.assertEqual(len(rows), 3960)
        self.assertEqual(rows, before)
        self.assertEqual(len(selected), 2860)
        self.assertEqual({row["date"] for row in selected}, set(DATES))
        self.assertEqual(Counter(row["date"] for row in selected), {day: 220 for day in DATES})
        self.assertEqual(len(rows) - len(selected), 1100)

    def test_selection_preserves_input_order_and_row_objects(self):
        rows = prepared_rows()[::-1]
        selected = select_weekday_rows(rows)
        expected = [row for row in rows if row["date"] in DATES]
        self.assertEqual([row["id"] for row in selected], [row["id"] for row in expected])
        self.assertTrue(all(a is b for a, b in zip(selected, expected)))

    def test_selection_does_not_depend_on_outcomes_or_day_type_labels(self):
        inputs = prepared_rows()
        expected = [row["id"] for row in select_weekday_rows(inputs)]
        changed = deepcopy(inputs)
        for i, row in enumerate(changed):
            row["outcome"] = {"status": "INFERRED" if i % 2 else "UNAVAILABLE"}
            row["eta_error_seconds"] = 999999 if i % 3 else -999999
            row["day_type"] = "SUNDAY" if row["date"] in DATES else "WEEKDAY"
        self.assertEqual([row["id"] for row in select_weekday_rows(changed)], expected)

    def test_inherited_representatives_and_predictions_are_unchanged(self):
        rows = prepared_rows()
        original = {row["id"]: deepcopy(row) for row in rows}
        selected = select_weekday_rows(rows)
        for row in selected:
            self.assertEqual(row, original[row["id"]])
        self.assertEqual(sum(row["event_representative"] for row in selected), 195)
        self.assertEqual(sum(row["event_representative"] for row in rows), 270)


class WeekdaySummaryTests(unittest.TestCase):
    def test_scoring_cannot_open_outcomes_before_full_october_model_seal(self):
        target = "data.november_weekday_peaks."
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            stack.enter_context(patch(target + "REPORT", Path(temporary) / "report.json"))
            stack.enter_context(patch(target + "read_json", return_value={
                "stage": "TRAINING", "training_dates": ["2026-10-01", "2026-10-31"]}))
            reader = stack.enter_context(patch(target + "read_labels"))
            selection = stack.enter_context(patch(target + "verify_selection"))
            with self.assertRaisesRegex(ValueError, "sealed before"):
                score()
            reader.assert_not_called()
            selection.assert_not_called()

    def test_daily_pooled_and_duration_cells_include_unavailable_days(self):
        selected = select_weekday_rows(scored_unknown_rows(prepared_rows()))
        before = deepcopy(selected)
        groups = summarize_weekdays(selected, CORRIDORS)
        self.assertEqual(selected, before)
        self.assertEqual(len(groups["daily"]), 195)
        self.assertEqual(len(groups["pooled"]), 15)
        self.assertEqual(len(groups["duration_band"]), 75)
        self.assertEqual(sum(cell["scheduled_checkpoints"] for cell in groups["daily"]), 2860)
        self.assertEqual(sum(cell["scheduled_checkpoints"] for cell in groups["pooled"]), 2860)
        for cell in groups["daily"]:
            self.assertEqual(cell["day_type"], "WEEKDAY")
            self.assertIn(cell["date"], DATES)
            self.assertEqual(cell["coverage_fraction"], 0)
            self.assertIsNone(cell["grid_weighted"]["mean_signed_seconds"])
            self.assertEqual(cell["grid_weighted"]["n"], 0)
            self.assertEqual(cell["scheduled_checkpoints"], 12 if cell["period"] == "MIDDAY" else 16)

    def test_daily_rows_use_corridor_then_calendar_then_period_order(self):
        selected = select_weekday_rows(scored_unknown_rows(prepared_rows()))[::-1]
        daily = summarize_weekdays(selected, CORRIDORS)["daily"]
        expected = [(corridor["id"], day, period) for corridor in CORRIDORS for day in DATES
                    for period in ("MORNING_PEAK", "MIDDAY", "EVENING_PEAK")]
        self.assertEqual([(row["corridor_id"], row["date"], row["period"]) for row in daily], expected)

    def test_known_weekday_errors_do_not_fill_unknown_weekday_rows(self):
        selected = select_weekday_rows(scored_unknown_rows(prepared_rows()))
        first = selected[0]
        first["outcome"] = {"status": "INFERRED"}
        first["eta_error_seconds"] = 600
        result = summarize_weekdays(selected, CORRIDORS)["pooled"][0]
        self.assertEqual(result["scheduled_checkpoints"], 13 * 16)
        self.assertEqual(result["usable_checkpoints"], 1)
        self.assertEqual(result["unknown_checkpoints"], 13 * 16 - 1)
        self.assertEqual(result["grid_weighted"]["mean_signed_seconds"], 600)
        self.assertEqual(result["grid_weighted"]["mean_positive_seconds"], 600)

    def test_scoring_accepts_source_artifact_size_metadata_and_opens_only_weekdays(self):
        """Exercise the source producer's path/bytes/hash contract using fake labels."""
        prepared = {"rows": prepared_rows(), "corridors": CORRIDORS}
        selected = select_weekday_rows(prepared["rows"])
        model = {"stage": "FROZEN_BEFORE_NOVEMBER_OUTCOME_ANALYSIS",
                 "training_dates": ["2026-10-01", "2026-10-31"],
                 "artifact": {"path": "data/artifacts/synthetic-profile.gz", "sha256": "sha"}}
        labels = {day: {"path": "data/processed/synthetic/" + day + ".labels.json.gz",
                        "bytes": 123, "sha256": "sha"} for day in DATES}
        source = {"stage": "PREPARED", "daily_labels": labels}

        def fake_read(path):
            if path == MODEL_FREEZE:
                return model
            if path == SOURCE:
                return source
            raise AssertionError("Unexpected manifest read: " + str(path))

        def fake_artifact(path):
            name = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            return {"path": str(name), "sha256": "sha"}

        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            target = "data.november_weekday_peaks."
            stack.enter_context(patch(target + "REPORT", Path(temporary) / "report.json"))
            stack.enter_context(patch(target + "SCORING_FREEZE", Path(temporary) / "freeze.json"))
            stack.enter_context(patch(target + "read_json", side_effect=fake_read))
            stack.enter_context(patch(target + "artifact", side_effect=fake_artifact))
            stack.enter_context(patch(target + "file_sha256", return_value="sha"))
            stack.enter_context(patch(target + "verify_selection", return_value=(prepared, selected, {})))
            stack.enter_context(patch(target + "code_provenance", return_value={"producer": "sha"}))
            reader = stack.enter_context(patch(target + "read_labels", return_value={}))
            for name in ("write_json", "write_csv", "write_markdown", "write_heatmap"):
                stack.enter_context(patch(target + name))
            with redirect_stdout(io.StringIO()):
                score()
            self.assertEqual(reader.call_count, 13)
            self.assertEqual([call.args[0] for call in reader.call_args_list],
                             [ROOT / labels[day]["path"] for day in DATES])
        self.assertTrue(all("outcome" not in row for row in prepared["rows"]))


if __name__ == "__main__":
    unittest.main()
