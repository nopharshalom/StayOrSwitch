"""Link supplied subway legs to live observations without computing journey ETAs.

``MATCHED`` means candidate services can be linked to every subway leg. It does
not identify the exact train used by the provider, establish an observed arrival,
or make a Stay/Switch recommendation. Reachability propagation exists only to
reject trains that leave before the supplied walking/transfer path reaches them.
"""

from datetime import datetime, timezone
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .mta import ALERTS_FEED_ID, alert_is_active, route_feed_ids, snapshot_status


_MTA_AGENCIES = {"mta", "mta nyct", "nyct", "mtasbwy", "mta new york city transit",
                 "mta nyc transit", "new york city transit", "metropolitan transportation authority"}


def _epoch(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
    else:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("Matching timestamps must include a timezone.")
        result = instant.timestamp()
    if not math.isfinite(result):
        raise ValueError("Matching timestamps must be finite.")
    return result


def _iso(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def _name(value: Any) -> str:
    value = str(value or "").lower().replace("&", " ").replace("/", " ")
    value = re.sub(r"\b(street|avenue|square|station)\b", lambda match: {
        "street": "st", "avenue": "av", "square": "sq", "station": ""
    }[match.group(0)], value)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    term = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, term))))


def _coordinates(location: Dict[str, Any], provider: bool = False) -> Optional[Tuple[float, float]]:
    source = location.get("coordinates") if provider else location
    if not source or source.get("latitude") is None or source.get("longitude") is None:
        return None
    try:
        point = float(source["latitude"]), float(source["longitude"])
    except (ValueError, TypeError):
        return None
    return point if all(math.isfinite(x) for x in point) and -90 <= point[0] <= 90 and -180 <= point[1] <= 180 else None


def _family_id(stop_id: str, stops: Dict[str, Any]) -> str:
    return stops[stop_id].get("parent_station") or stop_id


def _families(stops: Dict[str, Any]) -> Dict[str, List[str]]:
    result = {}  # type: Dict[str, List[str]]
    for stop_id in stops:
        result.setdefault(_family_id(stop_id, stops), []).append(stop_id)
    return result


def _line_ids(label: str, static_data: Dict[str, Any], trips: Iterable[Dict[str, Any]]) -> Set[str]:
    label = label.strip().upper()
    choices = set(static_data.get("route_stops", {})) | set(static_data.get("routes", {}))
    choices.update(trip.get("route_id", "") for trip in trips)
    result = {key for key in choices if key.upper() == label}
    for key, route in static_data.get("routes", {}).items():
        if str(route.get("short_name", "")).strip().upper() == label:
            result.add(key)
    # The provider may omit the diamond express designation. The actual ordered
    # boarding/alighting pair still has to be present in each candidate trip.
    if label in {"6", "7", "F"}:
        result.update(key for key in choices if key.upper() == label + "X")
    return result or {label}


def map_station(location: Dict[str, Any], line_ids: Iterable[str], static_data: Dict[str, Any],
                observed_route_stops: Optional[Dict[str, Set[str]]] = None,
                station_radius_meters: float = 200.0) -> Dict[str, Any]:
    """Resolve one station family; never select the closest of ambiguous stops.

    The radius is a metadata matching tolerance, not a passenger walking limit.
    Current trip stops augment static line membership to support known reroutes.
    """
    if not math.isfinite(station_radius_meters) or station_radius_meters <= 0:
        raise ValueError("Station matching radius must be positive and finite.")
    stops = static_data.get("stops", {})
    families = _families(stops)
    served = set()
    for route_id in line_ids:
        served.update(static_data.get("route_stops", {}).get(route_id, []))
        served.update((observed_route_stops or {}).get(route_id, set()))
    result = {"status": "UNMATCHED", "station_id": None, "platform_stop_ids": [],
              "candidate_station_ids": [], "method": None, "reason_codes": []}
    explicit = location.get("mta_stop_id")
    if explicit is not None and explicit not in stops:
        result["reason_codes"] = ["UNKNOWN_MTA_STOP_ID"]
        return result
    point = _coordinates(location, provider=True)
    provider_name = _name(location.get("name"))
    candidates = []
    exact_names = []
    for family, members in families.items():
        if explicit is not None and family != _family_id(explicit, stops):
            continue
        if not (set(members) | {family}) & served:
            continue
        names = {_name(stops[member].get("name")) for member in members}
        distances = [_distance(point, coords) for member in members
                     if point is not None for coords in [_coordinates(stops[member])] if coords is not None]
        name_matches = bool(provider_name) and provider_name in names
        if explicit is None:
            if point is not None and (not distances or min(distances) > station_radius_meters):
                continue
            if point is None and not name_matches:
                continue
        candidates.append(family)
        if name_matches:
            exact_names.append(family)
    if explicit is None and exact_names:
        candidates = exact_names
    candidates.sort()
    result["candidate_station_ids"] = candidates
    if len(candidates) != 1:
        result["status"] = "AMBIGUOUS" if candidates else "UNMATCHED"
        result["reason_codes"] = ["AMBIGUOUS_STATION" if candidates else "STATION_NOT_RESOLVED_FOR_ROUTE"]
        return result
    family = candidates[0]
    platform_ids = [sid for sid in families[family] if str(stops[sid].get("location_type", "0")) == "0"]
    if explicit is not None and explicit in platform_ids:
        platform_ids = [explicit]
    result.update(status="MATCHED", station_id=family, platform_stop_ids=sorted(platform_ids),
                  method="EXPLICIT_MTA_STOP_ID" if explicit else
                  "COORDINATES_NAME_ROUTE" if point is not None and family in exact_names else
                  "COORDINATES_ROUTE" if point is not None else "NAME_ROUTE")
    if not platform_ids:
        result.update(status="UNMATCHED", reason_codes=["NO_PLATFORM_STOPS"])
    return result


def _choose_snapshots(snapshots: List[Dict[str, Any]], cutoff: float) -> Dict[str, Dict[str, Any]]:
    selected = {}
    for snapshot in snapshots:
        feed_id = snapshot.get("feed_id")
        try:
            fetched = _epoch(snapshot["fetched_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if not feed_id or fetched > cutoff:
            continue
        previous = selected.get(feed_id)
        if previous is None or fetched > _epoch(previous["fetched_at"]):
            selected[feed_id] = snapshot
        elif fetched == _epoch(previous["fetched_at"]) and snapshot != previous:
            # A tie must not let input order hide a failure or conflicting full
            # feed observation. A caller can supply a later unambiguous fetch.
            missing = snapshot if snapshot.get("status") == "MISSING" else previous
            selected[feed_id] = dict(missing, status="MISSING", trips=[], alerts=[],
                                     reason_codes=list(dict.fromkeys(missing.get("reason_codes", []) +
                                                                     ["AMBIGUOUS_SNAPSHOT_AT_SAME_TIME"])))
    return selected


def _trip_observation_reason(trip: Dict[str, Any], snapshot: Dict[str, Any], cutoff: float,
                             max_age: float) -> Optional[str]:
    observed = trip.get("timestamp")
    if observed is None:
        return None
    try:
        observed = _epoch(observed)
    except (ValueError, TypeError):
        return "INVALID_TRIP_OBSERVATION_TIME"
    if observed > cutoff or observed > _epoch(snapshot["fetched_at"]):
        return "FUTURE_TRIP_OBSERVATION"
    if cutoff - observed > max_age:
        return "STALE_TRIP_OBSERVATION"
    return None


def _timing_candidate(trip: Dict[str, Any], boarding: Dict[str, Any], alighting: Dict[str, Any],
                      ready: Optional[float]) -> Tuple[Optional[Dict[str, Any]], str]:
    if trip.get("schedule_relationship") in {"CANCELED", "DELETED"}:
        return None, "TRIP_CANCELED"
    if not trip.get("id") or not re.fullmatch(r"\d{8}", str(trip.get("start_date") or "")):
        return None, "MISSING_SERVICE_DATE_IDENTITY"
    updates = trip.get("stop_updates", [])
    starts = [(index, stop) for index, stop in enumerate(updates) if stop.get("stop_id") in boarding["platform_stop_ids"]]
    ends = [(index, stop) for index, stop in enumerate(updates) if stop.get("stop_id") in alighting["platform_stop_ids"]]
    if not starts:
        return None, "BOARDING_STOP_NOT_IN_TRIP"
    if not ends:
        return None, "ALIGHTING_STOP_NOT_IN_TRIP"
    pairs = [(a, b) for ia, a in starts for ib, b in ends if ib > ia and
             (a.get("stop_sequence") is None or b.get("stop_sequence") is None or b["stop_sequence"] > a["stop_sequence"])]
    if not pairs:
        return None, "STOPS_IN_REVERSE_ORDER"
    if len(pairs) != 1:
        return None, "AMBIGUOUS_STOP_OCCURRENCE"
    start, end = pairs[0]
    if start.get("schedule_relationship") == "SKIPPED" or end.get("schedule_relationship") == "SKIPPED":
        return None, "STOP_SKIPPED"
    if start.get("schedule_relationship") == "NO_DATA" or end.get("schedule_relationship") == "NO_DATA":
        return None, "STOP_PREDICTION_UNAVAILABLE"
    # Arrival is a conservative boarding-time proxy when departure is absent.
    # Arrival at the destination itself is required; departure there is not an
    # arrival prediction and is never silently substituted.
    departure = start.get("departure_time")
    source = "DEPARTURE"
    if departure is None:
        departure, source = start.get("arrival_time"), "ARRIVAL_PROXY"
    arrival = end.get("arrival_time")
    if departure is None or arrival is None:
        return None, "MISSING_STOP_TIME"
    try:
        departure, arrival = _epoch(departure), _epoch(arrival)
    except (TypeError, ValueError):
        return None, "INVALID_STOP_TIME"
    if arrival < departure:
        return None, "NON_MONOTONIC_STOP_TIMES"
    if ready is not None and departure < ready:
        return None, "DEPARTS_BEFORE_READY"
    board_direction = start["stop_id"][-1:] if start["stop_id"][-1:] in {"N", "S"} else None
    end_direction = end["stop_id"][-1:] if end["stop_id"][-1:] in {"N", "S"} else None
    if board_direction and end_direction and board_direction != end_direction:
        return None, "PLATFORM_DIRECTION_CONFLICT"
    candidate = {"trip_id": trip["id"], "raw_trip_id": trip.get("trip_id"), "feed_id": trip.get("feed_id"),
                 "route_id": trip.get("route_id"), "service_date": trip.get("start_date"),
                 "start_time": trip.get("start_time"), "direction_id": trip.get("direction_id"),
                 "nyct_direction": trip.get("nyct_direction"), "platform_direction": board_direction,
                 "boarding_stop_id": start["stop_id"], "alighting_stop_id": end["stop_id"],
                 "departure_at": _iso(departure), "arrival_at": _iso(arrival),
                 "platform_ready_at": _iso(ready),
                 "segment_stop_ids": [stop["stop_id"] for stop in updates[updates.index(start):updates.index(end) + 1]
                                      if stop.get("stop_id")],
                 "boarding_time_source": source, "catchable": True if ready is not None else None,
                 "reason_codes": list(trip.get("reason_codes", []))}
    if source == "ARRIVAL_PROXY":
        candidate["reason_codes"].append("BOARDING_TIME_USES_ARRIVAL_PROXY")
    return candidate, ""


def _selector_relevance(selector: Dict[str, Any], line_ids: Set[str], stop_ids: Set[str],
                        candidates: List[Dict[str, Any]]) -> Optional[str]:
    agency = selector.get("agency_id")
    if agency and _name(agency) not in _MTA_AGENCIES:
        return None
    if selector.get("route_id") and selector["route_id"] not in line_ids:
        return None
    if selector.get("stop_id") and selector["stop_id"] not in stop_ids:
        return None
    matching = candidates
    constrained = False
    if selector.get("direction_id") is not None:
        constrained = True
        matching = [c for c in matching if c.get("direction_id") == selector["direction_id"]]
    trip = selector.get("trip") or {}
    if trip.get("route_id") and trip["route_id"] not in line_ids:
        return None
    if trip.get("trip_id"):
        constrained = True
        matching = [c for c in matching if c.get("raw_trip_id") == trip["trip_id"]]
    if trip.get("start_date"):
        constrained = True
        matching = [c for c in matching if c.get("service_date") == trip["start_date"]]
    if trip.get("start_time"):
        constrained = True
        matching = [c for c in matching if c.get("start_time") == trip["start_time"]]
    if trip.get("direction_id") is not None:
        constrained = True
        matching = [c for c in matching if c.get("direction_id") == trip["direction_id"]]
    if not constrained:
        return "MATCHED"
    if matching:
        return "MATCHED"
    # A leg without identified services cannot resolve trip/direction selectors.
    return "POSSIBLE" if not candidates else None


def relevant_alerts(alerts: Iterable[Dict[str, Any]], line_ids: Set[str], stop_ids: Set[str],
                    candidates: List[Dict[str, Any]], when: str) -> List[Dict[str, Any]]:
    """Match active alert selectors without treating alert text as route geometry."""
    results = []
    for alert in alerts:
        active_now = alert_is_active(alert, when)
        selectors = alert.get("informed_entities") or [{}]
        matches = []
        affected = []
        overlaps_candidate = False
        for candidate in candidates:
            candidate_stops = set(candidate.get("segment_stop_ids", [])) | set(candidate.get("segment_station_ids", []))
            candidate_stops.update(s for s in (candidate.get("boarding_stop_id"), candidate.get("alighting_stop_id")) if s)
            selector_matches = [_selector_relevance(s, {candidate["route_id"]}, candidate_stops, [candidate]) for s in selectors]
            if not any(selector_matches):
                continue
            periods = alert.get("active_periods", [])
            overlap = not periods or any(
                (period.get("start") is None or period["start"] <= _epoch(candidate["arrival_at"])) and
                (period.get("end") is None or period["end"] > _epoch(candidate.get("platform_ready_at") or candidate["departure_at"]))
                for period in periods)
            if active_now or overlap:
                matches.extend(selector_matches)
                affected.append(candidate["trip_id"])
                overlaps_candidate = overlaps_candidate or overlap
        if not candidates and active_now:
            matches = [_selector_relevance(s, line_ids, stop_ids, []) for s in selectors]
        if not any(matches):
            continue
        results.append({"id": alert.get("id"), "effect": alert.get("effect"), "cause": alert.get("cause"),
                        "header": alert.get("header"), "description": alert.get("description"),
                        "selector_match": "MATCHED" if "MATCHED" in matches else "POSSIBLE",
                        "active_at_decision": active_now,
                        "overlaps_candidate_interval": overlaps_candidate,
                        "matched_candidate_trip_ids": affected,
                        "active_periods": alert.get("active_periods", [])})
    return results


def match_request(request: Dict[str, Any], static_data: Dict[str, Any], snapshots: List[Dict[str, Any]], *,
                  station_radius_meters: float = 200.0, train_max_age_seconds: float = 180.0,
                  alerts_max_fetch_age_seconds: float = 300.0, provider_max_age_seconds: float = 300.0) -> Dict[str, Any]:
    """Produce as-of station and candidate-service diagnostics for each itinerary.

    Freshness thresholds are provisional engineering policy, not model confidence.
    This function assumes request schema/invariant validation by its caller and
    never replaces the selected current itinerary or invents an ETA comparison.
    """
    for value in (station_radius_meters, train_max_age_seconds, alerts_max_fetch_age_seconds, provider_max_age_seconds):
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Matching policy values must be positive and finite.")
    cutoff = _epoch(request["decision_time"])
    selected = _choose_snapshots(snapshots, cutoff)
    states = {key: snapshot_status(snapshot, request["decision_time"],
                                  train_max_age_seconds=train_max_age_seconds,
                                  alerts_max_fetch_age_seconds=alerts_max_fetch_age_seconds)
              for key, snapshot in selected.items()}
    fresh_trips = [trip for key, snapshot in selected.items() if states[key] == "FRESH" and snapshot.get("kind") == "train"
                   for trip in snapshot.get("trips", [])]
    trip_observation_reasons = {id(trip): _trip_observation_reason(trip, snapshot, cutoff, train_max_age_seconds)
                                for key, snapshot in selected.items() if states[key] == "FRESH" and snapshot.get("kind") == "train"
                                for trip in snapshot.get("trips", [])}
    fresh_alerts = [alert for key, snapshot in selected.items() if states[key] == "FRESH" and snapshot.get("kind") == "alerts"
                    for alert in snapshot.get("alerts", [])]
    observed = {}  # type: Dict[str, Set[str]]
    for trip in fresh_trips:
        if trip_observation_reasons[id(trip)]:
            continue
        observed.setdefault(trip.get("route_id", ""), set()).update(s.get("stop_id") for s in trip.get("stop_updates", []) if s.get("stop_id"))
    all_feed_ids = set(selected) | {s.get("feed_id") for s in snapshots if s.get("feed_id")} | {ALERTS_FEED_ID}
    route_reports = []
    for route in request["itineraries"]:
        reasons = []
        age = cutoff - _epoch(route["provider"]["queried_at"])
        if age < 0:
            reasons.append("PROVIDER_DATA_AFTER_DECISION")
        elif age > provider_max_age_seconds:
            reasons.append("STALE_PROVIDER_DATA")
        cursor = cutoff if not reasons else None
        legs = []
        prior_subway = False
        for leg in route["legs"]:
            report = {"leg_id": leg["id"], "mode": leg["mode"], "reason_codes": []}
            if leg["mode"] == "WALK":
                duration = leg.get("provider_duration_seconds")
                report.update(status="PROVIDER_WALK", ready_before_at=_iso(cursor), ready_after_at=None)
                if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration < 0:
                    report["reason_codes"].append("MISSING_WALK_DURATION")
                    report["status"], cursor = "UNMATCHED", None
                elif cursor is not None:
                    cursor += duration
                    report["ready_after_at"] = _iso(cursor)
                else:
                    report["reason_codes"].append("UPSTREAM_REACHABILITY_UNKNOWN")
                prior_subway = False
                legs.append(report)
                continue
            if leg["mode"] != "SUBWAY":
                report.update(status="UNMATCHED", reason_codes=["UNSUPPORTED_LEG_MODE"])
                cursor = None
                legs.append(report)
                continue
            if _name(leg["transit"].get("agency")) not in _MTA_AGENCIES:
                report.update(status="UNMATCHED", reason_codes=["UNSUPPORTED_TRANSIT_AGENCY"],
                              boarding_station=None, alighting_station=None, platform_ready_at=None,
                              candidates=[], rejected_candidates=[], reachability_basis_trip_id=None, alerts=[])
                cursor, prior_subway = None, True
                legs.append(report)
                continue
            if prior_subway:
                report["reason_codes"].append("MISSING_TRANSFER_WALK")
                cursor = None
            prior_subway = True
            line_ids = _line_ids(leg["transit"]["route_short_name"], static_data, fresh_trips)
            required = set(route_feed_ids(sorted(line_ids)))
            if not required:
                report["reason_codes"].append("UNSUPPORTED_ROUTE_FEED")
            alerts_state = states.get(ALERTS_FEED_ID, "MISSING")
            if alerts_state != "FRESH":
                report["reason_codes"].append("ALERTS_FEED_" + alerts_state)
            all_feed_ids.update(required)
            for feed_id in sorted(required):
                state = states.get(feed_id, "MISSING")
                if state != "FRESH":
                    report["reason_codes"].append("TRAIN_FEED_" + state)
            boarding = map_station(leg["from"], line_ids, static_data, observed, station_radius_meters)
            alighting = map_station(leg["to"], line_ids, static_data, observed, station_radius_meters)
            report.update(status="UNMATCHED", boarding_station=boarding, alighting_station=alighting,
                          platform_ready_at=_iso(cursor), candidates=[], rejected_candidates=[],
                          reachability_basis_trip_id=None, alerts=[])
            resolved = boarding["status"] == alighting["status"] == "MATCHED"
            if not resolved:
                report["reason_codes"].append("STATION_MAPPING_UNRESOLVED")
            else:
                for trip in fresh_trips:
                    if trip.get("route_id") not in line_ids:
                        continue
                    observation_problem = trip_observation_reasons[id(trip)]
                    if observation_problem:
                        report["rejected_candidates"].append({"trip_id": trip.get("id"), "reason_code": observation_problem})
                        continue
                    candidate, failure = _timing_candidate(trip, boarding, alighting, cursor)
                    if candidate is not None:
                        report["candidates"].append(candidate)
                    else:
                        report["rejected_candidates"].append({"trip_id": trip.get("id"), "reason_code": failure})
            report["candidates"].sort(key=lambda c: (_epoch(c["arrival_at"]), _epoch(c["departure_at"]), c["trip_id"]))
            if cursor is None:
                report["reason_codes"].append("UPSTREAM_REACHABILITY_UNKNOWN")
            if not report["candidates"]:
                report["reason_codes"].append("NO_CATCHABLE_CANDIDATE" if resolved and cursor is not None else "NO_LINKED_CANDIDATE")
            if required and resolved and report["candidates"] and cursor is not None and not any(r.startswith("TRAIN_FEED_") for r in report["reason_codes"]):
                selected_candidate = report["candidates"][0]
                report["status"] = "MATCHED"
                report["reachability_basis_trip_id"] = selected_candidate["trip_id"]
                cursor = _epoch(selected_candidate["arrival_at"])
            else:
                cursor = None
            stop_ids = set(boarding["platform_stop_ids"] + alighting["platform_stop_ids"])
            stop_ids.update(s for s in (boarding["station_id"], alighting["station_id"]) if s)
            for candidate in report["candidates"]:
                candidate["segment_station_ids"] = []
                for stop_id in candidate["segment_stop_ids"]:
                    stop_ids.add(stop_id)
                    if stop_id in static_data.get("stops", {}):
                        family_id = _family_id(stop_id, static_data["stops"])
                        stop_ids.add(family_id)
                        if family_id not in candidate["segment_station_ids"]:
                            candidate["segment_station_ids"].append(family_id)
            report["alerts"] = relevant_alerts(fresh_alerts, line_ids, stop_ids, report["candidates"], request["decision_time"])
            if report["alerts"]:
                report["reason_codes"].append("ACTIVE_SERVICE_ALERT")
            report["reason_codes"] = list(dict.fromkeys(report["reason_codes"]))
            legs.append(report)
        subway_reports = [leg for leg in legs if leg["mode"] == "SUBWAY"]
        matched_count = sum(leg["status"] == "MATCHED" for leg in subway_reports)
        complete = bool(subway_reports) and matched_count == len(subway_reports) and not reasons and all(leg["status"] != "UNMATCHED" for leg in legs)
        status = "MATCHED" if complete else "PARTIAL" if matched_count else "UNMATCHED"
        if not subway_reports:
            reasons.append("NO_SUBWAY_LEGS")
        if not complete:
            reasons.append("MATCHING_INCOMPLETE")
        route_reports.append({"id": route["id"], "provider_eta": route.get("provider_eta"), "status": status,
                              "reason_codes": reasons, "legs": legs})
    feed_report = []
    for feed_id in sorted(all_feed_ids):
        snapshot = selected.get(feed_id)
        feed_report.append({"feed_id": feed_id, "status": states.get(feed_id, "MISSING"),
                            "source_updated_at": snapshot.get("source_updated_at") if snapshot else None,
                            "fetched_at": snapshot.get("fetched_at") if snapshot else None,
                            "reason_codes": list(snapshot.get("reason_codes", [])) if snapshot else ["NO_SNAPSHOT_AT_CUTOFF"]})
    return {"stage": "LIVE_DATA_MATCHING", "request_id": request["request_id"],
            "data_mode": request["data_mode"],
            "decision_time": request["decision_time"], "current_itinerary_id": request.get("current_itinerary_id"),
            "policy": {"station_radius_meters": station_radius_meters, "train_max_age_seconds": train_max_age_seconds,
                       "alerts_max_fetch_age_seconds": alerts_max_fetch_age_seconds,
                       "provider_max_age_seconds": provider_max_age_seconds, "calibration_status": "PROVISIONAL",
                       "assumptions": ["PROVIDER_WALKING_DURATIONS_REACH_BOARDING_STOP", "BUILDING_ENTRANCES_NOT_INDEPENDENTLY_VERIFIED",
                                       "TRAIN_TIMES_ARE_PREDICTIONS", "ABSENT_TRIP_OBSERVATION_TIME_USES_FEED_FRESHNESS",
                                       "CANDIDATES_DO_NOT_IDENTIFY_PROVIDER_TRAIN"]},
            "feed_status": feed_report, "itineraries": route_reports}
