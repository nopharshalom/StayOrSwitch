"""Protect immutable endpoints and full identity checks in the D16 supplement."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.october.sources import write_gzip_json
from data.supplemental_endpoints import (build_supplemental_labels, collect_observed_stop,
    mark_supplemental_observations, merge_endpoint_labels, merge_trip_inventory)


def trip(raw="010000_F..S", service="20261026", **extra):
    return dict({"trip_id": raw, "route_id": "F", "feed_id": "bdfm",
        "start_date": service, "start_time": "01:40:00", "direction_id": None,
        "nyct_direction": "SOUTH", "schedule_relationship": "SCHEDULED",
        "identity_conflict": False, "observed_stop_ids": ["F09S", "A41S"]}, **extra)


class SupplementalEndpointTests(unittest.TestCase):
    def test_merge_keeps_old_endpoints_and_inputs_immutable(self):
        original = {"train": {"F09S": {"arrival_at": 123}}}
        supplement = {"train": {"D16S": {"arrival_at": 456}}}
        before = deepcopy((original, supplement))
        merged = merge_endpoint_labels(original, supplement, "D16S")
        self.assertEqual(merged["train"]["F09S"], original["train"]["F09S"])
        self.assertEqual((original, supplement), before)
        merged["train"]["F09S"]["arrival_at"] = 789
        self.assertEqual(original["train"]["F09S"]["arrival_at"], 123)

    def test_merge_rejects_existing_endpoint_even_if_identical(self):
        value = {"train": {"D16S": {"arrival_at": 456}}}
        with self.assertRaises(ValueError):
            merge_endpoint_labels(value, value, "D16S")

    def test_merge_rejects_unrequested_endpoint(self):
        with self.assertRaises(ValueError):
            merge_endpoint_labels({}, {"train": {"D16S": {}, "A41S": {}}}, "D16S")

    def test_only_observed_supplemental_stop_is_added(self):
        trips = {"seen": trip(), "unseen": trip(raw="020000_F..S")}
        mark_supplemental_observations(trips, {"seen"}, "D16S")
        self.assertEqual(trips["seen"]["observed_stop_ids"], {"D16S"})
        self.assertEqual(trips["unseen"]["observed_stop_ids"], set())
        self.assertEqual(trips["unseen"]["trip_id"], "020000_F..S")

    def test_missing_original_identity_fails_closed(self):
        with self.assertRaises(ValueError):
            mark_supplemental_observations({}, {"unexpected"}, "D16S")

    def test_observed_stop_collection_uses_input_updates(self):
        records = [{"trips": [
            {"id": "seen", "stop_updates": [{"stop_id": "D16S"}]},
            {"id": "other", "stop_updates": [{"stop_id": "D16N"}]},
            {"stop_updates": [{"stop_id": "D16S"}]},
        ]}]
        with patch("data.supplemental_endpoints.read_snapshots", return_value=iter(records)):
            self.assertEqual(collect_observed_stop("unused", "D16S"), {"seen"})

    def test_full_month_merge_detects_cross_service_date_uid_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_gzip_json(root / "a.gz", {"previous": trip(raw="144000_F..S", service="20261025")})
            write_gzip_json(root / "b.gz", {"current": trip(raw="000000_F..S", service="20261026")})
            days = [{"date": "2026-10-25", "outputs": {"trips": {"path": "a.gz"}}},
                    {"date": "2026-10-26", "outputs": {"trips": {"path": "b.gz"}}}]
            merged, observed = merge_trip_inventory(days, root)
            self.assertTrue(merged["previous"]["identity_conflict"])
            self.assertTrue(merged["current"]["identity_conflict"])
            self.assertEqual(observed["current"], ["2026-10-26"])

    def test_merge_preserves_direction_conflict_across_observation_days(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_gzip_json(root / "a.gz", {"same": trip()})
            write_gzip_json(root / "b.gz", {"same": trip(nyct_direction="NORTH")})
            days = [{"date": "2026-10-25", "outputs": {"trips": {"path": "a.gz"}}},
                    {"date": "2026-10-26", "outputs": {"trips": {"path": "b.gz"}}}]
            merged, _ = merge_trip_inventory(days, root)
            self.assertTrue(merged["same"]["identity_conflict"])

    def test_unchanged_builder_receives_all_same_date_identities_and_boundary_journals(self):
        trips = {"seen": trip(observed_stop_ids={"D16S"}),
                 "not_seen": trip(raw="020000_F..S", observed_stop_ids=set()),
                 "other_date": trip(service="20261020", observed_stop_ids=set())}
        identity_days = {"seen": ["2026-10-26", "2026-10-27"],
                         "not_seen": ["2026-10-26"], "other_date": ["2026-10-20"]}
        archives = [{"kind": "csv", "archive_date": "2026-10-" + day, "path": day}
                    for day in ("24", "25", "26", "27", "28", "29")]
        with patch("data.supplemental_endpoints.DailyReceiptIndex", return_value="receipt_index"), \
                patch("data.supplemental_endpoints.build_labels", return_value=({"seen": {"D16S": {}}}, {})) as builder:
            result, _, used = build_supplemental_labels(trips, identity_days, [], archives,
                                                       "America/New_York", "D16S")
        self.assertEqual(builder.call_count, 1)
        subset, paths, receipts, stops = builder.call_args.args
        self.assertEqual(set(subset), {"seen", "not_seen"})
        self.assertEqual(paths, ["25", "26", "27", "28"])
        self.assertEqual(receipts, "receipt_index")
        self.assertEqual(stops, {"D16S"})
        self.assertEqual(result, {"seen": {"D16S": {}}})
        self.assertEqual(len(used), 4)


if __name__ == "__main__":
    unittest.main()
