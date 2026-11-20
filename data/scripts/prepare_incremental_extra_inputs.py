#!/usr/bin/env python3
"""Prepare separate R16S input spans and labels using existing local archives."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.incremental_extra_inputs import (augmented_configuration, build_additional_labels,
    merge_label_additions, select_new_label_endpoints, verify_daily_projection)
from data.october.prepare import artifact, prepare_day
from data.october.sources import read_labels, sha256, write_gzip_json, write_json
from data.supplemental_endpoints import merge_trip_inventory


def verified(item):
    path = ROOT / item["path"]
    if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
        raise ValueError("Frozen input changed: " + str(path))
    return path


def main():
    started = time.monotonic()
    source_path = ROOT / "data/manifests/october.json"
    previous_path = ROOT / "data/manifests/google-corridor-inputs.json"
    source_digest, previous_digest = sha256(source_path), sha256(previous_path)
    source, previous = json.loads(source_path.read_text()), json.loads(previous_path.read_text())
    if source.get("stage") != "PREPARED" or previous.get("stage") != "PREPARED":
        raise ValueError("Original and preceding projections must be prepared.")
    for name, digest in source["label_producer_code_sha256"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError("Frozen producer changed: " + name)
    original_config = json.loads(verified(source["config"]).read_text())
    config = augmented_configuration(original_config)
    config_path = ROOT / "data/config/incremental-extra-projection.json"
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError("Existing supplemental configuration differs.")
    write_json(config_path, config)
    config_hash = sha256(config_path)
    paths = ["data/incremental_extra_inputs.py", "data/scripts/prepare_incremental_extra_inputs.py",
             "data/google_corridor_inputs.py", "data/preincident_inputs.py", "data/supplemental_endpoints.py"]
    code_hashes = {**source["label_producer_code_sha256"], **{p: sha256(ROOT / p) for p in paths}}
    selected = [day for day in source["days"] if "2026-10-24" <= day["date"] <= "2026-10-31"]
    if len(selected) != 8:
        raise ValueError("Eight observation dates including a boundary day are required.")
    old_by_day = {day["date"]: day for day in selected}
    previous_by_day = {day["date"]: day for day in previous["days"]}
    original_inputs = [source["config"], source["labels"], previous["labels"], previous["label_quality"]]
    for day in source["days"]:
        original_inputs.extend(day["outputs"][key] for key in ("trips", "receipts"))
    original_inputs.extend(item for day in selected for item in day["outputs"].values())
    original_inputs.extend(item for day in previous["days"] for item in day["outputs"].values())
    original_inputs.extend(item for item in source["archives"] if item["kind"] == "csv")
    for item in original_inputs:
        verified(item)
    archives = {item["archive_date"]: item for item in source["archives"] if item["kind"] == "gtfsrt"}
    output = ROOT / "data/processed/incremental-extra-inputs"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    print(json.dumps({"stage": "NORMALIZING_EXTRA_R16_SPAN", "days": 8, "feeds": config["feed_ids"]}), flush=True)
    with ProcessPoolExecutor(max_workers=2) as executor:
        pending = [executor.submit(prepare_day, day["date"], archives[day["date"]], config, output,
                                   code_hashes, config_hash) for day in selected]
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            print(json.dumps({"stage": "SUPPLEMENTAL_DAY_NORMALIZED", "date": result["date"],
                              "completed": len(results), "elapsed_seconds": round(time.monotonic() - started, 1)}), flush=True)
    results.sort(key=lambda day: day["date"])
    parity = {}
    for day in results:
        original_day, previous_day = old_by_day[day["date"]], previous_by_day[day["date"]]
        parity[day["date"]] = verify_daily_projection(
            ROOT / previous_day["outputs"]["snapshots"]["path"], ROOT / day["outputs"]["snapshots"]["path"])
        if day["outputs"]["alerts"]["sha256"] != original_day["outputs"]["alerts"]["sha256"]:
            raise ValueError("Supplement changed original alert captures.")
        old_receipts = read_labels(ROOT / previous_day["outputs"]["receipts"]["path"])
        new_receipts = read_labels(ROOT / day["outputs"]["receipts"]["path"])
        if new_receipts != {"nqrw": old_receipts["nqrw"]}:
            raise ValueError("Supplement changed raw receipt coverage or values.")
        print(json.dumps({"stage": "PROJECTION_PARITY_VERIFIED", "date": day["date"]}), flush=True)
    trips, identity_days = merge_trip_inventory(source["days"] + previous["days"] + results, ROOT)
    original_labels = read_labels(ROOT / source["labels"]["path"])
    for identity, endpoints in read_labels(ROOT / previous["labels"]["path"]).items():
        target = original_labels.setdefault(identity, {})
        if set(target) & set(endpoints):
            raise ValueError("Earlier supplemental labels overlap original labels.")
        target.update(endpoints)
    select_new_label_endpoints(trips, original_labels)
    labels, quality, journals = build_additional_labels(
        trips, identity_days, source["days"], source["archives"], original_config["timezone"])
    merge_label_additions(original_labels, labels)
    label_path, quality_path = output / "additional-labels.json.gz", output / "additional-label-quality.json"
    write_gzip_json(label_path, labels)
    write_json(quality_path, quality)
    for item in original_inputs:
        verified(item)
    for name, digest in code_hashes.items():
        if sha256(ROOT / name) != digest:
            raise ValueError("Producer changed during the run: " + name)
    if (sha256(source_path) != source_digest or sha256(previous_path) != previous_digest
            or sha256(config_path) != config_hash):
        raise ValueError("Input manifest or configuration changed during the run.")
    manifest = {
        "schema_version": "incremental-extra-supplemental-inputs-v1", "stage": "PREPARED",
        "source_manifest": {"path": str(source_path.relative_to(ROOT)), "sha256": source_digest},
        "previous_projection_manifest": {"path": str(previous_path.relative_to(ROOT)), "sha256": previous_digest},
        "config": artifact(config_path), "code_sha256": code_hashes,
        "observation_dates": [day["date"] for day in results], "test_dates": ["2026-10-25", "2026-10-31"],
        "replacement_feed_ids": config["feed_ids"],
        "integration_policy": "REPLACE_NQRW_ONLY; RETAIN_GOOGLE_NUMBERED_PREINCIDENT_BDFM_ORIGINAL_ACE_G_ALERTS; NEVER_APPEND_DUPLICATE_CAPTURES",
        "days": results, "projection_parity": parity,
        "labels": artifact(label_path), "label_quality": artifact(quality_path),
        "label_policy": "ONLY_NEW_R16S_R_ENDPOINT_KEYS; UNCHANGED_SCREENED_FINAL_MTA_RULES_AND_FULL_ORIGINAL_RECEIPT_CHECKS",
        "new_label_routes_and_stops": {"R": ["R16S"]},
        "csv_journals_used": journals, "original_inputs": original_inputs,
        "old_artifacts_unchanged": True, "old_endpoint_labels_unchanged": True,
        "training_profiles_unchanged": True, "physical_ground_truth": False,
        "source_archives_copied": False,
        "elapsed_seconds": round(time.monotonic() - started, 3)}
    target = ROOT / "data/manifests/incremental-extra-inputs.json"
    write_json(target, manifest)
    print(json.dumps({"stage": "PREPARED", "manifest": str(target.relative_to(ROOT)),
                      "elapsed_seconds": manifest["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
