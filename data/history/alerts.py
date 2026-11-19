"""Join historical service alerts using original collection-time availability.

Train and alert files are grouped separately inside the daily archive. Build this
index before enriching the compact derived rows; archive order is not temporal
availability. Alert text is not interpreted as proof that a route is infeasible.
"""

from bisect import bisect_left, bisect_right
from collections import Counter, OrderedDict, defaultdict
from copy import deepcopy
import hashlib
import json
from urllib.parse import unquote

from .features import epoch


_AGENCIES = {"mta", "mta nyct", "nyct", "mtasbwy", "mta new york city transit",
             "mta nyc transit", "new york city transit", "metropolitan transportation authority"}


def _stop_matches(selector_stop, stops):
    if selector_stop in stops:
        return True
    # An undirected parent station includes both platforms; a directed platform
    # selector must retain its direction instead of matching the opposite one.
    return selector_stop and not selector_stop.endswith(("N", "S")) and any(
        stop.endswith(("N", "S")) and stop[:-1] == selector_stop for stop in stops)


def _trip_parts(identity):
    parts = [unquote(part) for part in (identity or "").split(":")]
    if len(parts) != 6 or parts[0] != "MTA":
        return {}
    return {"service_date": parts[2], "route_id": parts[3], "trip_id": parts[4], "start_time": parts[5] or None}


def _row_scope(row):
    features = row["features"]
    pattern = features.get("segment_stop_pattern")
    if pattern is None:
        pattern = list(features.get("remaining_stop_pattern") or [])
        target = row.get("stop_id", features.get("stop_id"))
        if target in pattern:
            pattern = pattern[:pattern.index(target) + 1]
        elif target:
            pattern.append(target)
    direction = features.get("gtfs_direction_id")
    if direction is None and features.get("direction") in (0, 1):
        direction = features["direction"]
    return features.get("route_id"), tuple(pattern), direction, _trip_parts(row.get("trip_identity"))


def _selector_matches(selector, route, stops, direction, trip):
    """Return definite/possible/none; fields in one selector are conjunctive."""
    agency = selector.get("agency_id")
    if agency and " ".join(str(agency).lower().split()) not in _AGENCIES:
        return None
    if selector.get("route_id") and selector["route_id"] != route:
        return None
    if selector.get("stop_id") and not _stop_matches(selector["stop_id"], stops):
        return None
    # Extension fields may add constraints whose semantics this pipeline has
    # not implemented. Keep them visible as possible matches, never certainty.
    uncertain = bool(selector.get("extensions"))
    selected_trip = selector.get("trip") or {}
    if selected_trip.get("route_id") and selected_trip["route_id"] != route:
        return None
    for field, source_field in (("trip_id", "trip_id"), ("start_date", "service_date"),
                                ("start_time", "start_time")):
        wanted = selected_trip.get(field)
        if wanted is not None:
            actual = trip.get(source_field)
            if actual is None:
                uncertain = True
            elif str(wanted) != str(actual):
                return None
    for wanted in (selector.get("direction_id"), selected_trip.get("direction_id")):
        if wanted is not None:
            if direction is None:
                uncertain = True
            elif str(wanted) != str(direction):
                return None
    return "possible" if uncertain else "definite"


def _period_state(alert, decision, horizon):
    """Active periods are half-open; include known future starts by arrival."""
    periods = alert.get("active_periods") or [{}]
    active, upcoming = False, False
    for period in periods:
        start, end = period.get("start"), period.get("end")
        if (start is None or start <= decision) and (end is None or decision < end):
            active = True
        elif start is not None and decision < start <= horizon and (end is None or end > start):
            upcoming = True
    return "active" if active else "upcoming" if upcoming else None


def _alert_types(alert):
    values = []
    for extension in (alert.get("extensions") or {}).values():
        if isinstance(extension, dict) and extension.get("alert_type"):
            values.append(str(extension["alert_type"]))
    return values


class AlertsIndex:
    """A compact collection-time index with bounded matching-result caching."""

    def __init__(self, *, maximum_fetch_age_seconds=300, cache_size=20000):
        if maximum_fetch_age_seconds < 0 or cache_size < 1:
            raise ValueError("Alert freshness must be nonnegative and cache size positive.")
        self.maximum_fetch_age_seconds = maximum_fetch_age_seconds
        self.cache_size = cache_size
        self.times = []
        self.entries = []
        self.contents = {}
        self.cache = OrderedDict()
        self.counts = Counter()

    def _intern_content(self, alerts):
        compact = []
        identities = {}
        for alert in alerts:
            value = {key: deepcopy(alert.get(key)) for key in
                     ("id", "active_periods", "informed_entities", "cause", "effect", "extensions")}
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
            identity = value.get("id") or hashlib.sha256(encoded.encode()).hexdigest()
            previous = identities.get(identity)
            if previous is not None:
                if previous != encoded:
                    raise ValueError("Conflicting records share one alert identity.")
                continue
            identities[identity] = encoded
            for period in value.get("active_periods") or []:
                start, end = epoch(period.get("start")), epoch(period.get("end"))
                if start is not None and end is not None and end <= start:
                    raise ValueError("Alert active period has invalid ordering.")
                period["start"], period["end"] = start, end
            compact.append(value)
        encoded = json.dumps(compact, sort_keys=True, separators=(",", ":"))
        key = hashlib.sha256(encoded.encode()).hexdigest()
        if key not in self.contents:
            by_route, global_alerts, boundaries = defaultdict(list), [], set()
            for alert in compact:
                selectors = alert.get("informed_entities") or [{}]
                routes = {selector.get("route_id") or (selector.get("trip") or {}).get("route_id")
                          for selector in selectors}
                if None in routes:
                    global_alerts.append(alert)
                else:
                    for route in routes:
                        by_route[route].append(alert)
                for period in alert.get("active_periods") or []:
                    boundaries.update(value for value in (period.get("start"), period.get("end")) if value is not None)
            self.contents[key] = {"alerts": compact, "by_route": dict(by_route),
                                  "global": global_alerts, "boundaries": sorted(boundaries)}
        return key

    def add(self, snapshot, captured_at=None):
        """Record even failed captures, so an older success cannot hide failure."""
        self.counts["snapshots_added"] += 1
        try:
            capture = epoch(captured_at if captured_at is not None else snapshot.get(
                "captured_at", snapshot.get("fetched_at")))
        except (TypeError, ValueError):
            capture = None
        if capture is None:
            self.counts["unindexable_capture"] += 1
            return
        valid = snapshot.get("status", "AVAILABLE") == "AVAILABLE"
        try:
            source = epoch(snapshot.get("source_updated_at"))
            valid = valid and source is not None and source <= capture
            content = self._intern_content(snapshot.get("alerts", [])) if valid else None
        except (TypeError, ValueError):
            source, content, valid = None, None, False
        reason = None if valid else "INVALID_OR_UNAVAILABLE_ALERT_SNAPSHOT"
        entry = {"capture": capture, "source": source, "content": content, "reason": reason,
                 "member": snapshot.get("member_name")}
        position = bisect_left(self.times, capture)
        if position < len(self.times) and self.times[position] == capture:
            previous = self.entries[position]
            if (previous["content"], previous["source"], previous["reason"]) == (content, source, reason):
                self.counts["duplicate_captures"] += 1
                return
            entry.update(content=None, source=None, reason="CONFLICTING_ALERT_CAPTURE")
            self.entries[position] = entry
            self.counts["conflicting_captures"] += 1
        else:
            self.times.insert(position, capture)
            self.entries.insert(position, entry)
        self.counts["valid_captures" if valid else "invalid_captures"] += 1

    def _match(self, content_key, row, decision, horizon):
        content = self.contents[content_key]
        route, pattern, direction, trip = _row_scope(row)
        boundaries = content["boundaries"]
        cache_key = (content_key, route, pattern, direction, tuple(sorted(trip.items())),
                     bisect_right(boundaries, decision), bisect_right(boundaries, horizon))
        if cache_key in self.cache:
            self.cache.move_to_end(cache_key)
            return self.cache[cache_key]
        counts = Counter()
        effects, causes, types = set(), set(), set()
        candidates = content["global"] + content["by_route"].get(route, [])
        for alert in candidates:
            temporal = _period_state(alert, decision, horizon)
            if temporal is None:
                continue
            matches = [_selector_matches(selector, route, pattern, direction, trip)
                       for selector in (alert.get("informed_entities") or [{}])]
            match = "definite" if "definite" in matches else "possible" if "possible" in matches else None
            if match is None:
                continue
            counts[temporal + "_" + match] += 1
            if match == "definite":
                if alert.get("effect"):
                    effects.add(str(alert["effect"]))
                if alert.get("cause"):
                    causes.add(str(alert["cause"]))
                types.update(_alert_types(alert))
        result = {
            "service_alert_count": counts["active_definite"],
            "service_alert_possible_count": counts["active_possible"],
            "known_upcoming_service_alert_count": counts["upcoming_definite"],
            "known_upcoming_service_alert_possible_count": counts["upcoming_possible"],
            "service_alert_effects": sorted(effects), "service_alert_causes": sorted(causes),
            "service_alert_types": sorted(types),
        }
        self.cache[cache_key] = result
        if len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return result

    def features_for(self, row):
        """Return only inputs available by this row's collection-time cutoff."""
        self.counts["rows_joined"] += 1
        decision = epoch(row.get("decision_at"))
        if decision is None:
            raise ValueError("A row decision timestamp is required.")
        values = {"service_alerts_available": False, "service_alert_count": None,
                  "service_alert_possible_count": None, "known_upcoming_service_alert_count": None,
                  "known_upcoming_service_alert_possible_count": None, "service_alert_effects": None,
                  "service_alert_causes": None, "service_alert_types": None,
                  "service_alert_capture_at": None, "service_alert_source_updated_at": None,
                  "service_alert_fetch_age_seconds": None, "service_alert_status": "MISSING",
                  "service_alert_context_status": "UNAVAILABLE",
                  "last_observed_relevant_alert_count": None,
                  "last_observed_possible_alert_count": None,
                  "last_observed_alert_age_seconds": None}
        position = bisect_right(self.times, decision) - 1
        if position < 0:
            self.counts["rows_missing_prior_capture"] += 1
            return values
        entry = self.entries[position]
        age = decision - entry["capture"]
        values.update(service_alert_capture_at=entry["capture"],
                      service_alert_source_updated_at=entry["source"], service_alert_fetch_age_seconds=age,
                      last_observed_alert_age_seconds=age)
        if entry["reason"] is not None:
            values["service_alert_status"] = entry["reason"]
            self.counts["rows_unavailable_snapshot"] += 1
            return values
        try:
            horizon = epoch(row["features"].get("mta_arrival_at"))
        except (ValueError, TypeError):
            horizon = None
        horizon = max(decision, horizon if horizon is not None else decision)
        matched = self._match(entry["content"], row, decision, horizon)
        values.update(last_observed_relevant_alert_count=matched["service_alert_count"],
                      last_observed_possible_alert_count=matched["service_alert_possible_count"])
        if age > self.maximum_fetch_age_seconds:
            values.update(service_alert_status="STALE", service_alert_context_status="LAST_OBSERVED_UNVERIFIED")
            self.counts["rows_stale_capture"] += 1
            return values
        values.update({key: list(value) if isinstance(value, list) else value
                       for key, value in matched.items()})
        values.update(service_alerts_available=True, service_alert_status="FRESH", service_alert_context_status="FRESH")
        self.counts["rows_with_fresh_alerts"] += 1
        self.counts["rows_with_active_relevant_alerts"] += values["service_alert_count"] > 0
        self.counts["rows_with_known_upcoming_alerts"] += values["known_upcoming_service_alert_count"] > 0
        return values

    def report(self):
        return {"counts": dict(self.counts), "indexed_captures": len(self.times),
                "distinct_alert_contents": len(self.contents),
                "policy": {"maximum_fetch_age_seconds": self.maximum_fetch_age_seconds,
                           "availability_clock": "ARCHIVE_COLLECTOR_CAPTURE_TIME",
                           "old_source_header_allowed_with_fresh_capture": True,
                           "stale_capture": "LAST_OBSERVED_CONTEXT_ONLY_NOT_EVIDENCE_OF_COLLECTION_FAILURE",
                           "selector_fields_are_conjunctive": True,
                           "unknown_direction_or_trip_identity": "POSSIBLE_SEPARATE_COUNT",
                           "known_future_alerts": "STARTS_AFTER_DECISION_AND_BY_PREDICTED_TARGET_ARRIVAL",
                           "alert_text_implies_infeasibility": False}}
