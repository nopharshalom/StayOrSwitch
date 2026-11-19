"""Normalize Google Compute Routes responses without generating new routes.

Only provider WALK steps and MTA SUBWAY steps are supported. Walking geometry
must join within 25 metres. An explicit walk may meet a station representative
point within a configurable 250 metres, with an access-time warning. These
tolerances reconcile location labels, not walking time: every walking duration
must still come from an explicit provider step.
The function performs no I/O and never assigns an MTA stop or trip identifier.
"""

import copy
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone


_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)"
)
_DURATION = re.compile(r"(?:0|[1-9]\d*)(?:\.\d{1,9})?s")
_MTA_AGENCIES = {
    "mta", "mta new york city transit", "new york city transit",
    "mta nyc transit", "nyc transit",
}
_LOCATION_FIELDS = {"id", "name", "coordinates", "provider_place_id", "mta_stop_id"}
_BOUNDARY_TOLERANCE_METRES = 25.0


class _InvalidRoute(ValueError):
    def __init__(self, code, message, path):
        super().__init__(message)
        self.code, self.path = code, path


def _fail(code, message, path):
    raise _InvalidRoute(code, message, path)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _instant(value, path):
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        _fail("INVALID_TIMESTAMP", "An explicit-offset timestamp is required.", path)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("INVALID_TIMESTAMP", "Timestamp is not a valid calendar instant.", path)


def _timestamp(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _duration(value, path):
    if not isinstance(value, str) or not _DURATION.fullmatch(value):
        _fail("MISSING_OR_INVALID_DURATION", "A nonnegative Google seconds duration is required.", path)
    result = float(value[:-1])
    if not math.isfinite(result):
        _fail("MISSING_OR_INVALID_DURATION", "Duration must be finite.", path)
    return result


def _coordinates(value, path):
    if not isinstance(value, dict):
        _fail("MISSING_OR_INVALID_LOCATION", "Coordinates are required.", path)
    result = {}
    for field, bound in (("latitude", 90), ("longitude", 180)):
        number = value.get(field)
        if (isinstance(number, bool) or not isinstance(number, (int, float))
                or abs(number) > bound or not math.isfinite(number)):
            _fail("MISSING_OR_INVALID_LOCATION", "Coordinates are invalid.", path)
        result[field] = number
    return result


def _point(value, path):
    return _coordinates(value.get("latLng") if isinstance(value, dict) else None, path)


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _endpoint(value, path):
    if not isinstance(value, dict) or set(value) != _LOCATION_FIELDS:
        _fail("INVALID_ENDPOINT", "Supply a complete contract Location object.", path)
    if not _text(value.get("id")) or not _text(value.get("name")):
        _fail("INVALID_ENDPOINT", "Endpoint identity and name are required.", path)
    for key in ("provider_place_id", "mta_stop_id"):
        if value[key] is not None and not _text(value[key]):
            _fail("INVALID_ENDPOINT", "Optional endpoint identifiers must be nonempty strings.", path)
    if value["coordinates"] is not None:
        _coordinates(value["coordinates"], path + ".coordinates")
        if set(value["coordinates"]) != {"latitude", "longitude"}:
            _fail("INVALID_ENDPOINT", "Unexpected coordinate fields.", path)
    return copy.deepcopy(value)


def _stop(value, path):
    if not isinstance(value, dict) or not _text(value.get("name")):
        _fail("MISSING_STOP", "A named transit stop is required.", path)
    coordinates = _point(value.get("location"), path + ".location")
    # Canonical precision prevents provider float noise from redefining a stop.
    coordinates = {key: round(number, 5) for key, number in coordinates.items()}
    name = " ".join(value["name"].split())
    return {
        "id": "google-stop-" + _digest([name, coordinates]),
        "name": name, "coordinates": coordinates,
        "provider_place_id": None, "mta_stop_id": None,
    }


def _distance(first, second):
    lat1, lat2 = math.radians(first["latitude"]), math.radians(second["latitude"])
    delta_lat = lat2 - lat1
    delta_lon = math.radians(second["longitude"] - first["longitude"])
    term = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, term)))


def _boundary(first, second, path, reconciliations):
    distance = _distance(first, second)
    if distance > _BOUNDARY_TOLERANCE_METRES:
        _fail("DISCONNECTED_PROVIDER_GEOMETRY", "Provider step endpoints do not join.", path)
    if distance > 0.01:
        reconciliations.append({"path": path, "distance_metres": round(distance, 3)})


def _station_endpoint(endpoint, stop):
    return (endpoint["name"].strip().casefold() == stop["name"].casefold()
            and endpoint["coordinates"] is not None
            and _distance(endpoint["coordinates"], stop["coordinates"]) <= _BOUNDARY_TOLERANCE_METRES)


def _normalize_route(route, index, queried_at, origin, destination, station_boundary_tolerance_metres):
    base = "routes[{}]".format(index)
    if not isinstance(route, dict):
        _fail("INVALID_ROUTE", "A route object is required.", base)
    original_duration = _duration(route.get("duration"), base + ".duration")
    raw_legs = route.get("legs")
    if not isinstance(raw_legs, list) or not raw_legs:
        _fail("MISSING_STEPS", "Route legs and steps are required.", base + ".legs")
    units, reconciliations, subway_durations = [], [], []
    for leg_index, raw_leg in enumerate(raw_legs):
        steps = raw_leg.get("steps") if isinstance(raw_leg, dict) else None
        path = "{}.legs[{}].steps".format(base, leg_index)
        if not isinstance(steps, list) or not steps:
            _fail("MISSING_STEPS", "Each provider leg must contain steps.", path)
        for step_index, step in enumerate(steps):
            step_path = "{}[{}]".format(path, step_index)
            if not isinstance(step, dict):
                _fail("INVALID_STEP", "A step object is required.", step_path)
            mode = step.get("travelMode")
            if mode == "WALK":
                unit = {"mode": "WALK", "duration": _duration(step.get("staticDuration"), step_path + ".staticDuration"),
                        "start": _point(step.get("startLocation"), step_path + ".startLocation"),
                        "end": _point(step.get("endLocation"), step_path + ".endLocation"), "path": step_path}
            elif mode == "TRANSIT":
                details = step.get("transitDetails")
                line = details.get("transitLine") if isinstance(details, dict) else None
                if not isinstance(line, dict) or not isinstance(line.get("vehicle"), dict) or line["vehicle"].get("type") != "SUBWAY":
                    _fail("UNSUPPORTED_TRANSIT_MODE", "Only SUBWAY transit vehicles are supported.", step_path)
                agencies = line.get("agencies")
                if (not isinstance(agencies, list) or not agencies
                        or any(not isinstance(agency, dict) or not _text(agency.get("name"))
                               or " ".join(agency["name"].casefold().split()) not in _MTA_AGENCIES for agency in agencies)):
                    _fail("UNSUPPORTED_AGENCY", "Only identified MTA subway agencies are supported.", step_path)
                if not _text(line.get("nameShort")):
                    _fail("MISSING_LINE", "A provider subway line short name is required.", step_path)
                stops = details.get("stopDetails")
                if not isinstance(stops, dict):
                    _fail("MISSING_STOP", "Transit stop details are required.", step_path)
                start = _stop(stops.get("departureStop"), step_path + ".transitDetails.stopDetails.departureStop")
                end = _stop(stops.get("arrivalStop"), step_path + ".transitDetails.stopDetails.arrivalStop")
                departure, arrival = stops.get("departureTime"), stops.get("arrivalTime")
                if departure is None or arrival is None:
                    _fail("MISSING_TRANSIT_TIMING", "Both subway departure and arrival times are required.", step_path)
                seconds = (_instant(arrival, step_path + ".arrivalTime") - _instant(departure, step_path + ".departureTime")).total_seconds()
                if seconds < 0:
                    _fail("INVALID_TRANSIT_TIMING", "Subway arrival precedes departure.", step_path)
                static = None if "staticDuration" not in step else _duration(step["staticDuration"], step_path + ".staticDuration")
                subway_durations.append({"path": step_path, "static_duration_seconds": static, "clock_duration_seconds": seconds})
                headsign = details.get("headsign")
                if headsign is not None and not _text(headsign):
                    _fail("INVALID_HEADSIGN", "Headsign must be a nonempty string or null.", step_path)
                unit = {"mode": "SUBWAY", "duration": seconds, "from": start, "to": end,
                        "start": start["coordinates"], "end": end["coordinates"], "departure": departure, "arrival": arrival,
                        "transit": {"agency": "MTA New York City Transit", "provider_route_id": None,
                                    "route_short_name": line["nameShort"].strip(), "headsign": headsign,
                                    "direction_id": None, "provider_trip_id": None}, "path": step_path}
                for field, point in (("startLocation", unit["start"]), ("endLocation", unit["end"])):
                    if field in step:
                        _boundary(_point(step[field], step_path + "." + field), point, step_path + "." + field, reconciliations)
            else:
                _fail("UNSUPPORTED_MODE", "Only WALK and identified MTA SUBWAY steps are supported.", step_path)
            if units:
                if units[-1]["mode"] == unit["mode"] == "SUBWAY":
                    _fail("MISSING_TRANSFER_WALK", "Consecutive subway steps lack explicit transfer walking duration.", step_path)
                previous = units[-1]
                distance = _distance(previous["end"], unit["start"])
                station_boundary = previous["mode"] != unit["mode"]
                if station_boundary and distance > _BOUNDARY_TOLERANCE_METRES:
                    if distance > station_boundary_tolerance_metres:
                        _fail("DISCONNECTED_PROVIDER_GEOMETRY", "Walking and station points exceed the station boundary tolerance.", step_path)
                    walking_point = previous["end"] if previous["mode"] == "WALK" else unit["start"]
                    station_point = unit["start"] if unit["mode"] == "SUBWAY" else previous["end"]
                    reconciliations.append({"path": step_path, "distance_metres": round(distance, 3),
                                            "reason": "PROVIDER_PLATFORM_ACCESS_UNVERIFIED",
                                            "walking_endpoint_coordinates": walking_point,
                                            "station_point_coordinates": station_point,
                                            "tolerance_metres": station_boundary_tolerance_metres,
                                            "walking_duration_adjustment_seconds": 0})
                else:
                    _boundary(previous["end"], unit["start"], step_path, reconciliations)
            units.append(unit)

    for endpoint, point, path in ((origin, units[0]["start"], base + ".origin"), (destination, units[-1]["end"], base + ".destination")):
        if endpoint["coordinates"] is not None:
            _boundary(endpoint["coordinates"], point, path, reconciliations)
    if units[0]["mode"] == "SUBWAY" and not _station_endpoint(origin, units[0]["from"]):
        _fail("MISSING_ACCESS_WALK", "The origin-to-platform walking duration is missing.", base)
    if units[-1]["mode"] == "SUBWAY" and not _station_endpoint(destination, units[-1]["to"]):
        _fail("MISSING_EGRESS_WALK", "The platform-to-destination walking duration is missing.", base)

    grouped = []
    for unit in units:
        if unit["mode"] == "WALK" and grouped and grouped[-1]["mode"] == "WALK":
            grouped[-1]["duration"] += unit["duration"]
            if not math.isfinite(grouped[-1]["duration"]):
                _fail("MISSING_OR_INVALID_DURATION", "Grouped duration must be finite.", base)
        else:
            grouped.append(dict(unit))

    legs, structure = [], []
    previous_train_arrival, transfer_walking = None, 0.0
    for position, unit in enumerate(grouped):
        if unit["mode"] == "WALK":
            start = origin if position == 0 else grouped[position - 1]["to"]
            end = destination if position == len(grouped) - 1 else grouped[position + 1]["from"]
            transfer_walking += unit["duration"]
        else:
            start = origin if position == 0 else unit["from"]
            end = destination if position == len(grouped) - 1 else unit["to"]
            if previous_train_arrival is not None:
                available = (_instant(unit["departure"], unit["path"]) - previous_train_arrival).total_seconds()
                if available < transfer_walking:
                    _fail("UNREACHABLE_PROVIDER_TRANSFER", "The supplied train departs before the preceding ride and explicit transfer walk finish.", unit["path"])
            previous_train_arrival = _instant(unit["arrival"], unit["path"])
            transfer_walking = 0.0
        # A train's final headsign can change while the ridden segment stays the same.
        # Caller endpoint IDs are stable identities; display labels are not.
        structure.append([unit["mode"], start["id"], end["id"], unit.get("transit", {}).get("route_short_name")])
        legs.append({"id": "leg-{}".format(position + 1), "mode": unit["mode"], "from": start, "to": end,
                     "provider_duration_seconds": unit["duration"], "provider_departure_at": unit.get("departure"),
                     "provider_arrival_at": unit.get("arrival"), "transit": unit.get("transit")})

    transit_legs = [leg for leg in legs if leg["mode"] == "SUBWAY"]
    egress = legs[-1]["provider_duration_seconds"] if legs[-1]["mode"] == "WALK" else 0
    try:
        if transit_legs:
            last_arrival = transit_legs[-1]["provider_arrival_at"]
            eta = _instant(last_arrival, base) + timedelta(seconds=egress)
            eta_basis = "LAST_SUBWAY_ARRIVAL_PLUS_EGRESS"
        else:
            last_arrival = None
            eta = _instant(queried_at, "queried_at") + timedelta(seconds=egress)
            eta_basis = "WALKING_FROM_QUERY"
    except OverflowError:
        _fail("INVALID_TRANSIT_TIMING", "Destination arrival is outside the supported calendar range.", base)
    itinerary_id = "google-route-" + _digest(structure)
    itinerary = {"id": itinerary_id, "provider": {"name": "Google Routes", "itinerary_id": None, "queried_at": queried_at},
                 "provider_eta": _timestamp(eta), "legs": legs}
    provenance = {"original_duration_seconds": original_duration, "subway_durations": subway_durations,
                  "last_subway_arrival_at": last_arrival, "egress_walking_seconds": egress,
                  "derived_provider_eta": itinerary["provider_eta"], "eta_basis": eta_basis,
                  "duration_vs_clock_difference_seconds": (eta - _instant(queried_at, "queried_at")).total_seconds() - original_duration,
                  "boundary_reconciliations": reconciliations,
                  "unverified_endpoint_coordinates": [name for name, endpoint in (("origin", origin), ("destination", destination)) if endpoint["coordinates"] is None]}
    return itinerary, provenance


def normalize_google_response(response, *, queried_at, received_at, origin, destination,
                              decision_time, current_itinerary_id=None,
                              station_boundary_tolerance_metres=250.0):
    """Return a contract Request plus rejection/deduplication provenance.

    ``origin`` and ``destination`` are complete contract Location objects. The
    caller supplies timestamps for the request, receipt, and snapshot cutoff;
    all observations must be available by the cutoff. The output is marked
    live; synthetic callers must explicitly relabel test data if persisted.
    Station-boundary tolerance is a mapping policy, never an added travel-time
    estimate. Reconciled station offsets over 25 metres are explicitly flagged.
    A missing selected current route invalidates the request rather than
    silently selecting another reference. Invalid input yields issues and a
    null request. No response or decision is estimated here.
    """
    result = {"request": None, "issues": [], "provenance": []}

    def issue(error, index=None):
        result["issues"].append({"code": error.code, "message": str(error), "route_index": index, "path": error.path})

    try:
        query = _instant(queried_at, "queried_at")
        receipt = _instant(received_at, "received_at")
        cutoff = _instant(decision_time, "decision_time")
        if not query <= receipt <= cutoff:
            _fail("INVALID_SNAPSHOT_TIMING", "Require queried_at <= received_at <= decision_time.", "decision_time")
        origin, destination = _endpoint(origin, "origin"), _endpoint(destination, "destination")
        if origin["id"] == destination["id"] and origin != destination:
            _fail("CONFLICTING_LOCATION_ID", "One location ID cannot describe different endpoints.", "destination.id")
        if current_itinerary_id is not None and not _text(current_itinerary_id):
            _fail("INVALID_CURRENT_ITINERARY", "Current itinerary must be a nonempty ID or null.", "current_itinerary_id")
        if (isinstance(station_boundary_tolerance_metres, bool)
                or not isinstance(station_boundary_tolerance_metres, (int, float))):
            _fail("INVALID_MAPPING_TOLERANCE", "Station mapping tolerance must be a finite number of at least 25 metres.", "station_boundary_tolerance_metres")
        try:
            station_boundary_tolerance_metres = float(station_boundary_tolerance_metres)
        except OverflowError:
            _fail("INVALID_MAPPING_TOLERANCE", "Station mapping tolerance must be finite.", "station_boundary_tolerance_metres")
        if not math.isfinite(station_boundary_tolerance_metres) or station_boundary_tolerance_metres < 25:
            _fail("INVALID_MAPPING_TOLERANCE", "Station mapping tolerance must be a finite number of at least 25 metres.", "station_boundary_tolerance_metres")
        routes = response.get("routes") if isinstance(response, dict) else None
        if not isinstance(routes, list):
            _fail("INVALID_RESPONSE", "The Google response must contain a routes array.", "routes")
        if not routes:
            _fail("NO_ROUTES", "The provider returned no itineraries.", "routes")
    except _InvalidRoute as error:
        issue(error)
        return result

    selected, groups = {}, {}
    for index, route in enumerate(routes):
        record = {"route_index": index, "itinerary_id": None, "status": "REJECTED", "selected": False,
                  "source_route_indices": [index], "queried_at": queried_at, "received_at": received_at,
                  "original_duration_seconds": None}
        result["provenance"].append(record)
        try:
            if isinstance(route, dict):
                record["original_duration_seconds"] = _duration(route.get("duration"), "routes[{}].duration".format(index))
            itinerary, details = _normalize_route(route, index, queried_at, origin, destination, station_boundary_tolerance_metres)
            record.update(details)
            for boundary in details["boundary_reconciliations"]:
                if boundary.get("reason") == "PROVIDER_PLATFORM_ACCESS_UNVERIFIED":
                    issue(_InvalidRoute("PROVIDER_PLATFORM_ACCESS_UNVERIFIED", "An explicit walking endpoint differs from the named station point; platform access time is unverified and provider walking time is unchanged.", boundary["path"]), index)
            itinerary_id = itinerary["id"]
            record["itinerary_id"] = itinerary_id
            groups.setdefault(itinerary_id, []).append(index)
            prior = selected.get(itinerary_id)
            if prior is None or _instant(itinerary["provider_eta"], "provider_eta") < _instant(prior[0]["provider_eta"], "provider_eta"):
                selected[itinerary_id] = (itinerary, index)
        except _InvalidRoute as error:
            issue(error, index)

    for itinerary_id, indices in groups.items():
        chosen = selected[itinerary_id][1]
        for index in indices:
            result["provenance"][index].update(source_route_indices=list(indices), selected=index == chosen,
                                               status="NORMALIZED" if index == chosen else "DUPLICATE")
    if current_itinerary_id is not None and current_itinerary_id not in selected:
        issue(_InvalidRoute("CURRENT_ITINERARY_MISSING", "The selected current route is absent or unsupported; supply it before evaluation.", "current_itinerary_id"))
        return result
    if not selected:
        return result
    itineraries = [item[0] for item in selected.values()]
    locations = {}
    for itinerary in itineraries:
        for leg in itinerary["legs"]:
            for location in (leg["from"], leg["to"]):
                existing = locations.setdefault(location["id"], location)
                if existing != location:
                    issue(_InvalidRoute("CONFLICTING_LOCATION_ID", "One location ID has conflicting definitions.", "itineraries"))
                    return result
    result["request"] = {"schema_version": "1.0", "request_id": "google-" + _digest([queried_at, received_at, decision_time, [item["id"] for item in itineraries]]),
                         "data_mode": "live", "decision_time": decision_time, "user_state": "NOT_BOARDED",
                         "origin": origin, "destination": destination, "current_itinerary_id": current_itinerary_id, "itineraries": itineraries}
    return result
