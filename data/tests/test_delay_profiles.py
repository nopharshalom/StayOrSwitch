"""Historical profile evidence, independent support and cutoff regressions."""

from collections import Counter
from copy import deepcopy
import gzip
from pathlib import Path
import tempfile
import unittest

from data.delay_profiles.build import (ProfileDatabase, distinct_legs, fit_database,
    _incident_spans, observation_rows, profile_document, retain_earlier, scan_input_inventory,
    summarize_errors, train_eligible)
from data.delay_profiles.common import (digest, end_of_date, epoch, group_candidates,
    horizon_group, local_fields, read_json, write_json)
from data.delay_profiles.estimator import ProfileEstimator
from data.delay_profiles.incidents import IncidentIndex
from data.october.labels import canonical_event_trip_id


ROOT = Path(__file__).resolve().parents[2]
CONFIG = read_json(ROOT / "data/config/october.json")
CUTOFF = epoch("2026-10-05T08:00:00-04:00")


class FixedContext:
    """Use one explicit evidence state without constructing unrelated alert text."""

    def __init__(self, **overrides):
        self.value = {"state": "UNKNOWN", "cause": "UNKNOWN", "incident_ids": [],
                      "severe_incident_ids": [], "evidence_status": "UNKNOWN",
                      "first_observed_at": None, "age_seconds": None,
                      "ambiguous_scope": False, "applicable": None}
        self.value.update(overrides)
        self.calls = []

    def context_at(self, cutoff, route_id, stop_ids=None):
        self.calls.append((cutoff, route_id, stop_ids))
        return dict(self.value)


def endpoint_label(at, **overrides):
    value = {"arrival_at": at, "departure_at": at + 20,
             "available_at": at + 40, "confirmed_at": at + 45,
             "arrival_usable": True, "departure_usable": True,
             "quality_flags": [], "arrival_quality_flags": [], "departure_quality_flags": []}
    value.update(overrides)
    return value


def forecast(route_id="F", cutoff=CUTOFF):
    trip = {"id": "bdfm:20261005:060000_" + route_id + "..S", "route_id": route_id,
            "feed_id": "bdfm", "start_date": "20261005", "start_time": "10:00:00",
            "trip_id": "060000_" + route_id + "..S",
            "schedule_relationship": "SCHEDULED", "timestamp": cutoff - 10,
            "stop_updates": [
                {"stop_id": "F09S", "arrival_time": cutoff + 280, "departure_time": cutoff + 300},
                {"stop_id": "D20S", "arrival_time": cutoff + 600, "departure_time": cutoff + 620},
                {"stop_id": "A41S", "arrival_time": cutoff + 1200, "departure_time": cutoff + 1220}]}
    snapshot = {"captured_at": cutoff, "source_updated_at": cutoff - 10,
                "feed_id": "bdfm", "status": "AVAILABLE", "kind": "trains", "trips": [trip]}
    labels = {trip["id"]: {"F09S": endpoint_label(cutoff + 340),
                           "A41S": endpoint_label(cutoff + 1380)}}
    return snapshot, labels


def representative(event="arrival-one", **overrides):
    row = {"id": "observation-one", "event_id": event, "trip_id": "service-one", "route_id": "R",
           "target": "arrival", "from_stop_id": "G21S", "to_stop_id": "R29S",
           "decision_at": CUTOFF, "date": "2026-10-05", "split": "train",
           "horizon_seconds": 1200, "residual_seconds": 120,
           "label_confirmed_at": CUTOFF + 1400, "usable": True, "quality_flags": [],
           "context": {"state": "UNKNOWN", "cause": "UNKNOWN", "incident_ids": [],
                       "severe_incident_ids": [], "evidence_status": "UNKNOWN"}}
    row.update(overrides)
    return row


class DelayProfileTests(unittest.TestCase):
    def setUp(self):
        self.config = deepcopy(CONFIG)

    def candidates(self, context, **overrides):
        query = dict(target="arrival", route_id="F", start="F09S", end="A41S",
                     cutoff=CUTOFF, horizon_seconds=1200, context=context, config=self.config)
        query.update(overrides)
        return group_candidates(**query)

    def estimator(self, groups):
        return ProfileEstimator(profile_document(self.config, groups, "train", {}, {}, {}))

    def estimate(self, estimator, context, horizon=1200):
        return estimator.estimate("arrival", "F", "F09S", "A41S", CUTOFF, horizon, context)

    def test_time_bands_use_new_york_clock_and_keep_weekend_classes(self):
        expected = {"05:59": "OVERNIGHT", "06:00": "MORNING_PEAK",
                    "09:59": "MORNING_PEAK", "10:00": "LATE_MORNING",
                    "11:00": "MIDDAY", "13:59": "MIDDAY", "14:00": "AFTERNOON",
                    "16:00": "EVENING_PEAK", "19:59": "EVENING_PEAK", "20:00": "LATE_EVENING"}
        for clock, period in expected.items():
            with self.subTest(clock=clock):
                fields = local_fields("2026-10-05T" + clock + ":00-04:00", self.config)
                self.assertEqual(fields["period"], period)
                self.assertEqual(fields["day_type"], "WEEKDAY")
        self.assertEqual(local_fields("2026-10-04T03:30:00Z", self.config)["day_type"], "SATURDAY")
        self.assertEqual(local_fields("2026-10-04T12:00:00Z", self.config)["day_type"], "SUNDAY")
        self.assertEqual(local_fields("2026-10-05T12:00:00Z", self.config)["period"], "MORNING_PEAK")
        self.assertEqual(end_of_date("2026-11-01") - end_of_date("2026-10-31"), 25 * 3600)

    def test_timestamp_rejects_implicit_timezone_and_nonfinite_values(self):
        for value in ("2026-10-05T08:00:00", float("inf"), float("nan"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                epoch(value)

    def test_horizon_edges_do_not_merge_expired_or_invalid_predictions(self):
        expected = [(-1, "EXPIRED"), (0, "00_05_MIN"), (299, "00_05_MIN"),
                    (300, "05_15_MIN"), (900, "15_30_MIN"), (1800, "30_60_MIN"),
                    (3600, "OVER_60_MIN"), (None, "UNAVAILABLE"), (True, "UNAVAILABLE")]
        for seconds, name in expected:
            with self.subTest(seconds=seconds):
                self.assertEqual(horizon_group(seconds), name)

    def test_signed_positive_and_late_only_means_have_distinct_denominators(self):
        group = summarize_errors([-120, 0, 60, 660], ["2026-10-05", "2026-10-06"], ["i1", "i2", "i1"])
        stats = group["statistics"]
        self.assertEqual(stats["mean_signed_seconds"], 150)
        self.assertEqual(stats["mean_positive_seconds"], 180)
        self.assertEqual(stats["mean_if_late_seconds"], 360)
        self.assertEqual(stats["probability_over_5_minutes"], .25)
        self.assertEqual(stats["probability_over_10_minutes"], .25)
        self.assertEqual(group["date_count"], 2)
        self.assertEqual(group["incident_count"], 2)
        self.assertIsNone(summarize_errors([-60, 0])["statistics"]["mean_if_late_seconds"])

    def test_severe_group_requires_independent_incidents_then_falls_back_explicitly(self):
        context = {"state": "SEVERE", "cause": "SIGNAL", "evidence_status": "FRESH"}
        candidates = self.candidates(context)
        severe_key = next(key for level, key, _ in candidates if level == "CONTEXT_EXACT")
        time_key = next(key for level, key, _ in candidates if level == "TIME_EXACT")
        severe = summarize_errors([600] * 20, incidents=["i1", "i2"])
        ordinary = summarize_errors([60] * 20)
        result = self.estimate(self.estimator({severe_key: severe, time_key: ordinary}), context)
        self.assertEqual(result["correction_seconds"], 60)
        self.assertEqual(result["reason"], "INCIDENT_SUPPORT_INSUFFICIENT_USING_TIME_PROFILE")
        self.assertFalse(result["incident_supported"])
        severe = summarize_errors([600] * 20, incidents=["i1", "i2", "i3"])
        result = self.estimate(self.estimator({severe_key: severe, time_key: ordinary}), context)
        self.assertEqual(result["correction_seconds"], 600)
        self.assertTrue(result["incident_supported"])
        self.assertEqual(result["level"], "CONTEXT_EXACT")

    def test_large_incident_count_does_not_replace_minimum_event_support(self):
        context = {"state": "SEVERE", "cause": "SIGNAL", "evidence_status": "FRESH"}
        key = self.candidates(context)[0][1]
        group = summarize_errors([600] * 19, incidents=["i1", "i2", "i3", "i4"])
        result = self.estimate(self.estimator({key: group}), context)
        self.assertFalse(result["supported"])
        self.assertEqual(result["correction_seconds"], 0)
        self.assertIsNone(result["statistics"])

    def test_time_only_query_cannot_consume_incident_specific_profile(self):
        severe = {"state": "SEVERE", "cause": "SIGNAL", "evidence_status": "FRESH"}
        key = self.candidates(severe)[0][1]
        model = self.estimator({key: summarize_errors([600] * 25, incidents=["a", "b", "c"])})
        result = self.estimate(model, {"state": "TIME_ONLY"})
        self.assertFalse(result["supported"])
        self.assertEqual(result["context_requested"], "ANY")

    def test_unknown_and_stale_contexts_cannot_borrow_fresh_normal_group(self):
        normal = {"state": "NORMAL", "cause": "UNKNOWN", "evidence_status": "FRESH"}
        key = self.candidates(normal)[0][1]
        model = self.estimator({key: summarize_errors([60] * 20)})
        for context in ({"state": "UNKNOWN", "cause": "UNKNOWN", "evidence_status": "UNKNOWN"},
                        {"state": "NORMAL", "cause": "UNKNOWN", "evidence_status": "LAST_OBSERVED"}):
            with self.subTest(context=context):
                self.assertFalse(self.estimate(model, context)["supported"])

    def test_invalid_query_horizon_returns_explicit_zero_correction(self):
        for horizon in (-1, None, float("nan")):
            with self.subTest(horizon=horizon):
                result = self.estimate(self.estimator({}), {"state": "TIME_ONLY"}, horizon)
                self.assertFalse(result["supported"])
                self.assertEqual(result["reason"], "EXPIRED_OR_INVALID_FORECAST")

    def test_profile_seal_is_deterministic_and_detects_mutation(self):
        first = profile_document(self.config, {}, "train", {"a": "one", "b": "two"}, {}, {})
        second = profile_document(self.config, {}, "train", {"b": "two", "a": "one"}, {}, {})
        self.assertEqual(first["seal"], second["seal"])
        with tempfile.TemporaryDirectory() as directory:
            first_path, second_path = Path(directory) / "one.json.gz", Path(directory) / "two.json.gz"
            write_json(first_path, first)
            write_json(second_path, second)
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            self.assertEqual(ProfileEstimator(first_path).seal, first["seal"])
        first["configuration"]["min_profile_events"] = 1
        with self.assertRaisesRegex(ValueError, "seal"):
            ProfileEstimator(first)

    def test_monthly_description_is_not_a_predictive_profile(self):
        month = profile_document(self.config, {}, "month_descriptive", {}, {}, {})
        with self.assertRaises(ValueError):
            ProfileEstimator(month)

    def test_daily_cache_preserves_uncached_rows_groups_and_equal_cutoff_choice(self):
        late = representative(decision_at=CUTOFF + 60)
        early = representative(decision_at=CUTOFF, usable=False, quality_flags=["MISSING_ENDPOINT_OUTCOME"])
        equal_conflict = dict(early, residual_seconds=900, usable=True, quality_flags=[])
        separate = representative(event="separate-event", id="different-context", context={
            "state": "SEVERE", "cause": "SIGNAL", "evidence_status": "FRESH",
            "incident_ids": ["severe"], "severe_incident_ids": ["severe"]})
        rows = [late, separate, early, equal_conflict, late, separate]
        with tempfile.TemporaryDirectory() as directory:
            full = ProfileDatabase(Path(directory) / "full.sqlite")
            cached = ProfileDatabase(Path(directory) / "cached.sqlite")
            earliest = {}
            try:
                for row in rows:
                    full.add_observation(row)
                    if retain_earlier(row, earliest):
                        cached.add_observation(row)
                self.assertEqual(list(full.rows()), list(cached.rows()))
                self.assertEqual(fit_database(full, self.config, "train", {}, {}),
                                 fit_database(cached, self.config, "train", {}, {}))
                self.assertFalse(next(row for row in cached.rows() if row["id"] == early["id"])["usable"])
            finally:
                full.close()
                cached.close()

    def test_training_requires_receipt_and_purges_crossing_trip_or_incident(self):
        boundary = end_of_date("2026-10-17")
        row = representative(label_confirmed_at=boundary - 1)
        self.assertEqual(train_eligible(row, self.config, {}, {}), (True, None))
        cases = [
            (dict(row, label_confirmed_at=None), {}, {}, "OUTCOME_RECEIPT_NOT_CONFIRMED"),
            (dict(row, label_confirmed_at=boundary), {}, {}, "OUTCOME_CONFIRMED_AFTER_DEVELOPMENT"),
            (dict(row, split="validation"), {}, {}, "NOT_DEVELOPMENT_DATE"),
            (row, {"service-one": (CUTOFF, boundary)}, {}, "TRAIN_CROSSES_DEVELOPMENT_BOUNDARY"),
            (dict(row, context={"incident_ids": ["crossing"]}), {},
             {"crossing": (CUTOFF, boundary)}, "INCIDENT_CROSSES_DEVELOPMENT_BOUNDARY")]
        for current, trips, incidents, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(train_eligible(current, self.config, trips, incidents), (False, expected))

    def test_incident_removal_after_boundary_purges_last_prior_day_capture(self):
        boundary = end_of_date("2026-10-17")
        notice = {"id": "lmm:alert:boundary:30", "header": "F severe delays",
                  "informed_entities": [{"route_id": "F"}], "active_periods": [{}]}

        def capture(at, alerts, status="AVAILABLE"):
            return {"feed_id": "subway-alerts", "captured_at": at, "fetched_at": at,
                    "source_updated_at": at - 1, "status": status, "alerts": alerts}

        index = IncidentIndex([capture(boundary - 60, [notice]), capture(boundary + 60, [])])
        spans = _incident_spans(index, end_of_date("2026-10-31"))
        self.assertEqual(spans["lmm:alert:boundary"], (boundary - 60, boundary + 60))
        row = representative(label_confirmed_at=boundary - 1,
                             context={"incident_ids": ["lmm:alert:boundary"]})
        self.assertEqual(train_eligible(row, self.config, {}, spans),
                         (False, "INCIDENT_CROSSES_DEVELOPMENT_BOUNDARY"))

    def test_unresolved_incident_is_right_censored_and_missing_capture_is_not_removal(self):
        boundary, observation_end = end_of_date("2026-10-17"), end_of_date("2026-10-31")
        notice = {"id": "lmm:alert:unresolved:30", "header": "F severe delays",
                  "informed_entities": [{"route_id": "F"}], "active_periods": [{}]}
        snapshots = [
            {"feed_id": "subway-alerts", "captured_at": boundary - 60,
             "fetched_at": boundary - 60, "source_updated_at": boundary - 61,
             "status": "AVAILABLE", "alerts": [notice]},
            {"feed_id": "subway-alerts", "captured_at": boundary - 30,
             "fetched_at": boundary - 30, "source_updated_at": None,
             "status": "MISSING", "alerts": []}]
        spans = _incident_spans(IncidentIndex(snapshots), observation_end)
        self.assertEqual(spans["lmm:alert:unresolved"], (boundary - 60, observation_end))
        row = representative(label_confirmed_at=boundary - 1,
                             context={"incident_ids": ["lmm:alert:unresolved"]})
        self.assertEqual(train_eligible(row, self.config, {}, spans),
                         (False, "INCIDENT_CROSSES_DEVELOPMENT_BOUNDARY"))

    def test_incident_removed_before_boundary_remains_eligible(self):
        boundary = end_of_date("2026-10-17")
        notice = {"id": "lmm:alert:resolved:30", "header": "F severe delays",
                  "informed_entities": [{"route_id": "F"}], "active_periods": [{}]}
        snapshots = [{"feed_id": "subway-alerts", "captured_at": at, "fetched_at": at,
                      "source_updated_at": at - 1, "status": "AVAILABLE", "alerts": alerts}
                     for at, alerts in ((boundary - 120, [notice]), (boundary - 60, []))]
        spans = _incident_spans(IncidentIndex(snapshots), end_of_date("2026-10-31"))
        row = representative(label_confirmed_at=boundary - 1,
                             context={"incident_ids": ["lmm:alert:resolved"]})
        self.assertEqual(train_eligible(row, self.config, {}, spans), (True, None))

    def test_planned_only_and_unknown_only_notices_do_not_trigger_incident_purge(self):
        boundary = end_of_date("2026-10-17")
        cases = [
            ("lmm:planned_work:maintenance:30", "F trains have service changes during track maintenance.",
             "lmm:planned_work:maintenance", "PLANNED"),
            ("lmm:alert:information:30", "Information for F train customers.",
             "lmm:alert:information", "UNKNOWN")]
        for identifier, header, family, state in cases:
            notice = {"id": identifier, "header": header,
                      "informed_entities": [{"route_id": "F"}], "active_periods": [{}]}
            snapshots = [{"feed_id": "subway-alerts", "captured_at": at, "fetched_at": at,
                          "source_updated_at": at - 1, "status": "AVAILABLE", "alerts": [notice]}
                         for at in (boundary - 60, boundary + 60)]
            index = IncidentIndex(snapshots)
            with self.subTest(state=state):
                context = index.context_at(boundary - 30, "F", ["F09S", "A41S"])
                self.assertEqual(context["state"], state)
                self.assertIn(family, context["incident_ids"])
                spans = _incident_spans(index, end_of_date("2026-10-31"))
                self.assertNotIn(family, spans)
                row = representative(label_confirmed_at=boundary - 1, context=context)
                self.assertEqual(train_eligible(row, self.config, {}, spans), (True, None))

    def test_later_severe_version_purges_earlier_unknown_rows_without_backdating_context(self):
        boundary = end_of_date("2026-10-17")
        unknown = {"id": "lmm:alert:upgrade:10", "header": "Information for F train customers.",
                   "informed_entities": [{"route_id": "F"}], "active_periods": [{}]}
        severe = dict(unknown, id="lmm:alert:upgrade:30", header="F trains are running with severe delays.")
        snapshots = [{"feed_id": "subway-alerts", "captured_at": at, "fetched_at": at,
                      "source_updated_at": at - 1, "status": "AVAILABLE", "alerts": [notice]}
                     for at, notice in ((boundary - 60, unknown), (boundary + 60, severe))]
        index = IncidentIndex(snapshots)
        context = index.context_at(boundary - 30, "F", ["F09S", "A41S"])
        self.assertEqual(context["state"], "UNKNOWN")
        self.assertEqual(context["incident_ids"], ["lmm:alert:upgrade"])
        spans = _incident_spans(index, end_of_date("2026-10-31"))
        self.assertEqual(spans["lmm:alert:upgrade"][0], boundary - 60)
        row = representative(label_confirmed_at=boundary - 1, context=context)
        self.assertEqual(train_eligible(row, self.config, {}, spans),
                         (False, "INCIDENT_CROSSES_DEVELOPMENT_BOUNDARY"))

    def test_shared_endpoint_counts_once_when_pair_is_dropped(self):
        first = representative()
        later = representative(id="second-pair", from_stop_id="R17S", decision_at=CUTOFF + 60,
                               residual_seconds=180)
        with tempfile.TemporaryDirectory() as directory:
            database = ProfileDatabase(Path(directory) / "observations.sqlite")
            try:
                database.add_observation(later)
                database.add_observation(first)
                groups, _ = fit_database(database, self.config, "train", {}, {})
            finally:
                database.close()
        candidates = group_candidates("arrival", "R", "G21S", "R29S", CUTOFF, 1200,
                                      first["context"], self.config)
        key = next(key for level, key, _ in candidates if level == "TIME_ROUTE")
        self.assertEqual(groups[key]["event_count"], 1)
        self.assertEqual(groups[key]["statistics"]["mean_signed_seconds"], 120)
        pair_key = next(key for level, key, _ in candidates if level == "TIME_EXACT")
        self.assertEqual(groups[pair_key]["event_count"], 1)

    def test_later_usable_update_does_not_replace_first_missing_label_forecast(self):
        first = representative(usable=False, quality_flags=["MISSING_ENDPOINT_OUTCOME"],
                               residual_seconds=None)
        later = representative(decision_at=CUTOFF + 60, residual_seconds=30)
        with tempfile.TemporaryDirectory() as directory:
            database = ProfileDatabase(Path(directory) / "observations.sqlite")
            try:
                database.add_observation(later)
                database.add_observation(first)
                groups, report = fit_database(database, self.config, "train", {}, {})
                retained = list(database.rows())
            finally:
                database.close()
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0]["decision_at"], CUTOFF)
        self.assertFalse(retained[0]["usable"])
        self.assertEqual(groups, {})
        self.assertEqual(report["counts"]["unusable_observations"], 1)

    def test_broader_fallback_does_not_recount_event_after_period_or_context_change(self):
        first = representative()
        later = representative(id="later-period", decision_at=epoch("2026-10-05T11:00:00-04:00"),
                               residual_seconds=600,
                               context={"state": "SEVERE", "cause": "SIGNAL", "evidence_status": "FRESH",
                                        "incident_ids": ["one"], "severe_incident_ids": ["one"]})
        with tempfile.TemporaryDirectory() as directory:
            database = ProfileDatabase(Path(directory) / "observations.sqlite")
            try:
                database.add_observation(first)
                database.add_observation(later)
                groups, _ = fit_database(database, self.config, "train", {}, {})
            finally:
                database.close()
        key = next(key for level, key, _ in group_candidates("arrival", "R", "G21S", "R29S",
                   CUTOFF, 1200, first["context"], self.config) if level == "TIME_DAY")
        self.assertEqual(groups[key]["event_count"], 1)
        self.assertEqual(groups[key]["statistics"]["mean_signed_seconds"], 120)

    def test_severe_support_does_not_count_unrelated_planned_notice_families(self):
        context = {"state": "SEVERE", "cause": "SIGNAL", "evidence_status": "FRESH",
                   "incident_ids": ["severe-one", "planned-one", "planned-two"],
                   "severe_incident_ids": ["severe-one"]}
        row = representative(context=context)
        key = group_candidates("arrival", "R", "G21S", "R29S", CUTOFF, 1200, context, self.config)[0][1]
        with tempfile.TemporaryDirectory() as directory:
            database = ProfileDatabase(Path(directory) / "observations.sqlite")
            try:
                database.add_observation(row)
                groups, _ = fit_database(database, self.config, "train", {}, {})
            finally:
                database.close()
        self.assertEqual(groups[key]["incident_count"], 1)

    def test_route_aliases_are_retained_without_repeating_shared_route_legs(self):
        legs = distinct_legs(self.config)
        identities = [(leg["route_id"], leg["from_stop_id"], leg["to_stop_id"]) for leg in legs]
        self.assertIn(("FX", "F09S", "A41S"), identities)
        self.assertIn(("7X", "719S", "723S"), identities)
        self.assertEqual(identities.count(("R", "R17S", "R29S")), 1)
        snapshot, labels = forecast(route_id="FX")
        rows = list(observation_rows(snapshot, labels, self.config, FixedContext(), Counter()))
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["route_id"] for row in rows}, {"FX"})

    def test_endpoint_labels_do_not_borrow_the_other_endpoint_quality(self):
        snapshot, labels = forecast()
        arrival_label = labels[snapshot["trips"][0]["id"]]["A41S"]
        arrival_label.update(departure_usable=False, departure_quality_flags=["BAD_DEPARTURE"])
        rows = list(observation_rows(snapshot, labels, self.config, FixedContext(), Counter()))
        arrival = next(row for row in rows if row["target"] == "arrival")
        departure = next(row for row in rows if row["target"] == "departure")
        self.assertTrue(arrival["usable"])
        self.assertEqual(arrival["residual_seconds"], 180)
        self.assertEqual(departure["residual_seconds"], 60)
        self.assertNotEqual(arrival["event_id"], departure["event_id"])

    def test_missing_labels_remain_rows_with_explicit_quality_and_no_outcome(self):
        snapshot, _ = forecast()
        rows = list(observation_rows(snapshot, {}, self.config, FixedContext(), Counter()))
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertFalse(row["usable"])
            self.assertIsNone(row["outcome_at"])
            self.assertIsNone(row["residual_seconds"])
            self.assertIn("MISSING_ENDPOINT_OUTCOME", row["quality_flags"])

    def test_expired_boarding_keeps_both_endpoint_rows_unusable(self):
        snapshot, labels = forecast()
        snapshot["trips"][0]["stop_updates"][0]["departure_time"] = CUTOFF - 1
        rows = list(observation_rows(snapshot, labels, self.config, FixedContext(), Counter()))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row["usable"] for row in rows))
        self.assertTrue(all("EXPIRED_OR_PAST_BOARDING_FORECAST" in row["quality_flags"] for row in rows))

    def test_future_or_stale_source_and_trip_updates_are_not_usable_forecasts(self):
        for change in ("future_source", "stale_source", "future_trip", "stale_trip"):
            snapshot, labels = forecast()
            if change.endswith("source"):
                snapshot["source_updated_at"] = CUTOFF + 1 if change.startswith("future") else CUTOFF - 181
            else:
                snapshot["trips"][0]["timestamp"] = CUTOFF + 1 if change.startswith("future") else CUTOFF - 181
            counts = Counter()
            with self.subTest(change=change):
                self.assertEqual(list(observation_rows(snapshot, labels, self.config, FixedContext(), counts)), [])
                self.assertTrue(counts)

    def test_canceled_and_skipped_trips_are_counted_and_not_repaired(self):
        for kind in ("canceled", "skipped"):
            snapshot, labels = forecast()
            if kind == "canceled":
                snapshot["trips"][0]["schedule_relationship"] = "CANCELED"
            else:
                snapshot["trips"][0]["stop_updates"][1]["schedule_relationship"] = "SKIPPED"
            counts = Counter()
            with self.subTest(kind=kind):
                self.assertEqual(list(observation_rows(snapshot, labels, self.config, FixedContext(), counts)), [])
                self.assertGreater(counts["canceled_train_observations" if kind == "canceled"
                                          else "skipped_or_no_data_leg_path"], 0)

    def test_shared_arrival_event_identity_is_independent_of_boarding_stop(self):
        snapshot, _ = forecast()
        trip = snapshot["trips"][0]
        trip["route_id"] = "R"
        trip["id"] = "nqrw:20261005:060000_R..S"
        trip["trip_id"] = "060000_R..S"
        trip["feed_id"] = "nqrw"
        trip["stop_updates"] = [
            {"stop_id": "G21S", "arrival_time": CUTOFF + 280, "departure_time": CUTOFF + 300},
            {"stop_id": "R17S", "arrival_time": CUTOFF + 700, "departure_time": CUTOFF + 720},
            {"stop_id": "R29S", "arrival_time": CUTOFF + 1600, "departure_time": CUTOFF + 1620}]
        labels = {trip["id"]: {stop["stop_id"]: endpoint_label(stop["arrival_time"] + 60)
                              for stop in trip["stop_updates"]}}
        rows = list(observation_rows(snapshot, labels, self.config, FixedContext(), Counter()))
        arrivals = [row for row in rows if row["target"] == "arrival"]
        self.assertEqual(len(arrivals), 2)
        self.assertEqual(len({row["event_id"] for row in arrivals}), 1)
        self.assertEqual(len({row["id"] for row in arrivals}), 2)
        self.assertEqual(arrivals[0]["event_id"], digest([canonical_event_trip_id(trip), "arrival", "R29S"])[:32])

    def test_start_time_aliases_share_component_events_and_keep_normalized_provenance(self):
        first_snapshot, first_labels = forecast()
        second_snapshot = deepcopy(first_snapshot)
        second_snapshot["captured_at"] += 60
        second_snapshot["source_updated_at"] += 60
        first_trip, second_trip = first_snapshot["trips"][0], second_snapshot["trips"][0]
        second_trip.update(id=first_trip["id"] + ":revised-start", start_time="10:00:05")
        second_labels = {second_trip["id"]: deepcopy(first_labels[first_trip["id"]])}
        first_rows = list(observation_rows(first_snapshot, first_labels, self.config, FixedContext(), Counter()))
        second_rows = list(observation_rows(second_snapshot, second_labels, self.config, FixedContext(), Counter()))
        canonical_identity = canonical_event_trip_id(first_trip)
        self.assertEqual(canonical_event_trip_id(second_trip), canonical_identity)
        self.assertEqual(len(first_rows), 2)
        self.assertEqual(len(second_rows), 2)
        for target in ("arrival", "departure"):
            first = next(row for row in first_rows if row["target"] == target)
            second = next(row for row in second_rows if row["target"] == target)
            with self.subTest(target=target):
                self.assertTrue(first["usable"])
                self.assertTrue(second["usable"])
                self.assertEqual(first["event_id"], second["event_id"])
                self.assertEqual(first["canonical_event_trip_id"], canonical_identity)
                self.assertEqual(second["canonical_event_trip_id"], canonical_identity)
                self.assertEqual(first["trip_id"], first_trip["id"])
                self.assertEqual(second["trip_id"], second_trip["id"])
                self.assertNotEqual(first["trip_id"], second["trip_id"])

    def test_simultaneous_canonical_aliases_are_retained_as_unusable(self):
        snapshot, labels = forecast()
        first = snapshot["trips"][0]
        second = dict(deepcopy(first), id=first["id"] + ":other-start", start_time="10:00:05")
        snapshot["trips"].append(second)
        labels[second["id"]] = deepcopy(labels[first["id"]])
        rows = list(observation_rows(snapshot, labels, self.config, FixedContext(), Counter()))
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({row["canonical_event_trip_id"] for row in rows}), 1)
        for row in rows:
            self.assertFalse(row["usable"])
            self.assertIn("SIMULTANEOUS_CANONICAL_TRIP_ALIASES", row["quality_flags"])

    def test_canonical_trip_inventory_detects_boundary_crossing_across_aliases(self):
        boundary = end_of_date("2026-10-17")
        snapshot, _ = forecast()
        first = dict(snapshot["trips"][0], id="normalized-before", start_date="20261017")
        second = dict(first, id="normalized-after", start_time="10:00:05")
        canonical_identity = canonical_event_trip_id(first)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for day, trip in (("2026-10-17", first), ("2026-10-18", second)):
                write_json(directory / (day + ".trips.json.gz"), {trip["id"]: trip})
                (directory / (day + ".alerts.jsonl.gz")).write_bytes(gzip.compress(b"", mtime=0))
            _, trip_spans, _ = scan_input_inventory(directory, ["2026-10-17", "2026-10-18"], self.config)
        self.assertEqual(set(trip_spans), {canonical_identity})
        self.assertLess(trip_spans[canonical_identity][0], boundary)
        self.assertGreaterEqual(trip_spans[canonical_identity][1], boundary)
        row = representative(trip_id=first["id"], canonical_event_trip_id=canonical_identity,
                             label_confirmed_at=boundary - 1)
        self.assertEqual(train_eligible(row, self.config, trip_spans, {}),
                         (False, "TRAIN_CROSSES_DEVELOPMENT_BOUNDARY"))

    def test_label_canonical_identity_mismatch_is_not_usable(self):
        snapshot, labels = forecast()
        for label in labels[snapshot["trips"][0]["id"]].values():
            label["canonical_event_trip_id"] = "different-service-run"
        rows = list(observation_rows(snapshot, labels, self.config, FixedContext(), Counter()))
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertFalse(row["usable"])
            self.assertIn("LABEL_CANONICAL_IDENTITY_MISMATCH", row["quality_flags"])


if __name__ == "__main__":
    unittest.main()
