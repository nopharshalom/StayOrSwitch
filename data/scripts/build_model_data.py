#!/usr/bin/env python3
"""Prepare deterministic, chronological model views from verified pilot shards."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import time

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY / "algo"))

from data.modeling.features import (CATEGORICAL_FEATURES, FEATURE_NAMES, FEATURE_VERSION,
                                    disruption_group, horizon_bucket)
from data.modeling.views import (SelectionStore, _semantic, event_id, make_example,
                                 selection_priority, sha256, trip_selected, write_views)


def _json(path):
    return json.loads(path.read_text())


def _path(relative):
    path = (REPOSITORY / relative).resolve()
    if REPOSITORY not in path.parents:
        raise ValueError("Model data paths must remain inside the repository.")
    return path


def _verify(item):
    path = _path(item["path"])
    if "bytes" in item and path.stat().st_size != item["bytes"]:
        raise ValueError("Source size mismatch: " + item["path"])
    if sha256(path) != item["sha256"]:
        raise ValueError("Source checksum mismatch: " + item["path"])
    return path


def _progress(**values):
    print(json.dumps(values, sort_keys=True), flush=True)


def build(config_path):
    started = time.monotonic()
    config = _json(config_path)
    if (config["horizon_buckets_seconds"] != [0, 300, 900, 1800] or
            config["departure_basis"] != "DEPARTURE_PREDICTION" or
            config["feature_version"] != FEATURE_VERSION):
        raise ValueError("Configuration does not match implemented feature and selection semantics.")
    source_manifest_path = _path(config["source_manifest"])
    source_manifest = _json(source_manifest_path)
    if source_manifest.get("stage") != "PREPARED" or not source_manifest.get("full_configured_window_processed"):
        raise ValueError("A complete prepared historical pilot manifest is required.")
    _verify(source_manifest["config"])
    source_report = _json(_verify(source_manifest["report"]))
    if source_report["global_integrity"].get("status") != "PASS":
        raise ValueError("Historical global integrity must pass before model preparation.")
    for name, digest in source_manifest["code_sha256"].items():
        _verify({"path": name, "sha256": digest})
    if len(source_manifest["outputs"]) != 28:
        raise ValueError("The configured full pilot requires 28 historical shards.")
    code_paths = ["data/modeling/__init__.py", "data/modeling/features.py", "data/modeling/views.py",
                  "data/scripts/build_model_data.py"]
    code_hashes = {name: sha256(_path(name)) for name in code_paths}
    config_digest, source_digest = sha256(config_path), sha256(source_manifest_path)
    inputs = []
    for item in source_manifest["outputs"]:
        _verify(item)
        inputs.append(dict(item))
    _progress(stage="INPUTS_VERIFIED", shards=len(inputs))
    output_root = _path(config["output_directory"])
    output_root.mkdir(parents=True, exist_ok=True)
    database = output_root / "selection.sqlite"
    if database.exists():
        database.unlink()
    store = SelectionStore(database, config["sampling_seed"])
    source_counts = defaultdict(Counter)
    source_groups = defaultdict(Counter)
    trip_membership = {}
    processed = []
    try:
        for item in inputs:
            filename = item["path"]
            targets = ("arrival",) if ".arrivals." in filename else ("departure", "segment")
            bank = {}
            rows_read = 0
            with gzip.open(_path(filename), "rt", encoding="utf-8") as stream:
                for line in stream:
                    row = json.loads(line)
                    rows_read += 1
                    source, split, trip = row["features"], row["split"], row["trip_identity"]
                    if split not in ("train", "validation", "test"):
                        raise ValueError("Unknown chronological split in source shard.")
                    take = trip_membership.get(trip)
                    if take is None:
                        take = trip_selected(trip, config["trip_sample_percent"], config["sampling_seed"])
                        trip_membership[trip] = take
                    source_eligible = bool(row.get("eligible_for_training") and row["label"].get("usable_proxy") and not row["label"].get("quality_flags"))
                    for target in targets:
                        count_key = target + "/" + split
                        counters = source_counts[count_key]
                        counters["source_rows"] += 1
                        counters["source_label_eligible_rows"] += int(source_eligible)
                        actual_departure = target == "arrival" or source.get("origin_prediction_basis") == "DEPARTURE_PREDICTION"
                        counters["unsupported_departure_basis_rows"] += int(not actual_departure)
                        counters["source_label_and_basis_eligible_rows"] += int(source_eligible and actual_departure)
                        for group, value in (("day_type", source["day_type"]), ("route_id", source["route_id"]),
                                             ("disruption_group", disruption_group(source, target))):
                            source_groups[count_key + "/" + group][str(value)] += 1
                        if not take:
                            continue
                        counters["trip_sampled_candidate_rows"] += 1
                        horizon = source.get("prediction_horizon_seconds" if target == "arrival" else "departure_horizon_seconds")
                        bucket = horizon_bucket(horizon)
                        if bucket is None:
                            counters["invalid_horizon_rows"] += 1
                            continue
                        event = event_id(row, target)
                        key = (target, event, bucket)
                        priority = selection_priority({"event_id": event, "decision_at": row["decision_at"]}, config["sampling_seed"])
                        previous = bank.get(key)
                        if previous and previous[0] < priority:
                            continue
                        example = make_example(row, target)
                        if previous and previous[0] == priority:
                            old = previous[1]
                            if "CONFLICTING_DUPLICATE" in old["exclusion_reasons"]:
                                continue
                            if _semantic(old) == _semantic(example):
                                continue
                            example["eligible"] = False
                            example["exclusion_reasons"] = sorted(set(old["exclusion_reasons"] + example["exclusion_reasons"] + ["CONFLICTING_DUPLICATE"]))
                        bank[key] = (priority, example)
            for _, example in bank.values():
                store.consider(example)
            store.connection.commit()
            processed.append({"path": filename, "source_rows": rows_read, "selected_candidates_in_shard": len(bank)})
            _progress(stage="SHARD_SELECTED", path=filename, source_rows=rows_read,
                      selected_candidates=len(bank), elapsed_seconds=round(time.monotonic() - started, 1))
        outputs, selection_report = write_views(store, output_root)
    finally:
        store.close()
    database.unlink()
    for item in outputs:
        item["path"] = str(Path(item["path"]).relative_to(REPOSITORY))
    for name, digest in code_hashes.items():
        if sha256(_path(name)) != digest:
            raise ValueError("Processing code changed during dataset preparation: " + name)
    if sha256(config_path) != config_digest or sha256(source_manifest_path) != source_digest:
        raise ValueError("Configuration or source manifest changed during processing.")
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    limitations = [
        "Labels are final-prediction proxies from the same MTA source, not observed physical arrivals.",
        "The fixed trip sample and event/horizon selection do not represent all source snapshots or passenger queries.",
        "Selection precedes label filtering; unusable selected rows are excluded without replacement.",
        "Departure labels inherit both-endpoint segment quality restrictions; boarding-only alerts are unknown.",
        "Validation contains weekdays only; the held-out weekend must not guide model selection.",
        "Source extraction excludes already-past predictions and horizons beyond thirty minutes; severe stalls may be absent.",
        "No historical Google route predictions or complete passenger journey outcomes are present.",
        "Rolling arrival features are research metadata and are not part of the deployable snapshot core.",
    ]
    report = {"schema_version": "model-data-report-v1", "generated_at": now,
              "source_counts": {key: dict(value) for key, value in source_counts.items()},
              "source_groups": {key: dict(value) for key, value in source_groups.items()},
              "source_extraction_counts": {"arrival": source_report.get("arrival_counts"),
                                           "segment": source_report.get("segment_counts")},
              "selection": selection_report, "outputs": outputs, "processed_shards": processed,
              "limitations": limitations, "elapsed_seconds": round(time.monotonic() - started, 1)}
    report_path = _path(config["report_path"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    manifest = {"schema_version": "model-data-manifest-v1", "stage": "PREPARED", "generated_at": now,
                "source_manifest": {"path": config["source_manifest"], "sha256": source_digest},
                "config": {"path": str(config_path.relative_to(REPOSITORY)), "sha256": config_digest},
                "code_sha256": code_hashes, "feature_version": FEATURE_VERSION,
                "feature_names": FEATURE_NAMES, "categorical_features": CATEGORICAL_FEATURES,
                "sampling": {"trip_percent": config["trip_sample_percent"], "seed": config["sampling_seed"],
                             "selected_before_label_filter": True, "event_weight_total": 1.0},
                "splits": source_manifest["splits"], "inputs": inputs, "outputs": outputs,
                "report": {"path": config["report_path"], "sha256": sha256(report_path)},
                "runtime": {"python_version": sys.version, "dependencies": "Python standard library"},
                "limitations": limitations}
    manifest_path = _path(config["manifest_path"])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n")
    _progress(stage="PREPARED", manifest=str(manifest_path.relative_to(REPOSITORY)),
              rows=sum(item["rows"] for item in outputs), elapsed_seconds=report["elapsed_seconds"])
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="data/config/model-data.json", help="Repository-relative model data configuration")
    args = parser.parse_args()
    build(_path(args.config))


if __name__ == "__main__":
    main()
