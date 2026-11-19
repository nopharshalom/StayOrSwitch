"""Historical leakage, chronology, identity, and proxy-label regression tests."""

import copy
from datetime import datetime, timezone
import unittest
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2 as gtfs
from history.features import FeatureBuilder, LabelIndex, source_trip_uid, split_for_date, epoch


ZONE = ZoneInfo("America/New_York")


def at(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp())


def trip(day="20261102", trip_id="060000_F..S", identity="MTA:bdfm:20261102:F:060000_F..S:"):
    return {"id": identity, "trip_id": trip_id, "route_id": "F", "start_date": day,
            "nyct_direction": "SOUTH", "direction_id": None, "timestamp": None,
            "is_assigned": True, "schedule_relationship": "SCHEDULED",
            "stop_updates": [{"stop_id": "F01S", "arrival_time": at("2026-11-02T10:05:00"),
                              "schedule_relationship": "SCHEDULED"}]}


def snapshot(capture=None, train=None):
    capture = at("2026-11-02T10:00:00") if capture is None else capture
    return {"feed_id": "bdfm", "captured_at": capture, "source_updated_at": capture - 2,
            "status": "AVAILABLE", "trips": [trip() if train is None else train],
            "vehicles": [], "member_name": "synthetic.gtfsrt"}


def labels(train=None, arrival=None, **trip_changes):
    train = train or trip()
    uid = source_trip_uid(train)
    arrival = at("2026-11-02T10:06:00") if arrival is None else arrival
    source_trip = {"trip_uid": uid, "trip_id": train["trip_id"], "route_id": "F",
                   "num_schedule_changes": "0", "num_schedule_rewrites": "0"}
    source_trip.update(trip_changes)
    return LabelIndex([source_trip], [{"trip_uid": uid, "stop_id": "F01S",
                                      "arrival_time": str(arrival), "last_observed": str(arrival + 10),
                                      "marked_past": str(arrival + 15)}])


class LabelTests(unittest.TestCase):
    def test_uid_uses_explicit_service_date_and_encoded_start(self):
        source_start = int(datetime(2026, 11, 2, 10, tzinfo=timezone.utc).timestamp())
        self.assertEqual(source_trip_uid(trip()), str(source_start) + "_F..S")
        following = trip("20261103")
        self.assertNotEqual(source_trip_uid(following), source_trip_uid(trip()))
        extended = trip(trip_id="150000_F..S")
        next_start = int(datetime(2026, 11, 3, 1, tzinfo=timezone.utc).timestamp())
        self.assertEqual(source_trip_uid(extended), str(next_start) + "_F..S")

    def test_publisher_uid_uses_utc_identifier_not_physical_start(self):
        # Verified against the November 2 archive and publisher's journal code.
        self.assertEqual(source_trip_uid(trip(trip_id="030000_4..S06R")), "1793595600_4..S06R")
        self.assertEqual(source_trip_uid(trip(trip_id="144000_1..N03R")), "1793664000_1..N03R")

    def test_missing_or_invalid_service_identity_is_not_guessed(self):
        self.assertIsNone(source_trip_uid(trip(day="")))
        self.assertIsNone(source_trip_uid(trip(day="20261301")))
        self.assertIsNone(source_trip_uid(trip(trip_id="unqualified")))

    def test_proxy_is_not_physical_ground_truth(self):
        label = labels().lookup(trip(), "F01S")
        self.assertTrue(label["usable_proxy"])
        self.assertFalse(label["physical_ground_truth"])
        self.assertEqual(label["method"], "CSV_LAST_PREDICTION_PROXY")
        self.assertEqual(label["observation_gap_seconds"], 5)

    def test_conflicting_labels_are_ambiguous_not_averaged(self):
        index = labels()
        uid = source_trip_uid(trip())
        altered = dict(index.stops[(uid, "F01S")], arrival_time=str(at("2026-11-02T10:07:00")))
        index.add_stop(altered)
        found = index.lookup(trip(), "F01S")
        self.assertFalse(found["usable_proxy"])
        self.assertIn("AMBIGUOUS_CSV_LABEL", found["quality_flags"])

    def test_identical_duplicate_is_counted_without_ambiguity(self):
        index = labels()
        uid = source_trip_uid(trip())
        index.add_stop(index.stops[(uid, "F01S")])
        self.assertTrue(index.lookup(trip(), "F01S")["usable_proxy"])
        self.assertEqual(index.report()["identical_stop_duplicates"], 1)

    def test_schedule_change_is_retained_as_unreliable_proxy(self):
        index = labels(num_schedule_changes="2", num_schedule_rewrites="1")
        found = index.lookup(trip(), "F01S")
        self.assertIsNotNone(found["arrival_at"])
        self.assertFalse(found["usable_proxy"])
        self.assertEqual(found["quality_flags"], ["CSV_SCHEDULE_CHANGED", "CSV_SCHEDULE_REWRITTEN"])

    def test_missing_arrival_or_passage_is_not_zero(self):
        index = labels()
        uid = source_trip_uid(trip())
        index.stops[(uid, "F01S")]["arrival_time"] = ""
        index.stops[(uid, "F01S")]["marked_past"] = ""
        found = index.lookup(trip(), "F01S")
        self.assertIsNone(found["arrival_at"])
        self.assertIsNone(found["available_at"])
        self.assertFalse(found["usable_proxy"])

    def test_route_mismatch_and_large_gap_are_quality_flags(self):
        index = labels(route_id="G")
        uid = source_trip_uid(trip())
        index.stops[(uid, "F01S")]["marked_past"] = str(at("2026-11-02T11:00:00"))
        found = index.lookup(trip(), "F01S")
        self.assertIn("CSV_ROUTE_MISMATCH", found["quality_flags"])
        self.assertIn("LARGE_STOP_OBSERVATION_GAP", found["quality_flags"])

    def test_csv_uid_alias_cannot_match_different_raw_trip_id(self):
        first = trip("20261102", "144000_F..S")
        next_day = trip("20261103", "000000_F..S")
        self.assertEqual(source_trip_uid(first), source_trip_uid(next_day))
        found = labels(first).lookup(next_day, "F01S")
        self.assertFalse(found["usable_proxy"])
        self.assertIn("CSV_TRIP_ID_MISMATCH", found["quality_flags"])

    def test_missing_invalid_and_negative_history_are_not_known_zero(self):
        for value, expected in (("", "MISSING_CSV_SCHEDULE_HISTORY"),
                                (None, "MISSING_CSV_SCHEDULE_HISTORY"),
                                ("bad", "INVALID_CSV_SCHEDULE_HISTORY"),
                                ("-1", "INVALID_CSV_SCHEDULE_HISTORY")):
            label = labels(num_schedule_changes=value).lookup(trip(), "F01S")
            self.assertFalse(label["usable_proxy"])
            self.assertIn(expected, label["quality_flags"])

    def test_cached_labels_do_not_share_mutable_flags_or_residuals(self):
        index = labels()
        first = index.lookup(trip(), "F01S")
        first["quality_flags"].append("CALLER_FLAG")
        first["residual_seconds"] = 999
        next_label = index.lookup(trip(), "F01S")
        self.assertNotIn("CALLER_FLAG", next_label["quality_flags"])
        self.assertIsNone(next_label["residual_seconds"])

    def test_journal_addition_invalidates_cached_missing_label(self):
        index = LabelIndex()
        self.assertIn("MISSING_CSV_LABEL", index.lookup(trip(), "F01S")["quality_flags"])
        complete = labels()
        for row in complete.trips.values():
            index.add_trip(row)
        for row in complete.stops.values():
            index.add_stop(row)
        self.assertTrue(index.lookup(trip(), "F01S")["usable_proxy"])

    def test_label_cache_is_bounded_and_disabled_cache_matches(self):
        complete = labels()
        cached = LabelIndex(complete.trips.values(), complete.stops.values(), cache_size=1)
        uncached = LabelIndex(complete.trips.values(), complete.stops.values(), cache_size=0)
        self.assertEqual(cached.lookup(trip(), "F01S"), uncached.lookup(trip(), "F01S"))
        cached.lookup(trip(), "F02S")
        self.assertEqual(len(cached._label_cache), 1)
        self.assertEqual(cached.lookup(trip(), "F01S"), uncached.lookup(trip(), "F01S"))


class FeatureTests(unittest.TestCase):
    def test_residual_features_and_counts_are_separate(self):
        builder = FeatureBuilder(labels())
        row = builder.process(snapshot())[0]
        self.assertEqual(row["label"]["residual_seconds"], 60)
        self.assertEqual(row["features"]["prediction_horizon_seconds"], 300)
        self.assertTrue(row["eligible_for_training"])
        self.assertNotIn("residual_seconds", row["features"])
        self.assertNotIn("marked_past", row["features"])
        self.assertEqual(builder.report()["unique_stop_events"], 1)
        self.assertEqual(builder.report()["trip_split_counts"], {"train": 1})
        self.assertEqual(row["provenance"]["raw_trip_id"], "060000_F..S")
        self.assertNotIn("raw_trip_id", row["features"])

    def test_hindsight_change_flags_never_change_features(self):
        normal = FeatureBuilder(labels()).process(snapshot())[0]
        changed = FeatureBuilder(labels(num_schedule_rewrites="3")).process(snapshot())[0]
        self.assertEqual(normal["features"], changed["features"])
        self.assertTrue(normal["eligible_for_training"])
        self.assertFalse(changed["eligible_for_training"])

    def test_revisions_use_only_prior_sampled_predictions(self):
        builder = FeatureBuilder(labels())
        first = builder.process(snapshot())[0]
        second_input = snapshot(at("2026-11-02T10:01:00"))
        second_input["trips"][0]["stop_updates"][0]["arrival_time"] += 120
        second = builder.process(second_input)[0]
        self.assertIsNone(first["features"]["previous_prediction_delta_seconds"])
        self.assertEqual(second["features"]["previous_prediction_delta_seconds"], 120)
        self.assertEqual(second["features"]["seconds_since_previous_prediction"], 60)
        self.assertEqual(second["features"]["prediction_revisions_last_10_minutes"], 1)
        self.assertEqual(builder.report()["unique_stop_events"], 1)

    def test_future_source_and_stale_source_are_excluded(self):
        for offset in (1, -181):
            value = snapshot()
            value["source_updated_at"] = value["captured_at"] + offset
            self.assertEqual(FeatureBuilder(labels()).process(value), [])

    def test_future_trip_and_vehicle_observations_do_not_leak(self):
        value = snapshot()
        value["trips"][0]["timestamp"] = value["captured_at"] + 1
        self.assertEqual(FeatureBuilder(labels()).process(value), [])
        value["trips"][0]["timestamp"] = None
        value["vehicles"] = [{"trip_identity": value["trips"][0]["id"],
                               "timestamp": value["captured_at"] + 1, "stop_id": "F02S",
                               "current_status": "STOPPED_AT"}]
        row = FeatureBuilder(labels()).process(value)[0]
        self.assertIsNone(row["features"]["vehicle_status"])
        self.assertIsNone(row["features"]["vehicle_observation_age_seconds"])

    def test_duplicates_and_out_of_order_captures_are_not_new_examples(self):
        builder = FeatureBuilder(labels())
        builder.process(snapshot())
        self.assertEqual(builder.process(snapshot()), [])
        self.assertEqual(builder.process(snapshot(at("2026-11-02T09:59:00"))), [])
        self.assertEqual(builder.report()["counts"]["rows"], 1)

    def test_duplicate_source_payload_is_not_independent_observation(self):
        value = snapshot()
        value["sha256"] = "same-payload"
        builder = FeatureBuilder(labels())
        builder.process(value)
        value["captured_at"] += 10
        self.assertEqual(builder.process(value), [])
        self.assertEqual(builder.report()["counts"]["duplicate_source_payload"], 1)

    def test_canceled_skipped_and_missing_predictions_are_excluded(self):
        value = snapshot()
        value["trips"][0]["schedule_relationship"] = "CANCELED"
        self.assertEqual(FeatureBuilder(labels()).process(value), [])
        for relationship in ("SKIPPED", "NO_DATA"):
            value = snapshot()
            value["trips"][0]["stop_updates"][0]["schedule_relationship"] = relationship
            self.assertEqual(FeatureBuilder(labels()).process(value), [])
        value = snapshot()
        value["trips"][0]["stop_updates"][0]["arrival_time"] = None
        self.assertEqual(FeatureBuilder(labels()).process(value), [])

    def test_missing_csv_label_retains_coverage_row(self):
        row = FeatureBuilder(LabelIndex()).process(snapshot())[0]
        self.assertFalse(row["eligible_for_training"])
        self.assertIsNone(row["label"]["residual_seconds"])
        self.assertIn("MISSING_CSV_LABEL", row["label"]["quality_flags"])

    def test_weekday_saturday_and_sunday_are_distinct(self):
        for day, expected in (("2026-11-02", "WEEKDAY"), ("2026-11-07", "SATURDAY"), ("2026-11-08", "SUNDAY")):
            train = trip(day.replace("-", ""))
            captured = at(day + "T10:00:00")
            train["stop_updates"][0]["arrival_time"] = captured + 300
            row = FeatureBuilder(LabelIndex()).process(snapshot(captured, train))[0]
            self.assertEqual(row["features"]["day_type"], expected)

    def test_label_crossing_split_boundary_is_not_training_example(self):
        captured = at("2026-11-08T23:58:00")
        train = trip("20261108", "143000_F..S")
        train["stop_updates"][0]["arrival_time"] = captured + 180
        row = FeatureBuilder(labels(train, captured + 200)).process(snapshot(captured, train))[0]
        self.assertEqual(row["split"], "train")
        self.assertFalse(row["eligible_for_training"])
        self.assertIn("LABEL_AVAILABILITY_SPLIT_BOUNDARY", row["label"]["quality_flags"])

    def test_cross_midnight_trip_cannot_move_to_next_split(self):
        captured = at("2026-11-09T00:01:00")
        train = trip("20261108", "143000_F..S")
        train["stop_updates"][0]["arrival_time"] = captured + 180
        builder = FeatureBuilder(LabelIndex())
        self.assertEqual(builder.process(snapshot(captured, train)), [])
        self.assertEqual(builder.report()["counts"]["trip_capture_split_boundary"], 1)

    def test_same_split_midnight_trip_preserves_service_date(self):
        captured = at("2026-11-03T00:01:00")
        train = trip("20261102", "143000_F..S")
        train["stop_updates"][0]["arrival_time"] = captured + 180
        row = FeatureBuilder(LabelIndex()).process(snapshot(captured, train))[0]
        self.assertEqual(row["features"]["service_date"], "2026-11-02")
        self.assertEqual(row["features"]["decision_local_date"], "2026-11-03")

    def test_progress_is_not_mistaken_for_reroute(self):
        value = snapshot()
        value["trips"][0]["stop_updates"].append({"stop_id": "F02S", "arrival_time": value["captured_at"] + 600})
        builder = FeatureBuilder(LabelIndex())
        builder.process(value)
        value["captured_at"] += 60
        value["source_updated_at"] += 60
        value["trips"][0]["stop_updates"].pop(0)
        self.assertFalse(builder.process(value)[0]["features"]["remaining_stop_pattern_changed"])
        value["captured_at"] += 60
        value["source_updated_at"] += 60
        value["trips"][0]["stop_updates"].append({"stop_id": "F03S", "arrival_time": value["captured_at"] + 900})
        self.assertTrue(builder.process(value)[0]["features"]["remaining_stop_pattern_changed"])

    def test_forecast_headways_are_stop_specific_and_not_observed(self):
        value = snapshot()
        second = copy.deepcopy(value["trips"][0])
        second["id"] = "second-train"
        second["trip_id"] = "060500_F..S"
        second["stop_updates"][0]["arrival_time"] += 180
        value["trips"].append(second)
        rows = FeatureBuilder(LabelIndex()).process(value)
        self.assertEqual(rows[0]["features"]["forecast_gap_to_next_train_seconds"], 180)
        self.assertIsNone(rows[0]["features"]["forecast_gap_to_previous_train_seconds"])
        self.assertEqual(rows[1]["features"]["forecast_gap_to_previous_train_seconds"], 180)

    def test_alerts_absence_is_unknown_not_no_disruption(self):
        row = FeatureBuilder(labels()).process(snapshot())[0]
        self.assertFalse(row["features"]["service_alerts_available"])
        self.assertIsNone(row["features"]["service_alert_count"])

    def test_direction_can_use_observed_platform_without_csv_hindsight(self):
        value = snapshot()
        value["trips"][0]["nyct_direction"] = None
        row = FeatureBuilder(labels()).process(value)[0]
        self.assertEqual(row["features"]["direction"], "SOUTH")
        self.assertEqual(row["features"]["direction_source"], "PLATFORM_SUFFIX")

    def test_ambiguous_trip_and_repeated_stop_are_excluded(self):
        value = snapshot()
        value["trips"].append(copy.deepcopy(value["trips"][0]))
        self.assertEqual(FeatureBuilder(labels()).process(value), [])
        value = snapshot()
        value["trips"][0]["stop_updates"].append(copy.deepcopy(value["trips"][0]["stop_updates"][0]))
        self.assertEqual(FeatureBuilder(labels()).process(value), [])

    def test_past_label_is_flagged_without_silently_losing_coverage(self):
        row = FeatureBuilder(labels(arrival=at("2026-11-02T09:59:00"))).process(snapshot())[0]
        self.assertFalse(row["eligible_for_training"])
        self.assertIn("LABEL_NOT_AFTER_DECISION", row["label"]["quality_flags"])

    def test_scope_filters_do_not_invent_missing_predictions(self):
        self.assertEqual(FeatureBuilder(labels(), route_ids=["G"]).process(snapshot()), [])
        self.assertEqual(FeatureBuilder(labels(), stop_ids=["OTHER"]).process(snapshot()), [])
        self.assertEqual(FeatureBuilder(labels(), horizon_seconds=120).process(snapshot()), [])

    def test_raw_protobuf_interface_and_collector_provenance(self):
        now = at("2026-11-02T10:00:00")
        feed = gtfs.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        feed.header.timestamp = now - 2
        entity = feed.entity.add(id="test")
        entity.trip_update.trip.trip_id = "060000_F..S"
        entity.trip_update.trip.route_id = "F"
        entity.trip_update.trip.start_date = "20261102"
        entity.trip_update.stop_time_update.add(stop_id="F01S").arrival.time = now + 300
        row = FeatureBuilder(labels()).process({"feed_id": "bdfm", "captured_at": now,
                                               "payload": feed.SerializeToString(), "member_name": "synthetic.gtfsrt"})[0]
        self.assertEqual(row["provenance"]["archive_member"], "synthetic.gtfsrt")
        self.assertEqual(row["decision_at"], now)

    def test_malformed_protobuf_is_reported_and_skipped(self):
        builder = FeatureBuilder(labels())
        self.assertEqual(builder.process({"feed_id": "bdfm", "captured_at": at("2026-11-02T10:00:00"),
                                          "payload": b"bad"}), [])
        self.assertEqual(builder.report()["counts"]["invalid_snapshot"], 1)

    def test_timezone_and_split_validation(self):
        self.assertEqual(split_for_date("20261102"), "train")
        self.assertEqual(split_for_date("2026-11-10"), "validation")
        self.assertEqual(split_for_date("2026-11-15"), "test")
        self.assertIsNone(split_for_date("2026-11-16"))
        with self.assertRaises(ValueError):
            epoch("2026-11-02T10:00:00")


if __name__ == "__main__":
    unittest.main()
