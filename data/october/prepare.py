"""Prepare complete October snapshot streams and separately verified labels."""

from collections import Counter, defaultdict, OrderedDict
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import ExitStack
from datetime import date, timedelta, datetime
import gzip
import hashlib
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2 as gtfs

from .labels import build_labels, ReceiptIndex, source_trip_uid
from .projection import project_payload
from .sources import (ROOT, acquire, dates_between, epoch, iter_raw_snapshots,
                      now, read_labels, sha256, stamp, write_gzip_json, write_json)
from stayorswitch.mta import parse_train_feed, snapshot_status


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def code_hashes():
    paths = list((ROOT / "data/october").glob("*.py"))
    paths += [ROOT / "data/scripts/prepare_october.py", ROOT / "algo/stayorswitch/mta.py"]
    return {relative(path): sha256(path) for path in sorted(paths) if path.is_file()}


def artifact(path):
    return {"path": relative(path), "bytes": Path(path).stat().st_size, "sha256": sha256(path)}


def _missing(record, reason):
    return {"feed_id": record["feed_id"],
            "kind": "alerts" if record["feed_id"] == "subway-alerts" else "train",
            "fetched_at": stamp(record["captured_at"]),
            "requested_at": stamp(record["captured_at"]), "source_updated_at": None,
            "status": "MISSING", "trips": [], "alerts": [], "vehicles": [],
            "reason_codes": [reason], "trip_replacement_periods": []}


def normalize(record, config, *, project=True):
    if record.get("invalid_reason"):
        result = _missing(record, record["invalid_reason"])
    else:
        try:
            payload, projection = record["payload"], None
            if project and record["feed_id"] != "subway-alerts":
                payload, projection = project_payload(payload, record["feed_id"], config)
                projection["projected_payload_sha256"] = hashlib.sha256(payload).hexdigest()
            result = parse_train_feed(payload, record["feed_id"], stamp(record["captured_at"]))
            result["sha256"] = record["sha256"]
            if projection is not None:
                result["normalization_projection"] = projection
            if record["feed_id"] == "subway-alerts":
                result["kind"] = "alerts"
        except (ValueError, TypeError, DecodeError) as error:
            result = _missing(record, "INVALID_ARCHIVED_PAYLOAD")
            result["error_type"] = type(error).__name__
    result["captured_at"] = record["captured_at"]
    result["archive_provenance"] = {key: record[key] for key in ("archive", "archive_member", "sha256")}
    result["trips"] = [trip for trip in result.get("trips", []) if trip.get("route_id") in config["route_ids"]]
    identities = {trip["id"] for trip in result["trips"] if trip.get("id")}
    result["vehicles"] = [vehicle for vehicle in result.get("vehicles", []) if vehicle.get("trip_identity") in identities]
    result["replay_freshness"] = snapshot_status(result, stamp(record["captured_at"]),
        train_max_age_seconds=config["train_max_age_seconds"],
        alerts_max_fetch_age_seconds=config["alerts_max_age_seconds"])
    if result["kind"] == "alerts":
        result["archive_alert_limitation"] = "CONTENT_DEDUPLICATION_DOES_NOT_ESTABLISH_FRESH_UNCHANGED_FETCH"
    return result


def _merge_trip(target, trip, requested_stops):
    identity = trip.get("id")
    if not identity:
        return
    names = ("id", "trip_id", "route_id", "feed_id", "start_date", "start_time")
    value = {name: trip.get(name) for name in names}
    value.update({name: trip.get(name) for name in ("direction_id", "nyct_direction", "schedule_relationship")})
    observed = {stop.get("stop_id") for stop in trip.get("stop_updates", [])} & requested_stops
    if identity not in target:
        target[identity] = dict(value, observed_stop_ids=set(observed), identity_conflict=False)
    else:
        current = target[identity]
        current["identity_conflict"] |= any(current.get(name) != value[name] for name in names)
        for name in ("direction_id", "nyct_direction", "schedule_relationship"):
            if current.get(name) is not None and value[name] is not None and current[name] != value[name]:
                current["identity_conflict"] = True
            elif current.get(name) is None:
                current[name] = value[name]
        current["observed_stop_ids"].update(observed)


def raw_receipt(record, max_age_seconds=180):
    """Extract source time from every collector capture, without normalizing trips."""
    source, status = None, "MISSING"
    if not record.get("invalid_reason"):
        try:
            feed = gtfs.FeedMessage()
            feed.ParseFromString(record["payload"])
            if (feed.IsInitialized() and feed.header.HasField("timestamp")
                    and feed.header.incrementality == gtfs.FeedHeader.FULL_DATASET):
                source, status = int(feed.header.timestamp), "AVAILABLE"
        except DecodeError:
            pass
    if source is not None and source > record["captured_at"]:
        status = "MISSING"
    record["receipt_freshness"] = ("MISSING" if status == "MISSING" else
        "STALE" if record["captured_at"] - source > max_age_seconds else "FRESH")
    if status == "MISSING" and not record.get("invalid_reason"):
        record["invalid_reason"] = "INVALID_OR_UNSUPPORTED_ARCHIVED_SOURCE_HEADER"
    return {"captured_at": record["captured_at"], "source_updated_at": source, "status": status}


def prepare_day(day, archive, config, output, hashes, config_hash):
    """Stream one source archive once; readers retain its per-feed ordering."""
    output = Path(output)
    paths = {name: output / (day + suffix) for name, suffix in (
        ("snapshots", ".snapshots.jsonl.gz"), ("alerts", ".alerts.jsonl.gz"),
        ("trips", ".trips.json.gz"), ("receipts", ".receipts.json.gz"))}
    metadata_path = output / (day + ".source.json")
    fingerprint = {"archive_sha256": archive["sha256"], "config_sha256": config_hash,
                   "code_sha256": hashes}
    if metadata_path.is_file():
        previous = json.loads(metadata_path.read_text())
        if previous.get("fingerprint") == fingerprint and all(
                (ROOT / item["path"]).is_file() and sha256(ROOT / item["path"]) == item["sha256"]
                for item in previous.get("outputs", {}).values()):
            return dict(previous, cache_verified=True)
    path = Path(archive["path"])
    if path.stat().st_size != archive["bytes"] or sha256(path) != archive["sha256"]:
        raise ValueError("Raw archive differs from its acquisition manifest.")
    output.mkdir(parents=True, exist_ok=True)
    started, counts, raw_counts = time.monotonic(), Counter(), {}
    by_feed, trips, receipts = Counter(), {}, defaultdict(list)
    raw_bounds = {}
    zone = ZoneInfo(config["timezone"])

    def collect_receipt(record):
        capture, feed = record["captured_at"], record["feed_id"]
        if datetime.fromtimestamp(capture, zone).date().isoformat() != day:
            raise ValueError("Raw train capture lies outside its local-date archive partition.")
        receipts[feed].append(raw_receipt(record, config["train_max_age_seconds"]))
        bounds = raw_bounds.setdefault(feed, {"first_captured_at": capture, "last_captured_at": capture, "captures": 0})
        bounds["last_captured_at"] = capture
        bounds["captures"] += 1
    requested = set(config["stop_ids"])
    temporary = {name: path.with_suffix(path.suffix + ".part") for name, path in paths.items()}
    with temporary["snapshots"].open("wb") as snapshot_file, temporary["alerts"].open("wb") as alert_file:
        with gzip.GzipFile(fileobj=snapshot_file, mode="wb", filename="", mtime=0, compresslevel=1) as snapshots, \
                gzip.GzipFile(fileobj=alert_file, mode="wb", filename="", mtime=0, compresslevel=1) as alerts:
            for raw in iter_raw_snapshots(path, config["feed_ids"], config["sample_seconds"], raw_counts,
                                          receipt_callback=collect_receipt):
                record = normalize(raw, config)
                encoded = (json.dumps(record, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n").encode()
                snapshots.write(encoded)
                counts["snapshots"] += 1
                counts["state:" + record["replay_freshness"]] += 1
                for key in ("entities_before", "entities_after", "trips_before", "trips_after", "stops_before", "stops_after"):
                    counts["projection_" + key] += record.get("normalization_projection", {}).get(key, 0)
                by_feed[record["feed_id"]] += 1
                if record["kind"] == "alerts":
                    alerts.write(encoded)
                    counts["alert_snapshots"] += 1
                    counts["alert_versions_before_deduplication"] += len(record["alerts"])
                for trip in record["trips"]:
                    _merge_trip(trips, trip, requested)
    for item in trips.values():
        item["observed_stop_ids"] = sorted(item["observed_stop_ids"])
    for name in ("snapshots", "alerts"):
        temporary[name].replace(paths[name])
    write_gzip_json(paths["trips"], trips)
    write_gzip_json(paths["receipts"], receipts)
    result = {"date": day, "stage": "NORMALIZED", "fingerprint": fingerprint,
              "outputs": {name: artifact(path) for name, path in paths.items()},
              "counts": dict(counts), "by_feed": dict(by_feed), "raw_counts": raw_counts,
              "raw_train_capture_bounds": raw_bounds,
              "trip_count": len(trips), "elapsed_seconds": round(time.monotonic() - started, 2),
              "ordering": "CHRONOLOGICAL_WITHIN_EACH_FEED_NOT_GLOBAL", "cache_verified": False}
    if set(by_feed) != set(config["feed_ids"]) | {"subway-alerts"}:
        raise ValueError("A required feed has no observations on " + day)
    write_json(metadata_path, result)
    return result


class DailyReceiptIndex:
    """Search raw receipt days lazily with a bounded cache of compact indexes."""

    def __init__(self, day_reports, timezone):
        self.paths = {day["date"]: ROOT / day["outputs"]["receipts"]["path"] for day in day_reports}
        self.zone = ZoneInfo(timezone)
        self.cache = OrderedDict()

    def confirm(self, feed_id, available_at):
        if available_at is None:
            return None
        first = datetime.fromtimestamp(available_at, self.zone).date().isoformat()
        for day in sorted(self.paths):
            if day < first:
                continue
            if day not in self.cache:
                self.cache[day] = ReceiptIndex(read_labels(self.paths[day]))
                if len(self.cache) > 3:
                    self.cache.popitem(last=False)
            self.cache.move_to_end(day)
            confirmed = self.cache[day].confirm(feed_id, available_at)
            if confirmed is not None:
                return confirmed
        return None


def combine_labels(day_reports, archives, config, output):
    trips, by_day = {}, {}
    for report in day_reports:
        day_trips = read_labels(ROOT / report["outputs"]["trips"]["path"])
        by_day[report["date"]] = list(day_trips)
        for identity, value in day_trips.items():
            if identity not in trips:
                trips[identity] = dict(value, observed_stop_ids=set(value["observed_stop_ids"]))
            else:
                old = trips[identity]
                old["identity_conflict"] |= value.get("identity_conflict", False) or any(
                    old.get(key) != value.get(key) for key in ("trip_id", "route_id", "feed_id", "start_date", "start_time"))
                for key in ("direction_id", "nyct_direction", "schedule_relationship"):
                    if old.get(key) is not None and value.get(key) is not None and old[key] != value[key]:
                        old["identity_conflict"] = True
                    elif old.get(key) is None:
                        old[key] = value.get(key)
                old["observed_stop_ids"].update(value["observed_stop_ids"])
    journals = [item for item in archives if item["kind"] == "csv"]
    for item in journals:
        if sha256(item["path"]) != item["sha256"]:
            raise ValueError("CSV journal differs from its acquisition manifest.")
    groups, identity_days = defaultdict(dict), defaultdict(list)
    for day, identities in by_day.items():
        for identity in identities:
            identity_days[identity].append(day)
    for identity, trip in trips.items():
        groups[trip.get("start_date") or "UNKNOWN"][identity] = trip
    # An over-24-hour service offset can collide with the following service
    # date's opaque publisher UID. Detect those collisions before day grouping.
    uid_identities = defaultdict(set)
    for trip in trips.values():
        uid = source_trip_uid(trip)
        if uid is not None:
            uid_identities[uid].add(tuple(trip.get(key) for key in ("feed_id", "start_date", "route_id", "trip_id")))
    for trip in trips.values():
        if len(uid_identities.get(source_trip_uid(trip), set())) > 1:
            trip["identity_conflict"] = True
    receipts = DailyReceiptIndex(day_reports, config["timezone"])
    path = Path(output) / "labels.json.gz"
    paths = {"ALL": path, **{day: Path(output) / (day + ".labels.json.gz") for day in by_day}}
    temporary = {key: value.with_suffix(value.suffix + ".part") for key, value in paths.items()}
    quality = Counter()
    with ExitStack() as stack:
        streams, written = {}, Counter()
        for key, target in temporary.items():
            file = stack.enter_context(target.open("wb"))
            streams[key] = stack.enter_context(gzip.GzipFile(fileobj=file, mode="wb", filename="", mtime=0, compresslevel=1))
            streams[key].write(b"{")
        for service_date, subset in sorted(groups.items()):
            observed_days = [day for identity in subset for day in identity_days[identity]]
            first = (date.fromisoformat(min(observed_days)) - timedelta(days=1)).isoformat()
            last = (date.fromisoformat(max(observed_days)) + timedelta(days=1)).isoformat()
            journal_paths = [item["path"] for item in journals if first <= item["archive_date"] <= last]
            labels, counts = build_labels(subset, journal_paths, receipts, set(config["stop_ids"]))
            quality.update(counts)
            for identity, endpoints in sorted(labels.items()):
                encoded = (json.dumps(identity) + ":" + json.dumps(endpoints, sort_keys=True, separators=(",", ":"), allow_nan=False)).encode()
                for key in ["ALL", *identity_days[identity]]:
                    if written[key]:
                        streams[key].write(b",")
                    streams[key].write(encoded)
                    written[key] += 1
        for stream in streams.values():
            stream.write(b"}")
    for key, temporary_path in temporary.items():
        temporary_path.replace(paths[key])
    daily_outputs = {}
    for day in by_day:
        daily_outputs[day] = artifact(paths[day])
    return artifact(path), daily_outputs, dict(quality)


def prepare(config_path, *, selected_dates=None, process_only=False, download_only=False,
            workers=2, raw_directory=None, output_directory=None):
    started = time.monotonic()
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text())
    hashes, config_hash = code_hashes(), sha256(config_path)
    raw = Path(raw_directory or ROOT / "data/raw/october")
    output = Path(output_directory or ROOT / "data/processed/october")
    acquisition_path = ROOT / "data/manifests/october-acquisition.json"
    if process_only:
        acquisition = json.loads(acquisition_path.read_text())
        if acquisition.get("stage") != "ACQUIRED" or acquisition.get("errors"):
            raise ValueError("Complete acquisition is required for processing.")
        archives = acquisition["archives"]
    else:
        archives, errors = acquire(config, raw, workers=2)
        write_json(acquisition_path, {"stage": "INCOMPLETE" if errors else "ACQUIRED",
                                     "archives": archives, "errors": errors})
        if errors:
            raise ValueError("Some required archives could not be acquired.")
    if download_only:
        return {"stage": "ACQUIRED", "archive_count": len(archives)}
    dates = list(selected_dates or dates_between(config["start_date"], config["end_date"]))
    expected = set(dates_between(config["start_date"], config["end_date"]))
    if not dates or len(set(dates)) != len(dates) or not set(dates).issubset(expected):
        raise ValueError("Processing dates must be unique configured October dates.")
    indexed = {(item["archive_date"], item["kind"]): item for item in archives}
    day_reports = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending = {executor.submit(prepare_day, day, indexed[(day, "gtfsrt")], config, output, hashes, config_hash): day
                   for day in dates}
        for future in as_completed(pending):
            report = future.result()
            day_reports.append(report)
            print(json.dumps({"stage": "DAY_NORMALIZED", "date": report["date"],
                "snapshots": report["counts"]["snapshots"], "elapsed_seconds": report["elapsed_seconds"],
                "completed_days": len(day_reports), "total_days": len(dates), "cached": report["cache_verified"]}), flush=True)
    day_reports.sort(key=lambda item: item["date"])
    print(json.dumps({"stage": "BUILDING_SEPARATE_OUTCOME_LABELS", "days": len(day_reports)}), flush=True)
    labels, daily_labels, quality = combine_labels(day_reports, archives, config, output)
    if code_hashes() != hashes or sha256(config_path) != config_hash:
        raise ValueError("Source code or configuration changed during preparation.")
    complete = set(dates) == expected
    report = {"stage": "PREPARED" if complete else "SMOKE_PREPARED", "dates": dates,
              "full_month_processed": complete, "label_quality": quality,
              "day_reports": [{key: value for key, value in day.items() if key != "fingerprint"} for day in day_reports],
              "elapsed_seconds": round(time.monotonic() - started, 2),
              "limitations": ["Outcomes are screened MTA final-prediction proxies, not observed passenger arrivals.",
                  "Archived alerts are content-deduplicated; last capture age is not evidence of a fresh unchanged fetch.",
                  "Daily streams are chronological within each feed, not globally ordered.",
                  "Unregistered publisher protobuf extensions may be absent from normalized output; alert text is retained.",
                  "Boundary journals do not extend the October decision-date window."]}
    report_path = ROOT / "data/reports/october-source.json"
    write_json(report_path, report)
    manifest = {"schema_version": "october-source-v1", "stage": report["stage"], "full_month_processed": complete,
                "generated_at": now(), "config": artifact(config_path), "code_sha256": hashes,
                "acquisition": artifact(acquisition_path), "archives": archives,
                "dates": dates, "days": day_reports, "labels": labels, "daily_labels": daily_labels,
                "report": artifact(report_path)}
    write_json(ROOT / "data/manifests/october.json", manifest)
    print(json.dumps({"stage": report["stage"], "days": len(day_reports), "label_quality": quality,
                      "elapsed_seconds": report["elapsed_seconds"]}), flush=True)
    return manifest
