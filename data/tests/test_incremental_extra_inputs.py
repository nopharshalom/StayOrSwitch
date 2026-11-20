"""Protect additive R16S projection and label scope for two new corridors."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from data.google_corridor_inputs import augmented_configuration as previous_configuration
from data.incremental_extra_inputs import (
    augmented_configuration, check_snapshot_extension, merge_label_additions, select_new_label_endpoints,
    verify_daily_projection,
)
from data.tests.test_google_corridor_inputs import BASE, endpoint, snapshot


class ExtraProjectionTests(unittest.TestCase):
    def pair(self):
        trains = [("R", ["R16S", "R17S", "R18S", "R20S", "R28S", "R29S"])]
        return (snapshot(trains, "nqrw", previous_configuration(BASE)),
                snapshot(trains, "nqrw", augmented_configuration(BASE)))

    def test_configuration_preserves_previous_routes_and_adds_r16(self):
        before = deepcopy(BASE)
        previous, current = previous_configuration(BASE), augmented_configuration(BASE)
        self.assertEqual(BASE, before)
        self.assertEqual(current["feed_ids"], ["nqrw"])
        self.assertEqual(current["route_ids"], previous["route_ids"])
        self.assertEqual(set(current["stop_ids"]) - set(previous["stop_ids"]), {"R16S"})
        self.assertEqual(current["routes"][:-1], previous["routes"])

    def test_r16_and_ordered_span_are_added(self):
        old, new = self.pair()
        count = check_snapshot_extension(old, new)
        self.assertEqual(count["additional_r16_stop_updates"], 1)
        self.assertEqual(new["trips"][0]["stop_updates"][0]["stop_id"], "R16S")

    def test_parity_ignores_alert_stream_checked_separately(self):
        old, new = self.pair()
        alert = {"feed_id": "subway-alerts", "alerts": []}
        with patch("data.incremental_extra_inputs.read_snapshots", side_effect=[
                iter([alert, old]), iter([alert, new])]):
            result = verify_daily_projection("old", "new")
        self.assertEqual(result["compared_captures"], 1)
        self.assertEqual(result["additional_r16_stop_updates"], 1)

    def test_changed_old_endpoint_is_rejected(self):
        old, new = self.pair()
        new["trips"][0]["stop_updates"][-1]["arrival_time"] += 1
        with self.assertRaises(ValueError):
            check_snapshot_extension(old, new)

    def test_trip_capture_and_vehicle_changes_are_rejected(self):
        for defect in ("trip", "capture", "vehicle"):
            old, new = self.pair()
            if defect == "trip":
                new["trips"][0]["schedule_relationship"] = "CANCELED"
            elif defect == "capture":
                new["sha256"] = "different"
            else:
                new["vehicles"].append({"trip_identity": "unknown"})
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                check_snapshot_extension(old, new)

    def test_missing_trip_or_reordered_stops_are_rejected(self):
        for defect in ("missing", "order"):
            old, new = self.pair()
            if defect == "missing":
                new["trips"] = []
            else:
                new["trips"][0]["stop_updates"].reverse()
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                check_snapshot_extension(old, new)

    def test_only_r_observed_r16_requested(self):
        trips = {"r": {"route_id": "R", "observed_stop_ids": {"R16S", "R29S"}},
                 "n": {"route_id": "N", "observed_stop_ids": {"R16S"}}}
        select_new_label_endpoints(trips, {})
        self.assertEqual(trips["r"]["observed_stop_ids"], {"R16S"})
        self.assertEqual(trips["n"]["observed_stop_ids"], set())

    def test_label_merge_has_no_overwrites_or_mutations(self):
        old = {"r": {"R29S": endpoint("R", "R29S")}}
        addition = {"r": {"R16S": endpoint("R", "R16S")}}
        before = deepcopy((old, addition))
        result = merge_label_additions(old, addition)
        self.assertEqual((old, addition), before)
        self.assertEqual(set(result["r"]), {"R16S", "R29S"})
        with self.assertRaises(ValueError):
            merge_label_additions(result, addition)

    def test_wrong_route_stop_or_feed_is_rejected(self):
        for field, value in (("route_id", "N"), ("stop_id", "R17S"), ("feed_id", "numbered")):
            label = endpoint("R", "R16S")
            label[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                merge_label_additions({}, {"r": {"R16S": label}})


if __name__ == "__main__":
    unittest.main()
