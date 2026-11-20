#!/usr/bin/env python3
"""Add required raw-feed leg spans without replacing frozen October artifacts."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.october.prepare import artifact, prepare_day
from data.october.sources import read_labels, sha256, write_gzip_json, write_json
from data.preincident_inputs import augmented_configuration, verify_daily_projection
from data.supplemental_endpoints import (build_supplemental_labels, mark_supplemental_observations,
                                        merge_endpoint_labels, merge_trip_inventory)


def verified(item):
    path = ROOT / item["path"]
    if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
        raise ValueError("Frozen input changed: " + str(path))
    return path


def main():
    started = time.monotonic()
    source_path = ROOT / "data/manifests/october.json"
    original_d16 = ROOT / "data/manifests/october-supplemental-d16.json"
    source_digest, old_d16_digest = sha256(source_path), sha256(original_d16)
    source = json.loads(source_path.read_text())
    for path, expected in source["label_producer_code_sha256"].items():
        if sha256(ROOT / path) != expected:
            raise ValueError("Frozen original producer changed: " + path)
    original_config = json.loads(verified(source["config"]).read_text())
    config = augmented_configuration(original_config)
    config_path = ROOT / "data/config/preincident-projection.json"
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError("Existing supplemental projection configuration differs.")
    write_json(config_path, config)
    config_hash = sha256(config_path)
    code_paths = ["data/preincident_inputs.py", "data/scripts/prepare_preincident_inputs.py", "data/supplemental_endpoints.py"]
    code_hashes = {**source["label_producer_code_sha256"], **{path: sha256(ROOT / path) for path in code_paths}}
    selected = [day for day in source["days"] if "2026-10-24" <= day["date"] <= "2026-10-31"]
    if len(selected) != 8:
        raise ValueError("Eight observation dates including the boundary date are required.")
    original_inputs = [source["config"], source["labels"], *source["daily_labels"].values()]
    for day in source["days"]:
        original_inputs.extend(day["outputs"][key] for key in ("trips", "receipts"))
    original_inputs.extend(item for day in selected for item in day["outputs"].values())
    original_inputs.extend(item for item in source["archives"] if item["kind"] == "csv")
    old_d16_manifest = json.loads(original_d16.read_text())
    original_inputs.extend([old_d16_manifest["labels"], old_d16_manifest["quality_report"]])
    for item in original_inputs:
        verified(item)
    archives = {item["archive_date"]: item for item in source["archives"] if item["kind"] == "gtfsrt"}
    output = ROOT / "data/processed/preincident-inputs"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    print(json.dumps({"stage": "NORMALIZING_ADDITIONAL_LEG_SPANS", "days": 8, "feeds": config["feed_ids"]}), flush=True)
    with ProcessPoolExecutor(max_workers=2) as executor:
        pending = {executor.submit(prepare_day, day["date"], archives[day["date"]], config, output,
                                   code_hashes, config_hash): day for day in selected}
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            print(json.dumps({"stage": "SUPPLEMENTAL_DAY_NORMALIZED", "date": result["date"],
                              "completed": len(results), "days": 8}), flush=True)
    results.sort(key=lambda day: day["date"])
    parity, observed_ids = {}, set()
    old_by_day = {day["date"]: day for day in selected}
    for day in results:
        original_day = old_by_day[day["date"]]
        parity[day["date"]] = verify_daily_projection(
            ROOT / original_day["outputs"]["snapshots"]["path"], ROOT / day["outputs"]["snapshots"]["path"])
        if day["outputs"]["alerts"]["sha256"] != original_day["outputs"]["alerts"]["sha256"]:
            raise ValueError("Supplement changed original alert captures.")
        previous_receipts = read_labels(ROOT / original_day["outputs"]["receipts"]["path"])
        current_receipts = read_labels(ROOT / day["outputs"]["receipts"]["path"])
        if current_receipts != {feed: previous_receipts[feed] for feed in config["feed_ids"]}:
            raise ValueError("Supplement changed raw receipt coverage or facts.")
        for identity, trip in read_labels(ROOT / day["outputs"]["trips"]["path"]).items():
            if "D16S" in trip["observed_stop_ids"]:
                observed_ids.add(identity)
        print(json.dumps({"stage": "ORIGINAL_CAPTURE_AND_ENDPOINT_PARITY_VERIFIED", "date": day["date"]}), flush=True)
    trips, identity_days = merge_trip_inventory(source["days"], ROOT)
    mark_supplemental_observations(trips, observed_ids, "D16S")
    labels, quality, used_journals = build_supplemental_labels(
        trips, identity_days, source["days"], source["archives"], original_config["timezone"], "D16S")
    original_labels = read_labels(ROOT / source["labels"]["path"])
    merged = merge_endpoint_labels(original_labels, labels, "D16S")
    if any(merged[identity][stop] != value for identity, endpoints in original_labels.items()
           for stop, value in endpoints.items()):
        raise ValueError("Supplement changed an original endpoint label.")
    label_path, quality_path = output / "d16-labels.json.gz", output / "d16-label-quality.json"
    write_gzip_json(label_path, labels)
    write_json(quality_path, quality)
    for item in original_inputs:
        verified(item)
    for path, expected in code_hashes.items():
        if sha256(ROOT / path) != expected:
            raise ValueError("Producer changed during the run: " + path)
    if sha256(source_path) != source_digest or sha256(original_d16) != old_d16_digest or sha256(config_path) != config_hash:
        raise ValueError("Input manifest or configuration changed during the run.")
    manifest = {"schema_version": "preincident-supplemental-inputs-v1", "stage": "PREPARED",
        "source_manifest": {"path": str(source_path.relative_to(ROOT)), "sha256": source_digest},
        "previous_d16_attempt": {"path": str(original_d16.relative_to(ROOT)), "sha256": old_d16_digest,
            "retained_unchanged": True, "limitation": "Old projected spans omitted D16 after F09 disappeared."},
        "config": artifact(config_path), "code_sha256": code_hashes,
        "observation_dates": [day["date"] for day in results], "test_dates": ["2026-10-25", "2026-10-31"],
        "replacement_feed_ids": config["feed_ids"],
        "integration_policy": "REPLACE_ORIGINAL_BDFM_AND_NUMBERED_RECORDS; RETAIN_ORIGINAL_OTHER_FEEDS_AND_ALERTS; NEVER_APPEND_DUPLICATE_CAPTURES",
        "days": results, "projection_parity": parity,
        "labels": artifact(label_path), "label_quality": artifact(quality_path),
        "label_policy": "UNCHANGED_SCREENED_FINAL_MTA_PREDICTION_RULES_AND_FULL_MONTH_IDENTITY_RECEIPT_CHECKS",
        "csv_journals_used": used_journals, "original_inputs": original_inputs,
        "old_artifacts_unchanged": True, "old_endpoint_labels_unchanged": True,
        "physical_ground_truth": False, "training_profiles_unchanged": True,
        "elapsed_seconds": round(time.monotonic() - started, 3)}
    target = ROOT / "data/manifests/preincident-inputs.json"
    write_json(target, manifest)
    print(json.dumps({"stage": "PREPARED", "manifest": str(target.relative_to(ROOT)),
                      "elapsed_seconds": manifest["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
