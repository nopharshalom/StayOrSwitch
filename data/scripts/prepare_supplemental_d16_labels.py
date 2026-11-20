#!/usr/bin/env python3
"""Create separate D16S labels for the October test-week route supplement."""

from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.october.prepare import artifact
from data.october.sources import dates_between, read_labels, sha256, write_gzip_json, write_json
from data.supplemental_endpoints import (build_supplemental_labels, collect_observed_stop,
    mark_supplemental_observations, merge_endpoint_labels, merge_trip_inventory)


def verify(item):
    path = ROOT / item["path"]
    if sha256(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
        raise ValueError("Input differs from frozen provenance: " + str(path))
    return path


def scan_one(item):
    return item["date"], collect_observed_stop(ROOT / item["outputs"]["snapshots"]["path"], "D16S")


def main():
    started = time.monotonic()
    source_path = ROOT / "data/manifests/october.json"
    source_digest = sha256(source_path)
    source = json.loads(source_path.read_text())
    if source.get("stage") != "PREPARED" or not source.get("full_month_processed"):
        raise ValueError("Complete frozen October source required.")
    for path, expected in source["label_producer_code_sha256"].items():
        if sha256(ROOT / path) != expected:
            raise ValueError("Original label producer changed: " + path)
    config = json.loads(verify(source["config"]).read_text())
    if "D16S" in config["stop_ids"]:
        raise ValueError("D16S is no longer a supplemental endpoint.")
    selected_dates = list(dates_between("2026-10-24", "2026-10-31"))
    selected_days = [day for day in source["days"] if day["date"] in selected_dates]
    if len(selected_days) != len(selected_dates):
        raise ValueError("Incomplete test and prior-day observation window.")
    original_inputs = [source["config"], source["labels"], *source["daily_labels"].values()]
    for day in source["days"]:
        original_inputs.extend(day["outputs"][key] for key in ("trips", "receipts"))
    original_inputs.extend(day["outputs"]["snapshots"] for day in selected_days)
    original_inputs.extend(item for item in source["archives"] if item["kind"] == "csv")
    for item in original_inputs:
        verify(item)
    code_paths = ["data/supplemental_endpoints.py", "data/scripts/prepare_supplemental_d16_labels.py"]
    code_hashes = {path: sha256(ROOT / path) for path in code_paths}
    trips, identity_days = merge_trip_inventory(source["days"], ROOT)
    observed_ids, observations_by_day = set(), {}
    print(json.dumps({"stage": "SCANNING_SUPPLEMENTAL_STOP_OBSERVATIONS", "dates": selected_dates}), flush=True)
    with ProcessPoolExecutor(max_workers=2) as executor:
        for day, identities in executor.map(scan_one, selected_days):
            observed_ids.update(identities)
            observations_by_day[day] = len(identities)
            print(json.dumps({"stage": "SUPPLEMENTAL_INPUT_DAY_SCANNED", "date": day}), flush=True)
    mark_supplemental_observations(trips, observed_ids, "D16S")
    print(json.dumps({"stage": "BUILDING_SEPARATE_SUPPLEMENTAL_LABELS"}), flush=True)
    labels, quality, used_journals = build_supplemental_labels(
        trips, identity_days, source["days"], source["archives"], config["timezone"], "D16S")
    # Exercise the integration operation while proving it cannot alter old labels.
    original = read_labels(ROOT / source["labels"]["path"])
    merged = merge_endpoint_labels(original, labels, "D16S")
    for identity, endpoints in original.items():
        if any(merged[identity][stop] != value for stop, value in endpoints.items()):
            raise ValueError("Supplement changed an original outcome endpoint.")
    output = ROOT / "data/processed/october-supplemental-d16/labels.json.gz"
    write_gzip_json(output, labels)
    quality_path = output.parent / "label-quality.json"
    write_json(quality_path, quality)
    for item in original_inputs:
        verify(item)
    if sha256(source_path) != source_digest or any(sha256(ROOT / path) != value for path, value in code_hashes.items()):
        raise ValueError("Source or producer changed during supplement preparation.")
    manifest = {
        "schema_version": "supplemental-endpoint-labels-v1", "stage": "PREPARED",
        "stop_id": "D16S", "stop_name": "42 St-Bryant Pk", "platform_direction": "SOUTH",
        "observation_dates": selected_dates, "evaluation_dates": ["2026-10-25", "2026-10-31"],
        "prior_day_role": "Boundary selected-train observations only; not an additional test day.",
        "source_manifest": {"path": str(source_path.relative_to(ROOT)), "sha256": source_digest},
        "source_inputs": original_inputs, "source_label_producer_code_sha256": source["label_producer_code_sha256"],
        "supplement_producer_code_sha256": code_hashes, "labels": artifact(output),
        "quality_report": artifact(quality_path), "csv_journals_used": used_journals,
        "observed_trip_identity_counts_by_day": observations_by_day,
        "old_endpoints_unchanged": True, "original_artifacts_unchanged": True,
        "label_policy": "UNCHANGED_ORIGINAL_SCREENED_MTA_FINAL_PREDICTION_RULES",
        "physical_ground_truth": False, "used_for_training": False,
        "outcome_quality_summary_withheld_from_input_selection": True,
        "station_metadata_source": "https://data.ny.gov/Transportation/MTA-Subway-Stations/39hk-dx4f",
        "station_metadata_query": "https://data.ny.gov/resource/39hk-dx4f.json?gtfs_stop_id=D16",
        "station_metadata": {"gtfs_stop_id": "D16", "station_id": "226", "complex_id": "609",
            "stop_name": "42 St-Bryant Pk", "latitude": 40.754222, "longitude": -73.984569,
            "south_direction_label": "Downtown", "daytime_routes": "B D F M",
            "historical_service_verified_from_each_selected_train": True},
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    destination = ROOT / "data/manifests/october-supplemental-d16.json"
    write_json(destination, manifest)
    print(json.dumps({"stage": "PREPARED", "manifest": str(destination.relative_to(ROOT)),
                      "labels": str(output.relative_to(ROOT)), "elapsed_seconds": manifest["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
