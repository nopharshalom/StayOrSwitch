"""Riding-time endpoint, chronology, and hindsight-isolation regressions."""

import copy
from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from history.features import LabelIndex, source_trip_uid
from history.segments import SegmentBuilder


def at(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("America/New_York")).timestamp())


def snapshot(day="2026-11-02"):
    capture = at(day + "T10:00:00")
    return {
        "feed_id": "bdfm", "captured_at": capture,
        "source_updated_at": capture - 5, "status": "AVAILABLE",
        "member_name": "synthetic.gtfsrt", "trips": [{
            "id": "MTA:bdfm:" + day.replace("-", "") + ":F:060000_F..S:",
            "trip_id": "060000_F..S", "route_id": "F", "start_date": day.replace("-", ""),
            "nyct_direction": "SOUTH", "timestamp": None, "schedule_relationship": "SCHEDULED",
            "stop_updates": [
                {"stop_id": "F01S", "arrival_time": capture + 60, "departure_time": capture + 80},
                {"stop_id": "F02S", "arrival_time": capture + 200, "departure_time": capture + 210},
                {"stop_id": "F03S", "arrival_time": capture + 400, "departure_time": capture + 410},
            ],
        }],
    }


def labels(value):
    capture = value["captured_at"]
    trip = value["trips"][0]
    uid = source_trip_uid(trip)
    return LabelIndex([{"trip_uid": uid, "trip_id": trip["trip_id"], "route_id": "F",
                        "num_schedule_changes": "0", "num_schedule_rewrites": "0"}], [
        {"trip_uid": uid, "stop_id": "F01S", "arrival_time": str(capture + 60),
         "departure_time": str(capture + 90), "last_observed": str(capture + 95),
         "marked_past": str(capture + 100)},
        {"trip_uid": uid, "stop_id": "F03S", "arrival_time": str(capture + 450),
         "departure_time": str(capture + 460), "last_observed": str(capture + 465),
         "marked_past": str(capture + 470)},
    ])


def builder(index):
    return SegmentBuilder(index, route_ids=["F"], stop_ids=["F01S", "F03S"])


class SegmentTests(unittest.TestCase):
    def test_departure_to_arrival_proxy_excludes_origin_dwell(self):
        value = snapshot()
        row = builder(labels(value)).process(value)[0]
        self.assertEqual(row["features"]["predicted_duration_seconds"], 320)
        self.assertEqual(row["label"]["duration_seconds"], 360)
        self.assertEqual(row["label"]["residual_seconds"], 40)
        self.assertTrue(row["eligible_for_training"])
        self.assertFalse(row["label"]["physical_ground_truth"])
        self.assertEqual(row["features"]["segment_stop_pattern"], ["F01S", "F02S", "F03S"])
        self.assertNotIn("duration_seconds", row["features"])

    def test_future_csv_reroute_flags_do_not_change_features(self):
        value = snapshot()
        index = labels(value)
        initial = builder(index).process(value)[0]
        next(iter(index.trips.values()))["num_schedule_rewrites"] = "1"
        index.cache_clear()
        changed = builder(index).process(value)[0]
        self.assertEqual(initial["features"], changed["features"])
        self.assertFalse(changed["eligible_for_training"])
        self.assertIn("ORIGIN_CSV_SCHEDULE_REWRITTEN", changed["label"]["quality_flags"])

    def test_origin_terminal_arrival_may_be_missing_when_departure_exists(self):
        value = snapshot()
        index = labels(value)
        index.stops[(source_trip_uid(value["trips"][0]), "F01S")]["arrival_time"] = ""
        row = builder(index).process(value)[0]
        self.assertTrue(row["eligible_for_training"])
        self.assertEqual(row["label"]["duration_seconds"], 360)

    def test_missing_csv_departure_is_not_zero_or_arrival_substitution(self):
        value = snapshot()
        index = labels(value)
        index.stops[(source_trip_uid(value["trips"][0]), "F01S")]["departure_time"] = ""
        row = builder(index).process(value)[0]
        self.assertFalse(row["eligible_for_training"])
        self.assertIsNone(row["label"]["duration_seconds"])
        self.assertIn("MISSING_CSV_DEPARTURE", row["label"]["quality_flags"])

    def test_forecast_arrival_fallback_is_explicit(self):
        value = snapshot()
        del value["trips"][0]["stop_updates"][0]["departure_time"]
        result = builder(labels(value))
        row = result.process(value)[0]
        self.assertEqual(row["features"]["origin_prediction_basis"], "ARRIVAL_AS_DEPARTURE_PROXY")
        self.assertEqual(row["features"]["predicted_duration_seconds"], 340)
        self.assertEqual(result.report()["counts"]["origin_arrival_prediction_proxy_rows"], 1)

    def test_arrival_fallback_cannot_make_a_backwards_interval(self):
        value = snapshot()
        index = labels(value)
        del value["trips"][0]["stop_updates"][0]["departure_time"]
        value["trips"][0]["stop_updates"][0]["arrival_time"] = value["captured_at"] + 500
        self.assertEqual(builder(index).process(value), [])

    def test_endpoint_arrival_after_departure_invalidates_csv_label(self):
        for endpoint, flag in (("F01S", "ORIGIN_CSV_ARRIVAL_AFTER_DEPARTURE"),
                               ("F03S", "DESTINATION_CSV_ARRIVAL_AFTER_DEPARTURE")):
            value = snapshot()
            index = labels(value)
            stop = index.stops[(source_trip_uid(value["trips"][0]), endpoint)]
            stop["departure_time"] = str(int(stop["arrival_time"]) - 1)
            row = builder(index).process(value)[0]
            self.assertFalse(row["eligible_for_training"])
            self.assertIn(flag, row["label"]["quality_flags"])

    def test_raw_identifiers_are_provenance_and_gtfs_direction_is_explicit(self):
        value = snapshot()
        value["trips"][0]["direction_id"] = 0
        value["trips"][0]["nyct_train_id"] = "synthetic-train"
        row = builder(labels(value)).process(value)[0]
        self.assertEqual(row["features"]["gtfs_direction_id"], 0)
        self.assertEqual(row["provenance"]["raw_trip_id"], "060000_F..S")
        self.assertEqual(row["provenance"]["nyct_train_id"], "synthetic-train")
        self.assertNotIn("raw_trip_id", row["features"])
        self.assertNotIn("nyct_train_id", row["features"])

    def test_negative_csv_segment_is_retained_but_unusable(self):
        value = snapshot()
        index = labels(value)
        index.stops[(source_trip_uid(value["trips"][0]), "F03S")]["arrival_time"] = str(value["captured_at"] + 70)
        row = builder(index).process(value)[0]
        self.assertIsNone(row["label"]["duration_seconds"])
        self.assertFalse(row["eligible_for_training"])
        self.assertIn("NEGATIVE_CSV_SEGMENT_DURATION", row["label"]["quality_flags"])

    def test_label_availability_cannot_cross_evaluation_boundary(self):
        value = snapshot("2026-11-08")
        index = labels(value)
        index.stops[(source_trip_uid(value["trips"][0]), "F03S")]["marked_past"] = str(at("2026-11-09T00:00:00"))
        row = builder(index).process(value)[0]
        self.assertFalse(row["eligible_for_training"])
        self.assertIn("DESTINATION_LABEL_AVAILABILITY_SPLIT_BOUNDARY", row["label"]["quality_flags"])

    def test_canceled_skipped_and_repeated_stops_do_not_form_segments(self):
        for kind in ("cancel", "skip", "no_data", "repeat"):
            value = snapshot()
            index = labels(value)
            if kind == "cancel":
                value["trips"][0]["schedule_relationship"] = "CANCELED"
            elif kind in ("skip", "no_data"):
                value["trips"][0]["stop_updates"][-1]["schedule_relationship"] = "SKIPPED" if kind == "skip" else "NO_DATA"
            else:
                value["trips"][0]["stop_updates"].append(copy.deepcopy(value["trips"][0]["stop_updates"][0]))
            self.assertEqual(builder(index).process(value), [], kind)

    def test_bad_horizon_or_forecast_order_does_not_create_segment(self):
        for departure, arrival in ((-1, 400), (80, 20), (80, 1801)):
            value = snapshot()
            index = labels(value)
            value["trips"][0]["stop_updates"][0]["departure_time"] = value["captured_at"] + departure
            value["trips"][0]["stop_updates"][-1]["arrival_time"] = value["captured_at"] + arrival
            self.assertEqual(builder(index).process(value), [])

    def test_duplicate_snapshot_does_not_duplicate_events(self):
        value = snapshot()
        result = builder(labels(value))
        self.assertEqual(len(result.process(value)), 1)
        self.assertEqual(result.process(value), [])
        self.assertEqual(result.report()["unique_segment_events"], 1)

    def test_stale_and_future_source_or_trip_updates_are_excluded(self):
        for kind, delta in (("source", 1), ("source", -181), ("trip", 1), ("trip", -181)):
            value = snapshot()
            index = labels(value)
            if kind == "source":
                value["source_updated_at"] = value["captured_at"] + delta
            else:
                value["trips"][0]["timestamp"] = value["captured_at"] + delta
            self.assertEqual(builder(index).process(value), [])

    def test_day_types_and_service_split_are_kept_distinct(self):
        for day, expected in (("2026-11-02", "WEEKDAY"), ("2026-11-07", "SATURDAY"), ("2026-11-08", "SUNDAY")):
            value = snapshot(day)
            row = builder(labels(value)).process(value)[0]
            self.assertEqual(row["features"]["day_type"], expected)
            self.assertEqual(row["split"], "train")
        value = snapshot("2026-11-09")
        index = labels(value)
        value["trips"][0]["start_date"] = "20261108"
        self.assertEqual(builder(index).process(value), [])


if __name__ == "__main__":
    unittest.main()
