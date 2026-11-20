"""Prepare an isolated November 2026 follow-up without modifying October evidence."""

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import shutil
import time

from data.october.prepare import artifact, code_hashes as original_code_hashes, combine_labels, prepare_day
from data.october.sources import ROOT, dates_between, download_archive, now, sha256, write_json

CONFIG = ROOT / "data/config/november-2026.json"
OUTPUT = ROOT / "data/processed/november-2026"
RAW = ROOT / "data/raw/november-2026"
ACQUISITION = ROOT / "data/manifests/november-2026-acquisition.json"
MANIFEST = ROOT / "data/manifests/november-2026.json"
REPORT = ROOT / "data/reports/november-2026-source.json"
FEEDS = ["ace", "bdfm", "g", "nqrw", "numbered"]


def configuration(original):
    """Preserve the full declared five-corridor projection and refresh its scope."""
    value = deepcopy(original)
    value.update(schema_version="november-2026-source-v1", start_date="2026-11-01",
                 end_date="2026-11-19", feed_ids=list(FEEDS),
                 input_carry_date="2026-10-31",
                 splits={"analysis": ["2026-11-01", "2026-11-19"]})
    value["source_scope"] = "Five previously selected corridors; October 31 is input carry only."
    value["missing_following_boundary_policy"] = "Keep unconfirmed late endpoints unknown; never invent receipts."
    return value


def code_hashes():
    values = original_code_hashes()
    for relative in ("data/november_2026.py", "data/scripts/prepare_november_2026.py"):
        values[relative] = sha256(ROOT / relative)
    return values


def required_jobs(config):
    """Order November 1 first so model boundary evidence can be prepared promptly."""
    days = list(dates_between(config["start_date"], config["end_date"]))
    carry = config["input_carry_date"]
    previous = (date.fromisoformat(carry) - timedelta(days=1)).isoformat()
    return [(days[0], "gtfsrt")] + [(day, kind) for day in days for kind in ("csv", "gtfsrt")
                                   if (day, kind) != (days[0], "gtfsrt")] + [
        (carry, "gtfsrt"), (carry, "csv"), (previous, "csv")]


def cached_original(day, kind):
    """Reference a verified prior raw archive instead of copying it."""
    path = ROOT / "data/manifests/october-acquisition.json"
    for item in json.loads(path.read_text())["archives"]:
        if item["archive_date"] == day and item["kind"] == kind:
            raw = Path(item["path"])
            if raw.is_file() and raw.stat().st_size == item["bytes"] and sha256(raw) == item["sha256"]:
                return dict(item, cache_verified=True, reused_existing_raw_archive=True)
    return None


def acquire(config, workers=3):
    jobs = required_jobs(config)
    archives, errors = [], []
    def one(job):
        day, kind = job
        return cached_original(day, kind) or download_archive(day, kind, RAW)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, job): job for job in jobs}
        for future in as_completed(futures):
            day, kind = futures[future]
            try:
                item = future.result()
                archives.append(item)
                print(json.dumps({"stage": "ARCHIVE_VERIFIED", "date": day, "kind": kind,
                    "bytes": item["bytes"], "completed": len(archives), "total": len(jobs)}), flush=True)
            except Exception as error:
                errors.append({"date": day, "kind": kind, "error": type(error).__name__ + ": " + str(error)})
    # The next day need not have been published yet. Missing boundary evidence
    # limits labels but does not remove any requested decision date.
    boundary = (date.fromisoformat(config["end_date"]) + timedelta(days=1)).isoformat()
    try:
        archives.append(download_archive(boundary, "csv", RAW, retries=0))
        optional = {"date": boundary, "kind": "csv", "status": "AVAILABLE"}
    except Exception as error:
        optional = {"date": boundary, "kind": "csv", "status": "UNAVAILABLE",
                    "error": type(error).__name__ + ": " + str(error)}
    result = {"schema_version": "november-2026-acquisition-v1", "generated_at": now(),
              "stage": "INCOMPLETE" if errors else "ACQUIRED", "errors": errors,
              "archives": sorted(archives, key=lambda item: (item["archive_date"], item["kind"])),
              "required_jobs": [{"date": day, "kind": kind} for day, kind in jobs],
              "optional_following_boundary": optional}
    write_json(ACQUISITION, result)
    if errors:
        raise ValueError("Required November archives are incomplete; see acquisition manifest.")
    return result


def prepare(*, workers=4, inputs_only=False, labels_only=False, download_only=False, process_only=False):
    started = time.monotonic()
    config = json.loads(CONFIG.read_text())
    hashes, config_hash = code_hashes(), sha256(CONFIG)
    free_bytes = shutil.disk_usage(ROOT).free
    if free_bytes < 4 * 1024 ** 3:
        raise ValueError("At least 4 GiB free space is required for the isolated source outputs.")
    if labels_only or process_only:
        acquisition = json.loads(ACQUISITION.read_text())
        if acquisition.get("stage") != "ACQUIRED" or acquisition.get("errors"):
            raise ValueError("Required November archive acquisition is incomplete.")
    else:
        acquisition = acquire(config)
    if download_only:
        return acquisition
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dates = list(dates_between(config["start_date"], config["end_date"]))
    all_dates = [config["input_carry_date"], *dates]
    indexed = {(item["archive_date"], item["kind"]): item for item in acquisition["archives"]}
    reports = []
    if labels_only:
        prior = json.loads(MANIFEST.read_text())
        if prior["config"]["sha256"] != config_hash or prior["code_sha256"] != hashes:
            raise ValueError("Input sources must be regenerated after a producer change.")
        reports = prior["days"]
        for report in reports:
            for item in report["outputs"].values():
                if sha256(ROOT / item["path"]) != item["sha256"]:
                    raise ValueError("Prepared input changed before label construction.")
    else:
        order = [dates[0], *[day for day in all_dates if day != dates[0]]]
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(prepare_day, day, indexed[(day, "gtfsrt")], config,
                                      OUTPUT, hashes, config_hash): day for day in order}
            for future in as_completed(futures):
                report = future.result()
                report["boundary_input_only"] = report["date"] == config["input_carry_date"]
                reports.append(report)
                print(json.dumps({"stage": "DAY_NORMALIZED", "date": report["date"],
                    "snapshots": report["counts"]["snapshots"], "elapsed_seconds": report["elapsed_seconds"],
                    "completed_days": len(reports), "total_days": len(all_dates)}), flush=True)
        reports.sort(key=lambda item: item["date"])
    if code_hashes() != hashes or sha256(CONFIG) != config_hash:
        raise ValueError("Source producer or configuration changed during preparation.")
    manifest = {"schema_version": "november-2026-source-v1", "stage": "INPUTS_PREPARED",
        "generated_at": now(), "config": artifact(CONFIG), "code_sha256": hashes,
        "acquisition": artifact(ACQUISITION), "archives": acquisition["archives"],
        "dates": dates, "input_carry_dates": [config["input_carry_date"]], "days": reports,
        "requested_dates_complete": True, "following_boundary": acquisition["optional_following_boundary"]}
    # Consumers can begin input-only membership and forecast freezes here.
    write_json(MANIFEST, manifest)
    if inputs_only:
        return manifest
    print(json.dumps({"stage": "BUILDING_SEPARATE_OUTCOME_LABELS", "days": len(reports)}), flush=True)
    labels, daily_labels, quality = combine_labels(reports, acquisition["archives"], config, OUTPUT)
    if code_hashes() != hashes or sha256(CONFIG) != config_hash:
        raise ValueError("Source producer or configuration changed during label preparation.")
    report = {"schema_version": "november-2026-source-report-v1", "stage": "PREPARED",
        "decision_dates": dates, "input_carry_dates": [config["input_carry_date"]],
        "requested_dates_complete": True, "label_quality": quality,
        "following_boundary": acquisition["optional_following_boundary"],
        "elapsed_seconds": round(time.monotonic() - started, 2), "initial_free_bytes": free_bytes,
        "snapshot_count": sum(day["counts"]["snapshots"] for day in reports if not day["boundary_input_only"]),
        "alert_capture_count": sum(day["counts"]["alert_snapshots"] for day in reports if not day["boundary_input_only"]),
        "limitations": ["Screened final MTA prediction proxies are not independently observed passenger arrivals.",
            "November 1 uses America/New_York and has 25 civil hours; UTC timestamps remain distinct.",
            "October 31 is input carry only, outside November analysis exposure.",
            "No following-day source means late November 19 confirmation can remain unavailable.",
            "Archived alert deduplication does not establish fresh unchanged fetches.",
            "Daily snapshot streams are ordered within each feed, not globally."]}
    write_json(REPORT, report)
    manifest.update(stage="PREPARED", labels=labels, daily_labels=daily_labels, report=artifact(REPORT))
    write_json(MANIFEST, manifest)
    print(json.dumps({"stage": "PREPARED", "days": len(dates), "label_quality": quality,
                      "elapsed_seconds": report["elapsed_seconds"]}), flush=True)
    return manifest
