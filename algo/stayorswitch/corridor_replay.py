"""Exploratory fixed-path historical replay with frozen component models.

Predictions and train selection never read outcome labels. Routes and walking
durations are analyst-supplied scenario inputs, not historical Google responses.
Strict recommendation eligibility preserves the Step 4 fresh-alert policy;
conditional timing rankings are explicitly separate diagnostic hypotheses.
"""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import math
import json
from itertools import product
from zoneinfo import ZoneInfo

from data.modeling.snapshot import build_snapshot_case
from .baseline import _decision, _overlaps
from .matching import (_choose_snapshots, _epoch, _iso, _timing_candidate,
                       _trip_observation_reason, relevant_alerts)
from .model_training.inference import compose_candidate
from .mta import ALERTS_FEED_ID, snapshot_status


MODES = ("mta", "segment_model", "departure_segment_research")


def _seconds(value, name):
    if (isinstance(value, bool) or not isinstance(value, (float, int))
            or not math.isfinite(value) or value < 0):
        raise ValueError(name + " must be finite and nonnegative.")
    return float(value)


def validate_templates(templates):
    if len(templates) < 2:
        raise ValueError("A replay needs at least two explicit supplied paths.")
    ids = set()
    for route in templates:
        for key in ("id", "name", "boarding_stop_id", "alighting_stop_id", "feed_id"):
            if not isinstance(route.get(key), str) or not route[key]:
                raise ValueError("Route templates require " + key)
        if route["id"] in ids:
            raise ValueError("Route identifiers must be unique.")
        ids.add(route["id"])
        routes = route.get("route_ids", [route.get("route_id")])
        if not routes or any(not isinstance(item, str) or not item for item in routes):
            raise ValueError("Every template needs explicit line identifiers.")
        _seconds(route["access_walk_seconds"], "access_walk_seconds")
        _seconds(route["egress_walk_seconds"], "egress_walk_seconds")


def _context(case):
    cutoff = _epoch(case["decision_at"])
    chosen = _choose_snapshots(case["snapshots"], cutoff)
    states = {feed: snapshot_status(snapshot, _iso(cutoff)) for feed, snapshot in chosen.items()}
    alerts = chosen.get(ALERTS_FEED_ID)
    fresh_alerts = alerts.get("alerts", []) if alerts and states.get(ALERTS_FEED_ID) == "FRESH" else []
    return cutoff, chosen, states, fresh_alerts


def _model_correction(predictor, snapshot, identity, target, cutoff, **endpoints):
    if predictor is None:
        return {"correction_seconds": 0.0, "method": "MTA_FALLBACK", "reason": "NO_MODEL_SUPPLIED"}
    try:
        row = build_snapshot_case(snapshot, identity, target, decision_at=cutoff, **endpoints)
    except ValueError as error:
        return {"correction_seconds": 0.0, "method": "MTA_FALLBACK", "reason": str(error)}
    return predictor.predict_case(row)


def _corrections(candidate, trip, snapshot, cutoff, mode, predictors, anchor_ids):
    """Apply disjoint riding corrections while retaining every original dwell."""
    result = {"departure_correction_seconds": 0.0, "segment_correction_seconds": 0.0,
              "departure_model": None, "segments": [], "applied_segment_count": 0,
              "fallback_segment_count": 0}
    if mode == "mta":
        return result
    identity = trip["id"]
    if mode == "departure_segment_research":
        dep = _model_correction(predictors.get("departure"), snapshot, identity, "departure", cutoff,
                                stop_id=candidate["boarding_stop_id"])
        result["departure_model"] = dep
        result["departure_correction_seconds"] = dep["correction_seconds"]
    updates = trip["stop_updates"]
    pattern = [stop.get("stop_id") for stop in updates]
    start = pattern.index(candidate["boarding_stop_id"])
    end = pattern.index(candidate["alighting_stop_id"])
    anchors = [index for index in range(start, end + 1)
               if index in (start, end) or pattern[index] in anchor_ids]
    # Overlapping baseline segments cannot be independently corrected without
    # inventing dwell times. Preserve the coherent full-leg MTA estimate instead.
    for index in anchors[1:-1]:
        arrival, departure = updates[index].get("arrival_time"), updates[index].get("departure_time")
        if arrival is not None and departure is not None and _epoch(departure) < _epoch(arrival):
            result["fallback_segment_count"] = len(anchors) - 1
            result["segments"] = [{"method": "MTA_FALLBACK", "reason": "NONMONOTONIC_ANCHOR_DWELL"}]
            return result
    for left, right in zip(anchors, anchors[1:]):
        origin, destination = pattern[left], pattern[right]
        correction = _model_correction(predictors.get("segment"), snapshot, identity, "segment", cutoff,
                                       from_stop_id=origin, to_stop_id=destination)
        detail = dict(correction, from_stop_id=origin, to_stop_id=destination)
        result["segments"].append(detail)
        result["segment_correction_seconds"] += correction["correction_seconds"]
        result["applied_segment_count" if correction["method"] == "EXPERIMENTAL_COMPONENT_MODEL"
               else "fallback_segment_count"] += 1
    return result


def predict_routes(case, templates, mode="mta", *, predictors=None, anchor_ids=()):
    """Estimate supplied paths from as-of inputs only; no label argument exists."""
    validate_templates(templates)
    if mode not in MODES:
        raise ValueError("Unknown replay mode.")
    predictors = predictors or {}
    cutoff, snapshots, states, fresh_alerts = _context(case)
    estimates = []
    for route in templates:
        access = _seconds(route["access_walk_seconds"], "access_walk_seconds")
        egress = _seconds(route["egress_walk_seconds"], "egress_walk_seconds")
        ready = cutoff + access
        estimate = {"id": route["id"], "name": route["name"], "status": "UNAVAILABLE",
                    "comparison_eligible": False, "timing_eligible": False,
                    "eta": None, "total_duration_seconds": None, "selected_train": None,
                    "candidate_count": 0, "rejected": [], "mode": mode,
                    "access_walk_seconds": access, "egress_walk_seconds": egress,
                    "platform_ready_at": _iso(ready), "components": None}
        snap = snapshots.get(route["feed_id"])
        if snap is None or states.get(route["feed_id"]) != "FRESH":
            estimate["reason"] = "MISSING_OR_STALE_TRAIN_FEED"
            estimates.append(estimate)
            continue
        identities = Counter(trip.get("id") for trip in snap.get("trips", []))
        candidates = []
        line_ids = set(route.get("route_ids", [route.get("route_id")]))
        for trip in snap.get("trips", []):
            if trip.get("route_id") not in line_ids:
                continue
            identity = trip.get("id")
            reason = "AMBIGUOUS_TRIP_IDENTITY" if not identity or identities[identity] != 1 else (
                _trip_observation_reason(trip, snap, cutoff, 180))
            if reason:
                estimate["rejected"].append({"trip_id": identity, "reason": reason})
                continue
            candidate, reason = _timing_candidate(trip,
                {"platform_stop_ids": [route["boarding_stop_id"]]},
                {"platform_stop_ids": [route["alighting_stop_id"]]}, None)
            if candidate is None:
                estimate["rejected"].append({"trip_id": identity, "reason": reason})
                continue
            corrections = _corrections(candidate, trip, snap, cutoff, mode, predictors, set(anchor_ids))
            timing = compose_candidate({"trip_id": identity,
                "departure_at": _epoch(candidate["departure_at"]),
                "arrival_at": _epoch(candidate["arrival_at"]),
                "departure_correction_seconds": corrections["departure_correction_seconds"],
                "segment_correction_seconds": corrections["segment_correction_seconds"]},
                decision_at=cutoff, ready_at=ready)
            if timing["status"] != "USABLE":
                estimate["rejected"].append({"trip_id": identity, "reason": timing["reason_code"]})
                continue
            # Alert matching uses the corrected traversal interval, while alert
            # availability and every model feature keep the original cutoff.
            adjusted = dict(candidate, departure_at=_iso(timing["departure_at"]),
                            arrival_at=_iso(timing["arrival_at"]), platform_ready_at=_iso(ready), catchable=True)
            adjusted["segment_station_ids"] = sorted({stop[:-1] if stop.endswith(("N", "S")) else stop
                                                      for stop in candidate["segment_stop_ids"]})
            alerts = relevant_alerts(fresh_alerts, {trip["route_id"]},
                                    set(candidate["segment_stop_ids"] + adjusted["segment_station_ids"]),
                                    [adjusted], _iso(cutoff))
            conflict = any(alert.get("effect") == "NO_SERVICE" and identity in alert.get("matched_candidate_trip_ids", [])
                           and _overlaps(alert, datetime.fromtimestamp(timing["departure_at"], timezone.utc),
                                         datetime.fromtimestamp(timing["arrival_at"], timezone.utc)) for alert in alerts)
            if conflict:
                estimate["rejected"].append({"trip_id": identity, "reason": "NO_SERVICE_ALERT_CONFLICT"})
                continue
            candidates.append(dict(adjusted, timing=timing, corrections=corrections,
                                   baseline_departure_at=candidate["departure_at"],
                                   baseline_arrival_at=candidate["arrival_at"],
                                   relevant_alert_ids=[alert.get("id") for alert in alerts]))
        estimate["candidate_count"] = len(candidates)
        if candidates:
            selected = min(candidates, key=lambda item: (item["timing"]["arrival_at"],
                           item["timing"]["departure_at"], item["trip_id"]))
            timing = selected["timing"]
            estimate.update(status="ESTIMATED", timing_eligible=True,
                comparison_eligible=states.get(ALERTS_FEED_ID) == "FRESH",
                eta=_iso(timing["arrival_at"] + egress),
                total_duration_seconds=timing["arrival_at"] + egress - cutoff,
                selected_train=selected,
                components={"walking_seconds": access + egress,
                            "waiting_seconds": timing["waiting_seconds"],
                            "riding_seconds": timing["riding_seconds"]})
        else:
            estimate["reason"] = "NO_USABLE_CATCHABLE_TRAIN"
        estimates.append(estimate)
    return {"mode": mode, "routes": estimates, "feed_states": states,
            "feed_evidence": {feed: {"kind": snapshot.get("kind"), "status": states[feed],
                "source_updated_at": snapshot.get("source_updated_at"), "fetched_at": snapshot.get("fetched_at"),
                "receipt_age_seconds": cutoff - _epoch(snapshot["fetched_at"])} for feed, snapshot in snapshots.items()},
            "alerts_fresh": states.get(ALERTS_FEED_ID) == "FRESH"}


def decide(prediction, current_id):
    request = {"current_itinerary_id": current_id,
               "itineraries": [{"id": item["id"]} for item in prediction["routes"]]}
    strict = _decision(request, prediction["routes"])
    conditional = deepcopy(prediction["routes"])
    for route in conditional:
        route["comparison_eligible"] = route["timing_eligible"]
    return {"strict_decision": strict,
            "conditional_timing_decision": _decision(request, conditional),
            "conditional_policy": "ASSUME_NO_UNOBSERVED_SERVICE_CONSTRAINTS_AND_FIXED_WALK_TIMES"}


def _label_time(label, field):
    if not label or label.get("quality_flags") or label.get("usable_proxy") is False:
        return None
    prefix = "departure" if field == "departure_at" else "arrival"
    if label.get(prefix + "_usable") is not True or label.get(prefix + "_quality_flags"):
        return None
    try:
        return _epoch(label[field])
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


def outcome_for(route, labels, decision_at):
    """Judge exactly the forecast-selected train; never substitute an oracle."""
    chosen = route.get("selected_train")
    if chosen is None:
        return {"status": "UNAVAILABLE", "reason": "NO_PREDICTION_SELECTED_TRAIN"}
    trip_labels = labels.get(chosen["trip_id"], {})
    start = trip_labels.get(chosen["boarding_stop_id"])
    end = trip_labels.get(chosen["alighting_stop_id"])
    departure = _label_time(start, "departure_at")
    arrival = _label_time(end, "arrival_at")
    if departure is None or arrival is None:
        return {"status": "UNAVAILABLE", "reason": "MISSING_OR_UNUSABLE_ENDPOINT_LABEL",
                "trip_id": chosen["trip_id"]}
    if arrival < departure:
        return {"status": "UNAVAILABLE", "reason": "NONMONOTONIC_ENDPOINT_LABEL"}
    if departure < _epoch(route["platform_ready_at"]):
        return {"status": "MISSED_SELECTED_TRAIN", "reason": "INFERRED_DEPARTURE_BEFORE_PLATFORM_READY",
                "trip_id": chosen["trip_id"], "departure_at": _iso(departure),
                "platform_ready_at": route["platform_ready_at"]}
    destination = arrival + route["egress_walk_seconds"]
    return {"status": "INFERRED", "trip_id": chosen["trip_id"],
            "departure_at": _iso(departure), "arrival_at": _iso(arrival),
            "destination_arrival_at": _iso(destination),
            "total_duration_seconds": destination - _epoch(decision_at),
            "components": {"walking_seconds": route["access_walk_seconds"] + route["egress_walk_seconds"],
                           "waiting_seconds": departure - _epoch(route["platform_ready_at"]),
                           "riding_seconds": arrival - departure},
            "evidence": "FINAL_PREDICTION_ENDPOINT_PROXY_PLUS_FIXED_WALK_ASSUMPTIONS"}


def _prediction(case, templates, mode, predictors, anchor_ids, cache):
    if cache is None:
        return predict_routes(case, templates, mode, predictors=predictors, anchor_ids=anchor_ids)
    # Egress changes cannot affect subway readiness or train choice. Reuse the
    # forecast for that exact access-time scenario, then shift destination ETA.
    key = json.dumps([case["id"], case["decision_at"], mode,
                      [{name: value for name, value in route.items() if name != "egress_walk_seconds"}
                       for route in templates]], sort_keys=True)
    if key not in cache:
        cache[key] = predict_routes(case, templates, mode, predictors=predictors, anchor_ids=anchor_ids)
    prediction = deepcopy(cache[key])
    for route, template in zip(prediction["routes"], templates):
        delta = template["egress_walk_seconds"] - route["egress_walk_seconds"]
        route["egress_walk_seconds"] = template["egress_walk_seconds"]
        if route["timing_eligible"]:
            route["total_duration_seconds"] += delta
            route["eta"] = _iso(_epoch(route["eta"]) + delta)
            route["components"]["walking_seconds"] += delta
    return prediction


def evaluate_case(case, templates, labels, *, predictors=None, anchor_ids=(), modes=MODES, prediction_cache=None):
    """Choose a same-time MTA reference, then score frozen alternatives fairly."""
    baseline = _prediction(case, templates, "mta", None, anchor_ids, prediction_cache)
    available = [route for route in baseline["routes"] if route["timing_eligible"]]
    reference = min(available, key=lambda route: route["total_duration_seconds"]) if available else None
    reference_id = reference["id"] if reference else None
    reference_outcome = outcome_for(reference, labels, case["decision_at"]) if reference else None
    result = {"case_id": case["id"], "decision_at": case["decision_at"],
              "selection_reason": case.get("selection_reason"),
              "reference_policy": "FASTEST_UNMODIFIED_MTA_AT_THE_SAME_CUTOFF",
              "reference_route_id": reference_id, "reference": reference,
              "reference_outcome": reference_outcome, "reference_delay_seconds": None,
              "modes": {}, "exploratory_not_new_holdout": True}
    weekday = datetime.fromtimestamp(_epoch(case["decision_at"]), ZoneInfo("America/New_York")).weekday()
    result["day_type"] = "WEEKDAY" if weekday < 5 else "SATURDAY" if weekday == 5 else "SUNDAY"
    if reference_outcome and reference_outcome["status"] == "INFERRED":
        result["reference_delay_seconds"] = reference_outcome["total_duration_seconds"] - reference["total_duration_seconds"]
    result["reference_continuity_review_required"] = (result["reference_delay_seconds"] is not None
                                                       and result["reference_delay_seconds"] > 1800)
    # Crucially, none of these prediction calls receive labels or reference
    # outcomes. Only fixed as-of context and the frozen model influence choices.
    for mode in modes:
        prediction = baseline if mode == "mta" else _prediction(case, templates, mode, predictors, anchor_ids, prediction_cache)
        decision = decide(prediction, reference_id)
        outcomes = {route["id"]: outcome_for(route, labels, case["decision_at"])
                    for route in prediction["routes"]}
        recommended_id = decision["conditional_timing_decision"]["recommended_itinerary_id"]
        recommended_outcome = outcomes.get(recommended_id)
        current_outcome = outcomes.get(reference_id)
        savings = None
        switch_savings = None
        if (reference_outcome and reference_outcome["status"] == "INFERRED"
                and recommended_outcome and recommended_outcome["status"] == "INFERRED"):
            savings = reference_outcome["total_duration_seconds"] - recommended_outcome["total_duration_seconds"]
        if (current_outcome and current_outcome["status"] == "INFERRED"
                and recommended_outcome and recommended_outcome["status"] == "INFERRED"):
            switch_savings = current_outcome["total_duration_seconds"] - recommended_outcome["total_duration_seconds"]
        all_outcomes = bool(outcomes) and all(value["status"] == "INFERRED" for value in outcomes.values())
        regret = None
        if all_outcomes and recommended_outcome and recommended_outcome["status"] == "INFERRED":
            regret = recommended_outcome["total_duration_seconds"] - min(value["total_duration_seconds"] for value in outcomes.values())
        result["modes"][mode] = dict(prediction, **decision, outcomes=outcomes,
            inferred_savings_vs_original_reference_seconds=savings,
            inferred_switch_savings_seconds=switch_savings,
            inferred_regret_within_forecast_selected_candidate_trains_seconds=regret,
            comparable_outcomes_complete=all_outcomes,
            outcome_policy="SAME_FORECAST_SELECTED_TRAIN_NO_REASSIGNMENT_IF_MISSED")
    return result


def summarize_cases(cases, *, minimum_delay_seconds=300, include_day_types=True):
    delayed = [case for case in cases if case["reference_delay_seconds"] is not None
               and case["reference_delay_seconds"] >= minimum_delay_seconds]
    modes = {}
    for mode in MODES:
        values = [case["modes"][mode] for case in delayed if mode in case["modes"]]
        switches = [value for value in values if value["conditional_timing_decision"]["action"] == "SWITCH"]
        known = [value for value in switches if value["inferred_switch_savings_seconds"] is not None]
        strict_switches = [value for value in values if value["strict_decision"]["action"] == "SWITCH"]
        strict_known = [value for value in strict_switches if value["inferred_switch_savings_seconds"] is not None]
        modes[mode] = {
            "strict_actions": dict(Counter(value["strict_decision"]["action"] for value in values)),
            "conditional_timing_actions": dict(Counter(value["conditional_timing_decision"]["action"] for value in values)),
            "conditional_switches_with_comparable_outcomes": len(known),
            "conditional_switches_with_positive_inferred_savings": sum(value["inferred_switch_savings_seconds"] > 0 for value in known),
            "conditional_switches_with_nonpositive_inferred_savings": sum(value["inferred_switch_savings_seconds"] <= 0 for value in known),
            "conditional_switches_without_comparable_outcomes": len(switches) - len(known),
            "strict_switches_with_positive_inferred_savings": sum(value["inferred_switch_savings_seconds"] > 0 for value in strict_known),
            "strict_switches_with_nonpositive_inferred_savings": sum(value["inferred_switch_savings_seconds"] <= 0 for value in strict_known),
            "strict_switches_without_comparable_outcomes": len(strict_switches) - len(strict_known),
            "conditional_stays_with_faster_inferred_alternative": sum(
                value["conditional_timing_decision"]["action"] == "STAY"
                and value["inferred_regret_within_forecast_selected_candidate_trains_seconds"] is not None
                and value["inferred_regret_within_forecast_selected_candidate_trains_seconds"] > 0 for value in values),
            "selected_train_segment_model_applications": sum(route["selected_train"]["corrections"]["applied_segment_count"]
                for value in values for route in value["routes"] if route["selected_train"]),
            "selected_train_segment_model_fallbacks": sum(route["selected_train"]["corrections"]["fallback_segment_count"]
                for value in values for route in value["routes"] if route["selected_train"]),
        }
    summary = {"candidate_case_count": len(cases), "qualifying_reference_delay_cases": len(delayed),
            "qualifying_distinct_baseline_train_count": len({case["reference"]["selected_train"]["trip_id"] for case in delayed}),
            "minimum_reference_delay_seconds": minimum_delay_seconds,
            "reference_outcome_status_counts": dict(Counter(case["reference_outcome"]["status"] if case["reference_outcome"] else "NO_REFERENCE" for case in cases)),
            "baseline_route_status_counts": {route_id: dict(Counter(route["status"] for case in cases
                for route in case["modes"].get("mta", {}).get("routes", []) if route["id"] == route_id))
                for route_id in sorted({route["id"] for case in cases for route in case["modes"].get("mta", {}).get("routes", [])})},
            "selection_uses_model_switch_success": False, "modes": modes}
    if include_day_types:
        summary["by_day_type"] = {day: summarize_cases([case for case in cases if case.get("day_type") == day],
            minimum_delay_seconds=minimum_delay_seconds, include_day_types=False) for day in ("WEEKDAY", "SATURDAY", "SUNDAY")}
    return summary


def walking_sensitivity(case, templates, labels, *, predictors=None, anchor_ids=(), deltas=(-120, 0, 120)):
    """Recompute reference and train catchability for independent walk changes."""
    scenarios = []
    prediction_cache = {}
    for changes in product(deltas, repeat=len(templates) * 2):
        varied = deepcopy(templates)
        walks = {}
        for index, route in enumerate(varied):
            route["access_walk_seconds"] += changes[index * 2]
            route["egress_walk_seconds"] += changes[index * 2 + 1]
            walks[route["id"]] = {"access_walk_seconds": route["access_walk_seconds"],
                                  "egress_walk_seconds": route["egress_walk_seconds"]}
        result = evaluate_case(case, varied, labels, predictors=predictors, anchor_ids=anchor_ids,
                               prediction_cache=prediction_cache)
        scenarios.append({"walks": walks, "reference_route_id": result["reference_route_id"],
                          "reference_delay_seconds": result["reference_delay_seconds"],
                          "modes": {mode: {
                              "action": value["conditional_timing_decision"]["action"],
                              "recommended_itinerary_id": value["conditional_timing_decision"]["recommended_itinerary_id"],
                              "estimated_savings_seconds": value["conditional_timing_decision"]["estimated_savings_seconds"],
                              "inferred_switch_savings_seconds": value["inferred_switch_savings_seconds"],
                              "inferred_savings_vs_original_reference_seconds": value["inferred_savings_vs_original_reference_seconds"],
                              "selected_train_ids": {route["id"]: route["selected_train"]["trip_id"] if route["selected_train"] else None
                                                     for route in value["routes"]},
                              "outcome_statuses": {key: outcome["status"] for key, outcome in value["outcomes"].items()}}
                              for mode, value in result["modes"].items()}})
    return {"scenario_count": len(scenarios),
            "reference_route_counts": dict(Counter(item["reference_route_id"] for item in scenarios)),
            "mode_action_counts": {mode: dict(Counter(item["modes"][mode]["action"] for item in scenarios)) for mode in MODES},
            "scenarios": scenarios}
