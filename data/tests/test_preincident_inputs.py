"""Regression checks for boarding after an original projected route's origin."""

from copy import deepcopy
import hashlib
import unittest

from google.transit import gtfs_realtime_pb2 as gtfs

from data.october.projection import project_payload
from data.preincident_inputs import augmented_configuration, check_snapshot_extension
from stayorswitch.mta import parse_train_feed


BASE = {"feed_ids": ["bdfm", "numbered", "ace"], "route_ids": ["F", "FX", "7", "7X"],
        "stop_ids": ["F09S", "A41S", "719S", "723S", "725S"], "sample_seconds": 60,
        "routes": [
            {"id": "f", "legs": [{"route_id": "F", "route_ids": ["F", "FX"], "feed_id": "bdfm",
                                      "from_stop_id": "F09S", "to_stop_id": "A41S"}]},
            {"id": "7", "legs": [{"route_id": "7", "route_ids": ["7", "7X"], "feed_id": "numbered",
                                      "from_stop_id": "719S", "to_stop_id": "725S"}]}]}


def normalized(stops, route, feed_id, config, *, skipped=None):
    feed = gtfs.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1793000000
    update = feed.entity.add(id="one").trip_update
    update.trip.trip_id = "060000_" + route + "..S"
    update.trip.route_id = route
    update.trip.start_date = "20261026"
    for index, stop_id in enumerate(stops):
        stop = update.stop_time_update.add(stop_id=stop_id, stop_sequence=index + 1)
        stop.arrival.time = 1793000100 + 60 * index
        stop.departure.time = 1793000110 + 60 * index
        if stop_id == skipped:
            stop.schedule_relationship = gtfs.TripUpdate.StopTimeUpdate.SKIPPED
    original = feed.SerializeToString()
    payload, _ = project_payload(original, feed_id, config)
    result = parse_train_feed(payload, feed_id, 1793000001)
    # The original normalizer records the raw, not projected, payload digest.
    result["sha256"] = hashlib.sha256(original).hexdigest()
    return result


class PreincidentProjectionTests(unittest.TestCase):
    def test_config_preserves_original_paths_ids_and_sampling(self):
        before = deepcopy(BASE)
        expanded = augmented_configuration(BASE)
        self.assertEqual(BASE, before)
        self.assertEqual(expanded["routes"][:len(BASE["routes"])], BASE["routes"])
        self.assertEqual(expanded["route_ids"], BASE["route_ids"])
        self.assertEqual(expanded["sample_seconds"], 60)
        self.assertEqual(set(expanded["feed_ids"]), {"bdfm", "numbered"})

    def test_f_after_court_square_retains_new_boarding_and_intermediate_evidence(self):
        stops = ["D15S", "D16S", "D17S", "A41S"]
        old = normalized(stops, "F", "bdfm", BASE, skipped="D17S")
        new = normalized(stops, "F", "bdfm", augmented_configuration(BASE), skipped="D17S")
        self.assertEqual([x["stop_id"] for x in old["trips"][0]["stop_updates"]], ["A41S"])
        self.assertEqual([x["stop_id"] for x in new["trips"][0]["stop_updates"]], ["D16S", "D17S", "A41S"])
        self.assertEqual(new["trips"][0]["stop_updates"][1]["schedule_relationship"], "SKIPPED")
        self.assertEqual(check_snapshot_extension(old, new), 2)

    def test_7_after_court_square_retains_grand_central_leg(self):
        stops = ["723S", "724S", "725S"]
        old = normalized(stops, "7", "numbered", BASE)
        new = normalized(stops, "7", "numbered", augmented_configuration(BASE))
        self.assertEqual([x["stop_id"] for x in old["trips"][0]["stop_updates"]], ["723S", "725S"])
        self.assertEqual([x["stop_id"] for x in new["trips"][0]["stop_updates"]], stops)
        self.assertEqual(check_snapshot_extension(old, new), 1)

    def test_f_short_turn_before_jay_keeps_new_court_square_to_bryant_span(self):
        stops = ["F09S", "F11S", "F12S", "D15S", "D16S"]
        new = normalized(stops, "FX", "bdfm", augmented_configuration(BASE))
        self.assertEqual([x["stop_id"] for x in new["trips"][0]["stop_updates"]], stops)

    def test_original_full_path_values_and_order_are_preserved(self):
        stops = ["F09S", "F11S", "D16S", "D17S", "A41S"]
        old = normalized(stops, "F", "bdfm", BASE)
        new = normalized(stops, "F", "bdfm", augmented_configuration(BASE))
        self.assertEqual(check_snapshot_extension(old, new), 0)

    def test_parity_rejects_changed_original_forecast(self):
        old = normalized(["F09S", "A41S"], "F", "bdfm", BASE)
        changed = deepcopy(old)
        changed["trips"][0]["stop_updates"][1]["arrival_time"] += 1
        with self.assertRaises(ValueError):
            check_snapshot_extension(old, changed)

    def test_parity_rejects_changed_status_or_capture(self):
        old = normalized(["F09S", "A41S"], "F", "bdfm", BASE)
        for path in ("capture", "trip"):
            changed = deepcopy(old)
            if path == "capture":
                changed["fetched_at"] = "2026-10-26T00:00:00Z"
            else:
                changed["trips"][0]["schedule_relationship"] = "CANCELED"
            with self.assertRaises(ValueError):
                check_snapshot_extension(old, changed)


if __name__ == "__main__":
    unittest.main()
