"""Compare supplied subway journeys with time and incident delay profiles.

Every forecast uses one information cutoff. This module has no outcome-label
argument and does not generate paths. Absolute departure and arrival endpoints
are corrected separately; riding time is their difference, never another sum
of delay corrections. Formal incident advice and conditional timing rankings
are deliberately separate outputs.
"""

from collections import Counter
from copy import deepcopy
import math

from data.october.labels import canonical_event_trip_id

from .matching import (_choose_snapshots, _epoch, _iso, _timing_candidate,
                       _trip_observation_reason, relevant_alerts)
from .mta import ALERTS_FEED_ID, snapshot_status


MODES = ("mta", "time_profile", "incident_profile")
_STATE_ORDER = {"NORMAL": 0, "UNKNOWN": 1, "PLANNED": 2,
                "DISRUPTION": 3, "SEVERE": 4}


def _seconds(value, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError(name + " must be finite and nonnegative.")
    return float(value)


def validate_templates(templates):
    """Validate explicit provider/research paths without imposing detour caps."""
    identifiers = set()
    if not templates:
        raise ValueError("At least one supplied route is required.")
    for route in templates:
        identifier = route.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("Supplied route identifiers must be nonempty and unique.")
        identifiers.add(identifier)
        for key in ("access_walk_seconds", "egress_walk_seconds"):
            _seconds(route[key], key)
        legs = route.get("legs")
        if not isinstance(legs, list) or not legs:
            raise ValueError("Each supplied route requires subway legs.")
        transfers = route.get("transfer_walk_seconds")
        if not isinstance(transfers, list) or len(transfers) != len(legs) - 1:
            raise ValueError("Every transfer requires an explicit walking duration.")
        for value in transfers:
            _seconds(value, "transfer_walk_seconds")
        for leg in legs:
            for key in ("route_id", "feed_id", "from_stop_id", "to_stop_id"):
                if not isinstance(leg.get(key), str) or not leg[key]:
                    raise ValueError("Each subway leg requires " + key)
            aliases = leg.get("route_ids", [leg["route_id"]])
            if (not isinstance(aliases, list) or not aliases
                    or any(not isinstance(line, str) or not line for line in aliases)):
                raise ValueError("Leg line identifiers must be nonempty strings.")
            if leg["from_stop_id"] == leg["to_stop_id"]:
                raise ValueError("A riding leg must have distinct endpoints.")


def _unknown_context():
    return {"state": "UNKNOWN", "cause": "UNKNOWN", "incident_ids": [],
            "severe_incident_ids": [], "evidence_status": "UNKNOWN",
            "first_observed_at": None, "age_seconds": None, "alerts": [],
            "ambiguous_scope": False}


def _incident_context(index, cutoff, line, stops):
    if index is None:
        return _unknown_context()
    context = deepcopy(index.context_at(cutoff, line, stop_ids=stops))
    if not isinstance(context, dict):
        raise ValueError("Incident context must be a dictionary.")
    context.setdefault("state", "UNKNOWN")
    context.setdefault("evidence_status", "UNKNOWN")
    context.setdefault("incident_ids", [])
    context.setdefault("alerts", [])
    context.setdefault("ambiguous_scope", False)
    context.setdefault("severe_incident_ids", context["incident_ids"] if context["state"] == "SEVERE" else [])
    for key in ("captured_at", "capture_at", "first_observed_at"):
        if context.get(key) is not None and _epoch(context[key]) > cutoff:
            raise ValueError("Incident context contains future observation evidence.")
    return context


def _context_is_fresh(context):
    return (context.get("evidence_status") == "FRESH"
            and context.get("state") != "UNKNOWN"
            and not context.get("ambiguous_scope", False)
            and not context.get("scope_uncertain", False)
            # A fresh NORMAL context has applicable=False when no notice
            # affects this segment; that is valid negative evidence.
            and (context.get("state") == "NORMAL"
                 or context.get("applicable") is not False))


def _correction(estimator, target, leg, actual_line, cutoff, horizon, context, mode):
    fallback = {"correction_seconds": 0.0, "supported": False, "level": "MTA",
                "event_count": 0, "incident_count": 0, "statistics": None,
                "incident_supported": False, "reason": "UNMODIFIED_MTA"}
    if mode == "mta":
        return fallback
    if estimator is None:
        return dict(fallback, reason="PROFILE_NOT_SUPPLIED")
    requested = context if mode == "incident_profile" else {
        "state": "TIME_ONLY", "cause": "ANY", "incident_ids": []}
    value = dict(estimator.estimate(target, actual_line, leg["from_stop_id"],
                 leg["to_stop_id"], cutoff, horizon, requested))
    correction = value.get("correction_seconds")
    if (isinstance(correction, bool) or not isinstance(correction, (int, float))
            or not math.isfinite(correction)):
        raise ValueError("Profile corrections must be finite numeric seconds.")
    if not value.get("supported") and correction != 0:
        raise ValueError("An unsupported profile cannot modify a forecast.")
    return value


def _no_service_conflict(alerts, candidate, cutoff):
    alerts = [alert for alert in alerts if alert.get("effect") == "NO_SERVICE"]
    if not alerts:
        return False
    base_line = {"FX": "F", "7X": "7"}.get(candidate["route_id"])
    if base_line is not None:
        # Official base-route notices include their express variants. Keep
        # every other selector constraint and never rewrite profile route IDs.
        alerts = deepcopy(alerts)
        for alert in alerts:
            for selector in alert.get("informed_entities", []):
                if selector.get("route_id") == base_line:
                    selector["route_id"] = candidate["route_id"]
                trip = selector.get("trip") or {}
                if trip.get("route_id") == base_line:
                    trip["route_id"] = candidate["route_id"]
    relevant = relevant_alerts(alerts, {candidate["route_id"]},
                              set(candidate["segment_stop_ids"] + candidate["segment_station_ids"]),
                              [candidate], _iso(cutoff))
    return any(alert.get("effect") == "NO_SERVICE"
               and candidate["trip_id"] in alert.get("matched_candidate_trip_ids", [])
               for alert in relevant)


def _text_no_service_conflict(context, line):
    if not _context_is_fresh(context):
        return False
    lines = {line, {"FX": "F", "7X": "7"}.get(line, line)}
    return any(alert.get("no_service") and alert.get("no_service_scope") == "ROUTE_WIDE"
               and alert.get("state") in {"SEVERE", "PLANNED", "DISRUPTION"}
               and (not alert.get("no_service_route_ids")
                    or lines.intersection(alert["no_service_route_ids"]))
               for alert in context.get("alerts", []))


def _aggregate_context(contexts):
    if not contexts:
        return _unknown_context()
    state = max((context.get("state", "UNKNOWN") for context in contexts),
                key=lambda value: _STATE_ORDER.get(value, 1))
    evidence = "FRESH" if all(_context_is_fresh(context) for context in contexts) else (
        "LAST_OBSERVED" if any(context.get("evidence_status") == "LAST_OBSERVED" for context in contexts)
        else "UNKNOWN")
    return {"state": state, "evidence_status": evidence,
            "incident_ids": sorted({identifier for context in contexts for identifier in context.get("incident_ids", [])}),
            "severe_incident_ids": sorted({identifier for context in contexts for identifier in context.get("severe_incident_ids", [])}),
            "causes": sorted({context.get("cause", "UNKNOWN") for context in contexts}),
            "ambiguous_scope": any(context.get("ambiguous_scope", False) or context.get("scope_uncertain", False)
                                   for context in contexts)}


def predict_routes(snapshots, templates, cutoff, *, mode="mta", estimator=None,
                   incident_index=None, train_max_age_seconds=180,
                   alerts_max_age_seconds=300):
    """Predict exact supplied train sequences using only available inputs.

    Timestamps in the returned estimates are numeric UTC seconds. A route may
    have a timing estimate while lacking service evidence for formal advice.
    Incomplete routes have no door-to-door ETA, even if an early leg matched.
    """
    validate_templates(templates)
    if mode not in MODES:
        raise ValueError("Unsupported comparison mode.")
    cutoff = _epoch(cutoff)
    _seconds(train_max_age_seconds, "train_max_age_seconds")
    _seconds(alerts_max_age_seconds, "alerts_max_age_seconds")
    selected = _choose_snapshots(snapshots, cutoff)
    states = {feed: snapshot_status(snapshot, _iso(cutoff),
                    train_max_age_seconds=train_max_age_seconds,
                    alerts_max_fetch_age_seconds=alerts_max_age_seconds)
              for feed, snapshot in selected.items()}
    alerts = selected.get(ALERTS_FEED_ID)
    fresh_alerts = alerts.get("alerts", []) if alerts and states.get(ALERTS_FEED_ID) == "FRESH" else []
    identities_by_feed, physical_keys, physical_counts = {}, {}, {}
    for feed, snapshot in selected.items():
        if states[feed] != "FRESH":
            continue
        trips = snapshot.get("trips", [])
        identities_by_feed[feed] = Counter(trip.get("id") for trip in trips)
        # This helper reads only observed identity metadata, never labels.
        # Start-time jitter may change normalized IDs between captures, but
        # simultaneous aliases cannot be resolved by choosing the faster ETA.
        physical_keys[feed] = {id(trip): canonical_event_trip_id(trip) for trip in trips}
        physical_counts[feed] = Counter(value for value in physical_keys[feed].values()
                                        if value is not None)
    predictions = []
    for route in templates:
        access = float(route["access_walk_seconds"])
        egress = float(route["egress_walk_seconds"])
        cursor = cutoff + access
        result = {"id": route["id"], "family": route.get("family", route["id"]),
                  "name": route.get("name", route["id"]), "status": "UNAVAILABLE",
                  "mode": mode, "eta": None, "total_duration_seconds": None,
                  "timing_eligible": False, "comparison_eligible": False,
                  "selected_legs": [], "rejected": [], "leg_candidate_counts": [],
                  "access_walk_seconds": access, "egress_walk_seconds": egress,
                  "transfer_walk_seconds": list(route["transfer_walk_seconds"]),
                  "components": None, "reason_codes": [], "context": _unknown_context(),
                  "severe_incident_ids": [], "profile_supported_endpoint_count": 0,
                  "profile_fallback_endpoint_count": 0}
        waiting = riding = 0.0
        for position, leg in enumerate(route["legs"]):
            if position:
                cursor += route["transfer_walk_seconds"][position - 1]
            snapshot = selected.get(leg["feed_id"])
            if snapshot is None or states.get(leg["feed_id"]) != "FRESH":
                result["reason_codes"].append("MISSING_OR_STALE_TRAIN_FEED")
                break
            identities = identities_by_feed[leg["feed_id"]]
            options = []
            line_ids = set(leg.get("route_ids", [leg["route_id"]]))
            for trip in snapshot.get("trips", []):
                if trip.get("route_id") not in line_ids:
                    continue
                identity = trip.get("id")
                physical = physical_keys[leg["feed_id"]][id(trip)]
                if not identity or identities[identity] != 1:
                    reason = "AMBIGUOUS_TRIP_IDENTITY"
                elif physical is not None and physical_counts[leg["feed_id"]][physical] != 1:
                    reason = "SIMULTANEOUS_CANONICAL_TRIP_ALIASES"
                else:
                    reason = _trip_observation_reason(trip, snapshot, cutoff, train_max_age_seconds)
                candidate = None
                if not reason:
                    candidate, reason = _timing_candidate(trip,
                        {"platform_stop_ids": [leg["from_stop_id"]]},
                        {"platform_stop_ids": [leg["to_stop_id"]]}, None)
                if candidate is not None and candidate["boarding_time_source"] != "DEPARTURE":
                    reason, candidate = "TRUE_DEPARTURE_PREDICTION_REQUIRED", None
                if candidate is None:
                    result["rejected"].append({"leg_index": position, "trip_id": identity, "reason": reason})
                    continue
                raw_departure = _epoch(candidate["departure_at"])
                raw_arrival = _epoch(candidate["arrival_at"])
                if raw_departure < cutoff or raw_arrival < cutoff:
                    result["rejected"].append({"leg_index": position, "trip_id": identity,
                                               "reason": "EXPIRED_BASELINE_FORECAST"})
                    continue
                scope = sorted(set(candidate["segment_stop_ids"]) | {
                    stop[:-1] if stop.endswith(("N", "S")) else stop for stop in candidate["segment_stop_ids"]})
                context = _incident_context(incident_index, cutoff, trip["route_id"], scope)
                dep = _correction(estimator, "departure", leg, trip["route_id"], cutoff,
                                  raw_departure - cutoff, context, mode)
                arr = _correction(estimator, "arrival", leg, trip["route_id"], cutoff,
                                  raw_arrival - cutoff, context, mode)
                departure = raw_departure + dep["correction_seconds"]
                arrival = raw_arrival + arr["correction_seconds"]
                if arrival < departure:
                    reason = "NONMONOTONIC_CORRECTED_ENDPOINTS"
                elif departure < cursor:
                    reason = "DEPARTS_BEFORE_PLATFORM_READY"
                else:
                    reason = None
                adjusted = dict(candidate, departure_at=departure, arrival_at=arrival,
                                platform_ready_at=cursor, segment_station_ids=scope)
                if reason is None and (_no_service_conflict(fresh_alerts, adjusted, cutoff)
                                       or _text_no_service_conflict(context, trip["route_id"])):
                    reason = "NO_SERVICE_ALERT_CONFLICT"
                if reason:
                    result["rejected"].append({"leg_index": position, "trip_id": identity, "reason": reason})
                    continue
                options.append(dict(adjusted, from_stop_id=leg["from_stop_id"], to_stop_id=leg["to_stop_id"],
                    leg_index=position, feed_id=leg["feed_id"],
                    baseline_departure_at=raw_departure, baseline_arrival_at=raw_arrival,
                    incident_context=context, corrections={"departure": dep, "arrival": arr},
                    waiting_seconds=departure - cursor, riding_seconds=arrival - departure))
            result["leg_candidate_counts"].append(len(options))
            if not options:
                result["reason_codes"].append("NO_USABLE_CATCHABLE_TRAIN")
                break
            chosen = min(options, key=lambda value: (value["arrival_at"], value["departure_at"], value["trip_id"]))
            result["selected_legs"].append(chosen)
            waiting += chosen["waiting_seconds"]
            riding += chosen["riding_seconds"]
            cursor = chosen["arrival_at"]
            for correction in chosen["corrections"].values():
                result["profile_supported_endpoint_count" if correction.get("supported") else
                       "profile_fallback_endpoint_count"] += 1
        contexts = [leg["incident_context"] for leg in result["selected_legs"]]
        result["context"] = _aggregate_context(contexts)
        result["severe_incident_ids"] = result["context"]["severe_incident_ids"]
        if len(result["selected_legs"]) == len(route["legs"]):
            eta = cursor + egress
            result.update(status="ESTIMATED", timing_eligible=True,
                          comparison_eligible=all(_context_is_fresh(context) for context in contexts),
                          eta=eta, total_duration_seconds=eta - cutoff,
                          components={"walking_seconds": access + egress + sum(route["transfer_walk_seconds"]),
                                      "waiting_seconds": waiting, "riding_seconds": riding})
            if not result["comparison_eligible"]:
                result["reason_codes"].append("SERVICE_EVIDENCE_UNVERIFIED")
        predictions.append(result)
    return {"schema_version": "severe-comparison-v1", "mode": mode, "cutoff": cutoff,
            "routes": predictions, "feed_states": states,
            "policy": {"train_max_age_seconds": train_max_age_seconds,
                       "alerts_max_age_seconds": alerts_max_age_seconds,
                       "profile_endpoint_composition": "CORRECT_ABSOLUTE_ENDPOINTS_THEN_SUBTRACT",
                       "prediction_uses_outcomes": False}}


def _decision(routes, current_id, margin, *, strict, require_severe):
    current = next((route for route in routes if route["id"] == current_id), None)
    alternatives = [route for route in routes if route["id"] != current_id]
    result = {"action": "UNDETERMINED", "recommended_itinerary_id": None,
              "estimated_savings_seconds": None, "reason_codes": [],
              "comparison_complete": False, "comparison_scope": "SUPPLIED_ITINERARIES",
              "shared_incident_alternatives": [], "best_alternative_savings_seconds": None}
    key = "comparison_eligible" if strict else "timing_eligible"
    if current is None:
        result.update(action="NOT_APPLICABLE", reason_codes=["NO_CURRENT_ITINERARY"])
        return result
    if not current.get(key):
        result["reason_codes"] = ["CURRENT_SERVICE_EVIDENCE_UNVERIFIED" if strict and current.get("timing_eligible")
                                  else "CURRENT_UNAVAILABLE"]
        return result
    if not alternatives:
        result["reason_codes"] = ["NO_ALTERNATIVES"]
        return result
    complete = all(route.get(key) for route in alternatives)
    result["comparison_complete"] = complete
    available = [route for route in alternatives if route.get(key)]
    current_severe = set(current.get("severe_incident_ids", []))
    shared = [route["id"] for route in available
              if current_severe.intersection(route.get("severe_incident_ids", []))]
    result["shared_incident_alternatives"] = shared
    if available:
        best = min(available, key=lambda route: (route["total_duration_seconds"], route["id"]))
        result["best_alternative_savings_seconds"] = current["total_duration_seconds"] - best["total_duration_seconds"]
    if strict and require_severe and (current.get("context", {}).get("state") != "SEVERE" or not current_severe):
        if complete:
            result.update(action="STAY", recommended_itinerary_id=current_id,
                          estimated_savings_seconds=0.0, reason_codes=["NO_APPLICABLE_SEVERE_INCIDENT"])
        else:
            result["reason_codes"] = ["NO_APPLICABLE_SEVERE_INCIDENT", "UNASSESSED_ALTERNATIVES"]
        return result
    # Shared exposure is evidence to disclose, not a time penalty or proof
    # that a route cannot run. Compare its usable predictions on equal terms.
    switch_options = available
    fast = [route for route in switch_options
            if current["total_duration_seconds"] - route["total_duration_seconds"] >= margin
            and route["total_duration_seconds"] < current["total_duration_seconds"]]
    if fast:
        best = min(fast, key=lambda route: (route["total_duration_seconds"], route["id"]))
        result.update(action="SWITCH", recommended_itinerary_id=best["id"],
                      estimated_savings_seconds=current["total_duration_seconds"] - best["total_duration_seconds"],
                      reason_codes=["MEANINGFUL_FASTER_ALTERNATIVE"])
        if best["id"] in shared:
            result["reason_codes"].append("SHARED_SEVERE_INCIDENT_EXPOSURE")
    elif complete:
        result.update(action="STAY", recommended_itinerary_id=current_id,
                      estimated_savings_seconds=0.0, reason_codes=["NO_MEANINGFUL_TIME_ADVANTAGE"])
    else:
        result["reason_codes"] = ["UNASSESSED_ALTERNATIVES"]
    return result


def decide(prediction, current_route_id, *, switch_margin_seconds=300, require_severe=True):
    """Separate product advice from timing-only diagnostic rankings."""
    margin = _seconds(switch_margin_seconds, "switch_margin_seconds")
    if not isinstance(require_severe, bool):
        raise ValueError("require_severe must be boolean.")
    return {"strict_decision": _decision(prediction["routes"], current_route_id, margin,
                                        strict=True, require_severe=require_severe),
            "conditional_timing_decision": _decision(prediction["routes"], current_route_id, margin,
                                                    strict=False, require_severe=False),
            "current_route_id": current_route_id, "switch_margin_seconds": margin,
            "conditional_policy": "TIMING_ONLY_NOT_FORMAL_INCIDENT_ADVICE"}


def evaluate_modes(snapshots, templates, cutoff, current_route_id, *, estimator=None,
                   incident_index=None, switch_margin_seconds=300, require_severe=True,
                   **freshness):
    """Return all three modes without choosing or changing the Stay reference."""
    snapshots = list(snapshots)
    output = {}
    for mode in MODES:
        prediction = predict_routes(snapshots, templates, cutoff, mode=mode, estimator=estimator,
                                    incident_index=incident_index, **freshness)
        output[mode] = dict(prediction, **decide(prediction, current_route_id,
            switch_margin_seconds=switch_margin_seconds, require_severe=require_severe))
    return output
