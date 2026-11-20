"""As-of feed views and separate selected-train evidence for route replay.

This adapter reuses the verified, immutable November route archive. Selection
views contain only records present in a particular full feed capture. Screened
final endpoint labels are exposed through a separate selected-event accessor;
they never filter, rank or otherwise modify the candidate views.
"""

from bisect import bisect_right
from collections import defaultdict
from copy import deepcopy
import math
from pathlib import Path
import json
import time

from data.october.sources import epoch, read_labels, sha256, write_json


SCHEMA_VERSION = "feed-following-route-archive-v3"
SOURCE_SCHEMA_VERSION = "route-execution-archive-v2"


def _timestamp(value, name):
    result = epoch(value)
    if isinstance(value, bool) or result is None or not math.isfinite(result):
        raise ValueError(name + " must be a finite timestamp.")
    return result


def _key(item, route_id=None):
    return (item["feed_id"], route_id or item["route_id"],
            item["from_stop_id"], item["to_stop_id"])


def _lines(leg):
    return sorted(set(leg.get("route_ids", [leg["route_id"]])))


def _candidate(event, observation):
    """Whitelist contemporaneous fields; do not copy final outcome fields."""
    return {
        "event_key": event["canonical_trip_id"],
        "canonical_trip_id": event["canonical_trip_id"],
        "trip_id": observation.get("trip_id"),
        "feed_id": event["feed_id"], "route_id": event["route_id"],
        "from_stop_id": event["from_stop_id"], "to_stop_id": event["to_stop_id"],
        "at": observation["at"], "source_at": observation.get("source_at"),
        "path_status": observation.get("path_status", "UNKNOWN"),
        "reason_codes": list(observation.get("reason_codes", [])),
        "explicit_terminal_state": observation.get("explicit_terminal_state"),
        "departure_forecast_at": observation.get("departure_forecast_at"),
        "arrival_forecast_at": observation.get("arrival_forecast_at"),
        "snapshot_sha256": observation.get("snapshot_sha256"),
        "valid_until_at": observation.get("valid_until_at"),
    }


class FeedRouteArchive:
    """Expose chronological feed choices separately from screened outcomes.

    ``frames_for`` returns the latest full capture at/before readiness and then
    each later capture through the horizon. Omission from a new full capture
    means omission from that frame, not cancellation or proven train passage.
    ``event_for`` is for the executor's already selected train only.
    """

    def __init__(self, payload, *, provenance=None, quality_screen=None):
        if payload.get("schema_version") != SOURCE_SCHEMA_VERSION:
            raise ValueError("Unsupported source route archive schema.")
        self.provenance = deepcopy(provenance or {})
        self._quality_screen = quality_screen
        self._records = payload["feed_records"]
        self._times = {}
        for feed, records in self._records.items():
            times = [_timestamp(row["at"], "Capture") for row in records]
            if times != sorted(set(times)):
                raise ValueError("Full feed captures must be strictly ordered.")
            self._times[feed] = times

        self._events = {}
        self._members = defaultdict(lambda: defaultdict(list))
        observations = 0
        for event in payload["events"]:
            key = _key(event)
            event_key = event["canonical_trip_id"]
            lookup = key + (event_key,)
            if lookup in self._events:
                raise ValueError("Duplicate canonical route event.")
            self._events[lookup] = event
            feed_times = self._times.get(event["feed_id"], [])
            previous = None
            for observation in event["observations"]:
                at = _timestamp(observation["at"], "Observation")
                index = bisect_right(feed_times, at) - 1
                if index < 0 or feed_times[index] != at:
                    raise ValueError("Observation does not belong to a full feed capture.")
                if previous is not None and at <= previous:
                    raise ValueError("Canonical observations must be strictly ordered.")
                previous = at
                expected_until = feed_times[index + 1] if index + 1 < len(feed_times) else None
                if observation.get("valid_until_at") != expected_until:
                    raise ValueError("Observation membership interval differs from the full feed clock.")
                self._members[key][at].append((event, observation))
                observations += 1
        self.counts = {
            "source_event_count": len(self._events),
            "indexed_observation_count": observations,
            "full_feed_capture_count": sum(len(rows) for rows in self._records.values()),
            "leg_route_key_count": len(self._members),
        }

    def frames_for(self, leg, ready_at, horizon_at):
        """Yield as-of full frames without reading any endpoint label field."""
        ready = _timestamp(ready_at, "Platform readiness")
        horizon = _timestamp(horizon_at, "Execution horizon")
        if ready > horizon:
            raise ValueError("Execution horizon precedes readiness.")
        feed = leg["feed_id"]
        records = self._records.get(feed, [])
        times = self._times.get(feed, [])
        start = bisect_right(times, ready) - 1
        stop = bisect_right(times, horizon)
        if start < 0:
            yield {"at": ready, "source_at": None, "eligible": False,
                   "sha256": None, "candidates": [],
                   "reason": "NO_CAPTURE_AT_OR_BEFORE_READINESS",
                   "next_capture_at": times[0] if times else None,
                   "is_synthetic_missing_frame": True}
            start = 0
        for index in range(start, stop):
            row = records[index]
            at = row["at"]
            members = []
            # A bad frame is not replaced with an older good frame. Keeping
            # its timestamp also lets the executor identify a continuity gap.
            if row.get("eligible") is True:
                for line in _lines(leg):
                    members.extend(self._members.get(_key(leg, line), {}).get(at, []))
            candidates = [_candidate(event, observation) for event, observation in members]
            candidates.sort(key=lambda item: (item["route_id"], item["event_key"],
                                               item.get("trip_id") or ""))
            yield {"at": at, "source_at": row.get("source_at"),
                   "eligible": row.get("eligible") is True,
                   "sha256": row.get("sha256"),
                   "conflict": row.get("conflict", False),
                   "candidates": candidates,
                   "next_capture_at": times[index + 1] if index + 1 < len(times) else None,
                   "is_synthetic_missing_frame": False}

    def event_for(self, leg, event_key):
        """Return final evidence only for an explicitly selected event key."""
        matches = [self._events[_key(leg, line) + (event_key,)] for line in _lines(leg)
                   if _key(leg, line) + (event_key,) in self._events]
        if len(matches) != 1:
            raise ValueError("Selected event must have one exact route identity.")
        event = matches[0]
        keys = ("trip_id", "canonical_trip_id", "trip_aliases", "feed_id", "route_id",
                "from_stop_id", "to_stop_id", "departure_at", "arrival_at",
                "endpoint_flags", "endpoint_evidence")
        result = {"event_key": event_key, **{key: deepcopy(event.get(key)) for key in keys}}
        return self._quality_screen.screen(result) if self._quality_screen is not None else result


def load_feed_archive(root, source_manifest_path="data/manifests/november-route-archive-v2.json", *,
                      source_archive_path=None, manifest_output_path=None, progress=None,
                      quality_config_path="data/config/november-feed-outcome-quality.json"):
    """Verify and adapt the existing cache without rewriting earlier files.

    The previous cache has already been checked against its original source
    snapshots and labels. This adapter verifies the cache, manifest binding,
    source map and counts; it does not re-download or duplicate raw archives.
    """
    root = Path(root)
    manifest_path = Path(source_manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    manifest = json.loads(manifest_path.read_text())
    source_path = Path(source_archive_path or manifest["path"])
    if not source_path.is_absolute():
        source_path = root / source_path
    source_hash = sha256(source_path)
    if source_hash != manifest["sha256"]:
        raise ValueError("The source route archive hash differs from its manifest.")
    started = time.monotonic()
    if progress:
        progress({"stage": "FEED_ARCHIVE_LOADING", "source_path": str(source_path)})
    payload = read_labels(source_path)
    if (payload.get("counts") != manifest.get("counts")
            or payload.get("provenance", {}).get("binding") != manifest.get("binding")
            or payload.get("provenance", {}).get("sources") != manifest.get("sources")):
        raise ValueError("The source cache does not match its recorded lineage.")
    producer_path = root / "data/feed_route_archive.py"
    provenance = {
        "source_manifest": {"path": str(manifest_path.relative_to(root)), "sha256": sha256(manifest_path)},
        "source_archive": {"path": str(source_path.relative_to(root)), "sha256": source_hash},
        "producer": {"path": "data/feed_route_archive.py", "sha256": sha256(producer_path)},
        "source_schema_version": payload["schema_version"],
        "reuse_of_previously_verified_source_cache": True,
    }
    from data.route_outcome_sanity import load_outcome_quality
    quality_screen = load_outcome_quality(root, quality_config_path)
    provenance["outcome_quality"] = quality_screen.provenance
    archive = FeedRouteArchive(payload, provenance=provenance, quality_screen=quality_screen)
    record = {"schema_version": SCHEMA_VERSION, "provenance": provenance,
              "counts": archive.counts,
              "selection_views_contain_final_endpoint_labels": False,
              "selection_filters_by_outcome_quality": False,
              "membership_policy": "EXACT_LATEST_FULL_CAPTURE_ONLY",
              "future_frames_remain_timestamped": True,
              "source_endpoint_quality_unchanged": True,
              "selected_outcomes_receive_additional_geographic_screen": True,
              "geographic_screen_changes_candidate_views": False,
              "raw_endpoint_timestamps_retained": True}
    archive.manifest = record
    if manifest_output_path:
        output = Path(manifest_output_path)
        if not output.is_absolute():
            output = root / output
        if output.exists() and json.loads(output.read_text()) != record:
            raise ValueError("An existing feed archive manifest has different bindings.")
        write_json(output, record)
    if progress:
        progress({"stage": "FEED_ARCHIVE_READY", "elapsed_seconds": round(time.monotonic() - started, 3),
                  "counts": archive.counts})
    return archive


build_feed_archive = load_feed_archive
