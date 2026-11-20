"""Independent archive/executor integration checks for omitted trains."""

from copy import deepcopy
import unittest

from data.tests.test_route_archive import BASE, TEMPLATE, archive, labels_for, snapshot, trip
from stayorswitch.route_execution import execute_route


def later_train():
    value = trip(start_time="00:04:00", departure=110, arrival=500)
    value["trip_id"] = "000400_A..S01R"
    value["id"] = "MTA:ace:20261102:A:000400_A..S01R:00%3A04%3A00"
    return value


class RouteArchiveIndependentTests(unittest.TestCase):
    def terminal_evidence(self, *, terminal_at=60, skipped=False,
                          restored=False, ambiguous=False, stale=False):
        unknown, later = trip(departure=90, arrival=700), later_train()
        terminal = deepcopy(unknown)
        if skipped:
            terminal["stop_updates"][1]["schedule_relationship"] = "SKIPPED"
        else:
            terminal["schedule_relationship"] = "CANCELED"
            terminal["stop_updates"] = []
        terminal_trips = [terminal, later]
        if ambiguous:
            alias = deepcopy(terminal)
            alias["id"] += "00%3A02%3A00"
            alias["start_time"] = "00:02:00"
            terminal_trips.append(alias)
        terminal_snapshot = snapshot(terminal_at, terminal_trips)
        if stale:
            terminal_snapshot["source_updated_at"] = BASE + terminal_at - 150
        snapshots = [snapshot(0, [unknown, later])]
        if terminal_at > 60:
            snapshots.append(snapshot(60, [unknown, later]))
        snapshots.append(terminal_snapshot)
        snapshots.append(snapshot(100, [unknown, later] if restored else [later]))
        labels = {**labels_for(unknown, departure=90, arrival=700),
                  **labels_for(later, departure=110, arrival=500)}
        labels[unknown["id"]]["A27S"].update(
            departure_usable=False, departure_quality_flags=["MISSING_CSV_DEPARTURE"])
        return unknown, later, archive(snapshots, labels)

    def test_explicit_empty_stop_cancel_before_ready_retires_unknown(self):
        unknown, later, evidence = self.terminal_evidence()
        events = evidence.events_for(TEMPLATE["legs"][0], BASE + 70, BASE + 200,
                                     observation_start_at=BASE - 50)
        canceled = next(e for e in events if e["trip_id"] == unknown["id"])
        self.assertTrue(any(o.get("explicit_terminal_state") == "CANCELED"
                            for o in canceled["observations"]))
        result = execute_route(TEMPLATE, evidence, BASE + 70)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][0]["trip_id"], later["id"])

    def test_explicit_destination_skip_before_ready_retires_unknown(self):
        _, later, evidence = self.terminal_evidence(skipped=True)
        result = execute_route(TEMPLATE, evidence, BASE + 70)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][0]["trip_id"], later["id"])

    def test_cancel_after_ready_cannot_erase_possible_earlier_boarding(self):
        _, _, evidence = self.terminal_evidence(terminal_at=80)
        result = execute_route(TEMPLATE, evidence, BASE + 70)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_restore_after_cancel_reopens_unresolved_boarding(self):
        _, _, evidence = self.terminal_evidence(restored=True)
        result = execute_route(TEMPLATE, evidence, BASE + 70)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_ambiguous_cancel_aliases_cannot_resolve_unknown(self):
        _, _, evidence = self.terminal_evidence(ambiguous=True)
        result = execute_route(TEMPLATE, evidence, BASE + 70)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_stale_source_cancel_cannot_resolve_unknown(self):
        _, _, evidence = self.terminal_evidence(stale=True)
        result = execute_route(TEMPLATE, evidence, BASE + 70)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def long_access_evidence(self, unknown_arrival):
        unknown, later = trip(departure=90, arrival=unknown_arrival), later_train()
        later["stop_updates"][0]["arrival_time"] = BASE + 350
        later["stop_updates"][0]["departure_time"] = BASE + 350
        later["stop_updates"][1]["arrival_time"] = BASE + 700
        later["stop_updates"][1]["departure_time"] = BASE + 700
        labels = {**labels_for(unknown, departure=90, arrival=unknown_arrival),
                  **labels_for(later, departure=350, arrival=700)}
        labels[unknown["id"]]["A27S"].update(
            departure_usable=False, departure_quality_flags=["MISSING_CSV_DEPARTURE"])
        snapshots = [snapshot(0, [unknown])]
        snapshots += [snapshot(at, []) for at in (60, 120, 180, 240)]
        snapshots += [snapshot(at, [later]) for at in (300, 340)]
        return unknown, later, archive(snapshots, labels)

    def test_unknown_at_decision_is_not_forgotten_during_long_access_walk(self):
        unknown, _, evidence = self.long_access_evidence(600)
        route = dict(TEMPLATE, access_walk_seconds=300)
        result = execute_route(route, evidence, BASE)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")
        self.assertIn(unknown["id"],
                      [row["trip_id"] for row in result["possible_earlier_boardings"]])

    def test_usable_downstream_arrival_proves_unknown_departure_train_already_gone(self):
        _, later, evidence = self.long_access_evidence(200)
        route = dict(TEMPLATE, access_walk_seconds=300)
        result = execute_route(route, evidence, BASE)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][0]["trip_id"], later["id"])
        self.assertEqual(result["total_duration_seconds"], 700)

    def test_recent_unknown_departure_cannot_disappear_from_waiting_comparison(self):
        unknown, later = trip(departure=90, arrival=300), later_train()
        labels = {**labels_for(unknown, departure=90, arrival=300),
                  **labels_for(later, departure=110, arrival=500)}
        labels[unknown["id"]]["A27S"].update(
            departure_usable=False, departure_quality_flags=["MISSING_CSV_DEPARTURE"])
        evidence = archive([snapshot(0, [unknown, later]), snapshot(60, [later]),
                            snapshot(100, [later])], labels)
        result = execute_route(TEMPLATE, evidence, BASE + 70)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")
        self.assertIn(unknown["id"],
                      [row["trip_id"] for row in result["possible_earlier_boardings"]])

    def test_known_future_departure_needs_membership_at_boarding(self):
        ghost, later = trip(departure=90, arrival=300), later_train()
        labels = {**labels_for(ghost, departure=90, arrival=300),
                  **labels_for(later, departure=110, arrival=500)}
        evidence = archive([snapshot(0, [ghost, later]), snapshot(60, [later]),
                            snapshot(100, [later])], labels)
        result = execute_route(TEMPLATE, evidence, BASE + 70)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")
        self.assertIn("PATH_NO_LONGER_PRESENT_IN_LATEST_FEED",
                      [row["blocker_reason"] for row in result["possible_earlier_boardings"]])


if __name__ == "__main__":
    unittest.main()
