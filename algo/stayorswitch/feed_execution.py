"""Execute a fixed route using only each currently visible feed for choices.

Outcome labels validate movement of the selected train. They never rank input
candidates, remove an unselected train, or choose a better-recorded alternative.
Waiting with an unknown selected departure before its forecast boarding time is
an explicit feed-conditioned assumption, recorded separately in every result.
"""

from collections import Counter
from copy import deepcopy
import math

from data.delay_profiles.common import epoch
from .severe import validate_templates


EXECUTION_POLICY = "CAUSAL_VISIBLE_FEED_EARLIEST_DEPARTURE"
MAX_ELAPSED_SECONDS = 7200
MAX_OBSERVATION_GAP_SECONDS = 120


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _positive(value, name):
    if not _finite(value) or value <= 0:
        raise ValueError(name + " must be finite and positive.")
    return float(value)


def _event_key(candidate):
    return candidate.get("event_key") or candidate.get("canonical_trip_id")


def _same_leg(value, leg):
    return (value.get("feed_id") == leg["feed_id"]
            and value.get("route_id") in leg.get("route_ids", [leg["route_id"]])
            and value.get("from_stop_id") == leg["from_stop_id"]
            and value.get("to_stop_id") == leg["to_stop_id"])


def _endpoint(event, name):
    side = "boarding" if name == "departure" else "alighting"
    value = event.get(name + "_at")
    if (event.get("endpoint_flags") or {}).get(side) or not _finite(value):
        return None
    return value


def _event_reference(event, candidate):
    result = {key: deepcopy(event.get(key)) for key in (
        "trip_id", "canonical_trip_id", "trip_aliases", "feed_id", "route_id",
        "from_stop_id", "to_stop_id", "departure_at", "arrival_at", "endpoint_flags",
        "outcome_quality")}
    result["event_key"] = _event_key(candidate)
    result["canonical_trip_id"] = result["canonical_trip_id"] or candidate.get("canonical_trip_id")
    result["trip_id"] = result["trip_id"] or candidate.get("trip_id") or candidate.get("observedtrip_id")
    result["selected_input_trip_id"] = candidate.get("trip_id") or candidate.get("observedtrip_id")
    return result


def _frame_error(frame, clock, max_gap):
    at, source = frame.get("at"), frame.get("source_at")
    if not _finite(at) or at > clock:
        return "INVALID_OR_FUTURE_FEED_CAPTURE"
    if not frame.get("eligible"):
        return "UNUSABLE_FEED_CAPTURE"
    if (not _finite(source) or source > at or clock - at > max_gap
            or clock - source > max_gap):
        return "STALE_FEED_AT_PASSENGER_TIME"
    return None


def _input_candidates(frame, leg, clock, max_gap):
    """Validate visible inputs without inspecting event labels."""
    rows = frame.get("candidates", [])
    counts = Counter(_event_key(row) for row in rows)
    accepted, rejected = [], []
    for row in rows:
        key = _event_key(row)
        at, source, departure = row.get("at"), row.get("source_at"), row.get("departure_forecast_at")
        reason = None
        if not key or counts[key] != 1:
            reason = "AMBIGUOUS_INPUT_IDENTITY"
        elif not _same_leg(row, leg):
            reason = "INPUT_LEG_IDENTITY_MISMATCH"
        elif (not _finite(at) or at != frame["at"] or not _finite(source)
              or source > at or clock - source > max_gap):
            reason = "STALE_OR_INVALID_CANDIDATE_OBSERVATION"
        elif row.get("path_status") != "COMPATIBLE" or row.get("reason_codes"):
            reason = "INCOMPATIBLE_OR_UNCERTAIN_VISIBLE_PATH"
        elif not _finite(departure):
            reason = "MISSING_VISIBLE_DEPARTURE_ETA"
        if reason:
            rejected.append({"event_key": key, "reason": reason})
        else:
            accepted.append(row)
    accepted.sort(key=lambda row: (max(clock, row["departure_forecast_at"]),
                                   str(row.get("canonical_trip_id") or _event_key(row)),
                                   str(_event_key(row))))
    return accepted, rejected


def _selected_event(archive, leg, candidate):
    """The sole label lookup: called only after an input-only selection."""
    try:
        value = archive.event_for(leg, _event_key(candidate)) or {}
    except KeyError:
        value = {}
    except ValueError:
        return {}, "SELECTED_EVENT_IDENTITY_UNAVAILABLE"
    if value and not _same_leg(value, leg):
        return {}, "SELECTED_EVENT_LEG_IDENTITY_MISMATCH"
    canonical = value.get("canonical_trip_id")
    if canonical is not None and canonical != candidate.get("canonical_trip_id"):
        return {}, "SELECTED_EVENT_TRAIN_IDENTITY_MISMATCH"
    return value, None


def _leg_execution(leg, archive, ready, horizon, max_gap, leg_index, trace, counters, conditional):
    frames = list(archive.frames_for(leg, ready, horizon))
    if not frames or frames[0].get("at", float("inf")) > ready:
        return {"status": "UNAVAILABLE", "reason": "MISSING_INITIAL_ASOF_FEED"}
    if any(not _finite(row.get("at")) for row in frames) or any(
            right["at"] <= left["at"] for left, right in zip(frames, frames[1:])):
        return {"status": "UNAVAILABLE", "reason": "INVALID_FEED_CAPTURE_CHRONOLOGY"}
    selected = None
    selected_event = None
    selection_at = None
    selection_snapshot_at = None
    missed_seen = set()

    for position, frame in enumerate(frames):
        clock = ready if position == 0 else frame["at"]
        if clock > horizon:
            break
        error = _frame_error(frame, clock, max_gap)
        if error:
            return {"status": "UNAVAILABLE", "reason": error, "at": clock,
                    "snapshot_at": frame.get("at")}
        counters["feed_updates"] += 1
        accepted, rejected = _input_candidates(frame, leg, clock, max_gap)
        inputs = [{"event_key": _event_key(row), "canonical_trip_id": row.get("canonical_trip_id"),
                   "departure_forecast_at": row["departure_forecast_at"],
                   "effective_departure_at": max(clock, row["departure_forecast_at"]),
                   "due_now": row["departure_forecast_at"] <= clock} for row in accepted]

        # A previously selected service may change only through this new feed,
        # not because another train has a more convenient endpoint record.
        if selected is not None:
            previous_departure = _endpoint(selected_event, "departure")
            previously_missed = previous_departure is not None and previous_departure < clock
            matching = [row for row in frame.get("candidates", [])
                        if _event_key(row) == _event_key(selected)]
            if not previously_missed:
                if not matching:
                    counters["selected_unknown"] += 1
                    return {"status": "UNAVAILABLE", "reason": "SELECTED_SERVICE_DISAPPEARED",
                            "selected_event": _event_reference(selected_event, selected), "at": clock}
                current = matching[0] if len(matching) == 1 else {}
                current_source = current.get("source_at")
                fresh_current = (current.get("at") == frame["at"] and _finite(current_source)
                                 and current_source <= frame["at"] and clock - current_source <= max_gap)
                if (len(matching) != 1 or current.get("path_status") not in {"COMPATIBLE", "INCOMPATIBLE"}
                        or not fresh_current or not _same_leg(current, leg)
                        or (current.get("path_status") == "COMPATIBLE"
                            and (current.get("reason_codes") or not _finite(current.get("departure_forecast_at"))))):
                    counters["selected_unknown"] += 1
                    return {"status": "UNAVAILABLE", "reason": "SELECTED_SERVICE_INPUT_UNCERTAIN",
                            "selected_event": _event_reference(selected_event, selected), "at": clock}
                if current.get("path_status") == "INCOMPATIBLE":
                    trace.append({"action": "VISIBLE_SERVICE_EXCLUSION", "leg_index": leg_index,
                                  "at": clock, "snapshot_at": frame["at"],
                                  "event_key": _event_key(selected),
                                  "reason_codes": list(matching[0].get("reason_codes", [])),
                                  "explicit_terminal_state": matching[0].get("explicit_terminal_state")})

        chosen = accepted[0] if accepted else None
        previous_key = _event_key(selected) if selected else None
        chosen_key = _event_key(chosen) if chosen else None
        action = "NO_CANDIDATE" if chosen is None else "KEEP" if previous_key == chosen_key else "SELECT" if previous_key is None else "RESELECT"
        trace.append({"action": action, "leg_index": leg_index, "at": clock,
                      "snapshot_at": frame["at"], "source_at": frame["source_at"],
                      "snapshot_sha256": frame.get("sha256"), "event_key": chosen_key,
                      "departure_forecast_at": chosen.get("departure_forecast_at") if chosen else None,
                      "candidate_departures": inputs, "rejected_inputs": rejected,
                      "selection_reads_endpoint_labels": False})
        if previous_key != chosen_key:
            counters["chosen_train_updates"] += chosen is not None
        if chosen is not None and (selected is None or previous_key != chosen_key):
            selected_event, error = _selected_event(archive, leg, chosen)
            if error:
                counters["selected_unknown"] += 1
                return {"status": "UNAVAILABLE", "reason": error, "at": clock}
            selection_at, selection_snapshot_at = clock, frame["at"]
        selected = chosen
        if selected is None:
            selected_event = None

        if position + 1 < len(frames):
            next_capture = frames[position + 1]["at"]
            supplied_next = frame.get("next_capture_at")
            if supplied_next is not None and supplied_next != next_capture:
                return {"status": "UNAVAILABLE", "reason": "INCONSISTENT_NEXT_FEED_CAPTURE"}
        else:
            next_capture = frame.get("next_capture_at")
            if next_capture is None:
                next_capture = float("inf")
            elif not _finite(next_capture) or next_capture <= frame["at"]:
                return {"status": "UNAVAILABLE", "reason": "INVALID_NEXT_FEED_CAPTURE"}
        expiry = min(frame["at"] + max_gap, frame["source_at"] + max_gap)
        interval_end = min(next_capture, horizon, expiry)

        if selected is not None:
            departure = _endpoint(selected_event, "departure")
            if departure is not None and departure < clock:
                if chosen_key not in missed_seen:
                    missed_seen.add(chosen_key)
                    counters["known_missed_attempts"] += 1
                    trace.append({"action": "MISSED_SELECTED_SERVICE", "leg_index": leg_index,
                                  "at": clock, "event_key": chosen_key, "departure_at": departure,
                                  "selection_uses_this_departure": False})
            elif departure is not None and departure <= interval_end:
                trace.append({"action": "BOARD", "leg_index": leg_index, "at": departure,
                              "event_key": chosen_key, "selection_at": selection_at,
                              "selection_snapshot_at": selection_snapshot_at,
                              "outcome_quality": deepcopy(selected_event.get("outcome_quality")),
                              "boarding_precedes_equal_time_feed_update": True})
                event = _event_reference(selected_event, selected)
                arrival = _endpoint(selected_event, "arrival")
                details = {"event": event, "selection_at": selection_at,
                           "selection_snapshot_at": selection_snapshot_at,
                           "outcome_quality": deepcopy(selected_event.get("outcome_quality")),
                           "boarding_forecast_at": selected["departure_forecast_at"]}
                if arrival is None:
                    counters["selected_unknown"] += 1
                    if "IMPLAUSIBLE_LEG_TRAVEL_TIME" in (selected_event.get("endpoint_flags") or {}).get("alighting", []):
                        return dict(details, status="UNAVAILABLE", reason="SELECTED_OUTCOME_IMPLAUSIBLE_TRAVEL_TIME")
                    return dict(details, status="UNAVAILABLE", reason="SELECTED_TRAIN_ARRIVAL_UNAVAILABLE")
                if arrival < departure:
                    return dict(details, status="UNAVAILABLE", reason="NONMONOTONIC_SELECTED_ENDPOINTS")
                if arrival > horizon:
                    return dict(details, status="CENSORED", reason="SELECTED_TRAIN_ARRIVES_AFTER_HORIZON")
                return dict(details, status="INFERRED")
            elif departure is None:
                deadline = max(clock, selected["departure_forecast_at"])
                if deadline <= interval_end:
                    counters["selected_unknown"] += 1
                    trace.append({"action": "UNVERIFIED_BOARDING_BOUNDARY", "leg_index": leg_index,
                                  "at": deadline, "event_key": chosen_key,
                                  "forecast_departure_at": deadline})
                    return {"status": "UNAVAILABLE", "reason": "SELECTED_TRAIN_DEPARTURE_UNAVAILABLE",
                            "selected_event": _event_reference(selected_event, selected),
                            "forecast_boarding_at": deadline, "at": deadline}
                if interval_end > clock:
                    row = {"leg_index": leg_index, "event_key": chosen_key,
                           "start_at": clock, "end_at": interval_end,
                           "forecast_departure_at": deadline,
                           "assumption": "WAIT_BEFORE_VISIBLE_FORECAST_BOARDING_TIME"}
                    conditional.append(row)
                    trace.append(dict(row, action="CONDITIONAL_WAIT"))
                    counters["conditional_wait_intervals"] += 1
                    counters["unverified_selected_wait_intervals"] += 1

        if horizon <= next_capture and horizon <= expiry:
            return {"status": "CENSORED", "reason": "NO_SELECTED_BOARDING_WITHIN_HORIZON"}
        if expiry < next_capture:
            return {"status": "UNAVAILABLE", "reason": "FEED_COVERAGE_GAP_WHILE_WAITING",
                    "at": expiry, "next_capture_at": next_capture if _finite(next_capture) else None}

    return {"status": "CENSORED", "reason": "NO_SELECTED_BOARDING_WITHIN_HORIZON"}


def execute_route(template, archive, cutoff, *, max_elapsed_seconds=MAX_ELAPSED_SECONDS,
                  max_observation_gap_seconds=MAX_OBSERVATION_GAP_SECONDS):
    """Follow current raw-feed choices, then validate only selected trains.

    No prediction boarding margin is applied again at the platform. A currently
    selected train with an evidenced departure boards before an equal-time
    feed update. If its departure is unknown, reaching the current forecast
    boarding time also precedes that update and ends with selected uncertainty.
    """
    duration = _positive(max_elapsed_seconds, "max_elapsed_seconds")
    max_gap = _positive(max_observation_gap_seconds, "max_observation_gap_seconds")
    start = epoch(cutoff)
    if not _finite(start):
        raise ValueError("cutoff must be a finite timestamp.")
    try:
        validate_templates([template])
    except (KeyError, TypeError, ValueError) as error:
        return {"status": "UNAVAILABLE", "reason": "INCOMPLETE_ROUTE_TEMPLATE",
                "detail": str(error), "completed_legs": [], "execution_policy": EXECUTION_POLICY,
                "update_trace": [], "trace_counters": {}, "conditional_waiting": False,
                "conditional_wait_intervals": [], "conditional_on_unverified_selected_wait": False}
    horizon = start + duration
    access, egress = float(template["access_walk_seconds"]), float(template["egress_walk_seconds"])
    transfers = [float(value) for value in template["transfer_walk_seconds"]]
    ready = start + access
    trace, conditional, completed = [], [], []
    counters = Counter({"feed_updates": 0, "chosen_train_updates": 0,
                        "selected_unknown": 0, "known_missed_attempts": 0,
                        "conditional_wait_intervals": 0, "unverified_selected_wait_intervals": 0})
    waiting = riding = 0.0

    def result(**details):
        return dict(route_id=template["id"], execution_policy=EXECUTION_POLICY,
                    decision_at=start, horizon_at=horizon, max_elapsed_seconds=duration,
                    max_observation_gap_seconds=max_gap,
                    prediction_boarding_buffer_added_to_elapsed_time=False,
                    evidence="FEED_POLICY_SELECTED_SCREENED_ENDPOINTS_PLUS_AUTHORED_WALKS",
                    update_trace=trace, trace_counters=dict(counters),
                    conditional_waiting=bool(conditional), conditional_wait_intervals=conditional,
                    conditional_on_unverified_selected_wait=bool(conditional),
                    **details)

    for position, leg in enumerate(template["legs"]):
        if ready > horizon:
            return result(status="CENSORED", reason="PLATFORM_READY_AFTER_HORIZON",
                          leg_index=position, platform_ready_at=ready, completed_legs=completed)
        selected = _leg_execution(leg, archive, ready, horizon, max_gap,
                                  position, trace, counters, conditional)
        if selected["status"] != "INFERRED":
            return result(**selected, leg_index=position, platform_ready_at=ready,
                          completed_legs=completed)
        event = selected["event"]
        departure, arrival = event["departure_at"], event["arrival_at"]
        waiting += departure - ready
        riding += arrival - departure
        completed.append(dict(event, leg_index=position, platform_ready_at=ready,
                              selection_at=selected["selection_at"],
                              selection_snapshot_at=selected["selection_snapshot_at"],
                              boarding_forecast_at=selected["boarding_forecast_at"]))
        ready = arrival + (transfers[position] if position < len(transfers) else egress)
    if ready > horizon:
        return result(status="CENSORED", reason="DESTINATION_AFTER_HORIZON",
                      destination_arrival_at=ready, completed_legs=completed)
    walking = access + sum(transfers)
    walking += egress
    if not math.isclose(walking + waiting + riding, ready - start, abs_tol=0.000001, rel_tol=0):
        raise ValueError("Feed execution components are inconsistent.")
    return result(status="INFERRED", destination_arrival_at=ready,
                  total_duration_seconds=ready - start, selected_legs=completed,
                  components={"walking_seconds": walking, "waiting_seconds": waiting,
                              "riding_seconds": riding})
