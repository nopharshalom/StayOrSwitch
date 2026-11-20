"""Protect additive route-6 scope and new Google-corridor endpoint evidence."""

from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch

from google.transit import gtfs_realtime_pb2 as gtfs

from data.google_corridor_inputs import (
    augmented_configuration, build_additional_labels, check_snapshot_extension,
    merge_label_additions, select_new_label_endpoints,
)
from data.october.projection import project_payload
from data.preincident_inputs import augmented_configuration as preincident_configuration
from stayorswitch.mta import parse_train_feed


BASE = {
    "feed_ids": ["ace", "bdfm", "g", "nqrw", "numbered"],
    "route_ids": ["4", "5", "7", "7X", "F", "FX", "R"],
    "stop_ids": ["631S", "423S", "719S", "723S", "725S", "F09S", "A41S",
                 "G21S", "R17S", "R29S"],
    "sample_seconds": 60,
    "routes": [
        {"id": "r", "legs": [{"route_id": "R", "feed_id": "nqrw",
            "from_stop_id": "G21S", "to_stop_id": "R29S", "route_ids": ["R"]}]},
        {"id": "7", "legs": [{"route_id": "7", "feed_id": "numbered",
            "from_stop_id": "719S", "to_stop_id": "725S", "route_ids": ["7", "7X"]}]},
    ],
}


def snapshot(trains, feed_id, config):
    feed = gtfs.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1793000000
    for number, (route, stops) in enumerate(trains):
        update = feed.entity.add(id="train-" + str(number)).trip_update
        update.trip.trip_id = "060000_" + route + "..S"
        update.trip.route_id = route
        update.trip.start_date = "20261026"
        for index, stop_id in enumerate(stops):
            stop = update.stop_time_update.add(stop_id=stop_id, stop_sequence=index + 1)
            stop.arrival.time = 1793000100 + 60 * index
            stop.departure.time = 1793000110 + 60 * index
    raw = feed.SerializeToString()
    payload, _ = project_payload(raw, feed_id, config)
    result = parse_train_feed(payload, feed_id, 1793000001)
    result["sha256"] = hashlib.sha256(raw).hexdigest()
    return result


def endpoint(route, stop):
    return {"route_id": route, "stop_id": stop,
            "feed_id": "nqrw" if route == "R" else "numbered",
            "arrival_at": 1793000100, "departure_at": 1793000110,
            "arrival_usable": True, "departure_usable": True}


class GoogleCorridorProjectionTests(unittest.TestCase):
    def test_configuration_adds_only_route_six_and_keeps_prior_coverage(self):
        before = deepcopy(BASE)
        prior = preincident_configuration(BASE)
        expanded = augmented_configuration(BASE)
        self.assertEqual(BASE, before)
        self.assertEqual(set(expanded["feed_ids"]), {"numbered", "nqrw"})
        self.assertEqual(set(expanded["route_ids"]) - set(BASE["route_ids"]), {"6"})
        self.assertEqual(expanded["sample_seconds"], 60)
        self.assertEqual(expanded["routes"][:len(prior["routes"])], prior["routes"])
        self.assertTrue(set(prior["stop_ids"]).issubset(expanded["stop_ids"]))
        self.assertTrue({"631S", "635S", "724S", "R20S", "R28S"}.issubset(expanded["stop_ids"]))

    def test_new_six_trip_is_preserved_with_its_complete_requested_span(self):
        stops = ["631S", "632S", "633S", "634S", "635S"]
        old = snapshot([("6", stops)], "numbered", preincident_configuration(BASE))
        new = snapshot([("6", stops)], "numbered", augmented_configuration(BASE))
        self.assertEqual(old["trips"], [])
        self.assertEqual(new["trips"][0]["route_id"], "6")
        self.assertEqual([row["stop_id"] for row in new["trips"][0]["stop_updates"]], stops)
        self.assertIsInstance(check_snapshot_extension(old, new), dict)

    def test_union_square_r_boarding_survives_after_queens_plaza_disappears(self):
        stops = ["R20S", "R21S", "R22S", "R28S", "R29S"]
        old = snapshot([("R", stops)], "nqrw", BASE)
        new = snapshot([("R", stops)], "nqrw", augmented_configuration(BASE))
        self.assertEqual([row["stop_id"] for row in old["trips"][0]["stop_updates"]], ["R29S"])
        self.assertEqual([row["stop_id"] for row in new["trips"][0]["stop_updates"]], stops)
        check_snapshot_extension(old, new)

    def test_short_turn_seven_keeps_fifth_avenue_without_times_square(self):
        stops = ["723S", "724S"]
        old = snapshot([("7", stops)], "numbered", preincident_configuration(BASE))
        new = snapshot([("7", stops)], "numbered", augmented_configuration(BASE))
        self.assertEqual([row["stop_id"] for row in old["trips"][0]["stop_updates"]], ["723S"])
        self.assertEqual([row["stop_id"] for row in new["trips"][0]["stop_updates"]], stops)
        check_snapshot_extension(old, new)

    def test_existing_seven_span_and_train_are_unchanged_when_six_is_added(self):
        trains = [("7", ["723S", "724S", "725S"]), ("6", ["631S", "635S"])]
        old = snapshot(trains, "numbered", preincident_configuration(BASE))
        new = snapshot(trains, "numbered", augmented_configuration(BASE))
        self.assertEqual(old["trips"][0], new["trips"][0])
        check_snapshot_extension(old, new)


class GoogleCorridorParityTests(unittest.TestCase):
    def pair(self):
        trains = [("7", ["723S", "724S", "725S"]), ("6", ["631S", "635S"])]
        return (snapshot(trains, "numbered", preincident_configuration(BASE)),
                snapshot(trains, "numbered", augmented_configuration(BASE)))

    def test_changed_original_forecast_is_rejected(self):
        old, new = self.pair()
        new["trips"][0]["stop_updates"][0]["arrival_time"] += 1
        with self.assertRaises(ValueError):
            check_snapshot_extension(old, new)

    def test_removed_original_trip_is_rejected(self):
        old, new = self.pair()
        del new["trips"][0]
        with self.assertRaises(ValueError):
            check_snapshot_extension(old, new)

    def test_reordered_original_stops_are_rejected(self):
        old, new = self.pair()
        new["trips"][0]["stop_updates"].reverse()
        with self.assertRaises(ValueError):
            check_snapshot_extension(old, new)

    def test_changed_original_descriptor_or_capture_is_rejected(self):
        for defect in ("trip", "capture", "payload"):
            old, new = self.pair()
            if defect == "trip":
                new["trips"][0]["schedule_relationship"] = "CANCELED"
            elif defect == "capture":
                new["fetched_at"] = "2026-10-26T00:00:00Z"
            else:
                new["sha256"] = "changed-raw-payload"
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                check_snapshot_extension(old, new)

    def test_added_trip_other_than_six_is_rejected(self):
        old, new = self.pair()
        new["trips"][-1]["route_id"] = "Q"
        with self.assertRaises(ValueError):
            check_snapshot_extension(old, new)

    def test_added_vehicle_must_belong_to_the_new_six_trip(self):
        old, new = self.pair()
        new["vehicles"].append({"trip_identity": new["trips"][-1]["id"]})
        check_snapshot_extension(old, new)
        new["vehicles"][-1]["trip_identity"] = "unknown-trip"
        with self.assertRaises(ValueError):
            check_snapshot_extension(old, new)

    def test_existing_vehicle_state_cannot_change(self):
        old, new = self.pair()
        vehicle = {"trip_identity": old["trips"][0]["id"], "current_status": "STOPPED_AT"}
        old["vehicles"].append(deepcopy(vehicle))
        new["vehicles"].append(deepcopy(vehicle))
        check_snapshot_extension(old, new)
        new["vehicles"][-1]["current_status"] = "IN_TRANSIT_TO"
        with self.assertRaises(ValueError):
            check_snapshot_extension(old, new)

    def test_preexisting_duplicate_trip_descriptors_are_preserved_by_occurrence(self):
        old, new = self.pair()
        duplicate = deepcopy(old["trips"][0])
        duplicate["stop_updates"][0]["arrival_time"] += 30
        old["trips"].append(deepcopy(duplicate))
        new["trips"].append(deepcopy(duplicate))
        check_snapshot_extension(old, new)
        new["trips"][-1]["stop_updates"][0]["arrival_time"] += 1
        with self.assertRaises(ValueError):
            check_snapshot_extension(old, new)


class GoogleCorridorLabelMergeTests(unittest.TestCase):
    def test_allowed_new_endpoints_merge_without_mutating_original(self):
        original = {"old-four": {"631S": endpoint("4", "631S")}}
        addition = {
            "new-six": {"631S": endpoint("6", "631S"), "635S": endpoint("6", "635S")},
            "old-seven": {"724S": endpoint("7", "724S")},
            "old-r": {"R20S": endpoint("R", "R20S"), "R28S": endpoint("R", "R28S")},
        }
        before = deepcopy((original, addition))
        result = merge_label_additions(original, addition)
        self.assertEqual((original, addition), before)
        self.assertEqual(result["old-four"], original["old-four"])
        self.assertEqual(result["new-six"], addition["new-six"])
        result["old-four"]["631S"]["arrival_at"] = 0
        self.assertNotEqual(original["old-four"]["631S"]["arrival_at"], 0)

    def test_overwrite_is_rejected_even_if_identical(self):
        value = {"six": {"631S": endpoint("6", "631S")}}
        with self.assertRaises(ValueError):
            merge_label_additions(value, value)

    def test_unrequested_endpoint_or_wrong_route_is_rejected(self):
        for route, stop in (("R", "631S"), ("4", "635S"), ("7", "725S"), ("6", "423S")):
            with self.subTest(route=route, stop=stop), self.assertRaises(ValueError):
                merge_label_additions({}, {"train": {stop: endpoint(route, stop)}})

    def test_label_metadata_must_match_the_route_feed_and_endpoint_key(self):
        for field, replacement in (("feed_id", "nqrw"), ("stop_id", "631S")):
            value = endpoint("6", "635S")
            value[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                merge_label_additions({}, {"six": {"635S": value}})

    def test_selection_keeps_all_identities_but_only_observed_new_target_endpoints(self):
        trips = {
            "six": {"route_id": "6", "observed_stop_ids": {"631S", "635S", "423S"}},
            "seven": {"route_id": "7", "observed_stop_ids": {"723S", "724S", "725S"}},
            "unobserved-r": {"route_id": "R", "observed_stop_ids": {"R29S"}},
            "other-line": {"route_id": "4", "observed_stop_ids": {"631S", "635S"}},
        }
        original = {"six": {"631S": endpoint("6", "631S")}}
        select_new_label_endpoints(trips, original)
        self.assertEqual(set(trips), {"six", "seven", "unobserved-r", "other-line"})
        self.assertEqual(trips["six"]["observed_stop_ids"], {"635S"})
        self.assertEqual(trips["seven"]["observed_stop_ids"], {"724S"})
        self.assertEqual(trips["unobserved-r"]["observed_stop_ids"], set())
        self.assertEqual(trips["other-line"]["observed_stop_ids"], set())
        self.assertEqual(original["six"]["631S"], endpoint("6", "631S"))

    def test_label_builder_keeps_full_service_identity_group_and_boundary_journals(self):
        trips = {
            "new-six": {"start_date": "20261026", "observed_stop_ids": {"635S"}},
            "same-date-off-scope": {"start_date": "20261026", "observed_stop_ids": set()},
            "other-date": {"start_date": "20261020", "observed_stop_ids": set()},
        }
        identity_days = {"new-six": ["2026-10-26", "2026-10-27"],
                         "same-date-off-scope": ["2026-10-26"],
                         "other-date": ["2026-10-20"]}
        archives = [{"kind": "csv", "archive_date": "2026-10-" + day, "path": day}
                    for day in ("24", "25", "26", "27", "28", "29")]
        original_receipt_days = [{"date": "2026-10-26", "outputs": {"receipts": "original"}}]
        with patch("data.google_corridor_inputs.DailyReceiptIndex", return_value="original-receipts") as receipts, \
                patch("data.google_corridor_inputs.build_labels", return_value=({"new-six": {"635S": {}}}, {})) as builder:
            labels, _, journals = build_additional_labels(
                trips, identity_days, original_receipt_days, archives, "America/New_York")
        receipts.assert_called_once_with(original_receipt_days, "America/New_York")
        self.assertEqual(builder.call_count, 1)
        subset, paths, receipt_index, stops = builder.call_args.args
        self.assertEqual(set(subset), {"new-six", "same-date-off-scope"})
        self.assertEqual(paths, ["25", "26", "27", "28"])
        self.assertEqual(receipt_index, "original-receipts")
        self.assertEqual(stops, {"631S", "635S", "724S", "R20S", "R28S"})
        self.assertEqual(labels, {"new-six": {"635S": {}}})
        self.assertEqual(len(journals), 4)


if __name__ == "__main__":
    unittest.main()
