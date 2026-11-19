"""A small Google Routes client; route generation remains with the provider."""

import json

from .network import NetworkError


GOOGLE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
PILOT_ORIGIN = "Hayden LIC Apartments, 43-25 Hunter Street, Long Island City, NY 11101"
PILOT_DESTINATION = "NYU Tandon School of Engineering, 6 MetroTech Center, Brooklyn, NY 11201"
FIELD_MASK = ",".join([
    "routes.duration", "routes.distanceMeters", "routes.routeLabels",
    "routes.legs.startLocation", "routes.legs.endLocation",
    "routes.legs.steps.travelMode", "routes.legs.steps.staticDuration",
    "routes.legs.steps.startLocation", "routes.legs.steps.endLocation",
    "routes.legs.steps.transitDetails",
])


def query_routes(client, api_key, origin=PILOT_ORIGIN, destination=PILOT_DESTINATION):
    if not api_key or any(c.isspace() for c in api_key):
        raise ValueError("A valid local GOOGLE_ROUTES_API_KEY setting is required.")
    if not origin.strip() or not destination.strip():
        raise ValueError("Origin and destination addresses must be nonempty.")
    payload = {
        "origin": {"address": origin}, "destination": {"address": destination},
        "travelMode": "TRANSIT", "computeAlternativeRoutes": True,
        "transitPreferences": {"allowedTravelModes": ["SUBWAY"]},
        "languageCode": "en-US",
    }
    result = client.post_json(GOOGLE_ROUTES_URL, payload, {
        "Content-Type": "application/json", "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    })
    try:
        response = json.loads(result.body)
    except ValueError:
        raise NetworkError("INVALID_PROVIDER_JSON", "Google returned an unreadable JSON response.") from None
    if not isinstance(response, dict) or not isinstance(response.get("routes", []), list):
        raise NetworkError("INVALID_PROVIDER_RESPONSE", "Google returned an invalid routes collection.")
    return {"requested_at": result.requested_at, "received_at": result.fetched_at,
            "http_status": result.status_code, "request": payload, "response": response}
