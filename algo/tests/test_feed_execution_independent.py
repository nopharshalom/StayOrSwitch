"""Independent passenger-behavior checks for causal feed-following replay."""

from copy import deepcopy
import unittest

from stayorswitch.feed_execution import execute_route


LEG = {"feed_id": "ace", "route_id": "A", "route_ids": ["A"],
       "from_stop_id": "A27S", "to_stop_id": "A41S"}


def route(*, access=0, egress=0, second=None, transfer=0):
    return {"id": "independent_feed_route", "name": "Independent feed route",
            "legs": [LEG] if second is None else [LEG, second],
            "access_walk_seconds": access, "egress_walk_seconds": egress,
            "transfer_walk_seconds": [] if second is None else [transfer]}


def candidate(identity, departure, *, leg=None, arrival=900, status="COMPATIBLE",
              terminal=None):
    leg = leg or LEG
    return {"event_key": identity, "canonical_trip_id": identity,
            "observed_trip_id": identity, "trip_id": identity,
            "feed_id": leg["feed_id"], "route_id": leg["route_id"],
            "from_stop_id": leg["from_stop_id"], "to_stop_id": leg["to_stop_id"],
            "departure_forecast_at": departure, "arrival_forecast_at": arrival,
            "path_status": status, "reason_codes": ["TRIP_CANCELED"] if terminal else [],
            "explicit_terminal_state": terminal}


def frame(at, candidates, *, eligible=True):
    return {"at": at, "source_at": at, "eligible": eligible,
            "sha256": "capture-" + str(at), "feed_id": "ace",
            "candidates": [dict(row, at=at, source_at=at) for row in candidates]}


def event(identity, departure, arrival, *, leg=None):
    leg = leg or LEG
    return {"event_key": identity, "trip_id": identity,
            "canonical_trip_id": identity, "trip_aliases": [identity],
            "feed_id": leg["feed_id"], "route_id": leg["route_id"],
            "from_stop_id": leg["from_stop_id"], "to_stop_id": leg["to_stop_id"],
            "departure_at": departure, "arrival_at": arrival,
            "endpoint_flags": {"boarding": [], "alighting": []}}


class FeedEvidence:
    """Only the selected endpoint accessor exposes retrospective outcomes."""

    def __init__(self, frames, events, *, other_frames=None):
        self.frames = {LEG["from_stop_id"]: deepcopy(frames), **deepcopy(other_frames or {})}
        self.events = {row["event_key"]: deepcopy(row) for row in events}
        self.endpoint_reads = []

    def frames_for(self, leg, ready, horizon):
        rows = self.frames.get(leg["from_stop_id"], [])
        prior = [i for i, row in enumerate(rows) if row["at"] <= ready]
        first = prior[-1] if prior else 0
        for index in range(first, len(rows)):
            row = deepcopy(rows[index])
            if row["at"] > horizon:
                break
            row["next_capture_at"] = rows[index + 1]["at"] if index + 1 < len(rows) else None
            yield row

    def event_for(self, leg, event_key):
        self.endpoint_reads.append(event_key)
        return deepcopy(self.events[event_key])


def chosen(result):
    return [leg["canonical_trip_id"] for leg in result.get("selected_legs", [])]


class FeedExecutionIndependentTests(unittest.TestCase):
    def test_default_first_predicted_train_ignores_later_train_outcome_and_speed(self):
        a, b = candidate("A", 120, arrival=900), candidate("B", 360, arrival=600)
        evidence = FeedEvidence([frame(0, [b, a]), frame(60, [b, a]), frame(120, [b, a])],
                                [event("A", 120, 900), event("B", None, None)])
        first = execute_route(route(), evidence, 0)
        self.assertEqual(first["status"], "INFERRED")
        self.assertEqual(chosen(first), ["A"])
        self.assertEqual(first["total_duration_seconds"], 900)
        self.assertEqual(set(evidence.endpoint_reads), {"A"})
        evidence.events["B"] = event("B", 130, 140)
        self.assertEqual(execute_route(route(), evidence, 0), first)

    def test_selected_missing_arrival_does_not_fall_back_to_complete_competitor(self):
        a, b = candidate("A", 60), candidate("B", 100)
        evidence = FeedEvidence([frame(0, [a, b]), frame(60, [a, b])],
                                [event("A", 60, None), event("B", 100, 200)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(set(evidence.endpoint_reads), {"A"})
        self.assertNotIn("total_duration_seconds", result)

    def test_selected_missing_departure_stops_at_forecast_deadline(self):
        evidence = FeedEvidence([frame(0, [candidate("A", 60), candidate("B", 100)]),
                                frame(60, [candidate("B", 100)])],
                                [event("A", None, None), event("B", 100, 200)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "SELECTED_TRAIN_DEPARTURE_UNAVAILABLE")
        self.assertEqual(set(evidence.endpoint_reads), {"A"})

    def test_visible_reordering_before_boarding_updates_choice(self):
        evidence = FeedEvidence([
            frame(0, [candidate("A", 100), candidate("B", 120)]),
            frame(60, [candidate("A", 300), candidate("B", 100)])],
            [event("A", 300, None), event("B", 100, 200)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(chosen(result), ["B"])
        self.assertEqual(result["destination_arrival_at"], 200)
        self.assertFalse(result["conditional_on_unverified_selected_wait"])

    def test_unknown_departure_allows_visible_update_before_forecast_deadline(self):
        evidence = FeedEvidence([
            frame(0, [candidate("A", 100), candidate("B", 120)]),
            frame(60, [candidate("A", 300), candidate("B", 100)])],
            [event("A", None, None), event("B", 100, 200)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(chosen(result), ["B"])
        self.assertTrue(result["conditional_on_unverified_selected_wait"])
        self.assertEqual([(row["start_at"], row["end_at"])
                          for row in result["conditional_wait_intervals"]], [(0, 60)])

    def test_explicit_cancel_before_forecast_deadline_allows_next_train(self):
        evidence = FeedEvidence([
            frame(0, [candidate("A", 100), candidate("B", 120)]),
            frame(60, [candidate("A", None, status="INCOMPATIBLE", terminal="CANCELED"),
                       candidate("B", 100)])],
            [event("A", None, None), event("B", 100, 200)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(chosen(result), ["B"])

    def test_actual_selected_departure_precedes_later_cancellation_and_reordering(self):
        evidence = FeedEvidence([
            frame(0, [candidate("A", 100), candidate("B", 120)]),
            frame(60, [candidate("A", None, status="INCOMPATIBLE", terminal="CANCELED"),
                       candidate("B", 100)])],
            [event("A", 40, 300), event("B", 100, 200)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(chosen(result), ["A"])
        self.assertEqual(result["selected_legs"][0]["departure_at"], 40)
        self.assertEqual(set(evidence.endpoint_reads), {"A"})

    def test_cancel_at_unknown_boarding_deadline_cannot_repair_past_uncertainty(self):
        evidence = FeedEvidence([
            frame(0, [candidate("A", 60), candidate("B", 100)]),
            frame(60, [candidate("A", None, status="INCOMPATIBLE", terminal="CANCELED"),
                       candidate("B", 100)])],
            [event("A", None, None), event("B", 100, 200)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "SELECTED_TRAIN_DEPARTURE_UNAVAILABLE")
        self.assertEqual(set(evidence.endpoint_reads), {"A"})

    def test_known_boarding_at_same_time_as_refresh_precedes_refresh(self):
        evidence = FeedEvidence([
            frame(0, [candidate("A", 100), candidate("B", 120)]),
            frame(60, [candidate("A", None, status="INCOMPATIBLE", terminal="CANCELED"),
                       candidate("B", 100)])],
            [event("A", 60, 300), event("B", 100, 200)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(chosen(result), ["A"])
        self.assertEqual(result["selected_legs"][0]["departure_at"], 60)
        self.assertEqual(set(evidence.endpoint_reads), {"A"})

    def test_disappearance_without_resolution_does_not_select_good_replacement(self):
        evidence = FeedEvidence([
            frame(0, [candidate("A", 100), candidate("B", 120)]),
            frame(60, [candidate("B", 100)])],
            [event("A", None, None), event("B", 100, 200)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertNotEqual(chosen(result), ["B"])
        self.assertEqual(set(evidence.endpoint_reads), {"A"})

    def test_known_missed_train_requires_next_visible_update_and_never_backdates(self):
        evidence = FeedEvidence([
            frame(0, [candidate("A", 120), candidate("B", 180)]),
            frame(120, [candidate("B", 180)])],
            [event("A", 80, 250), event("B", 180, 300)])
        result = execute_route(route(access=100), evidence, 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(chosen(result), ["B"])
        self.assertGreaterEqual(result["selected_legs"][0]["selection_at"], 120)
        self.assertGreaterEqual(result["selected_legs"][0]["departure_at"], 100)

    def test_transfer_uses_actual_arrival_and_walk_without_repeating_boarding_buffer(self):
        second = {"feed_id": "ace", "route_id": "C", "route_ids": ["C"],
                  "from_stop_id": "A41S", "to_stop_id": "A42S"}
        evidence = FeedEvidence([frame(0, [candidate("A", 10)])],
                                [event("A", 10, 100),
                                 event("C", 150, 200, leg=second)],
                                other_frames={"A41S": [frame(120, [candidate("C", 150, leg=second)])]})
        result = execute_route(route(second=second, transfer=40, egress=30), evidence, 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(chosen(result), ["A", "C"])
        self.assertEqual(result["selected_legs"][1]["platform_ready_at"], 140)
        self.assertEqual(result["total_duration_seconds"], 230)

    def test_future_feed_cannot_backdate_a_new_train_selection(self):
        evidence = FeedEvidence([
            frame(0, [candidate("A", 100)]),
            frame(60, [candidate("A", 200), candidate("B", 50)])],
            [event("A", 200, 300), event("B", 50, 80)])
        result = execute_route(route(), evidence, 0)
        self.assertNotEqual(chosen(result), ["B"])
        self.assertNotEqual(result.get("destination_arrival_at"), 80)

    def test_fresh_overdue_forecast_selects_due_now_train_with_future_actual_departure(self):
        evidence = FeedEvidence([
            frame(0, [candidate("overdue", -30), candidate("later", 100)]),
            frame(60, [candidate("later", 100)])],
            [event("overdue", 20, 200), event("later", 100, 150)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(chosen(result), ["overdue"])
        self.assertEqual(result["selected_legs"][0]["departure_at"], 20)
        self.assertEqual(set(evidence.endpoint_reads), {"overdue"})

    def test_fresh_overdue_selected_train_with_unknown_departure_is_immediately_unknown(self):
        evidence = FeedEvidence([
            frame(0, [candidate("overdue", -30), candidate("later", 100)]),
            frame(60, [candidate("later", 100)])],
            [event("overdue", None, None), event("later", 100, 150)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "SELECTED_TRAIN_DEPARTURE_UNAVAILABLE")
        self.assertEqual(set(evidence.endpoint_reads), {"overdue"})

    def test_fresh_overdue_known_miss_waits_for_next_feed_before_reselection(self):
        evidence = FeedEvidence([
            frame(0, [candidate("overdue", -30), candidate("later", 100)]),
            frame(60, [candidate("later", 100)])],
            [event("overdue", -20, 200), event("later", 100, 150)])
        result = execute_route(route(), evidence, 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(chosen(result), ["later"])
        self.assertGreaterEqual(result["selected_legs"][0]["selection_at"], 60)


if __name__ == "__main__":
    unittest.main()
