"""Versioned boarding-safe predictions for the November repair benchmark.

The audited original predictor remains unchanged. Its validation, identity,
feed freshness, incident, and service checks are reused here. Sequence assembly
is versioned separately so a positive historical departure correction cannot
create catchability, and an early arrival correction cannot create a tight
transfer. These forecasts never consume outcome labels or future captures.
"""

from collections import Counter

from data.october.labels import canonical_event_trip_id

from .matching import (_choose_snapshots, _epoch, _iso, _timing_candidate,
                       _trip_observation_reason)
from .mta import ALERTS_FEED_ID, snapshot_status
from .severe import (MODES, _aggregate_context, _context_is_fresh, _correction,
                     _incident_context, _no_service_conflict, _seconds,
                     _text_no_service_conflict, _unknown_context, decide,
                     validate_templates)


def predict_routes(snapshots, templates, cutoff, *, mode="mta", estimator=None,
                   incident_index=None, train_max_age_seconds=180,
                   alerts_max_age_seconds=300, boarding_margin_seconds=120):
    """Predict supplied routes with a separate conservative boarding gate.

    Expected endpoint times still determine ETA ranking and duration components.
    Eligibility uses the earlier raw/corrected departure, the later raw/corrected
    preceding arrival, and an additional margin. The margin never changes an
    endpoint or adds duration; no outcome data enters this function.
    """
    validate_templates(templates)
    if mode not in MODES:
        raise ValueError("Unsupported comparison mode.")
    cutoff = _epoch(cutoff)
    _seconds(train_max_age_seconds, "train_max_age_seconds")
    _seconds(alerts_max_age_seconds, "alerts_max_age_seconds")
    margin = _seconds(boarding_margin_seconds, "boarding_margin_seconds")
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
        conservative_cursor = cursor
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
                conservative_cursor += route["transfer_walk_seconds"][position - 1]
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
                gate_departure = min(raw_departure, departure)
                gate = {
                    "departure_at": gate_departure,
                    "expected_platform_ready_at": cursor,
                    "conservative_platform_ready_at": conservative_cursor,
                    "slack_seconds": gate_departure - conservative_cursor,
                    "margin_seconds": margin,
                    "eligible": gate_departure >= conservative_cursor + margin,
                    "raw_departure_at": raw_departure,
                    "corrected_departure_at": departure,
                }
                if arrival < departure:
                    reason = "NONMONOTONIC_CORRECTED_ENDPOINTS"
                elif not gate["eligible"]:
                    reason = "INSUFFICIENT_BOARDING_MARGIN"
                else:
                    reason = None
                adjusted = dict(candidate, departure_at=departure, arrival_at=arrival,
                                platform_ready_at=cursor, segment_station_ids=scope,
                                boarding_gate=gate)
                if reason is None and (_no_service_conflict(fresh_alerts, adjusted, cutoff)
                                       or _text_no_service_conflict(context, trip["route_id"])):
                    reason = "NO_SERVICE_ALERT_CONFLICT"
                if reason:
                    result["rejected"].append({"leg_index": position, "trip_id": identity,
                                               "reason": reason, "boarding_gate": gate})
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
            conservative_cursor = max(chosen["baseline_arrival_at"], chosen["arrival_at"])
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
    return {"schema_version": "boarding-safe-comparison-v2", "mode": mode, "cutoff": cutoff,
            "routes": predictions, "feed_states": states,
            "policy": {"train_max_age_seconds": train_max_age_seconds,
                       "alerts_max_age_seconds": alerts_max_age_seconds,
                       "profile_endpoint_composition": "CORRECT_ABSOLUTE_ENDPOINTS_THEN_SUBTRACT",
                       "prediction_uses_outcomes": False,
                       "boarding_margin_seconds": margin,
                       "boarding_gate_departure": "MIN_RAW_AND_CORRECTED_DEPARTURE",
                       "transfer_readiness": "MAX_RAW_AND_CORRECTED_PREVIOUS_ARRIVAL_PLUS_WALK",
                       "positive_departure_correction_can_enable_boarding": False,
                       "boarding_margin_added_to_duration": False}}


def evaluate_modes(snapshots, templates, cutoff, current_route_id, *, estimator=None,
                   incident_index=None, switch_margin_seconds=300, require_severe=True,
                   boarding_margin_seconds=120, **freshness):
    """Apply the same boarding rule to raw MTA and both historical policies."""
    snapshots = list(snapshots)
    output = {}
    for mode in MODES:
        prediction = predict_routes(
            snapshots, templates, cutoff, mode=mode, estimator=estimator,
            incident_index=incident_index, boarding_margin_seconds=boarding_margin_seconds,
            **freshness)
        output[mode] = dict(prediction, **decide(
            prediction, current_route_id, switch_margin_seconds=switch_margin_seconds,
            require_severe=require_severe))
    return output
