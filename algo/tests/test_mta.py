"""Synthetic ingestion tests for missing observations, feed replacement, and time cutoffs."""

import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from zipfile import ZipFile

from google.transit import gtfs_realtime_pb2 as gtfs
from stayorswitch import mta


STAMP = 1795118400
FETCHED = datetime.fromtimestamp(STAMP + 10, timezone.utc).isoformat()
CUTOFF = datetime.fromtimestamp(STAMP + 20, timezone.utc).isoformat()


def make_feed(service_date="20261119", trip_id="120000_F..S01R"):
    feed = gtfs.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = STAMP
    entity = feed.entity.add(id="synthetic-train")
    entity.trip_update.trip.trip_id = trip_id
    entity.trip_update.trip.route_id = "F"
    if service_date:
        entity.trip_update.trip.start_date = service_date
    return feed, entity.trip_update


def parse(feed):
    return mta.parse_train_feed(feed.SerializeToString(), "bdfm", FETCHED)


class TrainFeedTests(unittest.TestCase):
    def test_missing_event_times_are_not_zero(self):
        feed, update = make_feed()
        stop = update.stop_time_update.add(stop_id="F01S")
        stop.arrival.delay = 90
        stop.departure.time = STAMP + 100
        snapshot = parse(feed)
        row = snapshot["trips"][0]["stop_updates"][0]
        self.assertIsNone(row["arrival_time"])
        self.assertEqual(row["departure_time"], STAMP + 100)
        self.assertIsNone(row["stop_sequence"])
        self.assertIsNone(snapshot["trips"][0]["direction_id"])

    def test_service_date_is_part_of_trip_identity(self):
        feed, _ = make_feed()
        second, _ = make_feed("20261120")
        self.assertNotEqual(parse(feed)["trips"][0]["id"], parse(second)["trips"][0]["id"])
        self.assertIn("20261119", parse(feed)["trips"][0]["id"])
        invalid, _ = make_feed("20261301")
        self.assertIsNone(parse(invalid)["trips"][0]["id"])
        missing, _ = make_feed(None)
        self.assertIsNone(parse(missing)["trips"][0]["id"])
        short_date, _ = make_feed("2026119")
        self.assertIsNone(parse(short_date)["trips"][0]["id"])

    def test_canceled_and_skipped_stop_relationships_are_preserved(self):
        feed, update = make_feed()
        update.trip.schedule_relationship = gtfs.TripDescriptor.CANCELED
        stop = update.stop_time_update.add(stop_id="F01S")
        stop.schedule_relationship = gtfs.TripUpdate.StopTimeUpdate.SKIPPED
        stop = update.stop_time_update.add(stop_id="F02S")
        stop.schedule_relationship = gtfs.TripUpdate.StopTimeUpdate.NO_DATA
        trip = parse(feed)["trips"][0]
        self.assertEqual(trip["schedule_relationship"], "CANCELED")
        self.assertEqual([x["schedule_relationship"] for x in trip["stop_updates"]],
                         ["SKIPPED", "NO_DATA"])

    def test_nyct_extensions_preserve_direction_and_track_changes(self):
        feed, update = make_feed()
        trip_ext = update.trip.Extensions[mta.NYCT_EXTENSIONS["nyct_trip_descriptor"]]
        trip_ext.direction = 3
        trip_ext.is_assigned = True
        trip_ext.train_id = "[F 1200 TEST/TEST"
        stop = update.stop_time_update.add(stop_id="F01S")
        stop_ext = stop.Extensions[mta.NYCT_EXTENSIONS["nyct_stop_time_update"]]
        stop_ext.scheduled_track = "1"
        stop_ext.actual_track = "2"
        header_ext = feed.header.Extensions[mta.NYCT_EXTENSIONS["nyct_feed_header"]]
        header_ext.nyct_subway_version = "1.0"
        period = header_ext.trip_replacement_period.add(route_id="F")
        period.replacement_period.end = STAMP + 1800
        snapshot = parse(feed)
        trip = snapshot["trips"][0]
        self.assertEqual(trip["nyct_direction"], "SOUTH")
        self.assertIsNone(trip["direction_id"])
        self.assertTrue(trip["is_assigned"])
        self.assertIn("TRACK_CHANGE_OBSERVED", trip["reason_codes"])
        self.assertEqual(snapshot["trip_replacement_periods"],
                         [{"route_id": "F", "start": None, "end": STAMP + 1800}])

    def test_differential_feed_is_not_mistaken_for_full_dataset(self):
        feed, _ = make_feed()
        feed.header.incrementality = gtfs.FeedHeader.DIFFERENTIAL
        snapshot = parse(feed)
        self.assertEqual(snapshot["status"], "MISSING")
        self.assertEqual(snapshot["trips"], [])
        self.assertIn("UNSUPPORTED_INCREMENTAL_FEED", snapshot["reason_codes"])

    def test_vehicle_observation_retains_timestamp_without_inventing_motion(self):
        feed, _ = make_feed()
        entity = feed.entity.add(id="synthetic-vehicle")
        entity.vehicle.trip.CopyFrom(feed.entity[0].trip_update.trip)
        entity.vehicle.timestamp = STAMP - 120
        entity.vehicle.stop_id = "F01S"
        entity.vehicle.current_status = gtfs.VehiclePosition.STOPPED_AT
        snapshot = parse(feed)
        vehicle = snapshot["vehicles"][0]
        self.assertEqual(vehicle["trip_identity"], snapshot["trips"][0]["id"])
        self.assertEqual(vehicle["timestamp"], STAMP - 120)
        self.assertEqual(vehicle["current_status"], "STOPPED_AT")
        self.assertNotIn("is_stalled", vehicle)

    def test_deleted_entity_is_not_restored(self):
        feed, _ = make_feed()
        feed.entity[0].is_deleted = True
        self.assertEqual(parse(feed)["trips"], [])

    def test_future_predictions_are_valid_but_future_source_is_not(self):
        feed, update = make_feed()
        update.stop_time_update.add(stop_id="F01S").arrival.time = STAMP + 7200
        self.assertEqual(mta.snapshot_status(parse(feed), CUTOFF), "FRESH")
        feed.header.timestamp = STAMP + 100
        self.assertEqual(mta.snapshot_status(parse(feed), CUTOFF), "MISSING")


class AlertAndFreshnessTests(unittest.TestCase):
    def alert_snapshot(self, stamp=STAMP):
        payload = {"header": {"timestamp": stamp}, "entity": [{"id": "synthetic-alert", "alert": {
            "active_period": [{"start": STAMP, "end": STAMP + 60}],
            "informed_entity": [{"route_id": "F", "stop_id": "F01S", "direction_id": 1}],
            "effect": "MODIFIED_SERVICE",
            "header_text": {"translation": [{"language": "es", "text": "Spanish"},
                                               {"language": "en", "text": "Synthetic service change"}]},
            "transit_realtime.mercury_alert": {"alert_type": "Planned - Trains Rerouted"}
        }}]}
        return mta.parse_alerts_feed(json.dumps(payload).encode(), FETCHED)

    def test_alert_period_and_selector_are_preserved(self):
        alert = self.alert_snapshot()["alerts"][0]
        self.assertTrue(mta.alert_is_active(alert, STAMP))
        self.assertFalse(mta.alert_is_active(alert, STAMP + 60))
        self.assertFalse(mta.alert_is_active(alert, STAMP - 1))
        self.assertEqual(alert["informed_entities"][0]["stop_id"], "F01S")
        self.assertEqual(alert["header"], "Synthetic service change")
        self.assertIn("transit_realtime.mercury_alert", alert["extensions"])
        alert["active_periods"] = []
        self.assertTrue(mta.alert_is_active(alert, STAMP))

    def test_unchanged_alert_source_is_not_expired_by_itself(self):
        snapshot = self.alert_snapshot(STAMP - 86400)
        self.assertEqual(mta.snapshot_status(snapshot, CUTOFF), "FRESH")
        self.assertEqual(mta.snapshot_status(snapshot, STAMP + 400), "STALE")

    def test_fetched_after_cutoff_is_unavailable(self):
        feed, _ = make_feed()
        self.assertEqual(mta.snapshot_status(parse(feed), STAMP + 5), "MISSING")
        feed.header.ClearField("timestamp")
        self.assertEqual(mta.snapshot_status(parse(feed), CUTOFF), "MISSING")

    def test_train_source_and_fetch_age_are_checked(self):
        feed, _ = make_feed()
        snapshot = parse(feed)
        self.assertEqual(mta.snapshot_status(snapshot, STAMP + 181), "STALE")
        snapshot["requested_at"] = datetime.fromtimestamp(STAMP + 12, timezone.utc).isoformat()
        self.assertEqual(mta.snapshot_status(snapshot, CUTOFF), "MISSING")


class CollectionAndCacheTests(unittest.TestCase):
    def test_feed_map_uses_current_official_groups(self):
        self.assertEqual(mta.route_feed_ids(["F", "FS", "7", "7X", "A"]),
                         ["ace", "bdfm", "numbered"])
        self.assertEqual(mta.route_feed_ids(["S"]), [])

    def test_single_feed_failure_does_not_erase_other_results(self):
        feed, _ = make_feed()
        def fetch(url):
            if "gtfs-g" in url:
                raise RuntimeError("A synthetic transport failure")
            body = json.dumps({"header": {"timestamp": STAMP}}).encode() if "alerts" in url else feed.SerializeToString()
            return SimpleNamespace(body=body, requested_at=FETCHED, fetched_at=FETCHED, status_code=200)
        snapshots = {s["feed_id"]: s for s in mta.collect_feeds(["F", "G", "S"], fetch)}
        self.assertEqual(snapshots["bdfm"]["status"], "AVAILABLE")
        self.assertEqual(snapshots["g"]["status"], "MISSING")
        self.assertEqual(snapshots["g"]["trips"], [])
        self.assertEqual(snapshots["subway-alerts"]["status"], "AVAILABLE")
        self.assertEqual(snapshots["unsupported:S"]["status"], "MISSING")

    def test_cache_asof_uses_whole_latest_feed_and_known_failure(self):
        feed, _ = make_feed()
        first = parse(feed)
        feed.ClearField("entity")
        second = mta.parse_train_feed(feed.SerializeToString(), "bdfm", STAMP + 30)
        with tempfile.TemporaryDirectory() as directory:
            cache = mta.SnapshotCache(directory)
            cache.put(first)
            cache.put(second)
            self.assertEqual(len(cache.latest("bdfm", CUTOFF)["trips"]), 1)
            self.assertEqual(cache.latest("bdfm", STAMP + 40)["trips"], [])
            missing = mta._missing(mta._base_snapshot("bdfm", "train", STAMP + 45), "FETCH_FAILED")
            cache.put(missing)
            self.assertEqual(cache.latest("bdfm", STAMP + 50)["status"], "MISSING")
            self.assertIsNone(cache.latest("bdfm", STAMP))

    def test_cache_future_source_invalidates_latest_without_old_fallback(self):
        feed, _ = make_feed()
        first = parse(feed)
        feed.header.timestamp = STAMP + 100
        future_source = mta.parse_train_feed(feed.SerializeToString(), "bdfm", STAMP + 30)
        with tempfile.TemporaryDirectory() as directory:
            cache = mta.SnapshotCache(directory)
            cache.put(first)
            cache.put(future_source)
            result = cache.latest("bdfm", STAMP + 40)
            self.assertEqual(result["status"], "MISSING")
            self.assertIn("INVALID_SNAPSHOT_TIMESTAMPS", result["reason_codes"])

    def test_cache_equal_time_failure_masks_success_in_either_write_order(self):
        feed, _ = make_feed()
        success = parse(feed)
        failure = mta._missing(mta._base_snapshot("bdfm", "train", FETCHED), "FETCH_FAILED")
        for sequence in ((success, failure), (failure, success)):
            with tempfile.TemporaryDirectory() as directory:
                cache = mta.SnapshotCache(directory)
                for snapshot in sequence:
                    cache.put(snapshot)
                self.assertEqual(cache.latest("bdfm", CUTOFF)["status"], "MISSING")

    def test_cache_equal_time_conflicting_full_feeds_are_ambiguous(self):
        feed, _ = make_feed()
        first = parse(feed)
        feed.ClearField("entity")
        second = parse(feed)
        with tempfile.TemporaryDirectory() as directory:
            cache = mta.SnapshotCache(directory)
            cache.put(first)
            cache.put(second)
            result = cache.latest("bdfm", CUTOFF)
            self.assertEqual(result["status"], "MISSING")
            self.assertIn("AMBIGUOUS_SNAPSHOT_ORDER", result["reason_codes"])

    def test_static_gtfs_maps_parent_and_directional_stations(self):
        data = io.BytesIO()
        with ZipFile(data, "w") as archive:
            archive.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon,parent_station,location_type\nX01,Example,40,-73,,1\nX01S,Example,40,-73,X01,0\n")
            archive.writestr("routes.txt", "route_id,route_short_name,route_type\nF,F,1\n")
            archive.writestr("trips.txt", "route_id,trip_id\nF,trip1\n")
            archive.writestr("stop_times.txt", "trip_id,stop_id\ntrip1,X01S\n")
        metadata = mta.load_static_gtfs(data.getvalue())
        self.assertEqual(metadata["route_stops"]["F"], ["X01", "X01S"])
        self.assertEqual(metadata["stops"]["X01S"]["parent_station"], "X01")


if __name__ == "__main__":
    unittest.main()
