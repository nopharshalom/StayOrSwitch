"""Offline composition of separately estimated departure and riding components.

These helpers validate arithmetic and connection behavior. They neither infer
physical outcomes nor establish passenger journey accuracy. Model feature and
support checks belong to the model loader; these functions do not call a route
provider or change the live Step 4 comparator.
"""

import math


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be a finite number.")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(name + " must be a finite number.") from None
    if not math.isfinite(result):
        raise ValueError(name + " must be a finite number.")
    return result


def _nonnegative(value, name):
    result = _finite(value, name)
    if result < 0:
        raise ValueError(name + " must be nonnegative.")
    return result


def _context(decision_at, ready_at):
    decision = _finite(decision_at, "decision_at")
    ready = _finite(ready_at, "ready_at")
    if ready < decision:
        raise ValueError("ready_at must not precede decision_at.")
    return decision, ready


def compose_candidate(candidate, *, decision_at, ready_at):
    """Apply each residual once and determine whether this train is catchable.

    Times are Unix seconds. ``departure_correction_seconds`` predicts a
    departure-time residual; ``segment_correction_seconds`` predicts a riding
    duration residual. An arrival residual cannot be substituted for either.
    Invalid predictions are explicitly unavailable, never silently clipped or
    substituted. Callers may independently choose the unmodified baseline as a
    documented fallback before invoking this helper.
    """
    decision, ready = _context(decision_at, ready_at)
    if not isinstance(candidate, dict):
        return {"trip_id": None, "status": "UNAVAILABLE", "reason_code": "INVALID_CANDIDATE"}
    result = {"trip_id": candidate.get("trip_id"), "status": "UNAVAILABLE"}
    if not isinstance(result["trip_id"], str) or not result["trip_id"].strip():
        return dict(result, reason_code="INVALID_TRIP_ID")
    if "arrival_correction_seconds" in candidate:
        return dict(result, reason_code="ARRIVAL_RESIDUAL_NOT_APPLICABLE_TO_COMPOSITION")
    try:
        departure = _finite(candidate["departure_at"], "departure_at")
        arrival = _finite(candidate["arrival_at"], "arrival_at")
        departure_delta = _finite(candidate.get("departure_correction_seconds", 0),
                                  "departure_correction_seconds")
        segment_delta = _finite(candidate.get("segment_correction_seconds", 0),
                                "segment_correction_seconds")
    except (KeyError, ValueError):
        return dict(result, reason_code="INVALID_COMPONENT_VALUE")
    if arrival < departure:
        return dict(result, reason_code="INVALID_BASELINE_TIME_ORDER")
    corrected_departure = departure + departure_delta
    corrected_duration = arrival - departure + segment_delta
    corrected_arrival = corrected_departure + corrected_duration
    if not all(math.isfinite(value) for value in
               (corrected_departure, corrected_duration, corrected_arrival)):
        return dict(result, reason_code="COMPONENT_ARITHMETIC_OVERFLOW")
    if corrected_duration < 0:
        return dict(result, reason_code="NEGATIVE_CORRECTED_RIDING_TIME")
    if corrected_departure < decision:
        return dict(result, reason_code="CORRECTED_DEPARTURE_BEFORE_DECISION")
    result.update({"departure_at": corrected_departure, "arrival_at": corrected_arrival,
                   "riding_seconds": corrected_duration,
                   "departure_correction_seconds": departure_delta,
                   "segment_correction_seconds": segment_delta})
    if corrected_departure < ready:
        return dict(result, reason_code="NOT_CATCHABLE_AT_READY_TIME")
    waiting = corrected_departure - ready
    if not math.isfinite(waiting):
        return dict(result, reason_code="COMPONENT_ARITHMETIC_OVERFLOW")
    return dict(result, status="USABLE", reason_code="COMPONENTS_COMPOSED",
                waiting_seconds=waiting)


def choose_catchable(candidates, *, decision_at, ready_at):
    """Select the earliest corrected arrival among the supplied candidates.

    An earlier arrival can wait for every later downstream connection on a
    fixed path. Therefore departure order is not an appropriate ranking when
    trains overtake. Exact arrival/departure ties preserve input order.
    """
    _context(decision_at, ready_at)
    evaluated = [compose_candidate(candidate, decision_at=decision_at, ready_at=ready_at)
                 for candidate in candidates]
    usable = [(row["arrival_at"], row["departure_at"], index, row)
              for index, row in enumerate(evaluated) if row["status"] == "USABLE"]
    return {"selected": min(usable, key=lambda item: item[:3])[3] if usable else None,
            "candidates": evaluated}


def evaluate_supplied_path(*, decision_at, access_walk_seconds, transit_legs,
                           egress_walk_seconds):
    """Replay a supplied fixed sequence of transit legs with walking readiness.

    Each leg is ``{"candidates": [...], "transfer_walk_seconds_after": seconds}``.
    Transfer walking is allowed only between transit legs; egress walking is
    supplied separately. Candidate predictions all describe the same decision
    time, and the simulated readiness cursor does not fetch future information.
    No itinerary or train is invented if a connection becomes unavailable.
    """
    decision = _finite(decision_at, "decision_at")
    access = _nonnegative(access_walk_seconds, "access_walk_seconds")
    egress = _nonnegative(egress_walk_seconds, "egress_walk_seconds")
    legs = list(transit_legs)
    transfers = []
    for index, leg in enumerate(legs):
        if not isinstance(leg, dict) or "candidates" not in leg:
            raise ValueError("Every transit leg must supply candidates.")
        transfer = _nonnegative(leg.get("transfer_walk_seconds_after", 0),
                                "transfer_walk_seconds_after")
        if index == len(legs) - 1 and transfer:
            raise ValueError("Use egress_walk_seconds after the final transit leg.")
        transfers.append(transfer)
    cursor = decision + access
    if not math.isfinite(cursor):
        raise ValueError("Walking arithmetic overflowed.")
    walking, waiting, riding = access + egress + sum(transfers), 0.0, 0.0
    results = []
    for leg, transfer in zip(legs, transfers):
        result = choose_catchable(leg["candidates"], decision_at=decision, ready_at=cursor)
        results.append(result)
        selected = result["selected"]
        if selected is None:
            return {"status": "UNAVAILABLE", "reason_code": "NO_CATCHABLE_CANDIDATE",
                    "arrival_at": None, "total_duration_seconds": None,
                    "components": None, "legs": results}
        waiting += selected["waiting_seconds"]
        riding += selected["riding_seconds"]
        cursor = selected["arrival_at"] + transfer
        if not math.isfinite(cursor):
            raise ValueError("Transfer arithmetic overflowed.")
    arrival = cursor + egress
    total = arrival - decision
    if not all(math.isfinite(value) for value in (arrival, total, walking, waiting, riding)):
        raise ValueError("Journey arithmetic overflowed.")
    return {"status": "AVAILABLE", "reason_code": "OFFLINE_COMPONENT_COMPOSITION",
            "arrival_at": arrival, "total_duration_seconds": total,
            "components": {"walking_seconds": walking, "waiting_seconds": waiting,
                           "riding_seconds": riding}, "legs": results}
