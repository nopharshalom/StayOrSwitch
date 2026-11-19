"""Replay cutoff, missing evidence, identity, and outcome isolation checks."""

import copy
import csv
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from google.transit import gtfs_realtime_pb2 as gtfs

from data.corridor_replay.extract import collect_labels, extract_snapshots
from data.history.archives import sha256_file
from data.history.features import epoch, source_trip_uid


BASE = epoch("2026-11-12T12:00:00Z")


def archive(path, entries):
    with tarfile.open(path, "w:xz") as target:
        for name, payload in entries:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            target.addfile(info, io.BytesIO(payload))


def name(feed, second, suffix="one"):
    return "nycsubway_{}_20261112T1200{:02d}Z_{}.gtfsrt".format(feed, second, suffix)


def payload(offset=0):
    message = gtfs.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    message.header.timestamp = int(BASE + offset)
    entity = message.entity.add()
    entity.id = "test-trip"
    update = entity.trip_update
    update.trip.trip_id = "043000_G..S"
    update.trip.route_id = "G"
    update.trip.start_date = "20261112"
    update.timestamp = int(BASE + offset)
    for stop_id, horizon in (("G22S", 600), ("A42S", 3000)):
        stop = update.stop_time_update.add()
        stop.stop_id = stop_id
        stop.arrival.time = int(BASE + horizon + offset)
        stop.departure.time = int(BASE + horizon + 20 + offset)
    return message.SerializeToString()


def table(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


class ReplayDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "archive.tar.xz"
        self.cases = [{"id": "case", "decision_at": BASE + 15}]

    def tearDown(self):
        self.temp.cleanup()

    def snapshots(self, entries):
        archive(self.path, entries)
        result = extract_snapshots(self.path, self.cases, ["g"])
        return {row["feed_id"]: row for row in result["snapshots"]["case"]}

    def test_latest_asof_capture_retains_long_horizon_without_future_capture(self):
        rows = self.snapshots([(name("G", 0), payload()), (name("G", 10), payload(10)),
                               (name("G", 20), payload(20))])
        self.assertEqual(rows["g"]["archive_provenance"]["captured_at"], "2026-11-12T12:00:10Z")
        self.assertEqual(rows["g"]["trips"][0]["stop_updates"][-1]["arrival_time"], BASE + 3010)
        self.assertEqual(rows["g"]["replay_freshness"], "FRESH")
        self.assertEqual(rows["subway-alerts"]["replay_freshness"], "MISSING")

    def test_latest_invalid_or_conflicting_capture_never_revives_prior_success(self):
        for last in ([(name("G", 10), b"invalid")],
                     [(name("G", 10, "one"), payload(10)),
                      (name("G", 10, "two"), payload(11))]):
            rows = self.snapshots([(name("G", 0), payload())] + last)
            self.assertEqual(rows["g"]["replay_freshness"], "MISSING")
            self.assertEqual(rows["g"]["trips"], [])

    def test_old_alert_is_preserved_as_stale_without_refreshing_capture(self):
        self.cases = [{"id": "case", "decision_at": BASE + 600}]
        rows = self.snapshots([(name("alerts", 0), payload())])
        self.assertEqual(rows["subway-alerts"]["replay_freshness"], "STALE")
        self.assertEqual(rows["subway-alerts"]["fetched_at"], "2026-11-12T12:00:00Z")
        self.assertEqual(rows["g"]["replay_freshness"], "MISSING")

    def label_result(self, *, invalid_departure=False, conflicting_identity=False):
        snapshots = list(self.snapshots([(name("G", 0), payload())]).values())
        trip = snapshots[0]["trips"][0]
        uid = source_trip_uid(trip)
        trip_rows = [{"trip_uid": uid, "trip_id": trip["trip_id"], "route_id": "G",
                      "num_schedule_changes": "0", "num_schedule_rewrites": "0"}]
        stops = [{"trip_uid": uid, "stop_id": stop, "arrival_time": str(int(BASE + horizon)),
                  "departure_time": "invalid" if invalid_departure else str(int(BASE + horizon + 20)),
                  "last_observed": str(int(BASE + horizon + 25)), "marked_past": str(int(BASE + horizon + 30))}
                 for stop, horizon in (("G22S", 600), ("A42S", 3000))]
        archive(self.path, [("subwaydatanyc_2026-11-12_trips.csv", table(trip_rows)),
                            ("subwaydatanyc_2026-11-12_stop_times.csv", table(stops))])
        later = copy.deepcopy(snapshots[0])
        later["trips"][0]["stop_updates"] = later["trips"][0]["stop_updates"][1:]
        if conflicting_identity:
            later["trips"][0]["route_id"] = "F"
        snapshots.append(later)
        original = copy.deepcopy(snapshots)
        item = {"path": self.path.name, "sha256": sha256_file(self.path),
                "bytes": self.path.stat().st_size, "archive_date": "2026-11-12"}
        result = collect_labels([item], snapshots, {"G22S", "A42S"}, root=self.root)
        self.assertEqual(snapshots, original)
        return result["labels"][trip["id"]]

    def test_later_snapshot_cannot_remove_earlier_boarding_outcome(self):
        labels = self.label_result()
        self.assertTrue(labels["G22S"]["departure_usable"])
        self.assertTrue(labels["A42S"]["arrival_usable"])
        self.assertFalse(labels["A42S"]["physical_ground_truth"])

    def test_departure_parse_error_does_not_invalidate_valid_arrival(self):
        labels = self.label_result(invalid_departure=True)
        self.assertFalse(labels["G22S"]["departure_usable"])
        self.assertTrue(labels["A42S"]["arrival_usable"])

    def test_conflicting_identity_is_not_joined_as_valid_outcome(self):
        labels = self.label_result(conflicting_identity=True)
        self.assertFalse(labels["A42S"]["arrival_usable"])
        self.assertIn("CONFLICTING_REPLAY_TRIP_IDENTITY", labels["A42S"]["quality_flags"])


if __name__ == "__main__":
    unittest.main()
