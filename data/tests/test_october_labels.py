"""Outcome identity, endpoint quality and receipt cutoff regression checks."""

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from data.october.labels import ReceiptIndex, build_labels, canonical_event_trip_id, source_trip_uid, timestamp


class OctoberLabelsTests(unittest.TestCase):
    def setUp(self):
        self.trip = {"id": "normalized", "trip_id": "060000_F..S", "route_id": "F",
                     "start_date": "20261005", "start_time": "10:00:00", "feed_id": "bdfm",
                     "observed_stop_ids": ["F09S", "A41S"]}
        self.uid = source_trip_uid(self.trip)
        self.base = datetime(2026, 10, 5, 14, tzinfo=timezone.utc).timestamp()
        self.journal_trip = {"trip_uid": self.uid, "trip_id": self.trip["trip_id"],
                             "route_id": "F", "num_schedule_changes": "0", "num_schedule_rewrites": "0"}
        self.stop = {"trip_uid": self.uid, "stop_id": "F09S", "arrival_time": str(self.base),
                     "departure_time": str(self.base + 20), "last_observed": str(self.base + 20),
                     "marked_past": str(self.base + 45)}
        self.receipts = {"bdfm": [(self.base + 50, self.base + 46)]}

    def build(self, trips=None, trip_rows=None, stop_rows=None, receipts=None):
        records = {"trips": [self.journal_trip] if trip_rows is None else trip_rows,
                   "stop_times": [self.stop] if stop_rows is None else stop_rows}
        with patch("data.october.labels._csv_rows", side_effect=lambda path, kind: iter(records[kind])):
            return build_labels({"normalized": self.trip} if trips is None else trips,
                                ["synthetic.csv.tar.xz"], self.receipts if receipts is None else receipts,
                                {"F09S", "A41S"})

    def test_uid_uses_utc_identifier_not_new_york_clock(self):
        expected = int(datetime(2026, 10, 5, 10, tzinfo=timezone.utc).timestamp())
        self.assertEqual(self.uid, str(expected) + "_F..S")
        november = dict(self.trip, start_date="20261101")
        expected = int(datetime(2026, 11, 1, 10, tzinfo=timezone.utc).timestamp())
        self.assertEqual(source_trip_uid(november), str(expected) + "_F..S")

    def test_uid_allows_over_midnight_source_offset(self):
        trip = dict(self.trip, trip_id="150000_F..S")
        expected = int(datetime(2026, 10, 6, 1, tzinfo=timezone.utc).timestamp())
        self.assertEqual(source_trip_uid(trip), str(expected) + "_F..S")
        self.assertIsNone(source_trip_uid(dict(trip, start_date="20260230")))

    def test_valid_label_retains_missing_other_endpoint(self):
        result, counts = self.build()
        good = result["normalized"]["F09S"]
        self.assertTrue(good["arrival_usable"])
        self.assertTrue(good["departure_usable"])
        self.assertEqual(good["available_at"], self.base + 45)
        self.assertEqual(good["confirmed_at"], self.base + 50)
        self.assertIn("MISSING_CSV_LABEL", result["normalized"]["A41S"]["quality_flags"])
        self.assertEqual(counts["endpoint_rows"], 2)

    def test_departure_failure_does_not_invalidate_arrival(self):
        invalid = dict(self.stop, departure_time=str(self.base - 1))
        result, _ = self.build(stop_rows=[invalid])
        label = result["normalized"]["F09S"]
        self.assertTrue(label["arrival_usable"])
        self.assertFalse(label["departure_usable"])
        self.assertIn("CSV_DEPARTURE_BEFORE_ARRIVAL", label["departure_quality_flags"])

    def test_changed_or_conflicting_trip_is_not_a_valid_outcome(self):
        changed = dict(self.journal_trip, num_schedule_changes="1")
        result, _ = self.build(trip_rows=[changed])
        self.assertIn("CSV_SCHEDULE_CHANGED", result["normalized"]["F09S"]["quality_flags"])
        result, counts = self.build(trip_rows=[self.journal_trip, changed])
        self.assertFalse(result["normalized"]["F09S"]["arrival_usable"])
        self.assertIn("AMBIGUOUS_CSV_LABEL", result["normalized"]["F09S"]["quality_flags"])
        self.assertEqual(counts["conflicting_journal_trips"], 1)

    def test_conflicting_endpoint_and_large_gap_are_visible(self):
        other = dict(self.stop, arrival_time=str(self.base - 10))
        result, _ = self.build(stop_rows=[self.stop, other])
        self.assertIn("AMBIGUOUS_CSV_LABEL", result["normalized"]["F09S"]["quality_flags"])
        result, _ = self.build(stop_rows=[dict(self.stop, marked_past=str(self.base + 500))])
        self.assertIn("LARGE_STOP_OBSERVATION_GAP", result["normalized"]["F09S"]["quality_flags"])

    def test_missing_receipt_stays_distinct_from_journal_quality(self):
        result, _ = self.build(receipts={})
        label = result["normalized"]["F09S"]
        self.assertTrue(label["arrival_usable"])
        self.assertIsNone(label["confirmed_at"])
        self.assertEqual(label["confirmation_status"], "UNVERIFIED")

    def test_start_time_aliases_share_one_canonical_event(self):
        other = dict(self.trip, id="other-alias", start_time="10:00:04")
        result, counts = self.build(trips={"normalized": self.trip, "other-alias": other})
        self.assertEqual(counts["ambiguous_source_uids"], 0)
        self.assertEqual(counts["aliased_source_uids"], 1)
        self.assertEqual(counts["extra_normalized_aliases"], 1)
        self.assertEqual(counts["canonical_service_runs"], 1)
        for identity in result:
            self.assertTrue(result[identity]["F09S"]["arrival_usable"])
            self.assertEqual(result[identity]["F09S"]["canonical_event_trip_id"], canonical_event_trip_id(self.trip))
            self.assertEqual(result[identity]["F09S"]["normalized_alias_count"], 2)

    def test_alias_jitter_does_not_override_journal_schedule_changes(self):
        other = dict(self.trip, id="other-alias", start_time="10:00:04")
        for key in ("num_schedule_changes", "num_schedule_rewrites"):
            result, _ = self.build(trips={"normalized": self.trip, "other-alias": other},
                                   trip_rows=[dict(self.journal_trip, **{key: "1"})])
            for identity in result:
                self.assertFalse(result[identity]["F09S"]["arrival_usable"])

    def test_different_core_services_cannot_share_one_journal_outcome(self):
        changes = ({"feed_id": "ace"}, {"route_id": "E"},
                   {"start_date": "20261004", "trip_id": "204000_F..S"})
        for change in changes:
            with self.subTest(change=change):
                other = dict(self.trip, id="other-service", **change)
                self.assertEqual(source_trip_uid(other), self.uid)
                result, counts = self.build(trips={"normalized": self.trip, "other-service": other})
                self.assertEqual(counts["ambiguous_source_uids"], 1)
                for identity in result:
                    self.assertFalse(result[identity]["F09S"]["arrival_usable"])
                    self.assertIn("AMBIGUOUS_NORMALIZED_TRIP_FOR_CSV_UID", result[identity]["F09S"]["quality_flags"])

    def test_explicit_direction_conflicts_invalidate_all_aliases(self):
        for field, first, second in (("direction_id", 0, 1), ("nyct_direction", "NORTH", "SOUTH")):
            a = dict(self.trip, **{field: first})
            b = dict(self.trip, id="other-alias", start_time="10:00:04", **{field: second})
            result, counts = self.build(trips={"normalized": a, "other-alias": b})
            self.assertEqual(counts["ambiguous_source_uids"], 1)
            self.assertTrue(all(not item["F09S"]["arrival_usable"] for item in result.values()))

    def test_raw_direction_is_checked_without_assuming_gtfs_cardinal_mapping(self):
        result, _ = self.build(trips={"normalized": dict(self.trip, nyct_direction="NORTH")})
        self.assertIn("RAW_TRIP_DIRECTION_MISMATCH", result["normalized"]["F09S"]["quality_flags"])
        for gtfs_direction in (0, 1):
            result, _ = self.build(trips={"normalized": dict(self.trip, direction_id=gtfs_direction, nyct_direction="SOUTH")})
            self.assertTrue(result["normalized"]["F09S"]["arrival_usable"])

    def test_observed_express_route_aliases_preserve_actual_service_identity(self):
        for route, raw_route in (("FX", "F"), ("7X", "7")):
            trip = dict(self.trip, route_id=route, trip_id="060000_" + raw_route + "..S")
            uid = source_trip_uid(trip)
            journal = dict(self.journal_trip, route_id=route, trip_id=trip["trip_id"], trip_uid=uid)
            result, _ = self.build(trips={"normalized": trip}, trip_rows=[journal],
                                   stop_rows=[dict(self.stop, trip_uid=uid)])
            self.assertTrue(result["normalized"]["F09S"]["arrival_usable"])
            self.assertNotEqual(canonical_event_trip_id(trip), canonical_event_trip_id(dict(trip, route_id=raw_route)))
        bad = dict(self.trip, route_id="E")
        result, _ = self.build(trips={"normalized": bad}, trip_rows=[dict(self.journal_trip, route_id="E")])
        self.assertIn("RAW_TRIP_ROUTE_MISMATCH", result["normalized"]["F09S"]["quality_flags"])

    def test_identity_conflict_in_one_alias_invalidates_shared_journal(self):
        other = dict(self.trip, id="other-alias", start_time="10:00:04", identity_conflict=True)
        result, _ = self.build(trips={"normalized": self.trip, "other-alias": other})
        self.assertTrue(all(not item["F09S"]["arrival_usable"] for item in result.values()))

    def test_unscheduled_identity_cannot_claim_scheduled_journal_outcome(self):
        result, _ = self.build(trips={"normalized": dict(self.trip, schedule_relationship="ADDED")})
        self.assertIn("AMBIGUOUS_UNSCHEDULED_TRIP_IDENTITY", result["normalized"]["F09S"]["quality_flags"])

    def test_unscheduled_alias_invalidates_shared_scheduled_identity(self):
        for relationship in ("ADDED", "UNSCHEDULED", "DUPLICATED"):
            other = dict(self.trip, id="other-alias", start_time="10:00:04", schedule_relationship=relationship)
            result, counts = self.build(trips={"normalized": self.trip, "other-alias": other})
            self.assertEqual(counts["ambiguous_source_uids"], 1)
            self.assertTrue(all(not item["F09S"]["arrival_usable"] for item in result.values()))

    def test_canonical_identity_uses_only_observation_identity(self):
        expected = canonical_event_trip_id(self.trip)
        self.assertEqual(canonical_event_trip_id(dict(self.trip, start_time="11:00:00", arrival_at=0)), expected)
        self.assertNotEqual(canonical_event_trip_id(dict(self.trip, start_date="20261006")), expected)
        self.assertIsNone(canonical_event_trip_id(dict(self.trip, feed_id=None)))

    def test_prebuilt_receipt_index_preserves_strict_confirmation_contract(self):
        result, _ = self.build(receipts=ReceiptIndex(self.receipts))
        self.assertEqual(result["normalized"]["F09S"]["confirmed_at"], self.base + 50)

    def test_receipt_index_handles_nonmonotonic_sources_and_future_sources(self):
        index = ReceiptIndex({"g": [(100, 90), (110, 80), (120, 115), (130, 200), (140, 135)]})
        self.assertEqual(index.confirm("g", 85), 100)
        self.assertEqual(index.confirm("g", 95), 120)
        self.assertEqual(index.confirm("g", 125), 140)
        self.assertIsNone(index.confirm("g", 140))
        self.assertIsNone(index.confirm("unknown", 50))

    def test_conflicting_equal_time_receipts_are_not_confirmation(self):
        index = ReceiptIndex({"g": [(100, 95), (100, 90), (120, 110)]})
        self.assertEqual(index.confirm("g", 95), 120)

    def test_equal_source_timestamp_does_not_confirm_later_journal_state(self):
        index = ReceiptIndex({"g": [(100, 95), (110, 100)]})
        self.assertEqual(index.confirm("g", 95), 110)

    def test_timestamp_does_not_guess_timezone_or_accept_boolean(self):
        for value in (True, float("nan"), -1, "2026-10-05T10:00:00"):
            with self.assertRaises(ValueError):
                timestamp(value)


if __name__ == "__main__":
    unittest.main()
