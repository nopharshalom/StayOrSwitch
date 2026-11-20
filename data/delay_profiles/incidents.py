"""As-of incident text and scope, separate from subsequent train outcomes.

The index interns alert versions, keeps snapshot replacement semantics, and
never backdates a later severity upgrade. An archived unchanged alert does not
establish a fresh successful fetch; stale text remains conditional evidence.
"""

from bisect import bisect_right
from collections import Counter, OrderedDict
from copy import deepcopy
from datetime import datetime
import hashlib
import html
import json
import math
import re


STATE_ORDER = {"UNKNOWN": 0, "NORMAL": 1, "PLANNED": 2, "DISRUPTION": 3, "SEVERE": 4}
_ALERT_BASE_ROUTE = {"FX": "F", "7X": "7"}
_FAMILY = re.compile(r"^(lmm:(?:alert|planned_work):[^:]+)(?::.*)?$")
_TAG = re.compile(r"<[^>]*>")
_SEVERE = re.compile(
    r"\b(?:severe|significant|major)\s+delays?\b|\bextremely limited\b|"
    r"\b(?:service (?:is |has been )?suspended|no (?:train )?service|"
    r"trains? (?:are |is )?(?:not running|stopped))\b", re.I)
_DELAY = re.compile(r"\bdelays?\b|\bdelayed\b|\blimited service\b|\brerout(?:ed|ing)\b|"
                    r"\bservice changes?\b|\bskipping\b|\brunning express\b", re.I)
_RECOVERY = re.compile(r"\b(?:normal|regular) service (?:has )?resumed\b|"
                       r"\bon or close to schedule\b|\bno longer delayed\b|"
                       r"\bgood service\b", re.I)
_CLEARED_DELAY = re.compile(
    r"\b(?:(?:severe|significant|major)\s+)?delays?\s+"
    r"(?:(?:have|has)\s+)?(?:ended|cleared|resolved)\b|"
    r"\b(?:(?:severe|significant|major)\s+)?delays?\s+(?:are|is)\s+"
    r"(?:over|resolved|cleared)\b|"
    r"\bno longer\s+(?:experiencing|running with|having)\s+"
    r"(?:(?:severe|significant|major)\s+)?delays?\b|"
    r"\bno longer delayed\b|\bno(?: more)?\s+"
    r"(?:(?:severe|significant|major)\s+)?delays?\b", re.I)
_CAUSES = (
    ("SIGNAL", re.compile(r"\bsignal(?:s|ing)?\b.{0,35}\b(?:malfunction|problem|failure|issue)|"
                          r"\b(?:malfunction|problem|failure)\b.{0,30}\bsignal", re.I)),
    ("TRACK_SWITCH", re.compile(r"\bswitch(?:es)?\b.{0,30}\b(?:problem|malfunction|failure|issue)", re.I)),
    ("FIRE", re.compile(r"\bfire\b|\bsmoke\b", re.I)),
    ("WATER", re.compile(r"\bflood(?:ing|ed)?\b|\bwater\b.{0,45}\btracks?\b|"
                         r"\btracks?\b.{0,45}\bwater\b", re.I)),
    ("MEDICAL", re.compile(r"\b(?:EMS|medical|sick passenger|ill passenger)\b", re.I)),
    ("POLICE", re.compile(r"\b(?:NYPD|police|investigation)\b", re.I)),
    ("MECHANICAL", re.compile(r"\b(?:mechanical|brake|door problem|disabled train|train with a problem)\b", re.I)),
    ("TRACK", re.compile(r"\b(?:track condition|broken rail|rail condition|track problem)\b", re.I)),
    ("WEATHER", re.compile(r"\b(?:weather|snow|ice|storm|wind)\b", re.I)),
    ("TRAIN_TRAFFIC", re.compile(r"\b(?:train traffic|congestion)\b", re.I)),
)


def epoch(value):
    """Parse an explicit instant without assigning a timezone to naive values."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            return None
        number = value.timestamp()
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        if parsed.tzinfo is None:
            return None
        number = parsed.timestamp()
    return number if math.isfinite(number) and number >= 0 else None


def incident_id(alert):
    """Keep a publisher incident together across its status-suffix changes."""
    value = str(alert.get("id") or "")
    match = _FAMILY.fullmatch(value)
    if match:
        return match.group(1)
    if value:
        return value
    # Unknown publisher identities cannot safely merge by a similar cause.
    encoded = json.dumps(alert, sort_keys=True, separators=(",", ":"), default=str)
    return "anonymous:" + hashlib.sha256(encoded.encode()).hexdigest()[:24]


def _text(alert):
    joined = " ".join(_TAG.sub(" ", html.unescape(str(alert.get(key) or "")))
                      for key in ("header", "description"))
    return " ".join(joined.split())


def _alert_routes(route_id):
    """Base-line notices cover express variants, without the reverse inference."""
    line = str(route_id)
    return {line, _ALERT_BASE_ROUTE.get(line, line)}


def _no_service_impact(alert):
    """Expose explicit closures without interpreting named geographic boundaries.

    Empty route IDs denote global wording only when scope is ROUTE_WIDE.
    Generic wording otherwise inherits the publisher's route selectors. Text
    segments remain uncertain even when their named boundaries sound familiar.
    """
    line = r"\[?(?:FX|7X|[1-7ABCDEFGJLMNQRSWZ])\]?"
    lines = rf"{line}(?:\s*(?:,\s*(?:and\s+)?|and\s+|&\s*|/\s*){line})*"
    explicit = re.compile(rf"\b(?P<before>{lines})\s+trains?\s+"
                          rf"(?:are\s+|is\s+)?not (?:running|operating)\b|"
                          rf"\bno\s+(?P<after>{lines})\s+trains?\b", re.I)
    generic = re.compile(r"\b(?:no (?:train )?service|service (?:is |has been )?suspended|"
                         r"trains? (?:are |is )?not (?:running|operating))\b", re.I)
    geographic = re.compile(r"\b(?:between|from|to|at|beyond|north of|south of|"
                            r"east of|west of|in (?:Brooklyn|Manhattan|Queens|the Bronx))\b", re.I)
    routes, scopes = set(), set()
    for sentence in re.split(r"[.!?]", _text(alert)):
        matches = list(explicit.finditer(sentence))
        if not matches and not generic.search(sentence):
            continue
        explicit_routes = set()
        for match in matches:
            route_text = match.group("before") or match.group("after")
            explicit_routes.update(re.findall(r"\b(?:FX|7X|[1-7ABCDEFGJLMNQRSWZ])\b",
                                               route_text.upper()))
        routes.update(explicit_routes or {str(item["route_id"]) for item in
            alert.get("informed_entities", []) if item.get("route_id") is not None})
        boundary_text = re.sub(r"\b(?:due|owing)\s+to\b", "", sentence, flags=re.I)
        scopes.add("TEXT_SEGMENT" if geographic.search(boundary_text) else "ROUTE_WIDE")
    if scopes:
        return {"no_service": True,
                "no_service_scope": "TEXT_SEGMENT" if "TEXT_SEGMENT" in scopes else "ROUTE_WIDE",
                "no_service_route_ids": sorted(routes)}
    return {"no_service": alert.get("effect") == "NO_SERVICE",
            "no_service_scope": "STRUCTURED" if alert.get("effect") == "NO_SERVICE" else None,
            "no_service_route_ids": []}


def classify_alert(alert):
    """Return transparent conservative text labels, not a measured severity score."""
    text = _text(alert)
    types = []
    for value in (alert.get("extensions") or {}).values():
        if isinstance(value, dict):
            types.append(str(value.get("alert_type") or value.get("alertType") or ""))
    kind = " ".join(types).lower()
    planned = (str(alert.get("id") or "").startswith("lmm:planned_work")
               or "planned" in kind or "scheduled maintenance" in text.lower())
    cause = next((name for name, pattern in _CAUSES if pattern.search(text)), None)
    raw_cause = str(alert.get("cause") or "UNKNOWN_CAUSE")
    if cause is None:
        cause = "UNKNOWN" if raw_cause in ("UNKNOWN_CAUSE", "OTHER_CAUSE", "None", "") else raw_cause
    effect = str(alert.get("effect") or "")
    if planned:
        return {"state": "PLANNED", "cause": "MAINTENANCE" if cause == "UNKNOWN" else cause,
                "classification_rule": "PLANNED_NOTICE", "recovery": False}
    # Remove only explicitly cleared/negated delay clauses. Other active
    # impacts remain: restored stopping patterns can coexist with severe delay.
    active_text, cleared_count = _CLEARED_DELAY.subn("", text)
    recovered = cleared_count > 0 or bool(_RECOVERY.search(active_text))
    if recovered and not _SEVERE.search(active_text) and not _DELAY.search(active_text):
        if effect in ("NO_SERVICE", "SIGNIFICANT_DELAYS", "REDUCED_SERVICE", "DETOUR", "MODIFIED_SERVICE"):
            return {"state": "UNKNOWN", "cause": cause,
                    "classification_rule": "RECOVERY_CONFLICTS_WITH_STRUCTURED_IMPACT", "recovery": False}
        return {"state": "NORMAL", "cause": cause,
                "classification_rule": "EXPLICIT_RECOVERY", "recovery": True}
    if (_SEVERE.search(active_text) or effect in ("NO_SERVICE", "SIGNIFICANT_DELAYS")
            or _no_service_impact(alert)["no_service"]):
        return {"state": "SEVERE", "cause": cause,
                "classification_rule": "EXPLICIT_SEVERE_IMPACT", "recovery": False}
    if _DELAY.search(active_text) or effect in ("REDUCED_SERVICE", "DETOUR", "MODIFIED_SERVICE"):
        return {"state": "DISRUPTION", "cause": cause,
                "classification_rule": "EXPLICIT_SERVICE_IMPACT", "recovery": False}
    if effect == "NO_EFFECT":
        return {"state": "NORMAL", "cause": cause,
                "classification_rule": "EXPLICIT_NO_EFFECT", "recovery": False}
    return {"state": "UNKNOWN", "cause": cause,
            "classification_rule": "UNCLASSIFIED_NOTICE", "recovery": False}


def _parent(stop):
    return stop[:-1] if isinstance(stop, str) and stop.endswith(("N", "S")) else stop


def _active(alert, cutoff):
    periods = alert.get("active_periods") or [{}]
    invalid = False
    for period in periods:
        start, end = epoch(period.get("start")), epoch(period.get("end"))
        if ((period.get("start") is not None and start is None)
                or (period.get("end") is not None and end is None)
                or (start is not None and end is not None and end <= start)):
            invalid = True
            continue
        if (start is None or start <= cutoff) and (end is None or cutoff < end):
            return True
    return None if invalid else False


def _scope(alert, route_id, stop_ids, impact=None):
    """Selectors are ORed; unsupported constraints never become a definite match."""
    selectors = alert.get("informed_entities") or [{}]
    requested = set(stop_ids or ())
    parents = {_parent(stop) for stop in requested}
    directions = {stop[-1] for stop in requested if isinstance(stop, str) and stop.endswith(("N", "S"))}
    possible = False
    scope = "GLOBAL"
    for selector in selectors:
        agency = selector.get("agency_id")
        if agency and agency not in ("MTASBWY", "MTA NYCT", "MTA", "NYCT"):
            continue
        line = selector.get("route_id")
        if line is not None and str(line) not in _alert_routes(route_id):
            continue
        stop = selector.get("stop_id")
        if stop is not None:
            if not requested:
                possible = True
                continue
            if stop not in requested and _parent(stop) not in parents:
                continue
            if str(stop).endswith(("N", "S")) and directions and str(stop)[-1] not in directions:
                continue
        if selector.get("trip") or selector.get("direction_id") is not None:
            possible = True
            continue
        impact = impact if impact is not None else _no_service_impact(alert)
        if (impact["no_service_scope"] == "TEXT_SEGMENT"
                and (not impact["no_service_route_ids"]
                     or _alert_routes(route_id).intersection(impact["no_service_route_ids"]))):
            possible = True
            continue
        scope = "STOP" if stop is not None else "ROUTE" if line is not None else "GLOBAL"
        # Only explicit compass words are mapped to the platform namespace.
        # Borough-bound wording cannot be universally mapped to N/S.
        header = str(alert.get("header") or "").lower()
        north = bool(re.search(r"\b(?:northbound|uptown)\b", header))
        south = bool(re.search(r"\b(?:southbound|downtown)\b", header))
        explicit_both = bool(re.search(r"\bboth directions\b|"
            r"\b(?:northbound|uptown)\s+(?:and|/)\s+(?:southbound|downtown)\b|"
            r"\b(?:southbound|downtown)\s+(?:and|/)\s+(?:northbound|uptown)\b", header))
        if north and south and not explicit_both:
            # A global severity classifier cannot assign different direction
            # clauses to individual lines without a richer text interpretation.
            possible = True
            continue
        if len(directions) == 1 and north != south:
            if (north and "N" not in directions) or (south and "S" not in directions):
                continue
        return True, scope
    return (None if possible else False), "AMBIGUOUS" if possible else "UNRELATED"


class IncidentIndex:
    """Compact full-snapshot alert index with cutoff-aware replacement semantics."""

    def __init__(self, snapshots, max_age_seconds=300):
        if isinstance(max_age_seconds, bool) or not math.isfinite(max_age_seconds) or max_age_seconds < 0:
            raise ValueError("Maximum alert age must be finite and nonnegative.")
        self.max_age_seconds = max_age_seconds
        self.versions = {}
        self.families = {}
        self.counts = Counter()
        self._context_cache = OrderedDict()
        records = {}
        for snapshot in snapshots:
            if snapshot.get("feed_id") != "subway-alerts" and snapshot.get("kind") != "alerts":
                continue
            self.counts["input_alert_snapshots"] += 1
            captured = epoch(snapshot.get("captured_at", snapshot.get("fetched_at")))
            if captured is None:
                self.counts["unindexable_capture"] += 1
                continue
            fetched = epoch(snapshot.get("fetched_at", captured))
            source = epoch(snapshot.get("source_updated_at"))
            requested = epoch(snapshot.get("requested_at", fetched))
            valid = (snapshot.get("status") == "AVAILABLE" and fetched is not None
                     and abs(fetched - captured) < 0.001 and source is not None
                     and source <= fetched and requested is not None and requested <= fetched)
            version_ids = []
            if valid:
                for alert in snapshot.get("alerts", []):
                    encoded = json.dumps(alert, sort_keys=True, separators=(",", ":"), allow_nan=False)
                    key = hashlib.sha256(encoded.encode()).hexdigest()
                    if key not in self.versions:
                        self.versions[key] = {"alert": deepcopy(alert), **classify_alert(alert),
                                              **_no_service_impact(alert),
                                              "incident_id": incident_id(alert)}
                    version_ids.append(key)
            record = {"captured_at": captured, "source_updated_at": source,
                      "valid": valid, "version_ids": tuple(sorted(set(version_ids)))}
            previous = records.get(captured)
            if previous is not None and previous != record:
                records[captured] = {"captured_at": captured, "source_updated_at": source,
                                     "valid": False, "version_ids": (), "conflicting": True}
                self.counts["conflicting_captures"] += 1
            elif previous is None:
                records[captured] = record
            else:
                self.counts["identical_captures"] += 1
        self.entries = [records[at] for at in sorted(records)]
        self.times = [item["captured_at"] for item in self.entries]
        # Build identities only from accepted observations, never conflicting ones.
        for entry in self.entries:
            if not entry["valid"]:
                continue
            for key in entry["version_ids"]:
                version = self.versions[key]
                family = self.families.setdefault(version["incident_id"], {
                    "incident_id": version["incident_id"], "first_observed_at": entry["captured_at"],
                    "last_observed_at": entry["captured_at"], "route_ids": set(), "states": set(),
                    "causes": set(), "versions": {},
                })
                family["last_observed_at"] = entry["captured_at"]
                family["route_ids"].update(str(selector["route_id"]) for selector in
                    version["alert"].get("informed_entities", []) if selector.get("route_id") is not None)
                family["states"].add(version["state"])
                family["causes"].add(version["cause"])
                item = family["versions"].setdefault(key, {"version_id": key,
                    "first_observed_at": entry["captured_at"], "last_observed_at": entry["captured_at"],
                    "state": version["state"], "cause": version["cause"],
                    "classification_rule": version["classification_rule"], "alert": version["alert"]})
                item["last_observed_at"] = entry["captured_at"]

    def context_at(self, cutoff, route_id, stop_ids=None):
        cutoff = epoch(cutoff)
        if cutoff is None:
            raise ValueError("Cutoff must identify a timezone-aware instant.")
        result = {"state": "UNKNOWN", "cause": "UNKNOWN", "incident_ids": [],
                  "severe_incident_ids": [], "ambiguous_scope": False, "applicable": None,
                  "evidence_status": "UNKNOWN", "first_observed_at": None, "age_seconds": None,
                  "alerts": [], "possible_alerts": [], "scope_ambiguous": False,
                  "captured_at": None, "receipt_age_seconds": None, "reason": "NO_ASOF_ALERT_CAPTURE"}
        index = bisect_right(self.times, cutoff) - 1
        if index < 0:
            return result
        cache_key = (index, cutoff, str(route_id), tuple(sorted(set(stop_ids or ()))))
        cached = self._context_cache.get(cache_key)
        if cached is not None:
            self._context_cache.move_to_end(cache_key)
            return deepcopy(cached)
        entry = self.entries[index]
        result.update(captured_at=entry["captured_at"], receipt_age_seconds=cutoff - entry["captured_at"])
        if not entry["valid"]:
            result["reason"] = "LATEST_ALERT_CAPTURE_INVALID"
            return result
        fresh = cutoff - entry["captured_at"] <= self.max_age_seconds
        result["evidence_status"] = "FRESH" if fresh else "LAST_OBSERVED"
        matched, possible = [], []
        for key in entry["version_ids"]:
            version = self.versions[key]
            alert = version["alert"]
            active = _active(alert, cutoff)
            if active is False:
                continue
            relevant, scope = _scope(alert, route_id, stop_ids, version)
            if relevant is False:
                continue
            family = self.families[version["incident_id"]]
            detail = {"id": alert.get("id"), "incident_id": version["incident_id"],
                      "version_id": key, "state": version["state"], "cause": version["cause"],
                      "classification_rule": version["classification_rule"], "scope": scope,
                      "effect": alert.get("effect"), "source_cause": alert.get("cause"),
                      "no_service": version["no_service"],
                      "no_service_scope": version["no_service_scope"],
                      "no_service_route_ids": list(version["no_service_route_ids"]),
                      "captured_at": entry["captured_at"],
                      "first_observed_at": family["first_observed_at"],
                      "age_seconds": cutoff - family["first_observed_at"],
                      "header": alert.get("header"), "description": alert.get("description"),
                      "informed_entities": deepcopy(alert.get("informed_entities") or []),
                      "active_periods": deepcopy(alert.get("active_periods") or []),
                      "recovery": version["recovery"]}
            (matched if relevant is True and active is True else possible).append(detail)
        result.update(alerts=matched, possible_alerts=possible, scope_ambiguous=bool(possible))
        result.update(ambiguous_scope=bool(possible), applicable=True if matched else None if possible else False,
                      severe_incident_ids=sorted({item["incident_id"] for item in matched if item["state"] == "SEVERE"}))
        ids = sorted({item["incident_id"] for item in matched + possible})
        result["incident_ids"] = ids
        if ids:
            first = min(self.families[value]["first_observed_at"] for value in ids)
            result.update(first_observed_at=first, age_seconds=cutoff - first)
        if matched:
            dominant = max(matched, key=lambda item: STATE_ORDER[item["state"]])
            state = dominant["state"]
            if state == "NORMAL" and (possible or any(item["state"] == "UNKNOWN" for item in matched)):
                state = "UNKNOWN"
            if state == "NORMAL" and not fresh:
                state = "UNKNOWN"
            causes = sorted({item["cause"] for item in matched if item["state"] == dominant["state"]})
            result.update(state=state, cause=causes[0] if len(causes) == 1 else "MULTIPLE",
                          reason="ASOF_APPLICABLE_NOTICE" if fresh else "LAST_OBSERVED_NOTICE_NOT_FRESH")
        elif fresh and not possible:
            result.update(state="NORMAL", reason="FRESH_NO_APPLICABLE_NOTICE")
        else:
            result["reason"] = "AMBIGUOUS_NOTICE_SCOPE" if possible else "STALE_ABSENCE_IS_NOT_NORMAL"
        self._context_cache[cache_key] = deepcopy(result)
        if len(self._context_cache) > 10000:
            self._context_cache.popitem(last=False)
        return result

    def inventory(self):
        """Return descriptive whole-period evidence, never prediction features."""
        incidents = []
        for family in sorted(self.families.values(), key=lambda value: (value["first_observed_at"], value["incident_id"])):
            value = {key: deepcopy(family[key]) for key in ("incident_id", "first_observed_at", "last_observed_at")}
            value.update({key: sorted(family[key]) for key in ("route_ids", "states", "causes")})
            value["versions"] = sorted((deepcopy(item) for item in family["versions"].values()),
                                       key=lambda item: (item["first_observed_at"], item["version_id"]))
            incidents.append(value)
        return {"schema_version": "october-incident-inventory-v1", "incidents": incidents,
                "snapshot_count": len(self.entries), "version_count": len(self.versions),
                "incident_count": len(incidents), "counts": dict(self.counts),
                "classification": "DETERMINISTIC_TEXT_RULES_NOT_INDEPENDENTLY_VALIDATED_CAUSAL_LABELS",
                "freshness_policy": "LAST_OBSERVED_CONTENT_IS_NOT_A_FRESH_SUCCESSFUL_FETCH"}

    def report(self):
        """Expose compact inventory counts without repeating every alert text."""
        inventory = self.inventory()
        return {key: value for key, value in inventory.items() if key != "incidents"}
