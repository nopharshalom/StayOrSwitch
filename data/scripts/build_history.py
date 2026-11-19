#!/usr/bin/env python3
"""Download, audit and build the explicitly scoped historical pilot dataset."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import json
import multiprocessing
from pathlib import Path
import sys
import time


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPOSITORY / "data"), str(REPOSITORY / "algo")]

from google.protobuf.message import DecodeError
from history.archives import download_archive, iter_csv_rows, iter_snapshots, sha256_file
from history.features import FeatureBuilder, LabelIndex, SPLITS, iso
from history.label_audit import VehicleLabelAudit
from history.segments import SegmentBuilder
from history.alerts import AlertsIndex
from history.label_receipts import LabelReceiptIndex
from history.integrity import audit_dataset, purge_ambiguous
from stayorswitch.mta import parse_train_feed


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def dates_between(start, end):
    current, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < current:
        raise ValueError("End date must not precede start date.")
    while current <= last:
        yield current.isoformat()
        current += timedelta(days=1)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def relative(path):
    return str(Path(path).resolve().relative_to(REPOSITORY))


def code_manifest():
    paths = sorted((REPOSITORY / "data/history").glob("*.py"))
    paths += [Path(__file__).resolve(), REPOSITORY / "algo/stayorswitch/mta.py"]
    return {relative(path): sha256_file(path) for path in paths}


def emit(event, **values):
    print(json.dumps({"event": event, "at": now(), **values}), flush=True)


def checked_local_archive(day, kind, root):
    path = root / ("subwaydatanyc_" + day + "_" + kind + ".tar.xz")
    metadata = json.loads(path.with_name(path.name + ".metadata.json").read_text())
    expected = "https://subwaydata.nyc/data/" + path.name
    if metadata.get("url") != expected or metadata.get("bytes") != path.stat().st_size:
        raise ValueError("Local archive metadata is invalid: " + path.name)
    if metadata.get("sha256") != sha256_file(path):
        raise ValueError("Local archive checksum does not match: " + path.name)
    metadata.update(path=str(path), cache_verified=True)
    return metadata


def obtain_archives(config, selected_dates, root, process_only):
    window = config["window"]
    first = date.fromisoformat(window["archive_start"]) - timedelta(days=1)
    last = date.fromisoformat(window["archive_end"]) + timedelta(days=1)
    all_dates = list(dates_between(first.isoformat(), last.isoformat()))
    # Publisher CSV partitioning follows its opaque UTC-based trip UID rather
    # than physical departure. Adjacent journals supply boundary labels only;
    # they do not extend the configured feature or evaluation date window.
    jobs = [(day, "csv") for day in all_dates] + [(day, "gtfsrt") for day in selected_dates]
    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(checked_local_archive if process_only else download_archive,
                                   day, kind, root): (day, kind) for day, kind in jobs}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            emit("archive_verified", date=result["archive_date"], kind=result["kind"],
                 bytes=result["bytes"], cached=result["cache_verified"])
    return sorted(results, key=lambda value: (value["archive_date"], value["kind"]))


def load_labels(archives, config):
    labels = LabelIndex()
    route_ids, stop_ids = set(config["route_ids"]), set(config["stop_ids"])
    for item in archives:
        if item["kind"] != "csv":
            continue
        for row in iter_csv_rows(item["path"], "trips"):
            if row.get("route_id") in route_ids:
                labels.add_trip(row)
        for row in iter_csv_rows(item["path"], "stop_times"):
            if row.get("stop_id") in stop_ids and row.get("trip_uid") in labels.trips:
                labels.add_stop(row)
    emit("label_index_ready", **labels.report())
    return labels


def summarize_reports(day_reports, labels, config):
    counts, segment_counts, audit_counts = Counter(), Counter(), Counter()
    by_route, by_day_type, flags = defaultdict(Counter), defaultdict(Counter), Counter()
    for report in day_reports:
        counts.update(report["arrivals"]["counts"])
        segment_counts.update(report["segments"].get("counts", {}))
        audit_counts.update(report["label_audit"]["counts"])
        for route, value in report["arrivals"]["by_route"].items():
            by_route[route].update(value)
        for day_type, value in report["arrivals"]["by_day_type"].items():
            by_day_type[day_type].update(value)
        flags.update(report["arrivals"]["label_quality_flags"])
    return {
        "generated_at": now(), "dataset_version": config["dataset_version"],
        "processed_archive_dates": [report["archive_date"] for report in day_reports],
        "arrival_counts": dict(counts), "segment_counts": dict(segment_counts),
        "label_index": labels.report(), "label_audit_counts": dict(audit_counts),
        "by_route": {key: dict(value) for key, value in sorted(by_route.items())},
        "by_day_type": {key: dict(value) for key, value in sorted(by_day_type.items())},
        "label_quality_flags": dict(flags), "days": day_reports,
        "limitations": [
            "Arrival and segment labels derive from final prediction journals, not physical ground truth.",
            "Vehicle-status checks use a different derivation of the same MTA source, not independent observations.",
            "Only configured target stations, routes, horizons and sampled collection times are included.",
            "Only two weekends are present; chronological validation contains weekdays only.",
            "No historical Google route predictions or defensible full passenger journey outcomes are supplied.",
            "Historical alert captures are content-deduplicated; old last-observed alerts do not establish fresh current alert state.",
            "No model has been trained and no prediction accuracy or realized time saving has been established.",
        ],
    }


def write_markdown(path, report):
    counts = report.get("final_arrival_counts", report["arrival_counts"])
    lines = ["# Historical Pilot Data Report", "", "Generated: " + report["generated_at"], "",
             "This report describes data preparation, not model accuracy. Labels are inferred final-prediction proxies.", "",
             "- Processed calendar dates: " + ", ".join(report["processed_archive_dates"]),
             "- Arrival examples: " + str(counts.get("rows", 0)),
             "- Arrival examples with usable proxy labels: " + str(counts.get("eligible_proxy_rows", 0)),
             "- Segment examples: " + str(report.get("final_segment_counts", report["segment_counts"]).get("rows", 0)),
             "- Quality status: " + report.get("quality_status", "NOT_CHECKED"), "",
             "| Decision-day type | All component rows | Usable proxy rows |", "|---|---:|---:|"]
    for day_type, values in report.get("global_integrity", {}).get("by_day_type", {}).items():
        lines.append("| " + day_type + " | " + str(values.get("rows", 0)) + " | "
                     + str(values.get("eligible_proxy_rows", 0)) + " |")
    lines += ["", "## Limitations", ""] + ["- " + value for value in report["limitations"]]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def attach_alerts(path, alerts, receipts):
    """Join by historical receipt cutoff after the archive's alerts group ends."""
    enriched = path.with_name(path.name + ".alerts")
    counts, flags = Counter(), Counter()
    groups = {key: defaultdict(Counter) for key in ("by_route", "by_day_type", "by_date")}
    eligible_events = set()
    with gzip.open(path, "rt", encoding="utf-8") as source, enriched.open("wb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", mtime=0, filename="", compresslevel=1) as target:
            for line in source:
                row = json.loads(line)
                row["features"].update(alerts.features_for(row))
                receipts.apply(row)
                status = "eligible_proxy_rows" if row["eligible_for_training"] else "ineligible_proxy_rows"
                counts.update({"rows": 1, status: 1})
                for group, key in (("by_route", "route_id"), ("by_day_type", "day_type"),
                                   ("by_date", "decision_local_date")):
                    groups[group][row["features"][key]].update({"rows": 1, status: 1})
                flags.update(row["label"]["quality_flags"])
                if row["eligible_for_training"]:
                    eligible_events.add((row["trip_identity"], row.get("stop_id"),
                                         row.get("from_stop_id"), row.get("to_stop_id")))
                target.write((json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n").encode())
    enriched.replace(path)
    return {"counts": dict(counts), "label_quality_flags": dict(flags),
            "unique_eligible_events": len(eligible_events),
            **{group: {key: dict(value) for key, value in values.items()} for group, values in groups.items()}}


def process_day(day, archive, labels, config, output, fingerprint, force=False):
    metadata_path = output / (day + ".report.json")
    arrival_path = output / (day + ".arrivals.jsonl.gz")
    segment_path = output / (day + ".segments.jsonl.gz")
    if not force and metadata_path.exists():
        cached = json.loads(metadata_path.read_text())
        if cached.get("build_fingerprint") == fingerprint and all(
                Path(REPOSITORY / value["path"]).exists()
                and sha256_file(REPOSITORY / value["path"]) == value["sha256"]
                for value in cached.get("outputs", [])) and len(cached.get("outputs", [])) == 2:
            emit("processed_day_reused", date=day)
            return cached
    started = time.monotonic()
    builder = FeatureBuilder(labels, route_ids=config["route_ids"], stop_ids=config["stop_ids"],
                             horizon_seconds=config["forecast_horizon_seconds"],
                             source_max_age_seconds=config["source_max_age_seconds"])
    segments = SegmentBuilder(labels, route_ids=config["route_ids"], stop_ids=config["stop_ids"],
                              horizon_seconds=config["forecast_horizon_seconds"],
                              source_max_age_seconds=config["source_max_age_seconds"])
    audit = VehicleLabelAudit(labels)
    alerts = AlertsIndex()
    receipts = LabelReceiptIndex()
    stream_stats = {}
    errors = Counter()
    count = 0
    arrival_temp = arrival_path.with_suffix(".gz.part")
    segment_temp = segment_path.with_suffix(".gz.part")
    with arrival_temp.open("wb") as arrival_binary, segment_temp.open("wb") as segment_binary:
        with gzip.GzipFile(fileobj=arrival_binary, mode="wb", mtime=0, filename="", compresslevel=1) as arrival_out, \
                gzip.GzipFile(fileobj=segment_binary, mode="wb", mtime=0, filename="", compresslevel=1) as segment_out:
            for sample in iter_snapshots(archive["path"], feed_ids=config["feed_ids"] + ["subway-alerts"],
                                         sample_seconds=config["sample_seconds"], stats=stream_stats):
                count += 1
                try:
                    parsed = parse_train_feed(sample["payload"], sample["feed_id"], iso(sample["captured_at"]))
                except (DecodeError, ValueError, TypeError):
                    errors["invalid_protobuf_snapshot"] += 1
                    if sample["feed_id"] == "subway-alerts":
                        alerts.add({"status": "MISSING", "fetched_at": iso(sample["captured_at"])})
                    continue
                parsed.update(captured_at=sample["captured_at"], member_name=sample["member_name"])
                if sample["feed_id"] == "subway-alerts":
                    alerts.add(parsed, captured_at=sample["captured_at"])
                    continue
                receipts.add(parsed)
                for row in builder.process(parsed):
                    arrival_out.write((json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n").encode())
                for row in segments.process(parsed):
                    segment_out.write((json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n").encode())
                audit.process(parsed)
                if count % 500 == 0:
                    emit("processing", date=day, sampled_snapshots=count,
                         arrival_rows=builder.counts.get("rows", 0), elapsed_seconds=round(time.monotonic() - started, 1))
    final_arrivals = attach_alerts(arrival_temp, alerts, receipts)
    final_segments = attach_alerts(segment_temp, alerts, receipts)
    arrival_temp.replace(arrival_path)
    segment_temp.replace(segment_path)
    arrival_report, segment_report = builder.report(), segments.report()
    for base, enriched, unique_key in ((arrival_report, final_arrivals, "unique_eligible_stop_events"),
                                       (segment_report, final_segments, "unique_eligible_segment_events")):
        base["counts"].update(enriched.pop("counts"))
        base[unique_key] = enriched.pop("unique_eligible_events")
        base.update(enriched)
        base["policy"]["historical_alerts"] = "JOINED_BY_COLLECTOR_CUTOFF"
        base["policy"]["label_receipts"] = "SAMPLED_SOURCE_WATERMARK_COLLECTOR_UPPER_BOUND"
    report = {"archive_date": day, "completed_at": now(), "build_fingerprint": fingerprint,
              "elapsed_seconds": round(time.monotonic() - started, 1), "archive_sha256": archive["sha256"],
              "archive_stream": stream_stats, "pipeline_errors": dict(errors),
              "arrivals": arrival_report, "segments": segment_report, "label_audit": audit.report(),
              "historical_alerts": alerts.report(),
              "outputs": [{"path": relative(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
                          for path in (arrival_path, segment_path)]}
    atomic_json(metadata_path, report)
    emit("day_completed", date=day, rows=builder.counts.get("rows", 0), elapsed_seconds=report["elapsed_seconds"])
    return report


_WORKER_LABELS = None


def process_worker(task):
    return process_day(labels=_WORKER_LABELS, **task)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPOSITORY / "data/config/pilot-history.json")
    parser.add_argument("--dates", help="Comma-separated subset of configured archive dates; default is the complete window.")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--process-only", action="store_true", help="Require verified local archives and perform no HTTP requests.")
    parser.add_argument("--force", action="store_true", help="Rebuild matching derived shards instead of reusing them.")
    parser.add_argument("--workers", type=int, default=2, choices=range(1, 5),
                        help="Bounded parallel day processors (1–4, default 2).")
    args = parser.parse_args(argv)
    if args.download_only and args.process_only:
        parser.error("Choose only one of --download-only and --process-only.")
    config = json.loads(args.config.read_text())
    if config["splits"] != {key: list(value) for key, value in SPLITS.items()}:
        parser.error("The configured split policy does not match the versioned feature implementation.")
    configured_dates = list(dates_between(config["window"]["archive_start"], config["window"]["archive_end"]))
    selected_dates = sorted(set(args.dates.split(","))) if args.dates else configured_dates
    if not selected_dates or any(day not in configured_dates for day in selected_dates):
        parser.error("Requested dates must belong to the configured historical window.")
    raw = REPOSITORY / "data/raw/subwaydata_nyc"
    output = REPOSITORY / "data/processed/history-pilot"
    output.mkdir(parents=True, exist_ok=True)
    archives = obtain_archives(config, selected_dates, raw, args.process_only)
    config_sha = sha256_file(args.config)
    code = code_manifest()
    inputs = {relative(item["path"]): item["sha256"] for item in archives}
    build_description = {"config_sha256": config_sha, "code_sha256": code,
                         "label_archives": {path: digest for path, digest in inputs.items() if "_csv." in path}}
    fingerprint = hashlib.sha256(json.dumps(build_description, sort_keys=True).encode()).hexdigest()
    manifest = {"dataset_version": config["dataset_version"], "generated_at": now(),
                "stage": "DOWNLOADED" if args.download_only else "PROCESSING",
                "config": {"path": relative(args.config), "sha256": config_sha},
                "code_sha256": code, "build_fingerprint": fingerprint,
                "requested_archive_dates": selected_dates, "splits": config["splits"],
                "archives": [{**item, "path": relative(item["path"])} for item in archives],
                "source_documentation": ["https://subwaydata.nyc/programmatic-access",
                                         "https://subwaydata.nyc/data-schema", "https://subwaydata.nyc/how-it-works"],
                "scope": config["scope_notes"]}
    manifest_path = REPOSITORY / "data/manifests/history-pilot.json"
    atomic_json(manifest_path, manifest)
    if args.download_only:
        return 0
    labels = load_labels(archives, config)
    raw_by_date = {item["archive_date"]: item for item in archives if item["kind"] == "gtfsrt"}
    tasks = []
    for day in selected_dates:
        day_fingerprint = hashlib.sha256((fingerprint + raw_by_date[day]["sha256"]).encode()).hexdigest()
        tasks.append({"day": day, "archive": raw_by_date[day], "config": config, "output": output,
                      "fingerprint": day_fingerprint, "force": args.force})
    reports = []
    if args.workers == 1:
        reports = [process_day(labels=labels, **task) for task in tasks]
    else:
        # The CLI has no active download threads here. Fork shares the read-only
        # label index without serializing hundreds of thousands of dictionaries.
        if "fork" not in multiprocessing.get_all_start_methods():
            parser.error("Parallel processing requires fork support; use --workers 1 on this platform.")
        global _WORKER_LABELS
        _WORKER_LABELS = labels
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("fork")) as pool:
            futures = [pool.submit(process_worker, task) for task in tasks]
            for future in as_completed(futures):
                reports.append(future.result())
        reports.sort(key=lambda value: value["archive_date"])
    paths = [REPOSITORY / value["path"] for day_report in reports for value in day_report["outputs"]]
    emit("global_integrity_started", files=len(paths))
    integrity = audit_dataset(paths)
    if integrity.get("ambiguous_eligible_rows", 0):
        purge = purge_ambiguous(paths, integrity["ambiguous_trip_identities"])
        integrity = audit_dataset(paths)
        integrity["purge"] = purge
        for day_report in reports:
            day_report["row_counts_scope"] = "AFTER_ALERT_AND_RECEIPT_JOIN_BEFORE_GLOBAL_CONTINUITY_PURGE"
            for value in day_report["outputs"]:
                path = REPOSITORY / value["path"]
                value.update(bytes=path.stat().st_size, sha256=sha256_file(path))
            atomic_json(output / (day_report["archive_date"] + ".report.json"), day_report)
    report = summarize_reports(reports, labels, config)
    report["global_integrity"] = integrity
    report["authoritative_counts"] = "GLOBAL_INTEGRITY_AFTER_ALL_ENRICHMENT_AND_PURGES"
    report["final_arrival_counts"] = integrity.get("by_kind", {}).get("arrival", {})
    report["final_segment_counts"] = integrity.get("by_kind", {}).get("segment", {})
    report["missing_selected_feeds"] = {day_report["archive_date"]: [feed for feed in config["feed_ids"]
            if not day_report["archive_stream"].get("feeds", {}).get(feed)] for day_report in reports}
    report["missing_selected_feeds"] = {day: feeds for day, feeds in report["missing_selected_feeds"].items() if feeds}
    if integrity.get("status") != "PASS":
        report["quality_status"] = "INTEGRITY_CHECK_FAILED"
    elif report["missing_selected_feeds"]:
        report["quality_status"] = "MISSING_REQUIRED_TRAIN_FEED"
    elif any(not integrity.get("by_split", {}).get(split, {}).get("eligible_proxy_rows")
             for split in config["splits"] if selected_dates == configured_dates):
        report["quality_status"] = "MISSING_ELIGIBLE_SPLIT"
    else:
        report["quality_status"] = "PREPARED_WITH_DOCUMENTED_PROXY_LIMITATIONS"
    report_path = REPOSITORY / "data/reports/history-pilot.json"
    atomic_json(report_path, report)
    write_markdown(REPOSITORY / "data/reports/history-pilot.md", report)
    manifest.update(stage="PREPARED" if report["quality_status"] == "PREPARED_WITH_DOCUMENTED_PROXY_LIMITATIONS" else "QUALITY_CHECK_FAILED", completed_at=now(),
                    full_configured_window_processed=selected_dates == configured_dates,
                    report={"path": relative(report_path), "sha256": sha256_file(report_path)},
                    outputs=[value for day_report in reports for value in day_report["outputs"]])
    atomic_json(manifest_path, manifest)
    emit("dataset_prepared", full_window=manifest["full_configured_window_processed"],
         arrival_rows=report["arrival_counts"].get("rows", 0), report=relative(report_path))
    return 0 if manifest["stage"] == "PREPARED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
