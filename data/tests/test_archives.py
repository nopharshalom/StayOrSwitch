"""Safety, availability, sampling, and cache tests for source archive ingestion."""

import io
import json
import lzma
from pathlib import Path
import tarfile
import tempfile
import unittest

import httpx
from google.transit import gtfs_realtime_pb2

from history.archives import (ArchiveError, download_archive, iter_csv_rows,
                              iter_snapshots)


def protobuf(timestamp):
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    message.header.timestamp = timestamp
    return message.SerializeToString()


def write_archive(path, entries):
    with tarfile.open(path, "w:xz") as archive:
        for name, payload in entries:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def snapshot_name(feed, instant, suffix="abc"):
    return "nycsubway_" + feed + "_20261102T" + instant + "Z_" + suffix + ".gtfsrt"


class ArchiveReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "sample.tar.xz"

    def tearDown(self):
        self.temp.cleanup()

    def test_collector_time_is_distinct_from_source_time(self):
        write_archive(self.path, [(snapshot_name("G", "050000.250"), protobuf(10))])
        rows = list(iter_snapshots(self.path))
        self.assertEqual(rows[0]["captured_at"], 1793595600.25)
        self.assertEqual(rows[0]["source_updated_at"], 10)
        self.assertEqual(rows[0]["feed_id"], "g")
        self.assertEqual(rows[0]["capture_time_basis"], "ARCHIVE_FILENAME_DOWNLOAD_TIME")

    def test_sampling_is_per_feed_and_fixed_time_bucket(self):
        write_archive(self.path, [
            (snapshot_name("G", "050000.000"), protobuf(1)),
            (snapshot_name("G", "050030.000"), protobuf(2)),
            (snapshot_name("G", "050100.000"), protobuf(3)),
            (snapshot_name("ACE", "050000.000"), protobuf(4)),
        ])
        stats = {}
        rows = list(iter_snapshots(self.path, sample_seconds=60, stats=stats))
        self.assertEqual(sorted(row["source_updated_at"] for row in rows), [1, 3, 4])
        self.assertEqual(stats["selected_snapshots"], 3)
        self.assertEqual(stats["skipped_sampling"], 1)

    def test_conflicting_capture_is_excluded_before_yield(self):
        write_archive(self.path, [
            (snapshot_name("G", "050000.000", "one"), protobuf(1)),
            (snapshot_name("G", "050000.000", "two"), protobuf(2)),
            (snapshot_name("G", "050005.000"), protobuf(3)),
        ])
        stats = {}
        rows = list(iter_snapshots(self.path, stats=stats))
        self.assertEqual([row["source_updated_at"] for row in rows], [3])
        self.assertEqual(stats["conflicting_capture"], 1)

    def test_invalid_payload_does_not_hide_a_conflicting_tie(self):
        write_archive(self.path, [
            (snapshot_name("G", "050000.000", "one"), b"bad"),
            (snapshot_name("G", "050000.000", "two"), protobuf(2)),
        ])
        stats = {}
        self.assertEqual(list(iter_snapshots(self.path, stats=stats)), [])
        self.assertEqual(stats["conflicting_capture"], 1)

    def test_identical_capture_duplicates_collapse(self):
        payload = protobuf(1)
        write_archive(self.path, [
            (snapshot_name("G", "050000.000", "one"), payload),
            (snapshot_name("G", "050000.000", "two"), payload),
        ])
        stats = {}
        self.assertEqual(len(list(iter_snapshots(self.path, stats=stats))), 1)
        self.assertEqual(stats["duplicate_capture"], 1)

    def test_backwards_time_within_feed_is_rejected(self):
        write_archive(self.path, [
            (snapshot_name("G", "050030.000"), protobuf(2)),
            (snapshot_name("G", "050000.000"), protobuf(1)),
        ])
        with self.assertRaisesRegex(ArchiveError, "chronological"):
            list(iter_snapshots(self.path))

    def test_feed_filter_preserves_coverage_counts(self):
        write_archive(self.path, [
            (snapshot_name("G", "050000.000"), protobuf(1)),
            (snapshot_name("ACE", "050000.000"), protobuf(2)),
        ])
        stats = {}
        rows = list(iter_snapshots(self.path, feed_ids=["g"], stats=stats))
        self.assertEqual([row["feed_id"] for row in rows], ["g"])
        self.assertEqual(stats["feeds"]["ace"]["snapshot_members"], 1)
        self.assertEqual(stats["skipped_feed"], 1)

    def test_real_archive_alerts_feed_is_supported(self):
        write_archive(self.path, [
            (snapshot_name("alerts", "050000.000"), protobuf(1)),
            (snapshot_name("alerts", "050005.000"), protobuf(2)),
        ])
        rows = list(iter_snapshots(self.path, feed_ids=["subway-alerts"]))
        self.assertEqual(rows[0]["feed_id"], "subway-alerts")
        self.assertEqual(len(rows), 2)

    def test_capture_gap_metrics_precede_sampling_and_feed_filtering(self):
        write_archive(self.path, [
            (snapshot_name("G", "050000.000"), protobuf(1)),
            (snapshot_name("G", "050030.000"), protobuf(2)),
            (snapshot_name("G", "050200.000"), protobuf(3)),
            (snapshot_name("alerts", "050000.000"), protobuf(4)),
            (snapshot_name("alerts", "051000.000"), protobuf(5)),
        ])
        stats = {}
        list(iter_snapshots(self.path, feed_ids=["g"], sample_seconds=300, stats=stats))
        train = stats["feeds"]["g"]
        self.assertEqual(train["max_capture_gap_seconds"], 90)
        self.assertEqual(train["capture_gaps_over_60_seconds"], 1)
        self.assertEqual(train["cumulative_capture_gap_seconds_over_60"], 90)
        self.assertEqual(train["capture_gap_examples"][0]["gap_seconds"], 90)
        self.assertEqual(stats["feeds"]["subway-alerts"]["max_capture_gap_seconds"], 600)
        self.assertIn("not proven collection outages", stats["capture_gap_diagnostic"]["interpretation"])

    def test_capture_gap_examples_are_bounded(self):
        write_archive(self.path, [
            (snapshot_name("G", "05" + str(minute).zfill(2) + "00.000"), protobuf(minute))
            for minute in range(0, 30, 2)
        ])
        stats = {}
        list(iter_snapshots(self.path, stats=stats))
        self.assertEqual(stats["feeds"]["g"]["capture_gaps_over_60_seconds"], 14)
        self.assertEqual(len(stats["feeds"]["g"]["capture_gap_examples"]), 10)

    def test_csv_streams_only_requested_table(self):
        write_archive(self.path, [
            ("subwaydatanyc_2026-11-02_trips.csv", b"trip_uid,route_id\na,G\n"),
            ("subwaydatanyc_2026-11-02_stop_times.csv", b"trip_uid,stop_id\na,G21S\n"),
        ])
        self.assertEqual(list(iter_csv_rows(self.path)), [{"trip_uid": "a", "route_id": "G"}])
        self.assertEqual(list(iter_csv_rows(self.path, "stop_times")),
                         [{"trip_uid": "a", "stop_id": "G21S"}])

    def test_missing_and_duplicate_csv_tables_are_rejected(self):
        write_archive(self.path, [("readme.md", b"No CSV")])
        with self.assertRaisesRegex(ArchiveError, "missing"):
            list(iter_csv_rows(self.path))
        entries = [("subwaydatanyc_2026-11-02_trips.csv", b"trip_uid\na\n")] * 2
        write_archive(self.path, entries)
        with self.assertRaisesRegex(ArchiveError, "duplicate"):
            list(iter_csv_rows(self.path))

    def test_path_traversal_and_symbolic_links_are_rejected(self):
        write_archive(self.path, [("../outside", b"bad")])
        with self.assertRaisesRegex(ArchiveError, "Unsafe"):
            list(iter_snapshots(self.path))
        with tarfile.open(self.path, "w:xz") as archive:
            info = tarfile.TarInfo("link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            archive.addfile(info)
        with self.assertRaisesRegex(ArchiveError, "Unsafe"):
            list(iter_csv_rows(self.path))


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.payload = lzma.compress(b"sample archive bytes")

    def tearDown(self):
        self.temp.cleanup()

    def test_allowed_redirect_cache_verification_and_corruption_repair(self):
        calls = []

        def handler(request):
            calls.append(str(request.url))
            if request.url.host == "subwaydata.nyc":
                return httpx.Response(302, headers={"location": "https://data.subwaydata.nyc/file.tar.xz"})
            return httpx.Response(200, content=self.payload)

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            first = download_archive("2026-11-02", "csv", self.temp.name, client=client)
            second = download_archive("2026-11-02", "csv", self.temp.name, client=client)
            self.assertFalse(first["cache_verified"])
            self.assertTrue(second["cache_verified"])
            self.assertEqual(len(calls), 2)
            Path(first["path"]).write_bytes(b"corrupt")
            third = download_archive("2026-11-02", "csv", self.temp.name, client=client)
            self.assertEqual(third["sha256"], first["sha256"])
            self.assertEqual(len(calls), 4)

    def test_redirect_outside_source_hosts_is_not_requested(self):
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://example.com/archive"})

        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            with self.assertRaisesRegex(ArchiveError, "approved HTTPS"):
                download_archive("2026-11-02", "csv", self.temp.name, client=client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(list(Path(self.temp.name).glob("*.part")), [])

    def test_size_limit_and_non_archive_response_leave_no_completed_file(self):
        for body, max_bytes in [(self.payload, 5), (b"<html>not an archive</html>", 1024)]:
            with httpx.Client(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, content=body))) as client:
                with self.assertRaises(ArchiveError):
                    download_archive("2026-11-02", "csv", self.temp.name,
                                     client=client, max_bytes=max_bytes)
            self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_date_input_cannot_escape_download_directory(self):
        with self.assertRaises(ArchiveError):
            download_archive("../../secrets", "csv", self.temp.name)


if __name__ == "__main__":
    unittest.main()
