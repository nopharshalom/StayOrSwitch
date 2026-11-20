"""Synthetic checks for route-execution evidence and unresolved candidates."""

from copy import deepcopy
from datetime import datetime, timezone
import unittest
from urllib.parse import quote

from data.route_archive import RouteArchive, build_from_snapshots


BASE = 1793595600
LEG = {"feed_id": "ace", "route_id": "A", "from_stop_id": "A27S", "to_stop_id": "A41S"}
TEMPLATE = {"id": "test_a", "access_walk_seconds": 0, "egress_walk_seconds": 0,
            "transfer_walk_seconds": [], "legs": [LEG]}


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def trip(*, route="A", start_time="", departure=100, arrival=500):
    raw = "000100_" + route + "..S01R"
    identity = "MTA:ace:20261102:" + route + ":" + raw + ":" + quote(start_time, safe="")
    return {"id": identity, "feed_id": "ace", "route_id": route,
            "trip_id": raw, "start_date": "20261102", "start_time": start_time or None,
            "timestamp": None, "schedule_relationship": "SCHEDULED", "reason_codes": [],
            "stop_updates": [
                {"stop_id": "A27S", "stop_sequence": 1, "schedule_relationship": "SCHEDULED",
                 "arrival_time": BASE + departure, "departure_time": BASE + departure},
                {"stop_id": "A41S", "stop_sequence": 2, "schedule_relationship": "SCHEDULED",
                 "arrival_time": BASE + arrival, "departure_time": BASE + arrival}]}


def snapshot(at, trips, *, status="AVAILABLE"):
    return {"feed_id": "ace", "kind": "train", "status": status,
            "replay_freshness": "FRESH", "captured_at": BASE + at,
            "fetched_at": stamp(BASE + at), "requested_at": stamp(BASE + at),
            "source_updated_at": stamp(BASE + at - 5), "incrementality": "FULL_DATASET",
            "sha256": "snapshot-" + str(at), "reason_codes": [], "trips": trips}


def labels_for(value, *, departure=100, arrival=500):
    canonical = "MTA_EVENT:ace:20261102:" + value["route_id"] + ":" + value["trip_id"]
    stops = {}
    for stop_id, time in (("A27S", departure), ("A41S", arrival)):
        stops[stop_id] = {
            "arrival_at": BASE + time, "departure_at": BASE + time,
            "arrival_usable": True, "departure_usable": True,
            "arrival_quality_flags": [], "departure_quality_flags": [], "quality_flags": [],
            "confirmation_status": "CONFIRMED", "confirmed_at": BASE + time + 5,
            "stop_last_observed_at": BASE + time + 1,
            "canonical_event_trip_id": canonical,
            "feed_id": "ace", "service_date": "20261102", "route_id": value["route_id"],
            "raw_trip_id": value["trip_id"], "stop_id": stop_id}
    return {value["id"]: stops}


def archive(snapshots, labels, templates=None):
    return RouteArchive(build_from_snapshots(snapshots, templates or [TEMPLATE], labels))


class RouteArchiveTests(unittest.TestCase):
    def test_known_departure_and_arrival_are_preserved(self):
        value = trip()
        result = archive([snapshot(0, [value])], labels_for(value)).events_for(LEG, BASE + 10, BASE + 200)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["departure_at"], BASE + 100)
        self.assertEqual(result[0]["arrival_at"], BASE + 500)
        self.assertEqual(result[0]["observations"][0]["path_status"], "COMPATIBLE")

    def test_known_departed_train_is_not_a_waiting_candidate(self):
        value = trip()
        result = archive([snapshot(100, [value])], labels_for(value)).events_for(LEG, BASE + 101, BASE + 200)
        self.assertEqual(result, [])

    def test_unknown_departure_remains_an_ordering_candidate(self):
        value = trip()
        labels = labels_for(value)
        labels[value["id"]]["A27S"].update(departure_usable=False,
                                               departure_quality_flags=["MISSING_CSV_DEPARTURE"])
        result = archive([snapshot(0, [value])], labels).events_for(LEG, BASE + 10, BASE + 200)
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["departure_at"])
        self.assertIn("MISSING_CSV_DEPARTURE", result[0]["endpoint_flags"]["boarding"])

    def test_unknown_arrival_does_not_remove_first_departure(self):
        value = trip()
        labels = labels_for(value)
        labels[value["id"]]["A41S"].update(arrival_usable=False,
                                               arrival_quality_flags=["MISSING_CSV_ARRIVAL"])
        result = archive([snapshot(0, [value])], labels).events_for(LEG, BASE + 10, BASE + 200)
        self.assertEqual(result[0]["departure_at"], BASE + 100)
        self.assertIsNone(result[0]["arrival_at"])

    def test_whole_trip_quality_flags_are_not_waived(self):
        value = trip()
        labels = labels_for(value)
        labels[value["id"]]["A41S"]["quality_flags"] = ["CSV_SCHEDULE_CHANGED"]
        result = archive([snapshot(0, [value])], labels).events_for(LEG, BASE + 10, BASE + 200)
        self.assertIsNone(result[0]["arrival_at"])
        self.assertIn("CSV_SCHEDULE_CHANGED", result[0]["endpoint_flags"]["alighting"])

    def test_missing_label_record_is_retained(self):
        value = trip()
        result = archive([snapshot(0, [value])], {}).events_for(LEG, BASE + 10, BASE + 200)
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["departure_at"])
        self.assertIsNone(result[0]["arrival_at"])

    def test_exact_route_membership_is_respected(self):
        a, c = trip(), trip(route="C")
        templates = [TEMPLATE, dict(TEMPLATE, id="test_c", legs=[dict(LEG, route_id="C")])]
        labels = {**labels_for(a), **labels_for(c)}
        indexed = archive([snapshot(0, [a, c])], labels, templates)
        self.assertEqual([x["route_id"] for x in indexed.events_for(LEG, BASE + 10, BASE + 200)], ["A"])
        expanded = dict(LEG, route_ids=["A", "C"])
        self.assertEqual({x["route_id"] for x in indexed.events_for(expanded, BASE + 10, BASE + 200)}, {"A", "C"})

    def test_sequential_aliases_merge_without_choosing_best_time(self):
        first, second = trip(start_time="00:01:00"), trip(start_time="00:02:00")
        labels = {**labels_for(first), **labels_for(second)}
        indexed = archive([snapshot(0, [first]), snapshot(60, [second])], labels)
        result = indexed.events_for(LEG, BASE + 10, BASE + 200)
        self.assertEqual(len(result), 1)
        self.assertEqual(set(result[0]["trip_aliases"]), {first["id"], second["id"]})
        self.assertEqual(result[0]["departure_at"], BASE + 100)

    def test_simultaneous_aliases_are_ambiguous_observations(self):
        first, second = trip(start_time="00:01:00"), trip(start_time="00:02:00")
        labels = {**labels_for(first), **labels_for(second)}
        result = archive([snapshot(0, [first, second])], labels).events_for(LEG, BASE + 10, BASE + 200)
        self.assertEqual(len(result), 1)
        self.assertTrue(all(x["path_status"] == "UNKNOWN" for x in result[0]["observations"]))

    def test_conflicting_alias_outcomes_do_not_choose_favorable_departure(self):
        first, second = trip(start_time="00:01:00"), trip(start_time="00:02:00", departure=130)
        labels = {**labels_for(first), **labels_for(second, departure=130)}
        result = archive([snapshot(0, [first]), snapshot(60, [second])], labels).events_for(
            LEG, BASE + 10, BASE + 200)
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["departure_at"])

    def test_recent_unknown_departure_survives_later_snapshot_omission(self):
        value = trip()
        labels = labels_for(value)
        labels[value["id"]]["A27S"].update(departure_usable=False,
                                               departure_quality_flags=["MISSING_CSV_DEPARTURE"])
        indexed = archive([snapshot(0, [value]), snapshot(60, [])], labels)
        result = indexed.events_for(LEG, BASE + 70, BASE + 150)
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["departure_at"])
        self.assertEqual(result[0]["observations"][0]["valid_until_at"], BASE + 60)
        # Feed omission does not establish departure or cancellation.

    def test_unknown_departure_outside_observability_lookback_is_excluded(self):
        value = trip()
        labels = labels_for(value)
        labels[value["id"]]["A27S"].update(departure_usable=False,
                                               departure_quality_flags=["MISSING_CSV_DEPARTURE"])
        indexed = archive([snapshot(0, [value]), snapshot(60, []), snapshot(120, [])], labels)
        # The archive's explicitly bounded membership policy uses a 120-second lookback.
        self.assertEqual(indexed.events_for(LEG, BASE + 121, BASE + 200), [])

    def test_explicit_case_observation_start_retains_transfer_blocker(self):
        value = trip()
        labels = labels_for(value)
        labels[value["id"]]["A27S"].update(departure_usable=False,
                                               departure_quality_flags=["MISSING_CSV_DEPARTURE"])
        indexed = archive([snapshot(0, [value]), snapshot(60, []), snapshot(300, [])], labels)
        self.assertEqual(indexed.events_for(LEG, BASE + 300, BASE + 600), [])
        result = indexed.events_for(LEG, BASE + 300, BASE + 600, observation_start_at=BASE)
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["departure_at"])
        self.assertEqual(result[0]["observations"][0]["at"], BASE)

    def test_confirmed_arrival_before_readiness_excludes_unknown_departure(self):
        value = trip()
        labels = labels_for(value, arrival=200)
        labels[value["id"]]["A27S"].update(departure_usable=False,
                                               departure_quality_flags=["MISSING_CSV_DEPARTURE"])
        indexed = archive([snapshot(0, [value]), snapshot(300, [])], labels)
        self.assertEqual(indexed.events_for(LEG, BASE + 300, BASE + 600,
                                            observation_start_at=BASE), [])

    def test_missing_normalized_identity_is_retained_as_unknown(self):
        value = trip()
        value.pop("id")
        result = archive([snapshot(0, [value])], {}).events_for(LEG, BASE + 10, BASE + 200)
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["departure_at"])
        self.assertTrue(all(row["path_status"] == "UNKNOWN" for row in result[0]["observations"]))

    def test_known_future_departure_retains_expired_path_evidence(self):
        value = trip()
        indexed = archive([snapshot(0, [value]), snapshot(60, [])], labels_for(value))
        result = indexed.events_for(LEG, BASE + 70, BASE + 150)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["departure_at"], BASE + 100)
        self.assertEqual(result[0]["observations"][0]["valid_until_at"], BASE + 60)
        # The executor must not use this expired pattern to certify boarding at 100.
        self.assertLess(result[0]["observations"][0]["valid_until_at"], result[0]["departure_at"])

    def test_reverse_path_cannot_become_compatible(self):
        value = trip()
        value["stop_updates"].reverse()
        result = archive([snapshot(0, [value])], labels_for(value)).events_for(LEG, BASE + 10, BASE + 200)
        self.assertTrue(all(x["path_status"] != "COMPATIBLE" for x in result[0]["observations"]))

    def test_skipped_stop_is_not_compatible(self):
        value = trip()
        value["stop_updates"][0]["schedule_relationship"] = "SKIPPED"
        result = archive([snapshot(0, [value])], labels_for(value)).events_for(LEG, BASE + 10, BASE + 200)
        self.assertEqual(result[0]["observations"][0]["path_status"], "INCOMPATIBLE")

    def test_no_data_stop_remains_unresolved(self):
        value = trip()
        value["stop_updates"][0]["schedule_relationship"] = "NO_DATA"
        result = archive([snapshot(0, [value])], labels_for(value)).events_for(LEG, BASE + 10, BASE + 200)
        self.assertEqual(result[0]["observations"][0]["path_status"], "UNKNOWN")

    def test_explicit_cancel_without_stops_updates_known_train_path(self):
        value = trip()
        canceled = dict(value, schedule_relationship="CANCELED", stop_updates=[])
        result = archive([snapshot(0, [value]), snapshot(60, [canceled])], {}).events_for(
            LEG, BASE + 70, BASE + 200, observation_start_at=BASE)
        self.assertEqual(len(result), 1)
        terminal = result[0]["observations"][-1]
        self.assertEqual(terminal["at"], BASE + 60)
        self.assertEqual(terminal["path_status"], "INCOMPATIBLE")
        self.assertEqual(terminal["explicit_terminal_state"], "CANCELED")
        self.assertIn("TRIP_CANCELED", terminal["reason_codes"])
        self.assertIsNone(result[0]["departure_at"])

    def test_simultaneous_alias_cancel_cannot_resolve_unknown_identity(self):
        first, second = trip(start_time="00:01:00"), trip(start_time="00:02:00")
        canceled = dict(second, schedule_relationship="CANCELED", stop_updates=[])
        result = archive([snapshot(0, [first]), snapshot(60, [first, canceled])], {}).events_for(
            LEG, BASE + 70, BASE + 200, observation_start_at=BASE)
        terminal = result[0]["observations"][-1]
        self.assertEqual(terminal["path_status"], "UNKNOWN")
        self.assertIsNone(terminal["explicit_terminal_state"])

    def test_cancel_without_previously_observed_path_does_not_invent_route(self):
        canceled = dict(trip(), schedule_relationship="CANCELED", stop_updates=[])
        result = archive([snapshot(0, [canceled])], {}).events_for(LEG, BASE + 10, BASE + 200)
        self.assertEqual(result, [])

    def test_explicit_stop_skip_is_distinguished_from_missing_stop(self):
        value = trip()
        skipped = deepcopy(value)
        skipped["stop_updates"][0]["schedule_relationship"] = "SKIPPED"
        result = archive([snapshot(0, [value]), snapshot(60, [skipped])], {}).events_for(
            LEG, BASE + 70, BASE + 200, observation_start_at=BASE)
        self.assertEqual(result[0]["observations"][-1]["explicit_terminal_state"], "BOARDING_STOP_SKIPPED")

    def test_post_departure_path_evidence_is_not_backdated(self):
        value = trip(departure=50)
        result = archive([snapshot(60, [value])], labels_for(value, departure=50)).events_for(
            LEG, BASE + 10, BASE + 200)
        self.assertEqual(len(result), 1)
        self.assertTrue(all(x["at"] > result[0]["departure_at"] for x in result[0]["observations"]))

    def test_ancient_snapshot_membership_does_not_persist_forever(self):
        value = trip(departure=300)
        result = archive([snapshot(0, [value])], labels_for(value, departure=300)).events_for(
            LEG, BASE + 121, BASE + 200)
        self.assertEqual(result, [])

    def test_recent_prior_snapshot_supports_waiting_membership(self):
        value = trip()
        result = archive([snapshot(0, [value])], labels_for(value)).events_for(LEG, BASE + 119, BASE + 200)
        # Its known departure has already passed even though the capture is recent.
        self.assertEqual(result, [])
        value = trip(departure=200)
        result = archive([snapshot(0, [value])], labels_for(value, departure=200)).events_for(
            LEG, BASE + 119, BASE + 250)
        self.assertEqual(len(result), 1)

    def test_regular_capture_coverage_is_eligible(self):
        indexed = archive([snapshot(at, []) for at in (0, 60, 120)], {})
        self.assertTrue(indexed.coverage_for("ace", BASE + 10, BASE + 100)["eligible"])

    def test_capture_gap_prevents_complete_route_coverage(self):
        indexed = archive([snapshot(at, []) for at in (0, 300)], {})
        coverage = indexed.coverage_for("ace", BASE + 10, BASE + 290)
        self.assertFalse(coverage["eligible"])
        self.assertTrue(coverage["gaps"])

    def test_build_does_not_mutate_input_evidence(self):
        value = trip()
        snapshots, labels = [snapshot(0, [value])], labels_for(value)
        original = deepcopy((snapshots, labels))
        archive(snapshots, labels)
        self.assertEqual((snapshots, labels), original)


if __name__ == "__main__":
    unittest.main()
