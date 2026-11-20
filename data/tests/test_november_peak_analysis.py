"""Check November departure-grid populations, ETA meanings and missing outcomes."""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import unittest

from data.november_peak_analysis import (
    daily_label_artifact, duration_band, load_corridors, mark_representatives, physical_sequence,
    report_groups, scheduled_grid, stats, summarize_rows,
)
from stayorswitch.october_evaluation import outcome_for


def forecast(train="060000_F..S01R", *, alias="10:00:00", feed="bdfm", line="F"):
    """Construct an input-only selected journey with an encoded physical identity."""
    return {"timing_eligible": True, "total_duration_seconds": 1200,
            "access_walk_seconds": 120, "egress_walk_seconds": 60,
            "transfer_walk_seconds": [],
            "context": {"state": "UNKNOWN"},
            "selected_legs": [{"trip_id": "normalized:" + train + ":" + alias,
                               "raw_trip_id": train, "start_time": alias,
                               "feed_id": feed, "route_id": line,
                               "service_date": "20261101",
                               "from_stop_id": "F09S", "to_stop_id": "A41S"}]}


def row(identifier="first", *, offset=0, train="060000_F..S01R", outcome="INFERRED", error=60):
    checkpoint = scheduled_grid("2026-11-01", "2026-11-01")[0]
    prediction = forecast(train)
    return dict(checkpoint, id=identifier, decision_at=checkpoint["decision_at"] + offset,
                corridor_id="test", forecast=prediction,
                duration_band=duration_band(prediction["total_duration_seconds"]),
                physical_sequence=physical_sequence(prediction),
                outcome={"status": outcome, "reason": "MISSING_LABEL"},
                eta_error_seconds=error if outcome == "INFERRED" else None)


def endpoint(arrival, departure=None):
    return {"arrival_at": arrival, "departure_at": arrival if departure is None else departure,
            "arrival_usable": True, "departure_usable": True,
            "quality_flags": [], "arrival_quality_flags": [], "departure_quality_flags": []}


class LocalDepartureGridTests(unittest.TestCase):
    def test_eighteen_dates_and_expected_five_corridor_population(self):
        grid = scheduled_grid()
        self.assertEqual(len(grid), 792)
        self.assertEqual(len({r["date"] for r in grid}), 18)
        self.assertEqual(min(r["date"] for r in grid), "2026-11-01")
        self.assertEqual(max(r["date"] for r in grid), "2026-11-18")
        self.assertEqual(len({r["decision_at"] for r in grid}), 792)
        self.assertEqual(len(load_corridors()) * len(grid), 3960)

    def test_outcome_manifest_uses_separate_daily_labels_mapping(self):
        item = {"path": "data/processed/november-2026/2026-11-01.labels.json.gz", "sha256": "abc"}
        manifest = {"stage": "PREPARED", "days": [{"date": "2026-11-01", "outputs": {"snapshots": {}}}],
                    "daily_labels": {"2026-11-01": item}}
        self.assertEqual(daily_label_artifact(manifest, "2026-11-01"), item)
        with self.assertRaises(ValueError):
            daily_label_artifact(manifest, "2026-11-02")
        manifest["stage"] = "INPUTS_PREPARED"
        with self.assertRaises(ValueError):
            daily_label_artifact(manifest, "2026-11-01")

    def test_period_counts_and_exclusive_end_times(self):
        rows = scheduled_grid("2026-11-02", "2026-11-02")
        self.assertEqual(Counter(r["period"] for r in rows),
                         {"MORNING_PEAK": 16, "MIDDAY": 12, "EVENING_PEAK": 16})
        times = [datetime.fromisoformat(r["local_time"]).strftime("%H:%M") for r in rows]
        for expected in ("06:00", "09:45", "11:00", "13:45", "16:00", "19:45"):
            self.assertIn(expected, times)
        for excluded in ("10:00", "14:00", "20:00"):
            self.assertNotIn(excluded, times)

    def test_dst_transition_uses_local_clock_not_fixed_utc_offset(self):
        first = scheduled_grid("2026-11-01", "2026-11-01")[0]
        self.assertEqual(first["local_time"], "2026-11-01T06:00:00-05:00")
        self.assertEqual(datetime.fromtimestamp(first["decision_at"], timezone.utc).hour, 11)
        self.assertEqual(first["day_type"], "SUNDAY")
        prior = scheduled_grid("2026-10-31", "2026-10-31")[0]
        self.assertEqual(prior["local_time"], "2026-10-31T06:00:00-04:00")
        self.assertEqual(first["decision_at"] - prior["decision_at"], 25 * 3600)

    def test_weekdays_saturdays_and_sundays_remain_distinct(self):
        grid = scheduled_grid()
        dates = {r["date"]: r["day_type"] for r in grid}
        self.assertEqual(Counter(dates.values()), {"WEEKDAY": 13, "SATURDAY": 2, "SUNDAY": 3})

    def test_duration_bands_and_invalid_predictions(self):
        for value, expected in ((0, "00_15_MIN"), (899.9, "00_15_MIN"),
                                (900, "15_30_MIN"), (1799.9, "15_30_MIN"),
                                (1800, "30_60_MIN"), (3599.9, "30_60_MIN"),
                                (3600, "OVER_60_MIN")):
            with self.subTest(value=value):
                self.assertEqual(duration_band(value), expected)
        for value in (None, True, -1, float("nan"), float("inf"), "900"):
            with self.subTest(invalid=value):
                self.assertEqual(duration_band(value), "UNAVAILABLE")


class ResidualStatisticsTests(unittest.TestCase):
    def test_three_mean_definitions_use_correct_denominators(self):
        result = stats([-120, 0, 300])
        self.assertEqual(result["n"], 3)
        self.assertEqual(result["mean_signed_seconds"], 60)
        self.assertEqual(result["mean_positive_seconds"], 100)
        self.assertEqual(result["mean_if_late_seconds"], 300)
        self.assertEqual(result["median_signed_seconds"], 0)
        self.assertAlmostEqual(result["p90_signed_seconds"], 240)
        self.assertEqual(result["share_over_five_minutes"], 0)

    def test_five_minute_boundary_is_strict_and_early_is_not_late(self):
        self.assertEqual(stats([300, 301])["share_over_five_minutes"], .5)
        result = stats([-120, 0])
        self.assertEqual(result["mean_positive_seconds"], 0)
        self.assertIsNone(result["mean_if_late_seconds"])

    def test_empty_support_is_unavailable_not_zero_delay(self):
        result = stats([])
        self.assertEqual(result["n"], 0)
        self.assertTrue(all(value is None for key, value in result.items() if key != "n"))

    def test_summary_preserves_unknown_denominator(self):
        rows = mark_representatives([row(error=120), row("missing", train="061000_F..S01R", outcome="UNAVAILABLE")])
        result = summarize_rows(rows)
        self.assertEqual(result["scheduled_checkpoints"], 2)
        self.assertEqual(result["usable_checkpoints"], 1)
        self.assertEqual(result["unknown_checkpoints"], 1)
        self.assertEqual(result["coverage_fraction"], .5)
        self.assertEqual(result["grid_weighted"]["mean_signed_seconds"], 120)
        self.assertEqual(result["unknown_reason_counts"], {"MISSING_LABEL": 1})

    def test_clock_time_and_train_balanced_estimands_are_distinct(self):
        rows = mark_representatives([row("first", error=600), row("repeat", offset=900, error=600),
                                     row("other", train="061000_F..S01R", offset=1800, error=0)])
        result = summarize_rows(rows)
        self.assertEqual(result["grid_weighted"]["mean_signed_seconds"], 400)
        self.assertEqual(result["event_balanced"]["mean_signed_seconds"], 300)
        self.assertEqual(result["distinct_physical_sequences"], 2)
        self.assertEqual(result["event_representatives"], 2)


class InputRepresentativeTests(unittest.TestCase):
    def test_start_time_aliases_share_physical_key_without_labels(self):
        first, second = forecast(alias="10:00:00"), forecast(alias="10:00:30")
        self.assertNotEqual(first["selected_legs"][0]["trip_id"], second["selected_legs"][0]["trip_id"])
        self.assertEqual(physical_sequence(first), physical_sequence(second))
        self.assertNotEqual(physical_sequence(first), physical_sequence(forecast(train="060100_F..S01R")))

    def test_route_feed_service_and_endpoint_namespaces_do_not_collapse(self):
        original = forecast()
        expected = physical_sequence(original)
        for field, value in (("feed_id", "different-feed"), ("route_id", "different-route"),
                             ("service_date", "20261102"), ("to_stop_id", "D16S")):
            changed = deepcopy(original)
            changed["selected_legs"][0][field] = value
            with self.subTest(field=field):
                self.assertNotEqual(physical_sequence(changed), expected)

    def test_unresolved_input_identity_is_not_repaired_from_outcomes(self):
        invalid = forecast()
        invalid["selected_legs"][0].pop("service_date")
        self.assertIsNone(physical_sequence(invalid))
        invalid = forecast()
        invalid["timing_eligible"] = False
        self.assertIsNone(physical_sequence(invalid))

    def test_earliest_unknown_representative_is_not_replaced_by_later_known_row(self):
        early = row("early", outcome="UNAVAILABLE")
        later = row("later", offset=900, error=100)
        rows = mark_representatives([later, early])
        self.assertTrue(early["event_representative"])
        self.assertFalse(later["event_representative"])
        self.assertEqual(later["representative_case_id"], "early")
        result = summarize_rows(rows)
        self.assertEqual(result["grid_weighted"]["n"], 1)
        self.assertEqual(result["event_balanced"]["n"], 0)
        self.assertIsNone(result["event_balanced"]["mean_signed_seconds"])

    def test_duration_band_and_period_preserve_separate_representatives(self):
        first = row()
        different_band = row("band", offset=900)
        different_band["duration_band"] = "30_60_MIN"
        different_period = row("period", offset=3600)
        different_period["period"] = "MIDDAY"
        rows = mark_representatives([first, different_band, different_period])
        self.assertEqual(sum(r["event_representative"] for r in rows), 3)
        self.assertEqual(len({r["physical_sequence_key"] for r in rows}), 1)


class ReportAndSelectedTrainTests(unittest.TestCase):
    def test_report_retains_all_daily_period_cells_without_usable_outcomes(self):
        corridors = [{"id": "corridor-" + str(i)} for i in range(5)]
        rows = []
        for corridor in corridors:
            for checkpoint in scheduled_grid():
                rows.append(dict(checkpoint, id=corridor["id"] + str(checkpoint["decision_at"]),
                                 corridor_id=corridor["id"], forecast={"timing_eligible": False},
                                 physical_sequence=None, duration_band="UNAVAILABLE",
                                 outcome={"status": "UNAVAILABLE", "reason": "MISSING_FEED"},
                                 eta_error_seconds=None))
        groups = report_groups(mark_representatives(rows), corridors)
        self.assertEqual(len(groups["daily"]), 270)
        self.assertEqual(len(groups["pooled"]), 15)
        self.assertEqual(len(groups["day_type"]), 45)
        self.assertEqual(len(groups["duration_band"]), 75)
        self.assertEqual(sum(r["scheduled_checkpoints"] for r in groups["daily"]), 3960)
        for cell in groups["daily"]:
            self.assertEqual(cell["coverage_fraction"], 0)
            self.assertEqual(cell["grid_weighted"]["n"], 0)
            self.assertIsNone(cell["grid_weighted"]["mean_signed_seconds"])

    def test_missed_forecast_selected_train_stays_unknown_despite_later_train(self):
        cutoff = scheduled_grid()[0]["decision_at"]
        selected = forecast()
        identity = selected["selected_legs"][0]["trip_id"]
        labels = {identity: {"F09S": endpoint(cutoff + 119), "A41S": endpoint(cutoff + 1000)},
                  "later-train": {"F09S": endpoint(cutoff + 240), "A41S": endpoint(cutoff + 1200)}}
        result = outcome_for(selected, labels, cutoff)
        self.assertEqual(result["status"], "MISSED_SELECTED_TRAIN")
        self.assertEqual(result["trip_id"], identity)
        self.assertNotIn("total_duration_seconds", result)

    def test_fixed_egress_cancels_in_paired_journey_residual(self):
        cutoff = scheduled_grid()[0]["decision_at"]
        selected = forecast()
        identity = selected["selected_legs"][0]["trip_id"]
        selected["total_duration_seconds"] = 1000 + selected["egress_walk_seconds"]
        labels = {identity: {"F09S": endpoint(cutoff + 120), "A41S": endpoint(cutoff + 1300)}}
        result = outcome_for(selected, labels, cutoff)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["total_duration_seconds"] - selected["total_duration_seconds"], 300)
        self.assertEqual(result["components"]["waiting_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
