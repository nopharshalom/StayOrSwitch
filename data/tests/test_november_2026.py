"""Boundary and isolation checks for the November follow-up source pipeline."""

from contextlib import redirect_stdout
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2 as gtfs

from data import november_2026 as source
from data.october.labels import source_trip_uid
from data.october.sources import iter_raw_snapshots


ROOT = Path(__file__).resolve().parents[2]


def fixture_config():
    original = json.loads((ROOT / "data/config/incremental-extra-projection.json").read_text())
    return source.configuration(original)


def archive_metadata(day, kind):
    return {"archive_date": day, "kind": kind, "bytes": 42,
            "path": "/unused/" + day + "-" + kind, "sha256": "test"}


class NovemberSourceTests(unittest.TestCase):
    def test_projection_covers_all_five_corridors_and_route_aliases(self):
        config = fixture_config()
        pairs = {(leg["feed_id"], route_id, leg["from_stop_id"], leg["to_stop_id"])
                 for route in config["routes"] for leg in route["legs"]
                 for route_id in leg.get("route_ids", [leg["route_id"]])}
        corridor_ids = set()
        for filename in ("google-corridors.json", "incremental-extra-corridors.json"):
            document = json.loads((ROOT / "data/config" / filename).read_text())
            for corridor in document["corridors"]:
                corridor_ids.add(corridor["id"])
                for route in corridor["routes"]:
                    for leg in route["legs"]:
                        self.assertIn(leg["feed_id"], config["feed_ids"])
                        for stop in (leg["from_stop_id"], leg["to_stop_id"]):
                            self.assertIn(stop, config["stop_ids"])
                        for route_id in leg.get("route_ids", [leg["route_id"]]):
                            self.assertIn(route_id, config["route_ids"])
                            self.assertIn((leg["feed_id"], route_id, leg["from_stop_id"],
                                           leg["to_stop_id"]), pairs)
        self.assertEqual(len(corridor_ids), 5)

    def test_configuration_does_not_mutate_previous_projection(self):
        original = json.loads((ROOT / "data/config/incremental-extra-projection.json").read_text())
        before = json.dumps(original, sort_keys=True)
        configured = source.configuration(original)
        configured["routes"][0]["legs"][0]["to_stop_id"] = "CHANGED"
        self.assertEqual(json.dumps(original, sort_keys=True), before)

    def test_required_jobs_include_all_november_dates_and_carry_boundaries(self):
        jobs = source.required_jobs(fixture_config())
        self.assertEqual(len(jobs), len(set(jobs)))
        for day in range(1, 20):
            for kind in ("csv", "gtfsrt"):
                self.assertIn(("2026-11-%02d" % day, kind), jobs)
        self.assertIn(("2026-10-31", "gtfsrt"), jobs)
        self.assertIn(("2026-10-31", "csv"), jobs)
        self.assertIn(("2026-10-30", "csv"), jobs)
        self.assertNotIn(("2026-11-20", "csv"), jobs)

    def test_missing_optional_boundary_does_not_hide_requested_date_coverage(self):
        def download(day, kind, *args, **kwargs):
            if day == "2026-11-20":
                raise FileNotFoundError("Following day not published")
            return archive_metadata(day, kind)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(source, "ACQUISITION", Path(folder) / "acquisition.json"), \
                patch.object(source, "cached_original", return_value=None), \
                patch.object(source, "download_archive", side_effect=download), \
                redirect_stdout(io.StringIO()):
            result = source.acquire(fixture_config(), workers=2)
        self.assertEqual(result["stage"], "ACQUIRED")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["optional_following_boundary"]["status"], "UNAVAILABLE")
        self.assertEqual({(row["archive_date"], row["kind"]) for row in result["archives"]},
                         set(source.required_jobs(fixture_config())))

    def test_missing_required_archive_is_recorded_and_blocks_completion(self):
        def download(day, kind, *args, **kwargs):
            if (day, kind) == ("2026-11-19", "gtfsrt"):
                raise FileNotFoundError("Required archive missing")
            return archive_metadata(day, kind)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "acquisition.json"
            with patch.object(source, "ACQUISITION", destination), \
                    patch.object(source, "cached_original", return_value=None), \
                    patch.object(source, "download_archive", side_effect=download), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    source.acquire(fixture_config(), workers=2)
            result = json.loads(destination.read_text())
        self.assertEqual(result["stage"], "INCOMPLETE")
        self.assertEqual([(row["date"], row["kind"]) for row in result["errors"]],
                         [("2026-11-19", "gtfsrt")])

    def test_reused_archive_is_hash_verified_without_rewriting_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "original.tar.xz"
            archive.write_bytes(b"original evidence")
            original_bytes = archive.read_bytes()
            manifest = root / "data/manifests/october-acquisition.json"
            manifest.parent.mkdir(parents=True)
            metadata = dict(archive_metadata("2026-11-01", "csv"),
                            path=str(archive), bytes=len(original_bytes),
                            sha256=hashlib.sha256(original_bytes).hexdigest())
            manifest.write_text(json.dumps({"archives": [metadata]}))
            manifest_bytes = manifest.read_bytes()
            with patch.object(source, "ROOT", root):
                result = source.cached_original("2026-11-01", "csv")
                self.assertTrue(result["reused_existing_raw_archive"])
                self.assertEqual(result["path"], str(archive))
                self.assertEqual(archive.read_bytes(), original_bytes)
                self.assertEqual(manifest.read_bytes(), manifest_bytes)
                archive.write_bytes(b"changed evidence!")
                self.assertIsNone(source.cached_original("2026-11-01", "csv"))

    def test_november_output_paths_cannot_overwrite_october_artifacts(self):
        for name in ("CONFIG", "OUTPUT", "RAW", "ACQUISITION", "MANIFEST", "REPORT"):
            path = getattr(source, name)
            self.assertIn("november-2026", str(path))
            self.assertNotIn("/october/", str(path))

    def test_fall_back_hour_keeps_two_distinct_raw_captures(self):
        timestamps = ("20261101T053000Z", "20261101T063000Z")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dst.tar.xz"
            with tarfile.open(path, "w:xz") as archive:
                for text in timestamps:
                    captured = datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(
                        tzinfo=ZoneInfo("UTC")).timestamp()
                    feed = gtfs.FeedMessage()
                    feed.header.gtfs_realtime_version = "2.0"
                    feed.header.timestamp = int(captured)
                    payload = feed.SerializeToString()
                    member = tarfile.TarInfo("nycsubway_ACE_" + text + "_test.gtfsrt")
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
            records = list(iter_raw_snapshots(path, ["ace"], 60))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]["captured_at"] - records[0]["captured_at"], 3600)
        local = [datetime.fromtimestamp(row["captured_at"], ZoneInfo("America/New_York"))
                 for row in records]
        self.assertEqual([value.strftime("%Y-%m-%d %H:%M") for value in local],
                         ["2026-11-01 01:30", "2026-11-01 01:30"])
        self.assertNotEqual(local[0].utcoffset(), local[1].utcoffset())

    def test_november_first_civil_day_has_twenty_five_hours(self):
        zone = ZoneInfo("America/New_York")
        first = datetime(2026, 11, 1, tzinfo=zone).timestamp()
        following = datetime(2026, 11, 2, tzinfo=zone).timestamp()
        self.assertEqual(following - first, 25 * 3600)

    def test_publisher_uid_stays_utc_based_during_dst_transition(self):
        trip = {"start_date": "20261101", "trip_id": "009000_F..S"}
        expected = int(datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("UTC")).timestamp())
        self.assertEqual(source_trip_uid(trip), str(expected) + "_F..S")


if __name__ == "__main__":
    unittest.main()
