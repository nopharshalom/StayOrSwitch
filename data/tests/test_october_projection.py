"""Semantic preservation checks for the configured October protobuf projection."""

import copy
import unittest

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2 as gtfs

from data.october.projection import project_payload
from stayorswitch import mta


STAMP = 1791194400
CONFIG = {
    "route_ids": ["F", "FX", "G"],
    "stop_ids": ["A", "B", "Q"],
    "routes": [{"id": "f", "legs": [{"feed_id": "bdfm", "route_id": "F",
                                          "route_ids": ["F", "FX"],
                                          "from_stop_id": "A", "to_stop_id": "B"}]}],
}


def feed_with_trip(stops, route="F", entity_id="train"):
    feed = gtfs.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = STAMP
    update = feed.entity.add(id=entity_id).trip_update
    update.trip.trip_id = "060000_F..S"
    update.trip.route_id = route
    update.trip.start_date = "20261005"
    update.trip.start_time = "10:00:04"
    update.timestamp = STAMP - 1
    for sequence, stop_id in enumerate(stops, 1):
        stop = update.stop_time_update.add(stop_id=stop_id, stop_sequence=sequence)
        stop.arrival.time = STAMP + sequence * 30
        stop.departure.time = STAMP + sequence * 30 + 10
    return feed, update


def normalized(feed):
    return mta.parse_train_feed(feed.SerializeToString(), "bdfm", STAMP + 10)


class OctoberProjectionTests(unittest.TestCase):
    def project(self, feed, config=CONFIG, feed_id="bdfm"):
        payload, metadata = project_payload(feed.SerializeToString(), feed_id, copy.deepcopy(config))
        self.assertIsInstance(payload, bytes)
        self.assertIsInstance(metadata, dict)
        result = gtfs.FeedMessage()
        result.ParseFromString(payload)
        self.assertTrue(result.IsInitialized())
        return result

    def test_duplicate_endpoints_keep_the_complete_ambiguous_span(self):
        feed, _ = feed_with_trip(["OUT", "A", "X", "B", "Y", "A", "Z", "B", "TAIL"])
        before = normalized(feed)["trips"][0]
        after = normalized(self.project(feed))["trips"][0]
        self.assertEqual(after["stop_updates"], before["stop_updates"][1:8])
        self.assertEqual([row["stop_id"] for row in after["stop_updates"]],
                         ["A", "X", "B", "Y", "A", "Z", "B"])

    def test_reversed_endpoints_remain_reversed_with_their_intermediate_stop(self):
        feed, _ = feed_with_trip(["OUT", "B", "X", "A", "TAIL"])
        after = normalized(self.project(feed))["trips"][0]
        self.assertEqual(after["stop_updates"], normalized(feed)["trips"][0]["stop_updates"][1:4])
        self.assertEqual([row["stop_id"] for row in after["stop_updates"]], ["B", "X", "A"])

    def test_intermediate_skip_and_no_data_evidence_are_preserved(self):
        feed, update = feed_with_trip(["OUT", "A", "X", "Y", "B", "TAIL"])
        update.stop_time_update[2].schedule_relationship = gtfs.TripUpdate.StopTimeUpdate.SKIPPED
        update.stop_time_update[3].schedule_relationship = gtfs.TripUpdate.StopTimeUpdate.NO_DATA
        after = normalized(self.project(feed))["trips"][0]
        self.assertEqual(after["stop_updates"], normalized(feed)["trips"][0]["stop_updates"][1:5])
        self.assertEqual([row["schedule_relationship"] for row in after["stop_updates"]],
                         ["SCHEDULED", "SKIPPED", "NO_DATA", "SCHEDULED"])

    def test_every_global_stop_occurrence_survives_without_a_complete_leg(self):
        feed, _ = feed_with_trip(["OUT", "A", "Q", "X", "Q", "TAIL"])
        after = normalized(self.project(feed))["trips"][0]
        before = normalized(feed)["trips"][0]["stop_updates"]
        self.assertEqual(after["stop_updates"], [before[1], before[2], before[4]])

    def test_configured_trip_with_no_relevant_stop_preserves_descriptor_and_status(self):
        feed, update = feed_with_trip(["OUT", "TAIL"])
        update.trip.schedule_relationship = gtfs.TripDescriptor.CANCELED
        extension = update.trip.Extensions[mta.NYCT_EXTENSIONS["nyct_trip_descriptor"]]
        extension.direction = 3
        extension.is_assigned = True
        extension.train_id = "test train"
        before = normalized(feed)["trips"][0]
        after = normalized(self.project(feed))["trips"][0]
        self.assertEqual(after, dict(before, stop_updates=[]))

    def test_express_alias_uses_its_configured_leg_and_keeps_actual_route(self):
        feed, _ = feed_with_trip(["OUT", "A", "X", "B", "TAIL"], route="FX")
        after = normalized(self.project(feed))["trips"][0]
        self.assertEqual(after["route_id"], "FX")
        self.assertEqual([row["stop_id"] for row in after["stop_updates"]], ["A", "X", "B"])

    def test_unexpected_feed_or_unscoped_route_retains_complete_stop_context(self):
        for route, feed_id in (("G", "bdfm"), ("F", "g")):
            with self.subTest(route=route, feed_id=feed_id):
                feed, _ = feed_with_trip(["OUT", "A", "X", "B", "TAIL"], route=route)
                after = self.project(feed, feed_id=feed_id).entity[0].trip_update
                self.assertEqual(after, feed.entity[0].trip_update)

    def test_each_matching_leg_keeps_its_own_contiguous_span(self):
        config = copy.deepcopy(CONFIG)
        config["routes"][0]["legs"].append({"feed_id": "bdfm", "route_id": "F",
                                                "from_stop_id": "C", "to_stop_id": "D"})
        feed, _ = feed_with_trip(["OUT", "A", "X", "B", "GAP", "C", "Y", "D", "TAIL"])
        projected = self.project(feed, config)
        self.assertEqual([stop.stop_id for stop in projected.entity[0].trip_update.stop_time_update],
                         ["A", "X", "B", "C", "Y", "D"])

    def test_track_change_outside_route_span_still_changes_trip_reason(self):
        feed, update = feed_with_trip(["OUT", "A", "X", "B", "TRACK", "TAIL"])
        extension = update.stop_time_update[4].Extensions[mta.NYCT_EXTENSIONS["nyct_stop_time_update"]]
        extension.scheduled_track = "1"
        extension.actual_track = "2"
        after = normalized(self.project(feed))["trips"][0]
        self.assertEqual(after["reason_codes"], normalized(feed)["trips"][0]["reason_codes"])
        self.assertIn("TRACK_CHANGE_OBSERVED", after["reason_codes"])
        self.assertEqual([row["stop_id"] for row in after["stop_updates"]], ["A", "X", "B", "TRACK"])

    def test_header_extensions_are_preserved_exactly(self):
        feed, _ = feed_with_trip(["A", "B"])
        extension = feed.header.Extensions[mta.NYCT_EXTENSIONS["nyct_feed_header"]]
        extension.nyct_subway_version = "1.0"
        period = extension.trip_replacement_period.add(route_id="F")
        period.replacement_period.start = STAMP - 60
        period.replacement_period.end = STAMP + 3600
        projected = self.project(feed)
        self.assertEqual(projected.header, feed.header)
        self.assertEqual(normalized(projected)["trip_replacement_periods"], normalized(feed)["trip_replacement_periods"])

    def test_unconfigured_mixed_entity_retains_alert_vehicle_and_unknown_fields(self):
        feed, update = feed_with_trip(["A", "X", "B"], route="M")
        entity = feed.entity[0]
        entity.vehicle.trip.CopyFrom(update.trip)
        entity.vehicle.timestamp = STAMP
        entity.vehicle.stop_id = "X"
        entity.alert.header_text.translation.add(language="en", text="Service disruption")
        entity.alert.informed_entity.add(route_id="F")
        entity.MergeFromString(b"\x9a\x06\x03new")
        expected = gtfs.FeedEntity()
        expected.CopyFrom(entity)
        expected.ClearField("trip_update")
        projected = self.project(feed)
        self.assertEqual(len(projected.entity), 1)
        self.assertEqual(projected.entity[0], expected)
        self.assertEqual(normalized(projected)["alerts"], normalized(feed)["alerts"])
        self.assertEqual(normalized(projected)["vehicles"], normalized(feed)["vehicles"])

    def test_configured_mixed_entity_preserves_non_trip_submessages(self):
        feed, update = feed_with_trip(["OUT", "A", "X", "B", "TAIL"])
        entity = feed.entity[0]
        entity.vehicle.trip.CopyFrom(update.trip)
        entity.vehicle.timestamp = STAMP
        entity.alert.header_text.translation.add(language="en", text="Shared entity")
        projected = self.project(feed)
        self.assertEqual(projected.entity[0].vehicle, entity.vehicle)
        self.assertEqual(projected.entity[0].alert, entity.alert)
        self.assertEqual(normalized(projected)["alerts"], normalized(feed)["alerts"])

    def test_deleted_entity_reason_survives_even_for_an_unconfigured_route(self):
        feed, _ = feed_with_trip(["OUT"], route="M")
        feed.entity[0].is_deleted = True
        projected = self.project(feed)
        self.assertEqual(len(projected.entity), 1)
        self.assertTrue(projected.entity[0].is_deleted)
        self.assertEqual(normalized(projected)["reason_codes"], ["DELETED_ENTITY_IGNORED"])

    def test_malformed_original_is_rejected_before_its_bad_trip_can_be_removed(self):
        feed, _ = feed_with_trip(["A", "B"])
        malformed = feed.entity.add(id="bad-unconfigured")
        malformed.trip_update.timestamp = STAMP
        self.assertFalse(feed.IsInitialized())
        with self.assertRaises(ValueError):
            project_payload(feed.SerializePartialToString(), "bdfm", copy.deepcopy(CONFIG))

    def test_invalid_wire_payload_is_rejected(self):
        with self.assertRaises((ValueError, DecodeError)):
            project_payload(b"\xff", "bdfm", copy.deepcopy(CONFIG))

    def test_scope_counts_describe_original_and_projected_records(self):
        feed, _ = feed_with_trip(["OUT", "A", "X", "B", "TAIL"])
        other, _ = feed_with_trip(["A", "X", "B"], route="M", entity_id="other")
        feed.entity.add().CopyFrom(other.entity[0])
        _, metadata = project_payload(feed.SerializeToString(), "bdfm", copy.deepcopy(CONFIG))
        self.assertTrue(metadata["original_message_validated"])
        self.assertTrue(metadata["projection_policy"])
        self.assertEqual(metadata["feed_id"], "bdfm")
        for name, expected in {"entities_before": 2, "entities_after": 2,
                               "trips_before": 2, "trips_after": 1,
                               "stops_before": 8, "stops_after": 3}.items():
            self.assertEqual(metadata[name], expected)


if __name__ == "__main__":
    unittest.main()
