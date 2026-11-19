#!/usr/bin/env python3
"""Prepare fixed historical corridor cases without model or route scoring."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import gzip
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo"), str(ROOT / "data")]

from data.corridor_replay.extract import collect_labels, extract_snapshots, verify_archive
from data.history.archives import sha256_file
from data.history.features import iso


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def emit(stage, **values):
    print(json.dumps({"stage": stage, **values}, sort_keys=True), flush=True)


def prepare(scout_path, config_path, output_path, *, workers=4):
    started = time.monotonic()
    config = json.loads(config_path.read_text())
    scout = json.loads(scout_path.read_text())
    manifest_path = ROOT / "data/manifests/history-pilot.json"
    history = json.loads(manifest_path.read_text())
    if history.get("stage") != "PREPARED" or not history.get("full_configured_window_processed"):
        raise ValueError("A complete verified historical source is required.")
    source_paths = [Path(__file__), ROOT / "data/scripts/scout_corridor_replay.py",
                    ROOT / "data/corridor_replay/extract.py",
                    ROOT / "data/corridor_replay/__init__.py", ROOT / "data/history/archives.py",
                    ROOT / "data/history/features.py", ROOT / "algo/stayorswitch/mta.py"]
    initial_hashes = {str(path.relative_to(ROOT)): sha256_file(path) for path in source_paths}
    input_hashes = {str(path.relative_to(ROOT)): sha256_file(path)
                    for path in (config_path, scout_path, manifest_path)}
    provenance = scout["provenance"]
    if provenance["source_sha256"] != sha256_file(ROOT / "data/scripts/scout_corridor_replay.py"):
        raise ValueError("Scout source differs from its recorded checksum.")
    history_outputs = {item["path"]: item for item in history["outputs"]}
    for shard in provenance["input_shards"]:
        path = Path(shard["path"]).resolve()
        relative = str(path.relative_to(ROOT))
        expected = history_outputs[relative]
        if shard["sha256"] != expected["sha256"] or sha256_file(path) != expected["sha256"]:
            raise ValueError("Discovery shard differs from the verified history manifest.")
        input_hashes[relative] = expected["sha256"]
    if "days" in scout:
        discovery_cases = [item for day in scout["days"].values() for item in day["all_delay_candidates"]]
        summary = {day: value["counts"] for day, value in scout["days"].items()}
        screening_scope = "ALL_DISCOVERED_CUTOFFS_BEFORE_EPISODE_SPACING"
        selection_rule = (
            "Use every retrospectively discovered qualifying cutoff for raw screening, "
            "before per-route limits, distinct-train filtering, or episode spacing. "
            "The scout's at-most-four per-route/day shortlist is a supplementary preview "
            "only and is not the replay input. The separate evaluator uses complete "
            "raw forecasts to choose the same-cutoff fastest unmodified-MTA supplied "
            "path, tests its destination proxy error, then selects chronological "
            "distinct-train episodes. Model outputs and alternative outcome advantages "
            "must not enter case selection."
        )
    else:
        discovery_cases = scout["cases"]
        summary = scout.get("summary")
        screening_scope = "SMALL_PRESPACED_DISCOVERY_POOL"
        selection_rule = scout.get("selection_rule")
    selection, cases, grouped = {}, [], defaultdict(list)
    for item in discovery_cases:
        cutoff = item["decision_at"]
        day = item["local_time"][:10]
        identifier = item.get("case_id", item.get("id")) or (
            day + "-" + item["route_id"] + "-" + item["local_time"][11:19].replace(":", ""))
        if day not in config["dates"] or not identifier or identifier in selection:
            raise ValueError("Case date or identity is invalid.")
        case = {"id": identifier, "decision_at": iso(cutoff), "local_time": item["local_time"],
                "archive_date": day}
        selection[identifier] = item
        grouped[day].append(case)
        cases.append(case)
    if not cases:
        raise ValueError("No selected retrospective case cutoffs exist.")
    feeds = sorted({route["feed_id"] for route in config["routes"]})
    archive_index = {(item["archive_date"], item["kind"]): item for item in history["archives"]}
    inputs, extraction = [], {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for day, day_cases in grouped.items():
            item = archive_index[(day, "gtfsrt")]
            path = verify_archive(ROOT, item)
            inputs.append(item)
            futures[executor.submit(extract_snapshots, path, day_cases, feeds)] = day
        for future in as_completed(futures):
            day = futures[future]
            extraction[day] = future.result()
            emit("DAY_SNAPSHOTS_EXTRACTED", day=day, cases=len(grouped[day]),
                 elapsed_seconds=round(time.monotonic() - started, 1), **extraction[day]["counts"])
    snapshots = []
    states = Counter()
    for case in cases:
        case["snapshots"] = extraction[case["archive_date"]]["snapshots"][case["id"]]
        snapshots.extend(case["snapshots"])
        for snapshot in case["snapshots"]:
            states[snapshot["feed_id"] + ":" + snapshot["replay_freshness"]] += 1
    # Adjacent publisher journals handle opaque UTC-based trip UID boundaries.
    first = datetime.fromisoformat(min(grouped)).date() - timedelta(days=1)
    last = datetime.fromisoformat(max(grouped)).date() + timedelta(days=1)
    csv_archives = [item for item in history["archives"] if item["kind"] == "csv"
                    and first.isoformat() <= item["archive_date"] <= last.isoformat()]
    endpoint_ids = {route[key] for route in config["routes"]
                    for key in ("boarding_stop_id", "alighting_stop_id")}
    label_result = collect_labels(csv_archives, snapshots, endpoint_ids, root=ROOT)
    inputs.extend(csv_archives)
    bundle = {
        "schema_version": "corridor-replay-bundle-v1", "cases": sorted(cases, key=lambda case: case["decision_at"]),
        "routes": config["routes"], "route_templates": config["routes"], "config": config,
        "labels": label_result["labels"],
        "case_selection": {"rule": selection_rule, "summary": summary,
                           "discovery_and_supplementary_preview_rule": scout.get("selection_rule"),
                           "raw_screening_scope": screening_scope,
                           "by_case": selection, "retrospective_outcome_conditioned": True,
                           "model_predictions_or_switch_results_used": False},
        "label_evidence": "QUALITY_SCREENED_MTA_FINAL_PREDICTION_PROXY",
        "limitations": [
            "Case discovery is retrospective and conditioned on later forecast errors, not an online delay detector.",
            "The initial candidate pool comes from the scoped zero-to-thirty-minute historical features; extracted raw snapshots retain all original trip forecasts.",
            "Fixed supplied paths and authored walking assumptions do not establish historical route-provider output or walking observations.",
            "Content-deduplicated historical alerts do not establish a fresh unchanged alert fetch.",
            "Final-prediction CSV outcomes are proxies, not observed passenger outcomes; missing or missed-boarding outcomes must remain unavailable.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
        compressed.write(json.dumps(bundle, separators=(",", ":"), sort_keys=True, allow_nan=False).encode())
    if initial_hashes != {str(path.relative_to(ROOT)): sha256_file(path) for path in source_paths}:
        raise ValueError("Replay preparation code changed during extraction.")
    for relative, expected in input_hashes.items():
        if sha256_file(ROOT / relative) != expected:
            raise ValueError("Replay preparation input changed during extraction.")
    report = {"stage": "PREPARED", "case_count": len(cases), "dates": sorted(grouped),
              "snapshots_by_freshness": dict(states), "label_quality": label_result["quality"],
              "selection_summary": summary, "selection_rule": selection_rule,
              "discovery_and_supplementary_preview_rule": scout.get("selection_rule"),
              "raw_screening_scope": screening_scope,
              "routes": config["routes"], "reference_policy": config["reference_policy"],
              "archive_extraction": {day: value["counts"] for day, value in extraction.items()},
              "elapsed_seconds": round(time.monotonic() - started, 1), "limitations": bundle["limitations"]}
    report_path = ROOT / "data/reports/corridor-replay-data.json"
    write_json(report_path, report)
    manifest = {"stage": "PREPARED", "schema_version": "corridor-replay-manifest-v1",
                "code_sha256": initial_hashes, "input_sha256": input_hashes,
                "archives": [{key: item[key] for key in ("path", "sha256", "bytes", "archive_date", "kind")}
                             for item in sorted(inputs, key=lambda item: (item["archive_date"], item["kind"]))],
                "bundle": {"path": str(output_path.relative_to(ROOT)), "sha256": sha256_file(output_path),
                           "bytes": output_path.stat().st_size, "case_count": len(cases)},
                "report": {"path": str(report_path.relative_to(ROOT)), "sha256": sha256_file(report_path)}}
    write_json(ROOT / "data/manifests/corridor-replay.json", manifest)
    emit("PREPARED", cases=len(cases), bundle=str(output_path.relative_to(ROOT)),
         elapsed_seconds=report["elapsed_seconds"])
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scout", type=Path, default=ROOT / "data/processed/corridor-replay/scout-primary.json")
    parser.add_argument("--config", type=Path, default=ROOT / "data/config/corridor-replay.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/corridor-replay/replay-bundle.json.gz")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    prepare(args.scout.resolve(), args.config.resolve(), args.output.resolve(), workers=args.workers)


if __name__ == "__main__":
    main()
