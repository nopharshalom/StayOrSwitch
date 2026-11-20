"""Replay a frozen route by boarding its first evidenced compatible train.

This is an outcome evaluator, not a prediction method. It may read subsequent
archived observations to reconstruct movement, but never chooses a route or a
train by its eventual destination arrival. It deliberately remains unknown
when an earlier possible boarding cannot be resolved from the archive.

The archive protocol is provided by ``data.route_archive.RouteArchive``:
``events_for(leg, ready_at, end_at, observation_start_at=...)`` and
``coverage_for(feed_id, start_at, end_at, max_gap_seconds=...)``. Events contain
screened endpoint proxies and chronological origin/path observations. The
prediction boarding margin is not an input here and is not added to elapsed
walking, waiting or riding time.
"""

from copy import deepcopy
import math

from data.delay_profiles.common import epoch

from .severe import validate_templates


MAX_ELAPSED_SECONDS = 7200
MAX_OBSERVATION_GAP_SECONDS = 120
EXECUTION_POLICY = "FIRST_COMPATIBLE_EVIDENCED_DEPARTURE"
_RETIREMENT_REASONS = {"CANCELED": "TRIP_CANCELED",
                       "BOARDING_STOP_SKIPPED": "STOP_SKIPPED",
                       "ALIGHTING_STOP_SKIPPED": "STOP_SKIPPED"}


def _finite(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _positive(value, name):
    if not _finite(value) or value <= 0:
        raise ValueError(name + " must be finite and positive.")
    return float(value)


def _event_reference(event):
    return {key: deepcopy(event.get(key)) for key in (
        "trip_id", "canonical_trip_id", "trip_aliases", "feed_id", "route_id",
        "from_stop_id", "to_stop_id", "departure_at", "arrival_at",
        "endpoint_flags", "first_observed_at", "last_observed_at")}


def _endpoint(event, name):
    flag_name = "boarding" if name == "departure" else "alighting"
    value = event.get(name + "_at")
    if (event.get("endpoint_flags") or {}).get(flag_name) or not _finite(value):
        return None
    return value


def _observation_signature(observation):
    return (observation.get("path_status"), observation.get("source_at"),
            tuple(sorted(observation.get("reason_codes", []))),
            observation.get("departure_forecast_at"),
            observation.get("arrival_forecast_at"), observation.get("trip_id"))


def _latest_observation(event, at, max_gap):
    previous = [row for row in event.get("observations", [])
                if _finite(row.get("at")) and row["at"] <= at]
    if not previous:
        return None, "NO_PATH_OBSERVATION_BEFORE_BOARDING"
    capture = max(row["at"] for row in previous)
    latest = [row for row in previous if row["at"] == capture]
    if len({_observation_signature(row) for row in latest}) != 1:
        return None, "CONFLICTING_EQUAL_CAPTURE_PATH_OBSERVATIONS"
    row = latest[0]
    valid_until = row.get("valid_until_at")
    if valid_until is not None:
        if not _finite(valid_until) or valid_until <= capture:
            return row, "INVALID_OBSERVATION_MEMBERSHIP_INTERVAL"
        if at >= valid_until:
            return row, "PATH_NO_LONGER_PRESENT_IN_LATEST_FEED"
    source = row.get("source_at")
    if (at - capture > max_gap or not _finite(source)
            or source > capture or at - source > max_gap):
        return row, "STALE_PATH_OBSERVATION_AT_BOARDING"
    if row.get("path_status") not in {"COMPATIBLE", "INCOMPATIBLE"}:
        return row, "UNRESOLVED_PATH_AT_BOARDING"
    return row, None


def _unknown_departure_can_precede(event, ready, end, observation_start, max_gap):
    """Keep unknown timing if it might affect the first boarding choice.

    The evidence window is fixed at the original decision cutoff minus the
    declared lookback, not moved forward when walking or transfers take time.
    Disappearance cannot establish that an unresolved train has already left.
    A screened downstream arrival before readiness can establish that fact.
    """
    arrival = _endpoint(event, "arrival")
    if arrival is not None and arrival < ready:
        return False
    relevant = [row for row in event.get("observations", [])
                if _finite(row.get("at")) and observation_start <= row["at"] <= end]
    if not relevant:
        return False
    for row in relevant:
        source = row.get("source_at")
        if (row.get("path_status") != "INCOMPATIBLE"
                or not _finite(source) or source > row["at"]
                or row["at"] - source > max_gap):
            return True
    return False


def _fresh_incompatible_observation(row, max_gap):
    at, source = row.get("at"), row.get("source_at")
    return (row.get("path_status") == "INCOMPATIBLE" and _finite(at)
            and _finite(source) and 0 <= at - source <= max_gap)


def _explicit_retirement_before_ready(event, ready, end, observation_start, max_gap):
    """Retire only explicit pre-readiness exclusion, never disappearance.

    A cancellation or explicitly skipped endpoint observed before platform
    readiness resolves earlier compatible predictions. The proof is fresh at
    its own capture and can persist across omitted later snapshots. It cannot
    erase a possible boarding before a later cancellation, and a subsequent
    compatible or uncertain observation invalidates retirement. This is an
    execution-policy exclusion, not an invented arrival/departure endpoint.
    """
    rows = [row for row in event.get("observations", [])
            if _finite(row.get("at")) and observation_start <= row["at"] <= end]
    proofs = []
    for row in rows:
        required_reason = _RETIREMENT_REASONS.get(row.get("explicit_terminal_state"))
        if (row["at"] <= ready and required_reason is not None
                and row.get("reason_codes") == [required_reason]
                and _fresh_incompatible_observation(row, max_gap)):
            proofs.append(row)
    if not proofs:
        return None
    proof = max(proofs, key=lambda row: row["at"])
    if any(not _fresh_incompatible_observation(row, max_gap)
           for row in rows if row["at"] >= proof["at"]):
        return None
    return deepcopy(proof)


def _matching_event(event, leg):
    lines = leg.get("route_ids", [leg["route_id"]])
    return (event.get("feed_id") == leg["feed_id"]
            and event.get("route_id") in lines
            and event.get("from_stop_id") == leg["from_stop_id"]
            and event.get("to_stop_id") == leg["to_stop_id"]
            and bool(event.get("trip_id")))


def _first_boarding(leg, archive, ready, horizon, max_gap, observation_start):
    events = list(archive.events_for(leg, ready, horizon,
                                   observation_start_at=observation_start))
    if any(not _matching_event(event, leg) for event in events):
        return {"status": "UNAVAILABLE", "reason": "ARCHIVE_LEG_IDENTITY_MISMATCH"}

    known, uncertain, unknown_departures = [], [], []
    excluded_before_ready = incompatible = 0
    for event in events:
        departure = _endpoint(event, "departure")
        if departure is None:
            unknown_departures.append(event)
            continue
        if departure < ready:
            excluded_before_ready += 1
            continue
        if departure > horizon:
            continue
        observation, reason = _latest_observation(event, departure, max_gap)
        if reason:
            uncertain.append((departure, event, reason))
        elif observation["path_status"] == "INCOMPATIBLE":
            incompatible += 1
        else:
            known.append((departure, event, observation))

    known.sort(key=lambda item: (item[0], item[1]["trip_id"]))
    first_at = known[0][0] if known else horizon
    coverage = archive.coverage_for(leg["feed_id"], ready, first_at,
                                    max_gap_seconds=max_gap)
    if not coverage.get("eligible"):
        return {"status": "UNAVAILABLE", "reason": "INSUFFICIENT_FEED_COVERAGE",
                "coverage": coverage}

    blockers = [dict(_event_reference(event), blocker_reason=reason)
                for departure, event, reason in uncertain if departure <= first_at]
    retirements = []
    for event in unknown_departures:
        proof = _explicit_retirement_before_ready(event, ready, first_at, observation_start, max_gap)
        if proof is not None:
            retirements.append(dict(_event_reference(event), retirement_proof=proof))
        elif _unknown_departure_can_precede(event, ready, first_at, observation_start, max_gap):
            blockers.append(dict(_event_reference(event), blocker_reason="UNKNOWN_DEPARTURE"))
    diagnostics = {"queried_events": len(events),
                   "known_departures_before_platform_ready": excluded_before_ready,
                   "known_incompatible_departures": incompatible,
                   "explicit_pre_readiness_retirements": retirements,
                   "coverage": coverage}
    if blockers:
        return {"status": "UNAVAILABLE", "reason": "UNRESOLVED_EARLIER_BOARDING",
                "possible_earlier_boardings": blockers, "selection_diagnostics": diagnostics}
    if not known:
        return {"status": "CENSORED", "reason": "NO_EVIDENCED_COMPATIBLE_TRAIN_WITHIN_HORIZON",
                "selection_diagnostics": diagnostics}

    simultaneous = [item for item in known if item[0] == first_at]
    if len(simultaneous) != 1:
        return {"status": "UNAVAILABLE", "reason": "AMBIGUOUS_SIMULTANEOUS_BOARDABLE_TRAINS",
                "possible_first_boardings": [_event_reference(item[1]) for item in simultaneous],
                "selection_diagnostics": diagnostics}
    _, chosen, observation = known[0]
    # Arrival quality is intentionally inspected only after selecting the first
    # boardable departure. A well-recorded later train cannot replace this one.
    arrival = _endpoint(chosen, "arrival")
    base = {"event": _event_reference(chosen), "boarding_observation": deepcopy(observation),
            "selection_diagnostics": diagnostics}
    if not _finite(arrival):
        return dict(base, status="UNAVAILABLE", reason="FIRST_BOARDABLE_TRAIN_ARRIVAL_UNAVAILABLE")
    if arrival < first_at:
        return dict(base, status="UNAVAILABLE", reason="NONMONOTONIC_FIRST_BOARDABLE_ENDPOINTS")
    if arrival > horizon:
        return dict(base, status="CENSORED", reason="FIRST_BOARDABLE_TRAIN_ARRIVES_AFTER_HORIZON")
    return dict(base, status="INFERRED")


def execute_route(template, archive, cutoff, *, max_elapsed_seconds=MAX_ELAPSED_SECONDS,
                  max_observation_gap_seconds=MAX_OBSERVATION_GAP_SECONDS):
    """Follow one fixed provider route using subsequent archived evidence.

    Every mode must call this with the same provider template, cutoff and
    archive. Forecast-selected trains and corrected durations are intentionally
    not arguments. Returned ``INFERRED`` means screened MTA endpoint proxies,
    not independent passenger observations. Missing records and unconfirmed
    disappearances are never treated as zero waiting or proven cancellation.
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
                "detail": str(error), "completed_legs": [], "execution_policy": EXECUTION_POLICY}

    horizon = start + duration
    access, egress = float(template["access_walk_seconds"]), float(template["egress_walk_seconds"])
    transfers = [float(value) for value in template["transfer_walk_seconds"]]
    ready = start + access
    waiting = riding = 0.0
    completed = []
    common = {"route_id": template["id"], "execution_policy": EXECUTION_POLICY,
              "decision_at": start, "horizon_at": horizon,
              "observation_start_at": start - max_gap,
              "max_elapsed_seconds": duration, "max_observation_gap_seconds": max_gap,
              "prediction_boarding_buffer_added_to_elapsed_time": False,
              "evidence": "SCREENED_FINAL_PREDICTION_ENDPOINTS_PLUS_AUTHORED_WALKS"}

    for position, leg in enumerate(template["legs"]):
        if ready > horizon:
            return dict(common, status="CENSORED", reason="PLATFORM_READY_AFTER_HORIZON",
                        leg_index=position, platform_ready_at=ready, completed_legs=completed)
        selection = _first_boarding(leg, archive, ready, horizon, max_gap, start - max_gap)
        if selection["status"] != "INFERRED":
            return dict(common, **selection, leg_index=position,
                        platform_ready_at=ready, completed_legs=completed)
        event = selection["event"]
        departure, arrival = event["departure_at"], event["arrival_at"]
        waiting += departure - ready
        riding += arrival - departure
        completed.append(dict(event, leg_index=position, platform_ready_at=ready,
                              boarding_observation=selection["boarding_observation"],
                              selection_diagnostics=selection["selection_diagnostics"]))
        ready = arrival + (transfers[position] if position < len(transfers) else egress)

    if ready > horizon:
        return dict(common, status="CENSORED", reason="DESTINATION_AFTER_HORIZON",
                    destination_arrival_at=ready, completed_legs=completed)
    walking = access + sum(transfers) + egress
    elapsed = ready - start
    if not math.isclose(walking + waiting + riding, elapsed, abs_tol=0.000001, rel_tol=0):
        raise ValueError("Route execution component arithmetic is inconsistent.")
    return dict(common, status="INFERRED", destination_arrival_at=ready,
                total_duration_seconds=elapsed, selected_legs=completed,
                components={"walking_seconds": walking, "waiting_seconds": waiting,
                            "riding_seconds": riding})
