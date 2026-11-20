"""Behavioral checks for fixed-route historical execution without hindsight."""

from copy import deepcopy
import unittest

from stayorswitch.route_execution import execute_route


START = 10000.0


def leg(line="A", origin="A01S", destination="A05S", feed="ace"):
    return {"route_id": line, "route_ids": [line], "feed_id": feed,
            "from_stop_id": origin, "to_stop_id": destination}


def route(*legs, access=60, egress=30, transfers=None):
    return {"id": "fixed-route", "legs": list(legs or [leg()]),
            "access_walk_seconds": access, "egress_walk_seconds": egress,
            "transfer_walk_seconds": transfers or []}


def observation(at, *, status="COMPATIBLE", source_at=None, trip_id="train"):
    return {"at": START + at, "source_at": START + (at if source_at is None else source_at),
            "path_status": status, "reason_codes": [], "trip_id": trip_id,
            "departure_forecast_at": None, "arrival_forecast_at": None}


def retirement(at, *, state="CANCELED", source_at=None, trip_id="train"):
    row = observation(at, status="INCOMPATIBLE", source_at=source_at, trip_id=trip_id)
    row["explicit_terminal_state"] = state
    row["reason_codes"] = ["TRIP_CANCELED" if state == "CANCELED" else "STOP_SKIPPED"]
    return row


def event(identity="train", departure=180, arrival=600, *, path=None, observations=None):
    path = path or leg()
    obs = observations if observations is not None else [
        observation((departure or 180) - 10, trip_id=identity)]
    return {"trip_id": identity, "canonical_trip_id": identity, "trip_aliases": [identity],
            "feed_id": path["feed_id"], "route_id": path["route_id"],
            "from_stop_id": path["from_stop_id"], "to_stop_id": path["to_stop_id"],
            "departure_at": START + departure if departure is not None else None,
            "arrival_at": START + arrival if arrival is not None else None,
            "observations": obs, "endpoint_flags": {"boarding": [], "alighting": []},
            "first_observed_at": min((row["at"] for row in obs), default=None),
            "last_observed_at": max((row["at"] for row in obs), default=None)}


class Archive:
    def __init__(self, events, *, gap_after=None, filter_legs=True):
        self.events = deepcopy(events)
        self.gap_after = START + gap_after if gap_after is not None else None
        self.filter_legs = filter_legs
        self.calls = []

    def events_for(self, selected_leg, ready, end, *, observation_start_at=None):
        self.calls.append(("events", selected_leg, ready, end, observation_start_at))
        if not self.filter_legs:
            return deepcopy(self.events)
        return [deepcopy(row) for row in self.events
                if all(row[key] == selected_leg[key]
                       for key in ("feed_id", "from_stop_id", "to_stop_id"))
                and row["route_id"] in selected_leg.get("route_ids", [selected_leg["route_id"]])]

    def coverage_for(self, feed, start, end, max_gap_seconds=120):
        self.calls.append(("coverage", feed, start, end, max_gap_seconds))
        eligible = self.gap_after is None or end <= self.gap_after
        return {"eligible": eligible, "reason": None if eligible else "ARCHIVE_GAP",
                "gaps": [] if eligible else [{"from": self.gap_after, "to": end}],
                "max_gap_seconds": max_gap_seconds, "snapshot_count": 3,
                "first_capture_at": start, "last_capture_at": end}


class RouteExecutionTests(unittest.TestCase):
    def test_boards_first_departure_even_when_later_train_arrives_faster(self):
        archive = Archive([event("slow-first", 180, 900), event("fast-later", 240, 600)])
        result = execute_route(route(), archive, START)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][0]["trip_id"], "slow-first")
        self.assertEqual(result["total_duration_seconds"], 930)

    def test_earlier_train_can_be_taken_without_forecast_selected_train_input(self):
        result = execute_route(route(), Archive([event("earlier", 90, 400),
                                               event("forecast-target", 180, 600)]), START)
        self.assertEqual(result["selected_legs"][0]["trip_id"], "earlier")
        self.assertEqual(result["total_duration_seconds"], 430)

    def test_missed_train_continues_to_next_and_includes_wait(self):
        result = execute_route(route(access=120), Archive([event("missed", 100, 500),
                                                          event("next", 300, 900)]), START)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][0]["trip_id"], "next")
        self.assertEqual(result["components"], {"walking_seconds": 150,
            "waiting_seconds": 180, "riding_seconds": 600})
        self.assertEqual(result["total_duration_seconds"], 930)

    def test_prediction_buffer_is_not_applied_to_actual_boarding(self):
        result = execute_route(route(access=120), Archive([event("just-catchable", 121, 300)]), START)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["components"]["waiting_seconds"], 1)
        self.assertEqual(result["total_duration_seconds"], 330)
        self.assertFalse(result["prediction_boarding_buffer_added_to_elapsed_time"])

    def test_departure_equal_to_readiness_is_boardable(self):
        result = execute_route(route(access=120), Archive([event(departure=120)]), START)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["components"]["waiting_seconds"], 0)

    def test_cannot_replace_first_train_with_better_recorded_later_train(self):
        result = execute_route(route(), Archive([event("first", 180, None),
                                               event("later", 240, 600)]), START)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "FIRST_BOARDABLE_TRAIN_ARRIVAL_UNAVAILABLE")
        self.assertEqual(result["event"]["trip_id"], "first")

    def test_unknown_departure_observed_while_waiting_blocks_complete_later_train(self):
        unknown = event("uncertain", None, None, observations=[observation(100, trip_id="uncertain")])
        result = execute_route(route(), Archive([unknown, event("complete", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")
        self.assertEqual(result["possible_earlier_boardings"][0]["trip_id"], "uncertain")

    def test_unknown_departure_freshly_visible_before_platform_readiness_blocks(self):
        unknown = event("uncertain", None, None, observations=[observation(30, trip_id="uncertain")])
        result = execute_route(route(), Archive([unknown, event("complete", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_old_or_future_unknown_departure_does_not_block_earlier_boarding(self):
        old = event("old", None, None, observations=[observation(-130, trip_id="old")])
        future = event("future", None, None, observations=[observation(200, trip_id="future")])
        result = execute_route(route(), Archive([old, future, event("first", 180, 600)]), START)
        self.assertEqual(result["status"], "INFERRED")

    def test_unknown_departure_window_stays_fixed_during_long_access_walk(self):
        unknown = event("uncertain", None, None,
                        observations=[observation(0, trip_id="uncertain")])
        result = execute_route(route(access=600),
            Archive([unknown, event("later", 720, 900)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_usable_downstream_arrival_proves_unknown_departure_train_already_gone(self):
        gone = event("gone", None, 500, observations=[observation(0, trip_id="gone")])
        result = execute_route(route(access=600), Archive([gone, event("next", 720, 900)]), START)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][0]["trip_id"], "next")

    def test_unknown_departure_window_does_not_restart_at_transfer(self):
        second = leg("C", "A05S", "A09S")
        unknown = event("uncertain", None, None, path=second,
                        observations=[observation(0, trip_id="uncertain")])
        archive = Archive([event("first", 180, 600), unknown,
                           event("later", 750, 900, path=second)])
        result = execute_route(route(leg(), second, transfers=[60]), archive, START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")
        self.assertEqual(result["leg_index"], 1)
        starts = [call[-1] for call in archive.calls if call[0] == "events"]
        self.assertEqual(starts, [START - 120, START - 120])

    def test_later_incompatible_notice_cannot_erase_unknown_earlier_boarding(self):
        unknown = event("uncertain", None, None, observations=[
            observation(80, trip_id="uncertain"),
            observation(160, status="INCOMPATIBLE", trip_id="uncertain")])
        result = execute_route(route(), Archive([unknown, event("complete", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_explicit_cancellation_before_ready_retires_prior_compatible_prediction(self):
        canceled = event("canceled", None, None, observations=[
            observation(0, trip_id="canceled"), retirement(30, trip_id="canceled")])
        result = execute_route(route(), Archive([canceled, event("next", 180, 600)]), START)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][0]["trip_id"], "next")
        proofs = result["selected_legs"][0]["selection_diagnostics"]["explicit_pre_readiness_retirements"]
        self.assertEqual(proofs[0]["retirement_proof"]["explicit_terminal_state"], "CANCELED")

    def test_explicit_skipped_endpoint_before_ready_retires_prior_prediction(self):
        for state in ("BOARDING_STOP_SKIPPED", "ALIGHTING_STOP_SKIPPED"):
            with self.subTest(state=state):
                skipped = event("skipped", None, None, observations=[
                    observation(0, trip_id="skipped"), retirement(30, state=state, trip_id="skipped")])
                result = execute_route(route(), Archive([skipped, event("next", 180, 600)]), START)
                self.assertEqual(result["status"], "INFERRED")

    def test_pre_ready_cancellation_persists_through_omission_during_long_walk(self):
        proof = retirement(30, trip_id="canceled")
        proof["valid_until_at"] = START + 60
        canceled = event("canceled", None, None,
                         observations=[observation(0, trip_id="canceled"), proof])
        result = execute_route(route(access=600),
            Archive([canceled, event("next", 720, 900)]), START)
        self.assertEqual(result["status"], "INFERRED")

    def test_cancellation_after_ready_cannot_erase_possible_earlier_boarding(self):
        canceled = event("canceled", None, None, observations=[
            observation(0, trip_id="canceled"), retirement(90, trip_id="canceled")])
        result = execute_route(route(), Archive([canceled, event("next", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_compatible_reactivation_after_cancellation_restores_unknown_blocker(self):
        canceled = event("canceled", None, None, observations=[
            observation(0, trip_id="canceled"), retirement(30, trip_id="canceled"),
            observation(100, trip_id="canceled")])
        result = execute_route(route(), Archive([canceled, event("next", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_uncertain_reactivation_after_cancellation_restores_unknown_blocker(self):
        canceled = event("canceled", None, None, observations=[
            observation(0, trip_id="canceled"), retirement(30, trip_id="canceled"),
            observation(100, status="UNKNOWN", trip_id="canceled")])
        result = execute_route(route(), Archive([canceled, event("next", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_reactivation_after_chosen_boarding_does_not_retroactively_change_retirement(self):
        canceled = event("canceled", None, None, observations=[
            observation(0, trip_id="canceled"), retirement(30, trip_id="canceled"),
            observation(200, trip_id="canceled")])
        result = execute_route(route(), Archive([canceled, event("next", 180, 600)]), START)
        self.assertEqual(result["status"], "INFERRED")

    def test_reactivation_then_new_pre_ready_cancellation_can_retire_again(self):
        canceled = event("canceled", None, None, observations=[
            observation(0, trip_id="canceled"), retirement(10, trip_id="canceled"),
            observation(20, trip_id="canceled"), retirement(30, trip_id="canceled")])
        result = execute_route(route(), Archive([canceled, event("next", 180, 600)]), START)
        self.assertEqual(result["status"], "INFERRED")

    def test_stale_cancellation_cannot_retire_unknown_departure(self):
        canceled = event("canceled", None, None, observations=[
            observation(0, trip_id="canceled"), retirement(30, source_at=-100, trip_id="canceled")])
        result = execute_route(route(), Archive([canceled, event("next", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_stale_incompatible_update_after_proof_keeps_unknown(self):
        canceled = event("canceled", None, None, observations=[
            observation(0, trip_id="canceled"), retirement(30, trip_id="canceled"),
            observation(100, source_at=-30, status="INCOMPATIBLE", trip_id="canceled")])
        result = execute_route(route(), Archive([canceled, event("next", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_equal_capture_reactivation_cannot_be_resolved_by_row_order(self):
        canceled = event("canceled", None, None, observations=[
            observation(0, trip_id="canceled"), retirement(30, trip_id="canceled"),
            observation(30, trip_id="canceled")])
        result = execute_route(route(), Archive([canceled, event("next", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_incompatible_without_explicit_terminal_proof_does_not_retire_prior_compatible(self):
        uncertain = event("uncertain", None, None, observations=[
            observation(0, trip_id="uncertain"),
            observation(30, status="INCOMPATIBLE", trip_id="uncertain")])
        result = execute_route(route(), Archive([uncertain, event("next", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_stale_incompatible_observation_cannot_exclude_unknown_departure(self):
        uncertain = event("uncertain", None, None, observations=[
            observation(100, source_at=-30, status="INCOMPATIBLE", trip_id="uncertain")])
        result = execute_route(route(), Archive([uncertain, event("complete", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_known_incompatible_path_is_not_boarded(self):
        wrong = event("wrong-path", 120, 300, observations=[
            observation(100, status="INCOMPATIBLE", trip_id="wrong-path")])
        result = execute_route(route(), Archive([wrong, event("correct", 180, 600)]), START)
        self.assertEqual(result["selected_legs"][0]["trip_id"], "correct")

    def test_future_compatible_path_cannot_retroactively_authorize_boarding(self):
        wrong = event("rerouted", 120, 300, observations=[
            observation(100, status="INCOMPATIBLE", trip_id="rerouted"),
            observation(130, trip_id="rerouted")])
        result = execute_route(route(), Archive([wrong, event("correct", 180, 600)]), START)
        self.assertEqual(result["selected_legs"][0]["trip_id"], "correct")

    def test_future_incompatibility_does_not_change_prior_boarding_choice(self):
        first = event("first", 120, 400, observations=[
            observation(110, trip_id="first"),
            observation(130, status="INCOMPATIBLE", trip_id="first")])
        result = execute_route(route(), Archive([first, event("later", 180, 600)]), START)
        self.assertEqual(result["selected_legs"][0]["trip_id"], "first")

    def test_unknown_path_blocks_before_later_compatible_train(self):
        uncertain = event("uncertain", 120, 300, observations=[
            observation(110, status="UNKNOWN", trip_id="uncertain")])
        result = execute_route(route(), Archive([uncertain, event("later", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_stale_train_observation_cannot_certify_boarding(self):
        stale = event("stale", 300, 600, observations=[
            observation(290, source_at=100, trip_id="stale")])
        result = execute_route(route(), Archive([stale]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_omitted_train_cannot_borrow_path_from_superseded_full_feed(self):
        earlier = observation(0, trip_id="ghost")
        earlier["valid_until_at"] = START + 60
        ghost = event("ghost", 100, 300, observations=[earlier])
        result = execute_route(route(access=10), Archive([ghost, event("next", 180, 600)]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")
        self.assertEqual(result["possible_earlier_boardings"][0]["blocker_reason"],
                         "PATH_NO_LONGER_PRESENT_IN_LATEST_FEED")

    def test_returning_train_can_use_its_new_compatible_observation(self):
        earlier = observation(0, trip_id="returned")
        earlier["valid_until_at"] = START + 60
        returned = event("returned", 100, 300, observations=[earlier,
            observation(90, trip_id="returned")])
        result = execute_route(route(access=10), Archive([returned]), START)
        self.assertEqual(result["status"], "INFERRED")

    def test_flagged_numeric_endpoint_is_not_treated_as_usable(self):
        invalid = event("first", 180, 300)
        invalid["endpoint_flags"]["alighting"] = ["UNCONFIRMED"]
        result = execute_route(route(), Archive([invalid, event("next", 240, 600)]), START)
        self.assertEqual(result["reason"], "FIRST_BOARDABLE_TRAIN_ARRIVAL_UNAVAILABLE")

    def test_simultaneous_distinct_trains_remain_ambiguous(self):
        result = execute_route(route(), Archive([event("a", 180, 600), event("b", 180, 300)]), START)
        self.assertEqual(result["reason"], "AMBIGUOUS_SIMULTANEOUS_BOARDABLE_TRAINS")

    def test_equal_capture_conflicting_path_records_remain_unknown(self):
        conflicting = event(observations=[observation(170), observation(170, status="INCOMPATIBLE")])
        result = execute_route(route(), Archive([conflicting]), START)
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_coverage_gap_before_boarding_prevents_claiming_first_train(self):
        result = execute_route(route(), Archive([event()], gap_after=100), START)
        self.assertEqual(result["reason"], "INSUFFICIENT_FEED_COVERAGE")

    def test_gap_after_boarding_is_not_a_platform_wait_coverage_failure(self):
        result = execute_route(route(), Archive([event()], gap_after=200), START)
        self.assertEqual(result["status"], "INFERRED")

    def test_missing_arrival_on_already_departed_train_does_not_block(self):
        result = execute_route(route(access=120), Archive([event("gone", 100, None),
                                                          event("next", 180, 600)]), START)
        self.assertEqual(result["status"], "INFERRED")

    def test_transfer_uses_actual_first_arrival_and_real_walking(self):
        second = leg("C", "A05S", "A09S")
        archive = Archive([event("first", 180, 600),
                           event("missed-transfer", 650, 900, path=second),
                           event("next-transfer", 750, 1100, path=second)])
        result = execute_route(route(leg(), second, transfers=[90]), archive, START)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual([r["trip_id"] for r in result["selected_legs"]], ["first", "next-transfer"])
        self.assertEqual(result["selected_legs"][1]["platform_ready_at"], START + 690)
        self.assertEqual(result["total_duration_seconds"], 1130)
        self.assertEqual(sum(result["components"].values()), 1130)

    def test_same_platform_zero_walk_transfer_is_valid(self):
        second = leg("C", "A05S", "A09S")
        result = execute_route(route(leg(), second, transfers=[0]),
            Archive([event("first", 180, 600), event("transfer", 601, 900, path=second)]), START)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][1]["platform_ready_at"], START + 600)

    def test_second_leg_unknown_preserves_completed_first_leg(self):
        second = leg("C", "A05S", "A09S")
        result = execute_route(route(leg(), second, transfers=[0]),
            Archive([event("first", 180, 600), event("second", 750, None, path=second)]), START)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(len(result["completed_legs"]), 1)
        self.assertEqual(result["leg_index"], 1)

    def test_horizon_no_train_is_censored_not_proven_no_service(self):
        result = execute_route(route(), Archive([]), START, max_elapsed_seconds=600)
        self.assertEqual(result["status"], "CENSORED")
        self.assertEqual(result["reason"], "NO_EVIDENCED_COMPATIBLE_TRAIN_WITHIN_HORIZON")
        self.assertNotIn("total_duration_seconds", result)

    def test_horizon_cannot_choose_later_faster_arriving_train(self):
        result = execute_route(route(), Archive([event("first", 180, 900),
                                               event("later", 240, 500)]), START,
                               max_elapsed_seconds=600)
        self.assertEqual(result["status"], "CENSORED")
        self.assertEqual(result["reason"], "FIRST_BOARDABLE_TRAIN_ARRIVES_AFTER_HORIZON")

    def test_horizon_includes_egress(self):
        result = execute_route(route(egress=40), Archive([event(arrival=580)]), START,
                               max_elapsed_seconds=600)
        self.assertEqual(result["reason"], "DESTINATION_AFTER_HORIZON")

    def test_horizon_includes_access_and_transfer_walk(self):
        result = execute_route(route(access=601), Archive([]), START, max_elapsed_seconds=600)
        self.assertEqual(result["reason"], "PLATFORM_READY_AFTER_HORIZON")

    def test_nonmonotonic_arrival_not_replaced_by_later_train(self):
        result = execute_route(route(), Archive([event("invalid", 180, 100),
                                               event("later", 240, 500)]), START)
        self.assertEqual(result["reason"], "NONMONOTONIC_FIRST_BOARDABLE_ENDPOINTS")

    def test_archive_cannot_silently_change_frozen_line_or_stops(self):
        result = execute_route(route(), Archive([event(path=leg("C"))], filter_legs=False), START)
        self.assertEqual(result["reason"], "ARCHIVE_LEG_IDENTITY_MISMATCH")

    def test_incomplete_provider_walking_is_not_invented(self):
        missing = route()
        missing["access_walk_seconds"] = None
        result = execute_route(missing, Archive([]), START)
        self.assertEqual(result["reason"], "INCOMPLETE_ROUTE_TEMPLATE")

    def test_invalid_configuration_rejected(self):
        for value in (0, -1, True, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                execute_route(route(), Archive([]), START, max_elapsed_seconds=value)

    def test_execution_does_not_mutate_inputs(self):
        template, events = route(), [event()]
        before = deepcopy((template, events))
        execute_route(template, Archive(events), START)
        self.assertEqual((template, events), before)


if __name__ == "__main__":
    unittest.main()
