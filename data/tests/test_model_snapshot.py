"""Offline/live feature parity and invalid-observation boundaries."""

from copy import deepcopy
import unittest

from modeling.features import build_features, support_key
from modeling.snapshot import build_snapshot_case


NOW = 1793631600  # November 2, 2026, 10:00 America/New_York.


def snapshot():
    return {"kind": "train", "status": "AVAILABLE", "feed_id": "bdfm",
            "source_updated_at": NOW - 5, "fetched_at": NOW - 2, "requested_at": NOW - 3,
            "trips": [{"id": "MTA:bdfm:20261102:F:060000_F..S:", "route_id": "F",
                       "feed_id": "bdfm", "timestamp": NOW - 5, "nyct_direction": "SOUTH",
                       "direction_id": 1, "is_assigned": True,
                       "schedule_relationship": "SCHEDULED", "stop_updates": [
                           {"stop_id": "F01S", "arrival_time": NOW + 70, "departure_time": NOW + 80},
                           {"stop_id": "F02S", "arrival_time": NOW + 200, "departure_time": NOW + 210},
                           {"stop_id": "F03S", "arrival_time": NOW + 400, "departure_time": NOW + 420}]}]}


def case(target, value=None, **kwargs):
    value = value or snapshot()
    endpoints = {"stop_id": "F03S"} if target == "arrival" else {"from_stop_id": "F01S"}
    if target == "segment":
        endpoints["to_stop_id"] = "F03S"
    endpoints.update(kwargs)
    return build_snapshot_case(value, value["trips"][0]["id"], target,
                               decision_at=NOW, **endpoints)


class SnapshotFeatureTests(unittest.TestCase):
    def test_actual_snapshot_matches_historical_core_features(self):
        historical = {
            "route_id": "F", "feed_id": "bdfm", "direction": "SOUTH", "gtfs_direction_id": 1,
            "day_type": "WEEKDAY", "seconds_since_local_midnight": 36000,
            "feed_age_seconds": 5, "trip_update_age_seconds": 5, "is_assigned": True,
            "stop_id": "F03S", "from_stop_id": "F01S", "to_stop_id": "F03S",
            "prediction_horizon_seconds": 400, "departure_horizon_seconds": 80,
            "arrival_horizon_seconds": 400, "predicted_duration_seconds": 320,
            "remaining_stop_pattern": ["F01S", "F02S", "F03S"],
            "segment_stop_pattern": ["F01S", "F02S", "F03S"],
        }
        for target in ("arrival", "departure", "segment"):
            with self.subTest(target=target):
                actual = case(target)
                expected = build_features(target, historical)
                self.assertEqual(actual["features"], expected)
                self.assertEqual(actual["support_key"], support_key(target, expected, historical))
                self.assertNotIn("label_seconds", actual)

    def test_arrival_and_departure_remain_separate(self):
        self.assertEqual(case("arrival", stop_id="F01S")["baseline_seconds"], 70)
        self.assertEqual(case("departure")["baseline_seconds"], 80)
        self.assertEqual(case("segment")["baseline_seconds"], 320)

    def test_arrival_cannot_substitute_for_missing_departure(self):
        value = snapshot()
        value["trips"][0]["stop_updates"][0]["departure_time"] = None
        for target in ("departure", "segment"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                case(target, value)

    def test_future_receipt_and_stale_source_are_rejected(self):
        for key, invalid in (("fetched_at", NOW + 1), ("source_updated_at", NOW - 181),
                             ("source_updated_at", NOW - 1), ("requested_at", NOW)):
            value = snapshot()
            value[key] = invalid
            with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                case("arrival", value)

    def test_future_and_stale_trip_observations_are_rejected(self):
        for invalid in (NOW - 181, NOW - 1, NOW + 1):
            value = snapshot()
            value["trips"][0]["timestamp"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                case("arrival", value)

    def test_missing_trip_age_is_not_zero(self):
        value = snapshot()
        value["trips"][0]["timestamp"] = None
        self.assertIsNone(case("arrival", value)["features"]["trip_update_age_seconds"])

    def test_canceled_skipped_repeated_and_reverse_patterns_rejected(self):
        canceled, skipped, repeated = (snapshot() for _ in range(3))
        canceled["trips"][0]["schedule_relationship"] = "CANCELED"
        skipped["trips"][0]["stop_updates"][0]["schedule_relationship"] = "SKIPPED"
        repeated["trips"][0]["stop_updates"].append(deepcopy(repeated["trips"][0]["stop_updates"][0]))
        for value in (canceled, skipped, repeated):
            with self.assertRaises(ValueError):
                case("segment", value)
        with self.assertRaises(ValueError):
            case("segment", from_stop_id="F03S", to_stop_id="F01S")

    def test_negative_horizon_and_long_segment_are_rejected(self):
        for invalid in (NOW - 1, NOW + 1801):
            value = snapshot()
            value["trips"][0]["stop_updates"][2]["arrival_time"] = invalid
            for target in ("arrival", "segment"):
                with self.subTest(target=target, invalid=invalid), self.assertRaises(ValueError):
                    case(target, value)

    def test_known_skipped_intermediate_is_outside_model_scope(self):
        for relationship in ("SKIPPED", "NO_DATA"):
            value = snapshot()
            value["trips"][0]["stop_updates"][1]["schedule_relationship"] = relationship
            for target in ("arrival", "segment"):
                with self.subTest(target=target, relationship=relationship), self.assertRaises(ValueError):
                    case(target, value)

    def test_invalid_timestamp_types_are_rejected(self):
        for invalid in (True, float("nan"), "2026-11-02T10:00:00"):
            value = snapshot()
            value["source_updated_at"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                case("arrival", value)

    def test_duplicate_trip_identity_is_ambiguous(self):
        value = snapshot()
        value["trips"].append(deepcopy(value["trips"][0]))
        with self.assertRaises(ValueError):
            case("arrival", value)

    def test_input_is_not_mutated(self):
        value = snapshot()
        saved = deepcopy(value)
        case("segment", value)
        self.assertEqual(value, saved)


if __name__ == "__main__":
    unittest.main()
