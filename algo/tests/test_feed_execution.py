"""Feed-policy behavior, uncertainty boundaries and trajectory arithmetic."""

from copy import deepcopy
import unittest

from stayorswitch.feed_execution import execute_route


LEG = {"feed_id": "ace", "route_id": "A", "from_stop_id": "A27S", "to_stop_id": "A41S"}
ROUTE = {"id": "a", "legs": [LEG], "access_walk_seconds": 0,
         "transfer_walk_seconds": [], "egress_walk_seconds": 0}


def candidate(name, at, departure, *, path="COMPATIBLE", source=None, reasons=None, leg=LEG):
    return dict(leg, event_key=name, canonical_trip_id=name, trip_id="trip-" + name,
                at=at, source_at=at if source is None else source, path_status=path,
                reason_codes=reasons or [], departure_forecast_at=departure,
                arrival_forecast_at=None if departure is None else departure + 300)


def frame(at, candidates, *, source=None, eligible=True, next_at=None):
    return {"at": at, "source_at": at if source is None else source, "eligible": eligible,
            "sha256": "frame-" + str(at), "candidates": candidates, "next_capture_at": next_at}


def event(name, departure, arrival, *, leg=LEG, departure_flags=None, arrival_flags=None):
    return dict(leg, trip_id="trip-" + name, canonical_trip_id=name, departure_at=departure,
                arrival_at=arrival, endpoint_flags={"boarding": departure_flags or [],
                                                   "alighting": arrival_flags or []})


class Archive:
    def __init__(self, frames, events):
        self.frames, self.events, self.reads = frames, events, []

    def frames_for(self, leg, ready, horizon):
        rows = self.frames[leg["from_stop_id"]] if isinstance(self.frames, dict) else self.frames
        previous = [row for row in rows if row["at"] <= ready]
        if previous:
            yield previous[-1]
        yield from (row for row in rows if ready < row["at"] <= horizon)

    def event_for(self, leg, key):
        self.reads.append(key)
        return self.events.get(key)


class FeedExecutionTests(unittest.TestCase):
    def run_route(self, rows, events, *, route=ROUTE, cutoff=1000, horizon=7200):
        archive = Archive(rows, events)
        return execute_route(route, archive, cutoff, max_elapsed_seconds=horizon), archive

    def test_outcome_quality_never_changes_input_choice(self):
        rows = [frame(1000, [candidate("A", 1000, 1050), candidate("B", 1000, 1060)])]
        result, archive = self.run_route(rows, {"A": event("A", None, None), "B": event("B", 1060, 1200)})
        self.assertEqual(result["reason"], "SELECTED_TRAIN_DEPARTURE_UNAVAILABLE")
        self.assertEqual(archive.reads, ["A"])

    def test_unknown_unselected_train_does_not_block_complete_route(self):
        rows = [frame(1000, [candidate("A", 1000, 1050), candidate("B", 1000, 1060)])]
        result, archive = self.run_route(rows, {"A": event("A", 1050, 1300)})
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(archive.reads, ["A"])
        self.assertEqual(result["total_duration_seconds"], 300)

    def test_missing_selected_arrival_is_not_replaced(self):
        rows = [frame(1000, [candidate("A", 1000, 1050), candidate("B", 1000, 1060)])]
        result, archive = self.run_route(rows, {"A": event("A", 1050, None), "B": event("B", 1060, 1200)})
        self.assertEqual(result["reason"], "SELECTED_TRAIN_ARRIVAL_UNAVAILABLE")
        self.assertEqual(archive.reads, ["A"])

    def test_implausible_selected_ride_is_unknown_without_better_record_fallback(self):
        rows = [frame(1000, [candidate("A", 1000, 1050), candidate("B", 1000, 1060)])]
        bad = event("A", 1050, 1060, arrival_flags=["IMPLAUSIBLE_LEG_TRAVEL_TIME"])
        bad["outcome_quality"] = {"status": "IMPLAUSIBLE", "direct_distance_meters": 6000,
                                  "observed_duration_seconds": 10, "maximum_speed_kph": 300}
        result, archive = self.run_route(rows, {"A": bad, "B": event("B", 1060, 1400)})
        self.assertEqual(result["reason"], "SELECTED_OUTCOME_IMPLAUSIBLE_TRAVEL_TIME")
        self.assertEqual(archive.reads, ["A"])
        self.assertEqual(result["event"]["arrival_at"], 1060)
        self.assertEqual(result["outcome_quality"], bad["outcome_quality"])
        self.assertEqual(result["event"]["outcome_quality"], bad["outcome_quality"])
        boarding = next(row for row in result["update_trace"] if row["action"] == "BOARD")
        self.assertEqual(boarding["outcome_quality"], bad["outcome_quality"])
        good_result, _ = self.run_route(rows, {"A": event("A", 1050, 1300), "B": event("B", 1060, 1400)})
        self.assertEqual(result["update_trace"][0], good_result["update_trace"][0])

    def test_unselected_implausible_ride_does_not_affect_selection(self):
        rows = [frame(1000, [candidate("A", 1000, 1050), candidate("B", 1000, 1060)])]
        bad = event("B", 1060, 1067, arrival_flags=["IMPLAUSIBLE_LEG_TRAVEL_TIME"])
        result, archive = self.run_route(rows, {"A": event("A", 1050, 1300), "B": bad})
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(archive.reads, ["A"])

    def test_implausible_selected_first_leg_cannot_drive_a_later_transfer(self):
        following = {"feed_id": "bdfm", "route_id": "F", "from_stop_id": "A41S", "to_stop_id": "F24S"}
        route = dict(ROUTE, legs=[LEG, following], transfer_walk_seconds=[60])
        rows = {"A27S": [frame(1000, [candidate("A", 1000, 1050)])]}
        result, archive = self.run_route(rows, {"A": event("A", 1050, 1060,
            arrival_flags=["IMPLAUSIBLE_LEG_TRAVEL_TIME"])}, route=route)
        self.assertEqual(result["reason"], "SELECTED_OUTCOME_IMPLAUSIBLE_TRAVEL_TIME")
        self.assertEqual(result["leg_index"], 0)
        self.assertEqual(result["completed_legs"], [])
        self.assertEqual(archive.reads, ["A"])

    def test_endpoint_flags_remain_effective(self):
        result, _ = self.run_route([frame(1000, [candidate("A", 1000, 1050)])],
                                  {"A": event("A", 1050, 1300, departure_flags=["UNCONFIRMED"])})
        self.assertEqual(result["reason"], "SELECTED_TRAIN_DEPARTURE_UNAVAILABLE")

    def test_actual_boarding_at_equal_update_precedes_cancellation(self):
        rows = [frame(1000, [candidate("A", 1000, 1100)]),
                frame(1060, [candidate("A", 1060, None, path="INCOMPATIBLE", reasons=["TRIP_CANCELED"])])]
        result, _ = self.run_route(rows, {"A": event("A", 1060, 1300)})
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["trace_counters"]["feed_updates"], 1)

    def test_unknown_departure_boundary_precedes_equal_update(self):
        rows = [frame(1000, [candidate("A", 1000, 1060)]),
                frame(1060, [candidate("B", 1060, 1100)])]
        result, archive = self.run_route(rows, {"A": event("A", None, None), "B": event("B", 1100, 1300)})
        self.assertEqual(result["reason"], "SELECTED_TRAIN_DEPARTURE_UNAVAILABLE")
        self.assertEqual(archive.reads, ["A"])

    def test_reordering_unknown_selected_train_before_deadline_is_conditional(self):
        rows = [frame(1000, [candidate("A", 1000, 1100), candidate("B", 1000, 1150)]),
                frame(1060, [candidate("A", 1060, 1200), candidate("B", 1060, 1110)])]
        result, archive = self.run_route(rows, {"A": event("A", None, None), "B": event("B", 1110, 1300)})
        self.assertEqual(result["status"], "INFERRED")
        self.assertTrue(result["conditional_on_unverified_selected_wait"])
        self.assertEqual(result["trace_counters"]["unverified_selected_wait_intervals"], 1)
        self.assertEqual(result["selected_legs"][0]["canonical_trip_id"], "B")
        self.assertEqual(archive.reads, ["A", "B"])

    def test_missing_selected_train_cannot_trigger_quality_fallback(self):
        rows = [frame(1000, [candidate("A", 1000, 1100)]),
                frame(1060, [candidate("B", 1060, 1110)])]
        result, archive = self.run_route(rows, {"A": event("A", None, None), "B": event("B", 1110, 1300)})
        self.assertEqual(result["reason"], "SELECTED_SERVICE_DISAPPEARED")
        self.assertEqual(archive.reads, ["A"])

    def test_stale_selected_state_does_not_silently_reorder(self):
        rows = [frame(1000, [candidate("A", 1000, 1100)]),
                frame(1060, [candidate("A", 1060, 1200, source=900), candidate("B", 1060, 1110)])]
        result, archive = self.run_route(rows, {"A": event("A", None, None), "B": event("B", 1110, 1300)})
        self.assertEqual(result["reason"], "SELECTED_SERVICE_INPUT_UNCERTAIN")
        self.assertEqual(archive.reads, ["A"])

    def test_known_missed_attempt_waits_for_visible_update(self):
        rows = [frame(1000, [candidate("A", 1000, 1100), candidate("B", 1000, 1080)]),
                frame(1060, [candidate("A", 1060, 1150), candidate("B", 1060, 1090)])]
        # B is selected solely because its displayed ETA is earlier, but its
        # valid departure is already past. No alternate is chosen at t1000.
        result, archive = self.run_route(rows, {"A": event("A", 1150, 1400), "B": event("B", 990, 1200)})
        self.assertNotEqual(result["status"], "INFERRED")
        self.assertEqual(archive.reads, ["B"])
        self.assertEqual(result["trace_counters"]["known_missed_attempts"], 1)

    def test_known_miss_can_be_followed_by_later_feed_choice(self):
        rows = [frame(1000, [candidate("A", 1000, 1040), candidate("B", 1000, 1090)]),
                frame(1060, [candidate("B", 1060, 1090)])]
        result, _ = self.run_route(rows, {"A": event("A", 990, 1200), "B": event("B", 1090, 1400)})
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][0]["canonical_trip_id"], "B")
        self.assertEqual(result["selected_legs"][0]["selection_at"], 1060)

    def test_fresh_expired_eta_is_due_now_and_not_discarded(self):
        rows = [frame(1000, [candidate("A", 1000, 990), candidate("B", 1000, 1090)])]
        result, archive = self.run_route(rows, {"A": event("A", 1020, 1300), "B": event("B", 1090, 1400)})
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(archive.reads, ["A"])
        self.assertTrue(result["update_trace"][0]["candidate_departures"][0]["due_now"])

    def test_unknown_due_now_selected_train_is_immediately_unknown(self):
        rows = [frame(1000, [candidate("A", 1000, 990), candidate("B", 1000, 1090)])]
        result, archive = self.run_route(rows, {"A": event("A", None, None), "B": event("B", 1090, 1400)})
        self.assertEqual(result["reason"], "SELECTED_TRAIN_DEPARTURE_UNAVAILABLE")
        self.assertEqual(result["at"], 1000)
        self.assertEqual(archive.reads, ["A"])

    def test_tie_uses_canonical_identity_not_final_arrival(self):
        rows = [frame(1000, [candidate("B", 1000, 1050), candidate("A", 1000, 1050)])]
        result, archive = self.run_route(rows, {"A": event("A", 1050, 1600), "B": event("B", 1050, 1200)})
        self.assertEqual(archive.reads, ["A"])
        self.assertEqual(result["destination_arrival_at"], 1600)

    def test_unknown_unselected_input_does_not_block_valid_input(self):
        rows = [frame(1000, [candidate("X", 1000, None, path="UNKNOWN"), candidate("A", 1000, 1050)])]
        result, archive = self.run_route(rows, {"A": event("A", 1050, 1300)})
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(archive.reads, ["A"])

    def test_duplicate_visible_identity_is_not_selected(self):
        a = candidate("A", 1000, 1050)
        rows = [frame(1000, [a, deepcopy(a), candidate("B", 1000, 1060)])]
        result, archive = self.run_route(rows, {"B": event("B", 1060, 1300)})
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(archive.reads, ["B"])

    def test_selected_event_cannot_change_route_identity(self):
        bad = event("A", 1050, 1300)
        bad["route_id"] = "C"
        result, _ = self.run_route([frame(1000, [candidate("A", 1000, 1050)])], {"A": bad})
        self.assertEqual(result["reason"], "SELECTED_EVENT_LEG_IDENTITY_MISMATCH")

    def test_departure_before_coverage_expiry_can_complete(self):
        rows = [frame(1000, [candidate("A", 1000, 1050)], next_at=1400)]
        result, _ = self.run_route(rows, {"A": event("A", 1050, 1300)})
        self.assertEqual(result["status"], "INFERRED")

    def test_departure_after_coverage_expiry_cannot_use_future_label(self):
        rows = [frame(1000, [candidate("A", 1000, 1300)], next_at=1400)]
        result, _ = self.run_route(rows, {"A": event("A", 1300, 1600)})
        self.assertEqual(result["reason"], "FEED_COVERAGE_GAP_WHILE_WAITING")

    def test_stale_initial_capture_is_unknown(self):
        result, archive = self.run_route([frame(800, [candidate("A", 800, 1050)])], {"A": event("A", 1050, 1300)})
        self.assertEqual(result["reason"], "STALE_FEED_AT_PASSENGER_TIME")
        self.assertEqual(archive.reads, [])

    def test_source_age_limits_wait_even_when_capture_is_recent(self):
        rows = [frame(1000, [candidate("A", 1000, 1100, source=950)], source=950)]
        result, _ = self.run_route(rows, {"A": event("A", 1100, 1300)})
        self.assertEqual(result["reason"], "FEED_COVERAGE_GAP_WHILE_WAITING")

    def test_route_horizon_censors_instead_of_inventing_duration(self):
        result, _ = self.run_route([frame(1000, [candidate("A", 1000, 1050)])],
                                  {"A": event("A", 1050, 1400)}, horizon=200)
        self.assertEqual(result["status"], "CENSORED")
        self.assertNotIn("total_duration_seconds", result)

    def test_walking_and_waiting_are_counted_once(self):
        route = dict(ROUTE, access_walk_seconds=30, egress_walk_seconds=40)
        result, _ = self.run_route([frame(1000, [candidate("A", 1000, 1050)])],
                                  {"A": event("A", 1050, 1300)}, route=route)
        self.assertEqual(result["total_duration_seconds"], 340)
        self.assertEqual(result["components"], {"walking_seconds": 70, "waiting_seconds": 20, "riding_seconds": 250})

    def test_no_candidate_waits_for_next_current_feed(self):
        rows = [frame(1000, []), frame(1060, [candidate("A", 1060, 1100)])]
        result, archive = self.run_route(rows, {"A": event("A", 1100, 1300)})
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][0]["selection_at"], 1060)
        self.assertEqual(archive.reads, ["A"])


if __name__ == "__main__":
    unittest.main()
