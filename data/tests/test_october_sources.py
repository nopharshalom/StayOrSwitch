"""Source-reader boundary tests using small synthetic archives."""

import io
import json
import lzma
from pathlib import Path
import tarfile
import tempfile
import unittest

from google.transit import gtfs_realtime_pb2 as gtfs

from data.october.prepare import _merge_trip, normalize, raw_receipt, DailyReceiptIndex
from data.october.sources import (checked_url, epoch, iter_csv_rows,
                                  iter_raw_snapshots, read_snapshots, write_gzip_json, read_labels)


def payload(stamp=1791158400):
    feed = gtfs.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = stamp
    feed.header.incrementality = gtfs.FeedHeader.FULL_DATASET
    return feed.SerializeToString()


class SourcesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, entries):
        path = self.root / "test.tar.xz"
        with lzma.open(path, "wb") as compressed, tarfile.open(fileobj=compressed, mode="w|") as archive:
            for name, data in entries:
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        return path

    def test_timestamp_numeric_strings_and_explicit_zone(self):
        self.assertEqual(epoch("123"), 123)
        self.assertEqual(epoch("1970-01-01T00:02:03Z"), 123)
        for value in (True, -1, float("nan"), float("inf"), "2026-10-01T00:00:00"):
            with self.assertRaises(ValueError):
                epoch(value)

    def test_download_url_scope(self):
        checked_url("https://subwaydata.nyc/data/test.tar.xz")
        for value in ("http://subwaydata.nyc/test", "https://example.com/test", "https://x@subwaydata.nyc/test"):
            with self.assertRaises(ValueError):
                checked_url(value)

    def test_first_train_bucket_all_alert_captures(self):
        archive = self.archive([
            ("nycsubway_G_20261005T000000Z_a.gtfsrt", payload()),
            ("nycsubway_G_20261005T000030Z_b.gtfsrt", payload()),
            ("nycsubway_G_20261005T000100Z_c.gtfsrt", payload()),
            ("nycsubway_alerts_20261005T000000Z_d.gtfsrt", payload()),
            ("nycsubway_alerts_20261005T000030Z_e.gtfsrt", payload()),
        ])
        rows = list(iter_raw_snapshots(archive, ["g"]))
        self.assertEqual([r["feed_id"] for r in rows].count("g"), 2)
        self.assertEqual([r["feed_id"] for r in rows].count("subway-alerts"), 2)

    def test_conflicting_equal_capture_is_retained_invalid(self):
        archive = self.archive([
            ("nycsubway_G_20261005T000000Z_a.gtfsrt", payload()),
            ("nycsubway_G_20261005T000000Z_b.gtfsrt", payload(1791158401)),
        ])
        row = list(iter_raw_snapshots(archive, ["g"]))[0]
        self.assertEqual(row["invalid_reason"], "CONFLICTING_EQUAL_TIME_PAYLOADS")
        result = normalize(row, {"route_ids": ["G"], "train_max_age_seconds": 180, "alerts_max_age_seconds": 300})
        self.assertEqual(result["status"], "MISSING")
        self.assertFalse(result["trips"])

    def test_all_raw_train_receipts_precede_snapshot_sampling(self):
        archive = self.archive([
            ("nycsubway_G_20261005T000000Z_a.gtfsrt", payload(1791158400)),
            ("nycsubway_G_20261005T000030Z_b.gtfsrt", payload(1791158430)),
            ("nycsubway_G_20261005T000100Z_c.gtfsrt", payload(1791158460)),
        ])
        receipts = []
        rows = list(iter_raw_snapshots(archive, ["g"], receipt_callback=lambda row: receipts.append(raw_receipt(row))))
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["source_updated_at"] for row in receipts], [1791158400, 1791158430, 1791158460])

    def test_conflicting_unsampled_receipts_cannot_confirm_an_outcome(self):
        archive = self.archive([
            ("nycsubway_G_20261005T000000Z_a.gtfsrt", payload()),
            ("nycsubway_G_20261005T000030Z_b.gtfsrt", payload(1791158430)),
            ("nycsubway_G_20261005T000030Z_c.gtfsrt", payload(1791158431)),
        ])
        receipts = []
        rows = list(iter_raw_snapshots(archive, ["g"], receipt_callback=lambda row: receipts.append(raw_receipt(row))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["invalid_reason"], "CONFLICTING_EQUAL_TIME_PAYLOADS")
        self.assertEqual(len(receipts), 2)
        self.assertEqual(receipts[-1]["status"], "MISSING")
        self.assertIsNone(receipts[-1]["source_updated_at"])

    def test_unsampled_payload_failure_and_recovery_replace_prior_snapshot(self):
        differential = gtfs.FeedMessage()
        differential.ParseFromString(payload())
        differential.header.incrementality = gtfs.FeedHeader.DIFFERENTIAL
        for bad in (b"malformed", differential.SerializeToString()):
            with self.subTest(payload=bad):
                archive = self.archive([
                    ("nycsubway_G_20261005T000000Z_a.gtfsrt", payload()),
                    ("nycsubway_G_20261005T000030Z_b.gtfsrt", bad),
                    ("nycsubway_G_20261005T000045Z_c.gtfsrt", payload()),
                ])
                rows = list(iter_raw_snapshots(archive, ["g"], receipt_callback=raw_receipt))
                self.assertEqual(len(rows), 3)
                self.assertTrue(rows[1]["invalid_reason"])
                self.assertIsNone(rows[2]["invalid_reason"])

    def test_unsampled_future_and_stale_source_replace_prior_success(self):
        for source, state in ((1791158431, "MISSING"), (1791158249, "STALE")):
            with self.subTest(state=state):
                archive = self.archive([
                    ("nycsubway_G_20261005T000000Z_a.gtfsrt", payload()),
                    ("nycsubway_G_20261005T000030Z_b.gtfsrt", payload(source)),
                    ("nycsubway_G_20261005T000045Z_c.gtfsrt", payload(1791158445)),
                ])
                rows = list(iter_raw_snapshots(archive, ["g"], receipt_callback=raw_receipt))
                self.assertEqual(len(rows), 3)
                self.assertEqual(rows[1]["receipt_freshness"], state)
                self.assertEqual(rows[-1]["receipt_freshness"], "FRESH")

    def test_bad_payload_remains_missing(self):
        row = {"feed_id": "g", "captured_at": 1791158400, "payload": b"broken", "sha256": "x",
               "archive": "x", "archive_member": "x", "invalid_reason": None}
        result = normalize(row, {"route_ids": ["G"], "train_max_age_seconds": 180, "alerts_max_age_seconds": 300})
        self.assertEqual(result["status"], "MISSING")

    def test_unsafe_member_rejected(self):
        archive = self.archive([("../escape", b"x")])
        with self.assertRaises(ValueError):
            list(iter_raw_snapshots(archive, ["g"]))

    def test_out_of_order_capture_rejected(self):
        archive = self.archive([
            ("nycsubway_G_20261005T000100Z_a.gtfsrt", payload()),
            ("nycsubway_G_20261005T000000Z_b.gtfsrt", payload()),
        ])
        with self.assertRaises(ValueError):
            list(iter_raw_snapshots(archive, ["g"]))

    def test_csv_reader_and_duplicate_table(self):
        body = b"trip_uid,route_id\n123_G,G\n"
        archive = self.archive([("day_trips.csv", body)])
        self.assertEqual(list(iter_csv_rows(archive, "trips"))[0]["route_id"], "G")
        archive = self.archive([("one_trips.csv", body), ("two_trips.csv", body)])
        with self.assertRaises(ValueError):
            list(iter_csv_rows(archive, "trips"))

    def test_observed_endpoints_union_and_identity_conflict(self):
        values = {}
        trip = {"id": "x", "trip_id": "000100_G", "route_id": "G", "feed_id": "g",
                "start_date": "20261005", "start_time": "00:01:00", "stop_updates": [{"stop_id": "G22S"}]}
        _merge_trip(values, trip, {"G22S", "A42S"})
        changed = dict(trip, stop_updates=[{"stop_id": "A42S"}])
        _merge_trip(values, changed, {"G22S", "A42S"})
        self.assertEqual(values["x"]["observed_stop_ids"], {"G22S", "A42S"})
        _merge_trip(values, dict(changed, route_id="F"), {"G22S", "A42S"})
        self.assertTrue(values["x"]["identity_conflict"])

    def test_gzip_artifact_roundtrip_is_deterministic(self):
        path = self.root / "labels.json.gz"
        write_gzip_json(path, {"x": [1, 2]})
        original = path.read_bytes()
        self.assertEqual(read_labels(path), {"x": [1, 2]})
        write_gzip_json(path, {"x": [1, 2]})
        self.assertEqual(original, path.read_bytes())

    def test_direction_missingness_and_conflicts_are_distinct(self):
        values = {}
        trip = {"id": "x", "trip_id": "000100_G..S", "route_id": "G", "feed_id": "g",
                "start_date": "20261005", "start_time": "00:01:00", "stop_updates": []}
        _merge_trip(values, trip, set())
        _merge_trip(values, dict(trip, nyct_direction="SOUTH"), set())
        self.assertFalse(values["x"]["identity_conflict"])
        self.assertEqual(values["x"]["nyct_direction"], "SOUTH")
        _merge_trip(values, dict(trip, nyct_direction="NORTH"), set())
        self.assertTrue(values["x"]["identity_conflict"])

    def test_lazy_receipt_index_crosses_midnight_with_strict_source_order(self):
        available = epoch("2026-10-05T03:59:59Z")
        reports = []
        for day, receipt in (("2026-10-04", [available, available]),
                             ("2026-10-05", [available + 2, available + 1])):
            path = self.root / (day + ".json.gz")
            write_gzip_json(path, {"g": [receipt]})
            reports.append({"date": day, "outputs": {"receipts": {"path": str(path)}}})
        index = DailyReceiptIndex(reports, "America/New_York")
        self.assertEqual(index.confirm("g", available), available + 2)
        self.assertIsNone(index.confirm("g", available + 10))


if __name__ == "__main__":
    unittest.main()
