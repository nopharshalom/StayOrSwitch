"""Extract decision-time observations and separate later outcome labels.

This module does not rank routes or inspect whether a model would switch. It
preserves complete normalized feed snapshots, including forecasts beyond the
model's thirty-minute horizon, for independently supplied route templates.
"""

from collections import Counter
import hashlib
import lzma
from pathlib import Path, PurePosixPath
import tarfile

from google.protobuf.message import DecodeError

from data.history.archives import (ARCHIVE_FEEDS, ArchiveError, MAX_SNAPSHOT_BYTES,
                                   SNAPSHOT_NAME, _members, _parse_capture,
                                   iter_csv_rows, sha256_file)
from data.history.features import LabelIndex, epoch, iso, source_trip_uid
from stayorswitch.mta import parse_train_feed, snapshot_status


def verify_archive(root, item):
    path = (Path(root) / item["path"]).resolve()
    if Path(root).resolve() not in path.parents:
        raise ValueError("Archive path must stay inside the repository.")
    if not path.is_file() or path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
        raise ValueError("Historical archive checksum or size differs from its manifest.")
    return path


def extract_snapshots(path, cases, feeds):
    """Select the latest captured payload at or before each case cutoff.

    A latest invalid/conflicting observation is missing, never replaced with an
    older successful result. Train captures older than 180 seconds are omitted;
    the last historical alert capture is retained even when stale, because
    content-deduplicated archives cannot establish a fresh alert fetch.
    """
    wanted = set(feeds) | {"subway-alerts"}
    if not wanted.issubset(set(ARCHIVE_FEEDS.values())):
        raise ValueError("Unknown requested feed.")
    cutoffs = {case["id"]: epoch(case["decision_at"]) for case in cases}
    if len(cutoffs) != len(cases):
        raise ValueError("Replay case IDs must be unique.")
    selected, previous, counts = {}, {}, Counter()
    with lzma.open(path, "rb") as decoded, tarfile.open(fileobj=decoded, mode="r|") as archive:
        for member in _members(archive):
            counts["archive_members"] += 1
            if not member.isfile():
                continue
            match = SNAPSHOT_NAME.fullmatch(PurePosixPath(member.name).name)
            if not match:
                if member.name.endswith(".gtfsrt"):
                    raise ArchiveError("Unrecognized snapshot member.")
                continue
            feed = ARCHIVE_FEEDS[match.group(1)]
            capture = _parse_capture(match.group(2))
            if capture < previous.get(feed, capture):
                raise ArchiveError("Archive captures are not chronological within a feed.")
            previous[feed] = capture
            if feed not in wanted:
                continue
            interested = [identifier for identifier, cutoff in cutoffs.items()
                          if capture <= cutoff and (feed == "subway-alerts" or cutoff - capture <= 180)]
            if not interested:
                continue
            if member.size > MAX_SNAPSHOT_BYTES:
                raise ArchiveError("Snapshot payload exceeds the configured limit.")
            payload = archive.extractfile(member).read()
            counts["candidate_payloads_read"] += 1
            digest = hashlib.sha256(payload).hexdigest()
            for identifier in interested:
                key = (identifier, feed)
                old = selected.get(key)
                if old is not None and old["capture"] == capture:
                    if old["sha256"] != digest:
                        old["conflict"] = True
                        counts["conflicting_capture"] += 1
                    else:
                        counts["identical_capture_duplicate"] += 1
                    continue
                selected[key] = {"capture": capture, "payload": payload,
                                 "sha256": digest, "member": member.name, "conflict": False}
    output = {identifier: [] for identifier in cutoffs}
    for identifier, cutoff in cutoffs.items():
        for feed in sorted(wanted):
            record = selected.get((identifier, feed))
            if record is None:
                output[identifier].append({"feed_id": feed, "kind": "alerts" if feed == "subway-alerts" else "train",
                    "status": "MISSING", "source_updated_at": None, "fetched_at": None,
                    "requested_at": None, "trips": [], "alerts": [], "vehicles": [],
                    "reason_codes": ["NO_ARCHIVED_CAPTURE_WITHIN_SCOPE"], "replay_freshness": "MISSING"})
                continue
            try:
                if record["conflict"]:
                    raise ValueError("Conflicting payloads share a collector timestamp.")
                value = parse_train_feed(record["payload"], feed, iso(record["capture"]))
                if feed == "subway-alerts":
                    value["kind"] = "alerts"
                value["replay_freshness"] = snapshot_status(value, iso(cutoff))
            except (ValueError, TypeError, DecodeError) as error:
                value = {"feed_id": feed, "kind": "alerts" if feed == "subway-alerts" else "train",
                         "status": "MISSING", "source_updated_at": None,
                         "fetched_at": iso(record["capture"]), "requested_at": iso(record["capture"]),
                         "trips": [], "alerts": [], "vehicles": [],
                         "reason_codes": ["ARCHIVED_CAPTURE_INVALID_OR_CONFLICTING"],
                         "replay_freshness": "MISSING", "error_type": type(error).__name__}
            value["archive_provenance"] = {"archive": Path(path).name, "member": record["member"],
                "payload_sha256": record["sha256"], "captured_at": iso(record["capture"]),
                "capture_basis": "ORIGINAL_ARCHIVE_COLLECTOR_FILENAME"}
            if feed == "subway-alerts":
                value["archive_alert_limitation"] = "CONTENT_DEDUPLICATION_DOES_NOT_PROVE_A_FRESH_UNCHANGED_FETCH"
            output[identifier].append(value)
    return {"snapshots": output, "counts": dict(counts)}


def collect_labels(archives, snapshots, stop_ids, *, root):
    """Build later CSV endpoint labels without inserting them into snapshots."""
    trips, observed_stops, conflicting_identities = {}, {}, set()
    identity_fields = ("trip_id", "route_id", "start_date", "start_time", "feed_id")
    for snapshot in snapshots:
        for trip in snapshot.get("trips", []):
            if trip.get("id"):
                identity = trip["id"]
                previous = trips.get(identity)
                if previous and any(previous.get(key) != trip.get(key) for key in identity_fields):
                    conflicting_identities.add(identity)
                trips.setdefault(identity, trip)
                observed_stops.setdefault(identity, set()).update(
                    stop.get("stop_id") for stop in trip.get("stop_updates", []))
    wanted = {source_trip_uid(trip) for trip in trips.values()}
    wanted.discard(None)
    labels = LabelIndex()
    provenance = []
    for item in archives:
        path = verify_archive(root, item)
        provenance.append({key: item[key] for key in ("path", "sha256", "bytes", "archive_date")})
        for row in iter_csv_rows(path, "trips"):
            if row.get("trip_uid") in wanted:
                labels.add_trip(row)
        for row in iter_csv_rows(path, "stop_times"):
            if row.get("trip_uid") in wanted and row.get("stop_id") in stop_ids:
                labels.add_stop(row)
    result, quality = {}, Counter()
    for identity, trip in trips.items():
        endpoints = {}
        for stop_id in sorted(stop_ids):
            if stop_id not in observed_stops[identity]:
                continue
            value = labels.lookup(trip, stop_id)
            flags = list(value["quality_flags"])
            if identity in conflicting_identities:
                flags.append("CONFLICTING_REPLAY_TRIP_IDENTITY")
            departure_flags = list(flags)
            raw = labels.stops.get((source_trip_uid(trip), stop_id), {})
            try:
                departure = epoch(raw.get("departure_time"))
            except (ValueError, TypeError):
                departure = None
                departure_flags.append("INVALID_CSV_DEPARTURE")
            if departure is None:
                departure_flags.append("MISSING_CSV_DEPARTURE")
            elif value.get("arrival_at") is not None and departure < value["arrival_at"]:
                departure_flags.append("CSV_DEPARTURE_BEFORE_ARRIVAL")
            if departure is not None and value.get("available_at") is not None and departure > value["available_at"]:
                departure_flags.append("CSV_DEPARTURE_AFTER_STOP_DISAPPEARANCE")
            endpoints[stop_id] = dict(value, departure_at=departure, quality_flags=sorted(set(flags)),
                usable_proxy=not flags,
                arrival_usable=not flags, departure_usable=not departure_flags,
                departure_quality_flags=sorted(set(departure_flags)),
                raw_trip_id=trip.get("trip_id"), route_id=trip.get("route_id"),
                service_date=trip.get("start_date"),
                evidence_class="MTA_FINAL_PREDICTION_PROXY", physical_ground_truth=False)
            quality["endpoint_rows"] += 1
            quality["usable_arrival_rows"] += not flags
            quality["usable_departure_rows"] += not departure_flags
        if endpoints:
            result[identity] = endpoints
    return {"labels": result, "quality": dict(quality), "csv_sources": provenance}
