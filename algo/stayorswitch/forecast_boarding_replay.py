"""Replay both supplied routes using fresh departure forecasts and screened arrivals."""
from collections import Counter
import math

from data.experiment_evidence import stop_bounds

MAX_ELAPSED_SECONDS = 7200
TIMING_FLAGS = {
    "MISSING_CSV_ARRIVAL",
    "MISSING_CSV_DEPARTURE",
    "MISSING_CSV_LABEL",
    "MISSING_OR_INVALID_ARCHIVED_CONFIRMATION",
    "MISSING_OR_INVALID_ENDPOINT_OBSERVATION_AGE",
    "MISSING_OR_INVALID_ENDPOINT_TIME",
    "MISSING_STOP_PASSAGE_CONFIRMATION",
    "UNUSABLE_ENDPOINT_LABEL",
    "ENDPOINT_OBSERVATION_AGE_EXCEEDS_LIMIT",
    "PREDICTED_DEPARTURE_AFTER_STOP_DISAPPEARANCE",
    "PREDICTED_ARRIVAL_AFTER_STOP_DISAPPEARANCE",
    "LARGE_STOP_OBSERVATION_GAP",
}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


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


def choose_leg(archive, positions, screen, leg, ready, horizon):
    trace = []
    expiry = None
    for frame in archive.frames_for(leg, ready, horizon):
        clock = max(ready, frame["at"])
        if expiry is None and frame["at"] > ready:
            return None, trace, "MISSING_INITIAL_ASOF_FEED"
        if expiry is not None and clock > expiry:
            return None, trace, "FEED_GAP"
        if _frame_error(frame, clock, 120):
            return None, trace, "UNUSABLE_FEED"
        expiry = min(frame["at"], frame["source_at"]) + 120
        accepted, _ = _input_candidates(frame, leg, clock, 120)
        for c in accepted:
            prediction = c["departure_forecast_at"]
            if prediction <= clock:
                continue
            # The forecast selects the train. Outcome quality never ranks candidates.
            e, error = _selected_event(archive, leg, c)
            if error or not e:
                return None, trace, error or "UNAVAILABLE_SELECTED_EVENT"
            key = c["event_key"]
            record = dict(
                platform_ready=ready,
                selected_at=clock,
                snapshot_at=frame["at"],
                train=key,
                forecast_departure=prediction,
            )
            trace.append(record)
            records = positions.get(key.partition(":")[2], ())
            record["boarding"] = "FORECAST_ASSUMPTION"
            arr = _endpoint(e, "arrival")
            arrival = (
                (arr, arr)
                if arr is not None
                else stop_bounds(records, leg["to_stop_id"]).get("arrival")
            )
            record["arrival_source"] = (
                "JOURNAL" if arr is not None else "VEHICLE" if arrival else None
            )
            if not arrival:
                return None, trace, "MISSING_RECORDED_ARRIVAL"
            flags = set(e["endpoint_flags"]["boarding"]) | set(
                e["endpoint_flags"]["alighting"]
            )
            if (
                flags
                - TIMING_FLAGS
                - {"CSV_SCHEDULE_CHANGED", "CSV_SCHEDULE_REWRITTEN"}
            ):
                return None, trace, "UNRESOLVED_IDENTITY_OR_QUALITY_CONFLICT"
            # When departure is only assumed, even the most generous possible ride
            # (boarding at readiness) must be physically plausible. The forecast is
            # used for catchability only; it does not timestamp a physical departure.
            checked = dict(
                e,
                departure_at=clock,
                arrival_at=arrival[0],
                endpoint_flags={"boarding": [], "alighting": []},
            )
            if screen.screen(checked)["outcome_quality"]["status"] != "PASSED":
                return None, trace, "IMPLAUSIBLE_ENDPOINTS"
            if arrival[1] > horizon:
                return None, trace, "HORIZON"
            record["arrival_bounds"] = arrival
            return arrival, trace, None
    return None, trace, "NO_LATER_VISIBLE_DEPARTURE"


def replay_side(archive, positions, screen, template, start):
    ready = start + template["access_walk_seconds"]
    horizon = start + MAX_ELAPSED_SECONDS
    trace = []
    for i in range(len(template["legs"])):
        arr, choices, error = choose_leg(
            archive,
            positions,
            screen,
            template["legs"][i],
            ready,
            horizon,
        )
        trace.extend(choices)
        if error:
            return dict(bounds=None, reason=error, trace=trace)
        if i == len(template["legs"]) - 1:
            ends = [t + template["egress_walk_seconds"] for t in arr]
            if ends[1] > horizon:
                return dict(bounds=None, reason="HORIZON", trace=trace)
            return dict(bounds=[t - start for t in ends], trace=trace)
        if arr[0] != arr[1]:
            return dict(bounds=None, reason="UNCERTAIN_TRANSFER_READINESS", trace=trace)
        ready = arr[0] + template["transfer_walk_seconds"][i]
    raise ValueError("Route has no legs")
