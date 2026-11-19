"""Estimate complete supplied journeys from as-of MTA predictions.

This baseline has no learned correction, route generator, or HTTP service. The
matching report is an internal Step 2 artifact, not a public API request. Detailed
limitations stay outside the version 1 Response, whose reason codes are fixed.
"""

from datetime import datetime, timedelta, timezone
import math

from .integration import REPOSITORY, instant, validate_request
from .matching import request_fingerprint
from .mta import ALERTS_FEED_ID
from .network import utc_now


BASELINE_VERSION = "0.1"


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _unique(values):
    return list(dict.fromkeys(values))


def _empty(identifier, reasons):
    return {"id": identifier, "status": "UNAVAILABLE", "method": "NONE",
            "comparison_eligible": False, "eta": None, "total_duration_seconds": None,
            "components": None, "uncertainty": None, "reason_codes": _unique(reasons), "legs": []}


def _feed_state(item, cutoff, train_max_age_seconds, alerts_max_fetch_age_seconds):
    """Do not trust a nominal freshness label with impossible observation times."""
    missing = {"status": "MISSING", "source_updated_at": None, "fetched_at": None}
    if not item or item.get("status") not in {"FRESH", "STALE"}:
        return missing
    try:
        source, fetched = instant(item["source_updated_at"]), instant(item["fetched_at"])
        if not source <= fetched <= cutoff:
            return missing
    except (KeyError, ValueError, TypeError, AttributeError):
        return missing
    age = (cutoff - fetched).total_seconds() if item.get("feed_id") == ALERTS_FEED_ID else max(
        (cutoff - source).total_seconds(), (cutoff - fetched).total_seconds())
    threshold = alerts_max_fetch_age_seconds if item.get("feed_id") == ALERTS_FEED_ID else train_max_age_seconds
    state = "STALE" if item["status"] == "STALE" or age > threshold else "FRESH"
    return {"status": state, "source_updated_at": item["source_updated_at"],
            "fetched_at": item["fetched_at"]}


def _aggregate(items):
    if not items or any(item["status"] == "MISSING" for item in items):
        return {"status": "MISSING", "source_updated_at": None, "fetched_at": None}
    return {"status": "STALE" if any(item["status"] == "STALE" for item in items) else "FRESH",
            "source_updated_at": min((item["source_updated_at"] for item in items), key=instant),
            "fetched_at": min((item["fetched_at"] for item in items), key=instant)}


def _matching_checks(request, matching):
    if matching.get("request_fingerprint") != request_fingerprint(request):
        raise ValueError("Matching report does not belong to the complete supplied request.")
    for field in ("request_id", "decision_time", "data_mode", "current_itinerary_id"):
        if matching.get(field) != request.get(field):
            raise ValueError("Matching report does not belong to this request: " + field)
    reports = matching.get("itineraries", [])
    if [route.get("id") for route in reports] != [route["id"] for route in request["itineraries"]]:
        raise ValueError("Matching report itinerary order does not match the supplied request.")
    for route, report in zip(request["itineraries"], reports):
        if [(leg.get("leg_id"), leg.get("mode")) for leg in report.get("legs", [])] != [
                (leg["id"], leg["mode"]) for leg in route["legs"]]:
            raise ValueError("Matching report leg sequence does not match the supplied request.")


def _overlaps(alert, start, end):
    periods = alert.get("active_periods") or []
    return not periods or any(
        (period.get("start") is None or period["start"] <= end.timestamp()) and
        (period.get("end") is None or period["end"] > start.timestamp())
        for period in periods)


def _candidate_alerts(report, candidate, departure, arrival):
    return [alert for alert in report.get("alerts", [])
            if candidate["trip_id"] in alert.get("matched_candidate_trip_ids", []) and
            _overlaps(alert, departure, arrival)]


def _live_candidate(report, cursor, feed_states, diagnostic):
    required = report.get("required_feed_ids", [])
    if not required or any(feed_states.get(feed, {}).get("status") != "FRESH" for feed in required):
        diagnostic["reason_codes"].append("REQUIRED_TRAIN_FEED_NOT_FRESH")
        return None
    if any((report.get(key) or {}).get("status") != "MATCHED"
           for key in ("boarding_station", "alighting_station")):
        diagnostic["reason_codes"].append("STATION_MAPPING_UNRESOLVED")
        return None
    options = []
    for candidate in report.get("candidates", []):
        try:
            departure, arrival = instant(candidate["departure_at"]), instant(candidate["arrival_at"])
            valid = (candidate.get("trip_id") and candidate.get("service_date") and
                     candidate.get("feed_id") in required and
                     feed_states.get(candidate["feed_id"], {}).get("status") == "FRESH" and
                     departure >= cursor and arrival >= departure)
        except (KeyError, ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            diagnostic["rejected_candidates"].append({"trip_id": candidate.get("trip_id"),
                                                       "reason_code": "NOT_CATCHABLE_AT_ACTUAL_READY_TIME"})
            continue
        alerts = _candidate_alerts(report, candidate, departure, arrival)
        # A fresh prediction and a structured no-service alert are conflicting
        # evidence. Do not silently turn either into a proof of feasibility.
        if any(alert.get("effect") == "NO_SERVICE" for alert in alerts):
            diagnostic["rejected_candidates"].append({"trip_id": candidate["trip_id"],
                                                       "reason_code": "NO_SERVICE_ALERT_CONFLICT"})
            continue
        options.append((arrival, departure, candidate["trip_id"], candidate, alerts))
    if not options:
        diagnostic["reason_codes"].append("NO_USABLE_LIVE_CANDIDATE")
        return None
    # For a fixed supplied path and fixed transfer walks, earlier arrival can
    # wait for every connection a later arrival can reach. Departure order alone
    # would be incorrect when trains overtake or serve different stopping paths.
    arrival, departure, _, candidate, alerts = min(options, key=lambda item: item[:3])
    diagnostic["selected_trip_id"] = candidate["trip_id"]
    diagnostic["selected_alert_ids"] = [alert.get("id") for alert in alerts]
    diagnostic["reason_codes"].extend(candidate.get("reason_codes", []))
    return departure, arrival, candidate["trip_id"]


def _provider_segment(leg, cursor):
    try:
        start, end = instant(leg["provider_departure_at"]), instant(leg["provider_arrival_at"])
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    if start < cursor or end < start:
        return None
    return start, end, None


def _leg_result(leg, start, end, cursor, source, trip_id=None):
    return {"leg_id": leg["id"], "mode": leg["mode"], "start_at": _iso(start),
            "end_at": _iso(end), "duration_seconds": (end - start).total_seconds(),
            "wait_before_seconds": (start - cursor).total_seconds(), "source": source,
            "matched_mta_trip_id": trip_id}


def _route_estimate(route, report, cutoff, feed_states, provider_max_age_seconds,
                    allow_provider_fallback, require_fresh_alerts):
    diagnostic = {"id": route["id"], "provider_eta": route.get("provider_eta"),
                  "provider_queried_at": route["provider"]["queried_at"], "reason_codes": [], "legs": []}
    age = (cutoff - instant(route["provider"]["queried_at"])).total_seconds()
    if age < 0 or age > provider_max_age_seconds:
        diagnostic["reason_codes"].append("PROVIDER_TIMING_NOT_FRESH")
        return _empty(route["id"], ["ROUTE_UNAVAILABLE"]), diagnostic
    cursor, estimated, reasons = cutoff, [], []
    transit_sources = set()
    prior_subway = False
    for leg, matched in zip(route["legs"], report["legs"]):
        detail = {"leg_id": leg["id"], "ready_at": _iso(cursor), "selected_trip_id": None,
                  "selected_alert_ids": [], "reason_codes": [], "rejected_candidates": []}
        diagnostic["legs"].append(detail)
        if leg["mode"] == "WALK":
            duration = leg["provider_duration_seconds"]
            try:
                end = cursor + timedelta(seconds=duration)
            except OverflowError:
                raise ValueError("Walking duration exceeds the supported timestamp range.") from None
            estimated.append(_leg_result(leg, cursor, end, cursor, "PROVIDER"))
            cursor, prior_subway = end, False
            continue
        if prior_subway or "MISSING_TRANSFER_WALK" in matched.get("reason_codes", []):
            detail["reason_codes"].append("MISSING_TRANSFER_WALK")
            return _empty(route["id"], ["ROUTE_UNAVAILABLE"]), diagnostic
        prior_subway = True
        if "UNSUPPORTED_TRANSIT_AGENCY" in matched.get("reason_codes", []):
            detail["reason_codes"].append("UNSUPPORTED_TRANSIT_AGENCY")
            return _empty(route["id"], ["ROUTE_UNAVAILABLE"]), diagnostic
        required = matched.get("required_feed_ids", [])
        for feed in required:
            state = feed_states.get(feed, {}).get("status", "MISSING")
            if state != "FRESH":
                reasons.append("STALE_TRAIN_FEED" if state == "STALE" else "MISSING_TRAIN_FEED")
        if not required:
            reasons.append("MISSING_TRAIN_FEED")
        if feed_states.get(ALERTS_FEED_ID, {}).get("status") != "FRESH":
            reasons.append("ALERTS_UNAVAILABLE")
        chosen = _live_candidate(matched, cursor, feed_states, detail)
        source = "MTA_REALTIME"
        if chosen is None:
            reasons.append("UNMATCHED_TRIP")
            conflict = any(item["reason_code"] == "NO_SERVICE_ALERT_CONFLICT"
                           for item in detail["rejected_candidates"])
            chosen = _provider_segment(leg, cursor) if allow_provider_fallback and not conflict else None
            if chosen is not None and any(alert.get("effect") == "NO_SERVICE" and
                                          _overlaps(alert, chosen[0], chosen[1])
                                          for alert in matched.get("provider_alerts", [])):
                detail["reason_codes"].append("PROVIDER_SERVICE_ALERT_CONFLICT_UNRESOLVED")
                chosen = None
            if chosen is None:
                return _empty(route["id"], reasons + ["ROUTE_UNAVAILABLE"]), diagnostic
            source = "PROVIDER"
            reasons.append("PROVIDER_FALLBACK")
            detail["reason_codes"].append("UNVERIFIED_PROVIDER_TRANSIT_FALLBACK")
        start, end, trip_id = chosen
        estimated.append(_leg_result(leg, start, end, cursor, source, trip_id))
        transit_sources.add(source)
        cursor = end
    if transit_sources == {"MTA_REALTIME"}:
        method = "MTA_REALTIME"
    elif "MTA_REALTIME" in transit_sources:
        method = "MIXED"
    else:
        method = "PROVIDER_FALLBACK"
        reasons.append("PROVIDER_FALLBACK")
    # Fresh walking durations already support access and transfers in subway
    # journeys; a supplied all-walking path needs no train or alert observations.
    walking_only = not transit_sources
    eligible = walking_only or (method == "MTA_REALTIME" and (not require_fresh_alerts or "ALERTS_UNAVAILABLE" not in reasons))
    if walking_only:
        diagnostic["reason_codes"].append("FRESH_PROVIDER_WALK_ONLY_ESTIMATE")
    if not eligible:
        diagnostic["reason_codes"].append("DISPLAY_ONLY_ESTIMATE")
    components = {"walking_seconds": sum(item["duration_seconds"] for item in estimated if item["mode"] == "WALK"),
                  "waiting_seconds": sum(item["wait_before_seconds"] for item in estimated),
                  "riding_seconds": sum(item["duration_seconds"] for item in estimated if item["mode"] == "SUBWAY")}
    result = {"id": route["id"], "status": "ESTIMATED", "method": method,
              "comparison_eligible": eligible, "eta": _iso(cursor),
              "total_duration_seconds": (cursor - cutoff).total_seconds(),
              "components": components, "uncertainty": None,
              "reason_codes": _unique(reasons), "legs": estimated}
    return result, diagnostic


def _decision(request, estimates):
    by_id = {route["id"]: route for route in estimates}
    current = by_id.get(request["current_itinerary_id"])
    alternatives = [route for route in estimates if route["id"] != request["current_itinerary_id"]]
    eligible = [by_id[route["id"]] for route in request["itineraries"] if by_id[route["id"]]["comparison_eligible"]]
    best = min(eligible, key=lambda route: route["total_duration_seconds"]) if eligible else None
    complete = bool(current and current["comparison_eligible"] and alternatives and all(
        route["comparison_eligible"] or route["status"] == "INFEASIBLE" for route in alternatives))
    recommendation, savings = None, None
    if current is None:
        action, reason, complete = "NOT_APPLICABLE", "NO_CURRENT_ITINERARY", False
        recommendation = best["id"] if best else None
    elif not current["comparison_eligible"]:
        action, reason, complete = "UNDETERMINED", "CURRENT_INFEASIBLE" if current["status"] == "INFEASIBLE" else "CURRENT_UNAVAILABLE", False
    elif not alternatives:
        action, reason, complete = "UNDETERMINED", "NO_ALTERNATIVES", False
    elif best and best["total_duration_seconds"] < current["total_duration_seconds"]:
        action, reason, recommendation = "SWITCH", "FASTEST_ELIGIBLE_ALTERNATIVE", best["id"]
        savings = current["total_duration_seconds"] - best["total_duration_seconds"]
    elif complete:
        action, reason, recommendation, savings = "STAY", "CURRENT_FASTEST_OR_TIED", current["id"], 0
    else:
        action, reason = "UNDETERMINED", "UNASSESSED_ALTERNATIVES"
    return {"action": action, "recommended_itinerary_id": recommendation,
            "estimated_savings_seconds": savings, "reason_codes": [reason],
            "comparison_complete": complete, "comparison_scope": "SUPPLIED_ITINERARIES"}


def evaluate_baseline(request, matching, *, evaluated_at=None, allow_provider_fallback=True,
                      require_fresh_alerts=True):
    """Return a validated contract Response plus separate baseline diagnostics.

    Freshness thresholds come from the matching policy. Provider transit
    fallbacks are display-only; fresh supplied walking paths remain eligible.
    Missing service
    information also withholds comparison by default, while retaining an ETA.
    """
    validate_request(request)
    _matching_checks(request, matching)
    cutoff = instant(request["decision_time"])
    evaluated_at = evaluated_at or utc_now()
    if instant(evaluated_at) < cutoff:
        raise ValueError("Evaluation time cannot precede the decision cutoff.")
    policy = matching.get("policy", {})
    provider_age = policy.get("provider_max_age_seconds", 300.0)
    train_age = policy.get("train_max_age_seconds", 180.0)
    alerts_age = policy.get("alerts_max_fetch_age_seconds", 300.0)
    for value in (provider_age, train_age, alerts_age):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError("Freshness thresholds must be positive and finite.")
    if not isinstance(allow_provider_fallback, bool) or not isinstance(require_fresh_alerts, bool):
        raise ValueError("Baseline policy switches must be boolean.")
    feed_states = {item["feed_id"]: _feed_state(item, cutoff, train_age, alerts_age)
                   for item in matching.get("feed_status", [])}
    estimates, diagnostics, required = [], [], set()
    for route, matched in zip(request["itineraries"], matching["itineraries"]):
        for leg in matched["legs"]:
            if leg["mode"] == "SUBWAY":
                required.update(leg.get("required_feed_ids") or ["unsupported:" + route["id"]])
        result, diagnostic = _route_estimate(route, matched, cutoff, feed_states, provider_age,
                                             allow_provider_fallback, require_fresh_alerts)
        estimates.append(result)
        diagnostics.append(diagnostic)
    missing = {"status": "MISSING", "source_updated_at": None, "fetched_at": None}
    data_status = {"train_feed": _aggregate([feed_states.get(feed, missing) for feed in sorted(required)]),
                   "alerts_feed": feed_states.get(ALERTS_FEED_ID, missing)}
    warnings = _unique(reason for result in estimates for reason in result["reason_codes"])
    if any(not result["comparison_eligible"] for result in estimates):
        warnings.append("PARTIAL_COVERAGE")
    response = {"schema_version": request["schema_version"], "request_id": request["request_id"],
                "data_mode": request["data_mode"], "decision_time": request["decision_time"],
                "evaluated_at": evaluated_at, "current_itinerary_id": request["current_itinerary_id"],
                "decision": _decision(request, estimates), "itineraries": estimates,
                "data_status": data_status, "model_version": None, "warnings": _unique(warnings)}
    from scripts.validate_contract import load_json, response_invariants, schema_validate
    schema_validate(response, "Response", load_json(REPOSITORY / "algo/contracts/evaluate.schema.json"))
    response_invariants(request, response)
    return {"stage": "BASELINE_EVALUATION", "baseline_version": BASELINE_VERSION, "response": response,
            "diagnostics": {"policy": {"allow_provider_fallback": allow_provider_fallback,
                                        "require_fresh_alerts": require_fresh_alerts,
                                        "provider_max_age_seconds": provider_age,
                                        "calibration_status": "PROVISIONAL"},
                            "itineraries": diagnostics},
            "limitations": ["UNMODIFIED_MTA_PREDICTIONS_NOT_OBSERVED_ARRIVALS",
                            "NO_LEARNED_DELAY_CORRECTION_OR_CALIBRATED_UNCERTAINTY",
                            "PROVIDER_WALKING_DURATIONS_ASSUMED_TO_REACH_PLATFORMS",
                            "BUILDING_ENTRANCES_NOT_INDEPENDENTLY_VERIFIED",
                            "ONLY_SUPPLIED_ITINERARIES_AND_AVAILABLE_TRAIN_HORIZON",
                            "PROVIDER_TRANSIT_FALLBACKS_ARE_DISPLAY_ONLY",
                            "STATION_ENTRANCE_ACCESS_DURING_SERVICE_CHANGES_NOT_VERIFIED",
                            "MISSING_TRAIN_IS_NOT_PROOF_OF_ROUTE_INFEASIBILITY"]}


def evaluate_integration(integration, **options):
    """Evaluate an in-memory Step 2 report without fetching or changing its cutoff."""
    if not integration.get("request") or not integration.get("matching"):
        raise ValueError("No supported provider itinerary is available for baseline evaluation.")
    report = evaluate_baseline(integration["request"], integration["matching"], **options)
    report["provider"] = integration.get("provider", {})
    return report
