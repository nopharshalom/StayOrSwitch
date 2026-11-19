"""Feature leakage, target semantics, and sampled-view integrity regressions."""

import copy
from datetime import datetime
import gzip
import json
import math
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from data.modeling.features import (
    CATEGORICAL_FEATURES, FEATURE_NAMES, ROLLING_FEATURE_NAMES, build_features,
    disruption_group, feature_vector, horizon_bucket, revision_group, support_key,
    support_keys,
)
from data.modeling.views import SelectionStore, make_example, trip_selected, write_views


def at(value):
    return int(datetime.fromisoformat(value).replace(
        tzinfo=ZoneInfo("America/New_York")).timestamp())


def source_features():
    decision = at("2026-11-02T10:00:00")
    return {
        "route_id": "F", "feed_id": "bdfm", "direction": "SOUTH",
        "direction_source": "NYCT_DESCRIPTOR", "gtfs_direction_id": 1,
        "stop_id": "F03S", "from_stop_id": "F01S", "to_stop_id": "F03S",
        "service_date": "2026-11-02", "decision_local_date": "2026-11-02",
        "day_type": "WEEKDAY", "day_of_week": 0,
        "seconds_since_local_midnight": 36000,
        "mta_arrival_at": decision + 400, "mta_departure_at": decision + 80,
        "prediction_horizon_seconds": 400, "departure_horizon_seconds": 80,
        "arrival_horizon_seconds": 400, "predicted_duration_seconds": 320,
        "origin_prediction_basis": "DEPARTURE_PREDICTION",
        "feed_age_seconds": 5, "trip_update_age_seconds": 5,
        "previous_prediction_delta_seconds": 15,
        "seconds_since_previous_prediction": 60,
        "prediction_revisions_last_10_minutes": 3,
        "sampled_updates_last_10_minutes": 8,
        "forecast_gap_to_previous_train_seconds": 300,
        "forecast_gap_to_next_train_seconds": 420,
        "vehicle_stop_id": "F01S", "vehicle_status": "IN_TRANSIT_TO",
        "vehicle_observation_age_seconds": 5, "is_assigned": True,
        "remaining_stop_pattern": ["F01S", "F02S", "F03S"],
        "segment_stop_pattern": ["F01S", "F02S", "F03S"],
        "remaining_stop_pattern_changed": False,
        "scheduled_track": "1", "actual_track": "1",
        "service_alerts_available": True, "service_alert_status": "FRESH",
        "service_alert_count": 0, "service_alert_possible_count": 0,
        "known_upcoming_service_alert_count": 0,
        "known_upcoming_service_alert_possible_count": 0,
        "service_alert_effects": [], "service_alert_causes": [],
        "service_alert_types": [], "service_alert_fetch_age_seconds": 10,
    }


def historical_row(target="arrival", day="2026-11-02"):
    decision = at(day + "T10:00:00")
    features = source_features()
    features.update(service_date=day, decision_local_date=day,
                    mta_arrival_at=decision + 400,
                    mta_departure_at=decision + 80)
    label = {
        "method": "CSV_LAST_PREDICTION_PROXY", "physical_ground_truth": False,
        "source_trip_uid": "opaque-source-key", "arrival_at": decision + 450,
        "available_at": decision + 480, "residual_seconds": 50,
        "receipt_confirmed_at": decision + 500,
        "quality_flags": [], "usable_proxy": True,
    }
    if target != "arrival":
        label.update(method="CSV_DEPARTURE_TO_ARRIVAL_PROXY",
                     departure_at=decision + 90, duration_seconds=360,
                     residual_seconds=40,
                     origin_available_at=decision + 100,
                     destination_available_at=decision + 480)
    return {
        "schema_version": "historical-arrival-v1" if target == "arrival" else "historical-segment-v1",
        "example_id": "synthetic-example", "split": "train",
        "trip_identity": "MTA:bdfm:" + day.replace("-", "") + ":F:060000_F..S:",
        "decision_at": decision, "source_updated_at": decision - 5,
        "stop_id": "F03S", "from_stop_id": "F01S", "to_stop_id": "F03S",
        "features": features, "label": label, "eligible_for_training": True,
        "provenance": {"label_source": "SUBWAY_DATA_NYC_CSV_JOURNAL"},
    }


class ModelFeatureTests(unittest.TestCase):
    def test_feature_names_are_explicit_and_forbid_future_or_identity_inputs(self):
        forbidden = {
            "trip_identity", "trip_id", "example_id", "service_date",
            "decision_local_date", "decision_at", "mta_arrival_at",
            "mta_departure_at", "arrival_at", "departure_at", "available_at",
            "residual_seconds", "quality_flags", "eligible_for_training",
            "source_trip_uid",
        }
        for target in ("arrival", "departure", "segment"):
            with self.subTest(target=target):
                features = build_features(target, source_features())
                self.assertEqual(set(features), set(FEATURE_NAMES[target]))
                self.assertTrue(forbidden.isdisjoint(features))
                self.assertTrue(set(CATEGORICAL_FEATURES[target]).issubset(features))

    def test_source_outcomes_and_exact_dates_cannot_change_features(self):
        original = source_features()
        changed = copy.deepcopy(original)
        changed.update(trip_id="different-trip", trip_identity="future-identity",
                       service_date="2099-01-01", decision_local_date="2099-01-01",
                       arrival_at=123456789, departure_at=123456780,
                       mta_arrival_at=123456789, mta_departure_at=123456780,
                       source_trip_uid="different-csv-key", residual_seconds=9999,
                       eligible_for_training=False, quality_flags=["FUTURE_FLAG"])
        for target in ("arrival", "departure", "segment"):
            with self.subTest(target=target):
                self.assertEqual(build_features(target, original), build_features(target, changed))

    def test_default_features_do_not_require_rolling_history(self):
        first = source_features()
        second = copy.deepcopy(first)
        second.update(previous_prediction_delta_seconds=900,
                      seconds_since_previous_prediction=None,
                      prediction_revisions_last_10_minutes=1000,
                      sampled_updates_last_10_minutes=None,
                      remaining_stop_pattern_changed=True)
        self.assertEqual(build_features("arrival", first), build_features("arrival", second))

    def test_transformation_does_not_mutate_historical_features(self):
        original = source_features()
        saved = copy.deepcopy(original)
        for target in ("arrival", "departure", "segment"):
            build_features(target, original)
        self.assertEqual(original, saved)

    def test_unknown_alert_state_is_not_fresh_no_disruption(self):
        fresh = source_features()
        unknown = copy.deepcopy(fresh)
        unknown.update(service_alerts_available=False, service_alert_status="STALE",
                       service_alert_count=None, service_alert_possible_count=None,
                       known_upcoming_service_alert_count=None,
                       known_upcoming_service_alert_possible_count=None,
                       service_alert_effects=None, service_alert_causes=None,
                       service_alert_types=None)
        for target in ("arrival", "segment"):
            with self.subTest(target=target):
                self.assertEqual(disruption_group(fresh, target), "FRESH_NO_KNOWN_DISRUPTION")
                self.assertEqual(disruption_group(unknown, target), "UNKNOWN_ALERT_STATE")
        # Segment-scoped alert annotations do not establish boarding-only scope.
        self.assertEqual(disruption_group(fresh, "departure"), "UNKNOWN_ALERT_STATE")

    def test_core_features_do_not_depend_on_optional_alert_annotations(self):
        original = source_features()
        changed = copy.deepcopy(original)
        changed.update(service_alert_count=10, service_alert_effects=["SIGNIFICANT_DELAYS"])
        for target in ("arrival", "departure", "segment"):
            self.assertEqual(build_features(target, original), build_features(target, changed))

    def test_rolling_features_require_opt_in_and_keep_missing_history(self):
        original = source_features()
        original["previous_prediction_delta_seconds"] = None
        core = build_features("arrival", original)
        rolling = build_features("arrival", original, include_rolling=True)
        self.assertTrue(set(ROLLING_FEATURE_NAMES).isdisjoint(core))
        self.assertTrue(set(ROLLING_FEATURE_NAMES).issubset(rolling))
        self.assertIsNone(rolling["previous_prediction_delta_seconds"])
        with self.assertRaises(ValueError):
            build_features("departure", original, include_rolling=True)

    def test_disruption_group_preserves_possible_and_upcoming_evidence(self):
        original = source_features()
        original["service_alert_possible_count"] = 1
        self.assertEqual(disruption_group(original, "arrival"), "POSSIBLE_DISRUPTION")
        original["known_upcoming_service_alert_count"] = 1
        self.assertEqual(disruption_group(original, "arrival"), "KNOWN_UPCOMING_ONLY")

    def test_invalid_or_unsupported_horizon_has_no_bucket(self):
        for value in (-1, 1801, None, float("nan"), "300"):
            with self.subTest(value=value):
                self.assertIsNone(horizon_bucket(value))

    def test_vectors_follow_declared_order(self):
        for target in ("arrival", "departure", "segment"):
            features = build_features(target, source_features())
            self.assertEqual(feature_vector(target, features), [features[key] for key in FEATURE_NAMES[target]])

    def test_missing_numeric_input_remains_missing_in_model_vector(self):
        source = source_features()
        source["trip_update_age_seconds"] = None
        features = build_features("arrival", source)
        vector = feature_vector("arrival", features)
        self.assertIsNone(features["trip_update_age_seconds"])
        self.assertTrue(math.isnan(vector[FEATURE_NAMES["arrival"].index("trip_update_age_seconds")]))

    def test_horizon_buckets_preserve_boundary_distinctions(self):
        self.assertEqual(horizon_bucket(0), horizon_bucket(299))
        self.assertNotEqual(horizon_bucket(299), horizon_bucket(300))
        self.assertEqual(horizon_bucket(300), horizon_bucket(899))
        self.assertNotEqual(horizon_bucket(899), horizon_bucket(900))
        self.assertEqual(horizon_bucket(900), horizon_bucket(1800))

    def test_normal_progress_does_not_change_station_support(self):
        for target in ("arrival", "departure"):
            with self.subTest(target=target):
                before = source_features()
                before["remaining_stop_pattern"] = ["F00S", "F01S", "F02S", "F03S"]
                after = copy.deepcopy(before)
                after["remaining_stop_pattern"] = ["F01S", "F02S", "F03S"]
                learned = support_keys(target, build_features(target, before), before)
                current = support_key(target, build_features(target, after), after)
                self.assertIn(current, learned)

    def test_new_approach_stop_is_not_hidden_by_station_only_support(self):
        before = source_features()
        after = copy.deepcopy(before)
        after["remaining_stop_pattern"] = ["F01S", "F99S", "F03S"]
        self.assertNotIn(support_key("arrival", build_features("arrival", after), after),
                         support_keys("arrival", build_features("arrival", before), before))

    def test_unknown_revision_history_is_not_no_revisions(self):
        source = source_features()
        source["prediction_revisions_last_10_minutes"] = None
        self.assertEqual(revision_group(source, "arrival"), "UNAVAILABLE")
        source["prediction_revisions_last_10_minutes"] = 0
        self.assertEqual(revision_group(source, "arrival"), "NOT_REVISED_IN_OBSERVED_WINDOW")

    def test_segment_support_preserves_intermediate_stopping_pattern(self):
        original = source_features()
        changed = copy.deepcopy(original)
        changed["segment_stop_pattern"] = ["F01S", "F03S"]
        self.assertNotEqual(support_key("segment", build_features("segment", original)),
                            support_key("segment", build_features("segment", changed)))


class ModelTargetTests(unittest.TestCase):
    def test_arrival_target_is_remaining_time_residual(self):
        example = make_example(historical_row(), "arrival")
        self.assertTrue(example["eligible"])
        self.assertEqual(example["baseline_seconds"], 400)
        self.assertEqual(example["label_seconds"], 450)
        self.assertEqual(example["target_residual_seconds"], 50)

    def test_departure_target_does_not_use_arrival_residual(self):
        example = make_example(historical_row("segment"), "departure")
        self.assertTrue(example["eligible"])
        self.assertEqual(example["baseline_seconds"], 80)
        self.assertEqual(example["label_seconds"], 90)
        self.assertEqual(example["target_residual_seconds"], 10)
        self.assertEqual(example["features"]["stop_id"], "F01S")

    def test_segment_target_excludes_origin_waiting_and_dwell(self):
        example = make_example(historical_row("segment"), "segment")
        self.assertTrue(example["eligible"])
        self.assertEqual(example["baseline_seconds"], 320)
        self.assertEqual(example["label_seconds"], 360)
        self.assertEqual(example["target_residual_seconds"], 40)

    def test_arrival_as_departure_proxy_is_retained_as_unsupported(self):
        row = historical_row("segment")
        row["features"]["origin_prediction_basis"] = "ARRIVAL_AS_DEPARTURE_PROXY"
        for target in ("departure", "segment"):
            example = make_example(row, target)
            self.assertFalse(example["eligible"])
            self.assertTrue(example["exclusion_reasons"])

    def test_label_exclusion_cannot_change_predictors_or_event_identity(self):
        row = historical_row()
        original = make_example(row, "arrival")
        row["eligible_for_training"] = False
        row["label"].update(usable_proxy=False, quality_flags=["FUTURE_SCHEDULE_CHANGE"],
                            arrival_at=None, residual_seconds=None)
        excluded = make_example(row, "arrival")
        self.assertFalse(excluded["eligible"])
        self.assertEqual(original["features"], excluded["features"])
        self.assertEqual(original["event_id"], excluded["event_id"])
        self.assertEqual(original["horizon_bucket"], excluded["horizon_bucket"])

    def test_missing_departure_label_is_not_zero(self):
        row = historical_row("segment")
        row["label"]["departure_at"] = None
        row["eligible_for_training"] = False
        row["label"]["usable_proxy"] = False
        example = make_example(row, "departure")
        self.assertFalse(example["eligible"])
        self.assertIsNone(example["label_seconds"])

    def test_invalid_split_metadata_fails_closed(self):
        row = historical_row()
        row["split"] = "unknown"
        with self.assertRaises(ValueError):
            make_example(row, "arrival")

    def test_future_source_timestamp_fails_closed(self):
        row = historical_row()
        row["source_updated_at"] = row["decision_at"] + 1
        with self.assertRaises(ValueError):
            make_example(row, "arrival")

    def test_cross_split_receipt_cannot_make_eligible_training_label(self):
        row = historical_row()
        row["label"]["receipt_confirmed_at"] = at("2026-11-09T00:00:00")
        example = make_example(row, "arrival")
        self.assertFalse(example["eligible"])
        self.assertIn("LABEL_RECEIPT_NOT_CONFIRMED_WITHIN_SPLIT", example["exclusion_reasons"])

    def test_nonfinite_label_is_excluded_even_if_source_eligibility_is_true(self):
        row = historical_row()
        row["label"]["arrival_at"] = float("nan")
        example = make_example(row, "arrival")
        self.assertFalse(example["eligible"])
        self.assertIsNone(example["label_seconds"])
        self.assertIsNone(example["target_residual_seconds"])

    def test_departure_event_deduplicates_across_destination_annotations(self):
        first = historical_row("segment")
        second = copy.deepcopy(first)
        second["to_stop_id"] = "F04S"
        second["features"]["to_stop_id"] = "F04S"
        second["example_id"] = "another-segment"
        departure_first = make_example(first, "departure")
        departure_second = make_example(second, "departure")
        self.assertEqual(departure_first["event_id"], departure_second["event_id"])
        self.assertEqual(departure_first["features"], departure_second["features"])
        self.assertNotEqual(make_example(first, "segment")["event_id"],
                            make_example(second, "segment")["event_id"])


class ModelSelectionTests(unittest.TestCase):
    def test_trip_sampling_is_stable_and_uses_entire_trip(self):
        identity = historical_row()["trip_identity"]
        self.assertEqual(trip_selected(identity, 25, "fixed-seed"),
                         trip_selected(identity, 25, "fixed-seed"))
        self.assertFalse(trip_selected(identity, 0, "fixed-seed"))
        self.assertTrue(trip_selected(identity, 100, "fixed-seed"))

    def test_selection_is_order_independent_and_one_per_event_bucket(self):
        first = make_example(historical_row(), "arrival")
        second = copy.deepcopy(first)
        second["decision_at"] += 60
        second["example_id"] = "second-snapshot"
        chosen = []
        for values in ((first, second), (second, first)):
            store = SelectionStore(":memory:", "fixed-seed")
            try:
                for value in values:
                    store.consider(value)
                selected = list(store.selected())
                self.assertEqual(len(selected), 1)
                chosen.append(selected[0]["decision_at"])
            finally:
                store.close()
        self.assertEqual(chosen[0], chosen[1])

    def test_unusable_selected_label_is_not_replaced_by_usable_snapshot(self):
        first = make_example(historical_row(), "arrival")
        second = copy.deepcopy(first)
        second["decision_at"] += 60
        second["example_id"] = "second-snapshot"
        probe = SelectionStore(":memory:", "fixed-seed")
        try:
            probe.consider(first)
            probe.consider(second)
            chosen_decision = list(probe.selected())[0]["decision_at"]
        finally:
            probe.close()
        values = [first, second]
        for value in values:
            if value["decision_at"] == chosen_decision:
                value.update(eligible=False, exclusion_reasons=["UNUSABLE_LABEL"],
                             label_seconds=None, target_residual_seconds=None)
        store = SelectionStore(":memory:", "fixed-seed")
        try:
            for value in reversed(values):
                store.consider(value)
            chosen = list(store.selected())[0]
            self.assertEqual(chosen["decision_at"], chosen_decision)
            self.assertFalse(chosen["eligible"])
        finally:
            store.close()

    def test_conflicting_duplicate_labels_are_not_arbitrarily_chosen(self):
        first = make_example(historical_row(), "arrival")
        second = copy.deepcopy(first)
        second.update(label_seconds=600, target_residual_seconds=200)
        store = SelectionStore(":memory:", "fixed-seed")
        try:
            store.consider(first)
            store.consider(second)
            result = list(store.selected())
            self.assertEqual(len(result), 1)
            self.assertFalse(result[0]["eligible"])
            self.assertTrue(result[0]["exclusion_reasons"])
        finally:
            store.close()

    def test_retained_horizon_weights_sum_to_one_per_event(self):
        first = make_example(historical_row(), "arrival")
        second = copy.deepcopy(first)
        second.update(decision_at=first["decision_at"] + 60,
                      example_id="second-bucket", horizon_bucket="00_05_MIN")
        excluded = copy.deepcopy(first)
        excluded.update(decision_at=first["decision_at"] - 900,
                        example_id="excluded-bucket", horizon_bucket="15_30_MIN",
                        eligible=False, exclusion_reasons=["UNUSABLE_LABEL"])
        store = SelectionStore(":memory:", "fixed-seed")
        try:
            for example in (first, second, excluded):
                store.consider(example)
            with tempfile.TemporaryDirectory() as temporary:
                outputs, report = write_views(store, temporary)
                arrival = next(item for item in outputs if item["target"] == "arrival" and item["split"] == "train")
                with gzip.open(Path(arrival["path"]), "rt", encoding="utf-8") as stream:
                    rows = [json.loads(line) for line in stream]
                self.assertEqual(arrival["rows"], 2)
                self.assertEqual(arrival["events"], 1)
                self.assertEqual([row["weight"] for row in rows], [0.5, 0.5])
                self.assertEqual(sum(row["weight"] for row in rows), 1)
                self.assertEqual(report["selected_before_label_filter"]["arrival/train"], 3)
                self.assertEqual(report["selected_exclusions"]["arrival/train/UNUSABLE_LABEL"], 1)
        finally:
            store.close()

    def test_trip_cannot_enter_two_splits_even_under_different_event_ids(self):
        first = make_example(historical_row(), "arrival")
        second = copy.deepcopy(first)
        second.update(split="test", event_id="different-stop-event", example_id="other-example")
        store = SelectionStore(":memory:", "fixed-seed")
        try:
            store.consider(first)
            store.consider(second)
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(ValueError):
                    write_views(store, temporary)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
