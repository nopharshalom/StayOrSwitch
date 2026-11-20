"""Verified archive evidence for a fixed-route passenger execution replay.

This module constructs observations and screened endpoint events. It does not
choose a route or a train, and never fills missing outcomes with a timetable or
with the last forecast merely because a stop disappeared from the feed.
"""

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from data.november_outcomes import screen_labels
from data.october.labels import canonical_event_trip_id
from data.october.sources import (epoch, read_labels, read_snapshots, sha256,
                                  write_gzip_json, write_json)
from stayorswitch.matching import _timing_candidate, _trip_observation_reason


SCHEMA_VERSION = "route-execution-archive-v2"
OBSERVATION_LOOKBACK_SECONDS = 120.0
ENDPOINT_AGE_SECONDS = 180.0


def _json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def leg_key(leg, actual_route=None):
    return (leg["feed_id"], actual_route or leg["route_id"],
            leg["from_stop_id"], leg["to_stop_id"])


def _windows(windows):
    if windows is None:
        return None
    output = []
    for first, last in sorted((epoch(a), epoch(b)) for a, b in windows):
        if first > last:
            raise ValueError("Archive windows must be ordered.")
        if output and first <= output[-1][1]:
            output[-1][1] = max(output[-1][1], last)
        else:
            output.append([first, last])
    return output


def _in_windows(at, windows):
    if windows is None:
        return True
    starts = [item[0] for item in windows]
    index = bisect_right(starts, at) - 1
    return index >= 0 and at <= windows[index][1]


def _endpoint(labels, aliases, canonical, stop_id, endpoint):
    records = [labels[alias][stop_id] for alias in aliases
               if alias in labels and stop_id in labels[alias]]
    if not records:
        return None, ["MISSING_LABEL_RECORD"], []
    values, flags, sources = set(), set(), []
    for label in records:
        reasons = list(label.get("quality_flags", [])) + list(label.get(endpoint + "_quality_flags", []))
        if label.get("canonical_event_trip_id") != canonical:
            reasons.append("CANONICAL_LABEL_IDENTITY_MISMATCH")
        if label.get(endpoint + "_usable") is not True:
            reasons.append("UNUSABLE_ENDPOINT_LABEL")
        value = None
        try:
            value = epoch(label.get(endpoint + "_at"))
        except (ValueError, TypeError, OverflowError):
            pass
        if value is None:
            reasons.append("MISSING_OR_INVALID_ENDPOINT_TIME")
        flags.update(reasons)
        if value is not None:
            values.add(value)
        sources.append({key: label.get(key) for key in (
            "feed_id", "route_id", "service_date", "raw_trip_id", "stop_id",
            endpoint + "_at", "confirmed_at", "stop_last_observed_at",
            "confirmation_status", "canonical_event_trip_id")})
    if len(values) > 1:
        flags.add("CONFLICTING_CANONICAL_ALIAS_ENDPOINTS")
    return (next(iter(values)) if len(values) == 1 and not flags else None,
            sorted(flags), sorted(sources, key=lambda x: json.dumps(x, sort_keys=True)))


def _observation(trip, snapshot, origin, destination, ambiguous):
    at = epoch(snapshot.get("captured_at", snapshot["fetched_at"]))
    source = epoch(snapshot.get("source_updated_at"))
    reason = None
    if ambiguous:
        reason = "AMBIGUOUS_SIMULTANEOUS_TRAIN_IDENTITY"
    elif canonical_event_trip_id(trip) is None:
        reason = "UNRESOLVED_CANONICAL_TRAIN_IDENTITY"
    else:
        reason = _trip_observation_reason(trip, snapshot, at, 180)
    candidate, timing_reason = _timing_candidate(
        trip, {"platform_stop_ids": [origin]}, {"platform_stop_ids": [destination]}, None)
    if candidate and candidate.get("boarding_time_source") != "DEPARTURE":
        candidate, timing_reason = None, "TRUE_DEPARTURE_PREDICTION_REQUIRED"
    if reason:
        state = "UNKNOWN"
    elif candidate:
        state = "COMPATIBLE"
    else:
        reason = timing_reason
        state = "INCOMPATIBLE" if reason in {
            "TRIP_CANCELED", "ALIGHTING_STOP_NOT_IN_TRIP", "STOPS_IN_REVERSE_ORDER",
            "STOP_SKIPPED", "PLATFORM_DIRECTION_CONFLICT"} else "UNKNOWN"
    terminal = None
    if state == "INCOMPATIBLE":
        if trip.get("schedule_relationship") == "CANCELED":
            terminal = "CANCELED"
        elif reason == "STOP_SKIPPED":
            boarding_skipped = any(stop.get("stop_id") == origin and
                                   stop.get("schedule_relationship") == "SKIPPED"
                                   for stop in trip.get("stop_updates", []))
            terminal = "BOARDING_STOP_SKIPPED" if boarding_skipped else "ALIGHTING_STOP_SKIPPED"
    return {"at": at, "source_at": source, "path_status": state,
            "reason_codes": [reason] if reason else [],
            "explicit_terminal_state": terminal,
            "departure_forecast_at": epoch(candidate["departure_at"]) if candidate else None,
            "arrival_forecast_at": epoch(candidate["arrival_at"]) if candidate else None,
            "trip_id": trip.get("id"), "snapshot_sha256": snapshot.get("sha256")}


def build_from_snapshots(snapshots, templates, labels, *, windows=None):
    """Build evidence from an iterable; labels must pass the November screen.

    Future observations remain timestamped. Consumers must establish route
    compatibility at or before boarding, never using a later pattern to repair
    an earlier decision. Simultaneous aliases are retained as unknown evidence.
    """
    original_windows = _windows(windows)
    expanded_windows = _windows([(a - OBSERVATION_LOOKBACK_SECONDS,
                                  b + OBSERVATION_LOOKBACK_SECONDS)
                                 for a, b in original_windows]) if original_windows is not None else None
    pairs = defaultdict(set)
    for template in templates:
        for leg in template["legs"]:
            for line in leg.get("route_ids", [leg["route_id"]]):
                pairs[(leg["feed_id"], line)].add((leg["from_stop_id"], leg["to_stop_id"]))
    screened, screening = screen_labels(labels, ENDPOINT_AGE_SECONDS)
    canonical_aliases = defaultdict(set)
    for identity, stops in screened.items():
        for label in stops.values():
            canonical = label.get("canonical_event_trip_id")
            if canonical:
                canonical_aliases[canonical].add(identity)
    events, feed_records, counts = {}, defaultdict(dict), Counter()
    for snapshot in snapshots:
        feed = snapshot.get("feed_id")
        if not any(key[0] == feed for key in pairs):
            continue
        try:
            at = epoch(snapshot.get("captured_at", snapshot["fetched_at"]))
            source = epoch(snapshot.get("source_updated_at"))
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
        if at is None or not _in_windows(at, expanded_windows):
            continue
        eligible = (snapshot.get("status") in {"AVAILABLE", "FRESH"}
                    and snapshot.get("replay_freshness", "FRESH") == "FRESH"
                    and source is not None and 0 <= at - source <= 180
                    and snapshot.get("incrementality", "FULL_DATASET") == "FULL_DATASET")
        record = {"at": at, "source_at": source, "eligible": eligible,
                  "sha256": snapshot.get("sha256")}
        previous = feed_records[feed].get(at)
        if previous and previous != record:
            record["eligible"] = False
            record["conflict"] = True
        feed_records[feed][at] = record
        counts["snapshots"] += 1
        if not eligible:
            counts["unusable_snapshots"] += 1
            continue
        trips = snapshot.get("trips", [])
        identities = Counter(t.get("id") for t in trips)
        physicals = [canonical_event_trip_id(t) for t in trips]
        physical_counts = Counter(x for x in physicals if x is not None)
        for trip_position, (trip, canonical) in enumerate(zip(trips, physicals)):
            applicable = pairs.get((feed, trip.get("route_id")))
            if not applicable:
                continue
            stops = {stop.get("stop_id") for stop in trip.get("stop_updates", [])}
            identity = trip.get("id")
            if not identity:
                identity = "UNRESOLVED_OBSERVATION:" + feed + ":" + str(at) + ":" + str(trip_position)
                trip = dict(trip, id=identity)
            physical = canonical or "UNRESOLVED:" + identity
            ambiguous = identities[identity] != 1 or (canonical and physical_counts[canonical] != 1)
            for origin, destination in applicable:
                key = (feed, trip["route_id"], origin, destination, physical)
                if origin not in stops:
                    # Whole-trip CANCELED messages normally have no stops.
                    # They can update a previously observed canonical path;
                    # they cannot invent an unobserved route, and ambiguity
                    # still produces UNKNOWN rather than cancellation proof.
                    if (trip.get("schedule_relationship") != "CANCELED" or
                            canonical is None or key not in events):
                        continue
                if key not in events:
                    events[key] = {"trip_id": identity, "canonical_trip_id": physical,
                        "trip_aliases": set(), "feed_id": feed, "route_id": trip["route_id"],
                        "from_stop_id": origin, "to_stop_id": destination, "observations": []}
                event = events[key]
                event["trip_aliases"].add(identity)
                event["observations"].append(_observation(trip, snapshot, origin, destination, ambiguous))
                counts["origin_observations" if origin in stops else "terminal_state_observations"] += 1
    feed_times = {feed: sorted(records) for feed, records in feed_records.items()}
    finalized = []
    for key, event in sorted(events.items()):
        canonical = event["canonical_trip_id"]
        aliases = event["trip_aliases"] | canonical_aliases.get(canonical, set())
        event["trip_aliases"] = sorted(aliases)
        event["observations"].sort(key=lambda row: (row["at"], row["trip_id"]))
        # Equal-time alias conflicts remain explicit; no optimistic ETA wins.
        by_time = defaultdict(list)
        for row in event["observations"]:
            by_time[row["at"]].append(row)
        observations = []
        for at, rows in sorted(by_time.items()):
            row = rows[0]
            if any(other != row for other in rows[1:]):
                row = dict(row, path_status="UNKNOWN", reason_codes=["AMBIGUOUS_SIMULTANEOUS_TRAIN_IDENTITY"],
                           departure_forecast_at=None, arrival_forecast_at=None,
                           explicit_terminal_state=None)
            times = feed_times[event["feed_id"]]
            next_capture = bisect_right(times, at)
            # A full snapshot supersedes previous membership. Absence is not
            # passage or cancellation, but it cannot leave an old compatible
            # path valid until the generic freshness limit expires.
            row["valid_until_at"] = times[next_capture] if next_capture < len(times) else None
            observations.append(row)
        event["observations"] = observations
        event["first_observed_at"] = observations[0]["at"]
        event["last_observed_at"] = observations[-1]["at"]
        departure, dep_flags, dep_sources = _endpoint(screened, aliases, canonical, event["from_stop_id"], "departure")
        arrival, arr_flags, arr_sources = _endpoint(screened, aliases, canonical, event["to_stop_id"], "arrival")
        if departure is not None and arrival is not None and arrival < departure:
            departure = arrival = None
            dep_flags.append("NONMONOTONIC_ENDPOINT_LABEL")
            arr_flags.append("NONMONOTONIC_ENDPOINT_LABEL")
        event.update(departure_at=departure, arrival_at=arrival,
                     endpoint_flags={"boarding": dep_flags, "alighting": arr_flags},
                     endpoint_evidence={"boarding": dep_sources, "alighting": arr_sources})
        counts["events"] += 1
        counts["usable_departures" if departure is not None else "unusable_departures"] += 1
        counts["usable_arrivals" if arrival is not None else "unusable_arrivals"] += 1
        finalized.append(event)
    return {"schema_version": SCHEMA_VERSION, "events": finalized,
            "feed_records": {feed: [record for _, record in sorted(records.items())]
                             for feed, records in sorted(feed_records.items())},
            "windows": original_windows, "endpoint_screening": screening,
            "counts": dict(sorted(counts.items())),
            "policy": {"membership_lookback_seconds": OBSERVATION_LOOKBACK_SECONDS,
                       "executor_supplies_fixed_case_observation_start": True,
                       "endpoint_max_absolute_age_seconds": ENDPOINT_AGE_SECONDS,
                       "future_observation_times_preserved": True,
                       "unknown_events_retained": True,
                       "event_times_are_final_mta_prediction_proxies": True}}


class RouteArchive:
    """Query timestamped candidate evidence without performing train selection."""

    def __init__(self, payload):
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported route archive schema.")
        self.payload = payload
        self._events = defaultdict(list)
        for event in payload["events"]:
            self._events[leg_key(event)].append(event)
        for events in self._events.values():
            events.sort(key=lambda value: value["first_observed_at"])
        self._event_starts = {key: [event["first_observed_at"] for event in events]
                              for key, events in self._events.items()}
        self._departures = {key: sorted((event["departure_at"], index) for index, event in enumerate(events)
                                       if event["departure_at"] is not None)
                            for key, events in self._events.items()}
        self._departure_times = {key: [row[0] for row in rows] for key, rows in self._departures.items()}
        self._records = payload["feed_records"]
        self._times = {feed: [row["at"] for row in rows] for feed, rows in self._records.items()}

    def to_payload(self):
        return self.payload

    def events_for(self, leg, ready_at, end_at, *, observation_start_at=None):
        ready_at, end_at = epoch(ready_at), epoch(end_at)
        if ready_at > end_at:
            raise ValueError("Archive query ends before readiness.")
        observation_start_at = (ready_at - OBSERVATION_LOOKBACK_SECONDS if observation_start_at is None
                                else epoch(observation_start_at))
        if observation_start_at > ready_at:
            raise ValueError("Observation window begins after passenger readiness.")
        times = self._times.get(leg["feed_id"], [])
        position = bisect_right(times, ready_at) - 1
        prior = times[position] if position >= 0 and ready_at - times[position] <= OBSERVATION_LOOKBACK_SECONDS else None
        result = []
        for line in leg.get("route_ids", [leg["route_id"]]):
            key = leg_key(leg, line)
            candidates = self._events.get(key, [])
            known = self._departures.get(key, [])
            dep_times = self._departure_times.get(key, [])
            selected = {index for _, index in known[bisect_left(dep_times, ready_at):bisect_right(dep_times, end_at)]}
            stop = bisect_right(self._event_starts.get(key, []), end_at)
            selected.update(index for index in range(stop) if candidates[index]["departure_at"] is None)
            for index in sorted(selected):
                event = candidates[index]
                departure = event["departure_at"]
                if departure is None and event["arrival_at"] is not None and event["arrival_at"] < ready_at:
                    continue
                if departure is None and event["last_observed_at"] < observation_start_at:
                    continue
                observations = event["observations"]
                # Omission from a newer full snapshot is not evidence of
                # physical passage or cancellation. Preserve every unresolved
                # candidate within the fixed per-case observation window;
                # its superseded path is a blocker, never silently refreshed.
                relevant = [row for row in observations
                            if observation_start_at <= row["at"] <= end_at]
                if not relevant and departure is None:
                    continue
                item = dict(event)
                item["relevant_from_at"] = min((max(ready_at, row["at"]) for row in relevant), default=ready_at)
                item["relevant_until_at"] = max((row["at"] for row in relevant), default=departure)
                item["ready_membership_capture_at"] = prior if any(row["at"] == prior for row in relevant) else None
                result.append(item)
        return sorted(result, key=lambda event: (event["departure_at"] if event["departure_at"] is not None else float("inf"),
                                                event["canonical_trip_id"]))

    def coverage_for(self, feed_id, start, end, max_gap_seconds=120):
        start, end = epoch(start), epoch(end)
        if start > end or max_gap_seconds <= 0:
            raise ValueError("Invalid feed coverage request.")
        times, records = self._times.get(feed_id, []), self._records.get(feed_id, [])
        before = bisect_right(times, start) - 1
        after = bisect_right(times, end)
        rows = records[max(0, before):after]
        gaps = []
        if before < 0 or start - times[before] > max_gap_seconds:
            gaps.append({"start": start, "end": rows[0]["at"] if rows else end,
                         "reason": "MISSING_FRESH_INITIAL_SNAPSHOT"})
        for row in rows:
            if not row["eligible"]:
                gaps.append({"start": row["at"], "end": row["at"], "reason": "UNUSABLE_ARCHIVED_SNAPSHOT"})
        for left, right in zip(rows, rows[1:]):
            if right["at"] - left["at"] > max_gap_seconds:
                gaps.append({"start": left["at"], "end": right["at"], "reason": "ARCHIVED_CAPTURE_GAP"})
        if not rows or end - rows[-1]["at"] > max_gap_seconds:
            gaps.append({"start": rows[-1]["at"] if rows else start, "end": end,
                         "reason": "MISSING_FRESH_FINAL_SNAPSHOT"})
        return {"eligible": not gaps, "reason": "ARCHIVE_COVERAGE_GAP" if gaps else None,
                "gaps": gaps, "max_gap_seconds": max_gap_seconds, "snapshot_count": len(rows),
                "first_capture_at": rows[0]["at"] if rows else None,
                "last_capture_at": rows[-1]["at"] if rows else None}


def load_archive(path):
    return RouteArchive(read_labels(path))


def build_archive(root, manifest_path, templates, *, windows=None, cache_path=None,
                  manifest_output_path=None, progress=None):
    """Load verified local archives after prediction freeze and cache evidence."""
    root, manifest_path = Path(root), Path(manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("stage") != "PREPARED":
        raise ValueError("The November source package is incomplete.")
    windows = _windows(windows)
    producers = ["data/route_archive.py", "data/november_outcomes.py", "data/october/labels.py",
                 "data/october/sources.py", "algo/stayorswitch/matching.py"]
    binding = {"source_manifest_sha256": sha256(manifest_path),
               "templates_sha256": _json_hash(templates), "windows": windows,
               "producer_sha256": {p: sha256(root / p) for p in producers}}
    if cache_path is not None:
        cache_path = Path(cache_path)
        if not cache_path.is_absolute():
            cache_path = root / cache_path
        sidecar = cache_path.with_suffix(cache_path.suffix + ".manifest.json")
        if cache_path.exists() and sidecar.exists():
            previous = json.loads(sidecar.read_text())
            if previous.get("binding") == binding and previous.get("sha256") == sha256(cache_path):
                return load_archive(cache_path)
    labels, sources = {}, {}
    for item in manifest["daily_labels"].values():
        path = root / item["path"]
        if sha256(path) != item["sha256"]:
            raise ValueError("Outcome source hash mismatch: " + item["path"])
        sources[item["path"]] = item["sha256"]
        for identity, stops in read_labels(path).items():
            target = labels.setdefault(identity, {})
            for stop, label in stops.items():
                if stop in target and target[stop] != label:
                    raise ValueError("Conflicting daily endpoint labels.")
                target[stop] = label
    def snapshots():
        for day in manifest["days"]:
            if windows is not None:
                day_date = date.fromisoformat(day["date"])
                first = datetime.combine(day_date, time(), tzinfo=ZoneInfo("America/New_York")).timestamp()
                last = datetime.combine(day_date + timedelta(days=1), time(), tzinfo=ZoneInfo("America/New_York")).timestamp()
                if not any(a - OBSERVATION_LOOKBACK_SECONDS <= last and
                           b + OBSERVATION_LOOKBACK_SECONDS >= first for a, b in windows):
                    continue
            item = day["outputs"]["snapshots"]
            path = root / item["path"]
            if sha256(path) != item["sha256"]:
                raise ValueError("Snapshot source hash mismatch: " + item["path"])
            sources[item["path"]] = item["sha256"]
            if progress is not None:
                progress({"stage": "ROUTE_ARCHIVE_DAY", "date": day["date"], "path": item["path"]})
            yield from read_snapshots(path)
    payload = build_from_snapshots(snapshots(), templates, labels, windows=windows)
    payload["provenance"] = {"binding": binding, "sources": sources}
    if cache_path is not None:
        write_gzip_json(cache_path, payload)
        record = {"schema_version": SCHEMA_VERSION, "binding": binding,
                  "path": str(cache_path.relative_to(root)), "sha256": sha256(cache_path),
                  "counts": payload["counts"], "sources": sources}
        write_json(sidecar, record)
        if manifest_output_path is not None:
            target = Path(manifest_output_path)
            write_json(target if target.is_absolute() else root / target, record)
    return RouteArchive(payload)
