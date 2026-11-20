"""Summarize current provider routes without treating them as historical outcomes."""

import math

from stayorswitch.google_routes import normalize_google_response
from stayorswitch.integration import endpoint


def duration_seconds(value):
    if not isinstance(value, str) or not value.endswith("s"):
        return None
    try:
        number = float(value[:-1])
    except ValueError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def select_stay(routes):
    """Preserve a unique explicit default even when an alternative is faster."""
    defaults = [index for index, route in enumerate(routes)
                if "DEFAULT_ROUTE" in route.get("routeLabels", [])]
    if len(defaults) == 1:
        return {"route_index": defaults[0], "method": "GOOGLE_DEFAULT_ROUTE"}
    if defaults:
        return {"route_index": None, "method": "AMBIGUOUS_GOOGLE_DEFAULT_ROUTES"}
    available = [(duration_seconds(route.get("duration")), index)
                 for index, route in enumerate(routes)]
    available = [(duration, index) for duration, index in available if duration is not None]
    if not available:
        return {"route_index": None, "method": "NO_USABLE_PROVIDER_DURATION"}
    return {"route_index": min(available)[1],
            "method": "FASTEST_PROVIDER_DURATION_NO_EXPLICIT_DEFAULT"}


def summarize_capture(provider, corridor):
    routes = provider["response"].get("routes", [])
    selection = select_stay(routes)
    normalized = normalize_google_response(provider["response"],
        queried_at=provider["requested_at"], received_at=provider["received_at"],
        decision_time=provider["received_at"],
        origin=endpoint("origin", corridor["origin"]),
        destination=endpoint("destination", corridor["destination"]))
    provenance = {row["route_index"]: row for row in normalized["provenance"]}
    summaries = []
    for index, route in enumerate(routes):
        segments = []
        for leg_index, leg in enumerate(route.get("legs", [])):
            for step_index, step in enumerate(leg.get("steps", [])):
                detail = step.get("transitDetails", {})
                line, stops = detail.get("transitLine", {}), detail.get("stopDetails", {})
                segments.append({"leg_index": leg_index, "step_index": step_index,
                    "travel_mode": step.get("travelMode"),
                    "static_duration_seconds": duration_seconds(step.get("staticDuration")),
                    "start_location": step.get("startLocation"), "end_location": step.get("endLocation"),
                    "line": line.get("nameShort"), "vehicle_type": line.get("vehicle", {}).get("type"),
                    "headsign": detail.get("headsign"),
                    "departure_stop": stops.get("departureStop"), "arrival_stop": stops.get("arrivalStop"),
                    "departure_time": stops.get("departureTime"), "arrival_time": stops.get("arrivalTime")})
        record = provenance.get(index, {})
        summaries.append({"route_index": index, "route_labels": route.get("routeLabels", []),
            "provider_duration_seconds": duration_seconds(route.get("duration")),
            "selected_as_stay": selection["route_index"] == index,
            "normalization_status": record.get("status", "UNAVAILABLE"),
            "normalized_itinerary_id": record.get("itinerary_id"),
            "steps": segments})
    chosen = next((row for row in summaries if row["selected_as_stay"]), None)
    return {"corridor": corridor, "requested_at": provider["requested_at"],
        "received_at": provider["received_at"], "http_status": provider["http_status"],
        "stay_selection": selection, "selected_stay_normalization_status":
            chosen["normalization_status"] if chosen else "UNAVAILABLE",
        "routes": summaries, "normalization": normalized,
        "current_provider_minutes_are_not_historical_outcomes": True}
