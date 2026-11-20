"""Rebuild labels after a reviewed namespace fix without rewriting observations."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import time

from data.october.prepare import artifact, code_hashes, combine_labels
from data.october.sources import ROOT, now, read_labels, sha256, write_json


APPROVED_CHANGED_PATHS = {"data/october/labels.py"}
APPROVED_QUALITY_COUNTS = {"usable_arrival_rows", "usable_departure_rows", "flag:RAW_TRIP_ROUTE_MISMATCH"}


def reviewed_code_delta(previous, current):
    changed = {path for path in set(previous) | set(current) if previous.get(path) != current.get(path)}
    if changed != APPROVED_CHANGED_PATHS:
        raise ValueError("Label-only rebuild requires exactly the reviewed labels.py producer change.")
    return sorted(changed)


def expected_label_digest(labels, *, copy_input=True):
    """Permit only the approved raw-prefix flag removal; preserve every outcome."""
    result = deepcopy(labels) if copy_input else labels
    for endpoints in result.values():
        for label in endpoints.values():
            raw = re.fullmatch(r"[0-9]{6}_([^_.]+)\.\.([NS]).*", str(label.get("raw_trip_id") or ""))
            actual = label.get("route_id")
            allowed = {actual} | {"W": {"N"}, "FX": {"F"}, "7X": {"7"}}.get(actual, set())
            if raw is not None and raw.group(1) in allowed:
                for key in ("quality_flags", "arrival_quality_flags", "departure_quality_flags"):
                    label[key] = [flag for flag in label[key] if flag != "RAW_TRIP_ROUTE_MISMATCH"]
                label["arrival_usable"] = not label["arrival_quality_flags"]
                label["departure_usable"] = not label["departure_quality_flags"]
    return label_digest(result)


def label_digest(labels):
    body = json.dumps(labels, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(body).hexdigest()


def verify_artifacts(items):
    verified = {}
    for item in items:
        path = (ROOT / item["path"]).resolve()
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError("An input artifact differs from its recorded provenance: " + str(path))
        verified[str(path)] = item["sha256"]
    return verified


def preserve(path, destination):
    body = path.read_bytes()
    if destination.exists() and destination.read_bytes() != body:
        raise ValueError("Refusing to overwrite different origin provenance.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    return artifact(destination)


def rebuild():
    started = time.monotonic()
    manifest_path = ROOT / "data/manifests/october.json"
    previous = json.loads(manifest_path.read_text())
    if previous.get("stage") != "PREPARED" or not previous.get("full_month_processed") or len(previous.get("days", [])) != 31:
        raise ValueError("A complete, verified October source preparation is required.")
    active_code = code_hashes()
    changed = reviewed_code_delta(previous["code_sha256"], active_code)
    script = artifact(Path(__file__))
    config_path = ROOT / previous["config"]["path"]
    config = json.loads(config_path.read_text())
    retained = [previous["config"], previous["acquisition"], *previous["archives"]]
    for day in previous["days"]:
        retained.extend(day["outputs"].values())
        daily_path = ROOT / "data/processed/october" / (day["date"] + ".source.json")
        daily = json.loads(daily_path.read_text())
        if ({key: value for key, value in daily.items() if key != "cache_verified"}
                != {key: value for key, value in day.items() if key != "cache_verified"}):
            raise ValueError("Daily metadata differs from the original normalization manifest.")
        retained.append(artifact(daily_path))
        if day["fingerprint"]["code_sha256"] != previous["code_sha256"]:
            raise ValueError("Original daily normalization provenance is inconsistent.")
    verified = verify_artifacts(retained)
    verify_artifacts([previous["labels"], previous["report"], *previous["daily_labels"].values()])
    expectations = {day: expected_label_digest(read_labels(ROOT / item["path"]), copy_input=False)
                    for day, item in previous["daily_labels"].items()}
    merged_expectation = expected_label_digest(read_labels(ROOT / previous["labels"]["path"]), copy_input=False)
    origin_manifest = preserve(manifest_path, ROOT / "data/manifests/october-normalization-origin.json")
    report_path = ROOT / previous["report"]["path"]
    origin_report = preserve(report_path, ROOT / "data/reports/october-source-normalization-origin.json")
    report = json.loads(report_path.read_text())
    write_json(manifest_path, dict(previous, stage="RELABELING", full_month_processed=False,
                                  label_generation_pending={"previous_manifest": origin_manifest,
                                      "rebuild_script": script, "approved_changed_paths": changed}))
    print(json.dumps({"stage": "REBUILDING_LABELS_ONLY", "retained_artifacts_verified": len(verified),
                      "approved_changed_paths": changed}), flush=True)
    labels, daily_labels, quality = combine_labels(previous["days"], previous["archives"], config,
                                                  ROOT / "data/processed/october")
    if set(daily_labels) != set(expectations):
        raise ValueError("Label rebuild changed the daily label coverage.")
    for day, item in daily_labels.items():
        if label_digest(read_labels(ROOT / item["path"])) != expectations[day]:
            raise ValueError("Label rebuild changed more than the approved prefix flag: " + day)
    if label_digest(read_labels(ROOT / labels["path"])) != merged_expectation:
        raise ValueError("Merged label rebuild changed more than the approved prefix flag.")
    old_quality = report["label_quality"]
    changed_counts = {key for key in set(old_quality) | set(quality) if old_quality.get(key, 0) != quality.get(key, 0)}
    if not changed_counts.issubset(APPROVED_QUALITY_COUNTS):
        raise ValueError("Unexpected label-quality changes beyond the approved namespace fix.")
    if code_hashes() != active_code or artifact(Path(__file__)) != script:
        raise ValueError("Label producer code changed during the rebuild.")
    verify_artifacts(retained)
    elapsed = round(time.monotonic() - started, 2)
    lineage = {"previous_manifest": origin_manifest, "previous_report": origin_report,
               "rebuild_script": script, "generated_at": now(), "approved_changed_paths": changed,
               "retained_artifacts_verified": len(verified), "daily_normalization_metadata_unchanged": True,
               "normalization_rerun": False, "elapsed_seconds": elapsed,
               "policy_change": "ACTUAL_RAW_PREFIX_OR_REVIEWED_W_FROM_N_FX_FROM_F_7X_FROM_7",
               "all_daily_labels_match_only_approved_flag_change": True,
               "merged_labels_match_only_approved_flag_change": True,
               "previous_label_artifacts": {"merged": previous["labels"], "daily": previous["daily_labels"]},
               "quality_changes": {key: {"before": old_quality.get(key, 0), "after": quality.get(key, 0)}
                                   for key in sorted(changed_counts)}}
    report["label_quality"] = quality
    report["label_generation"] = lineage
    write_json(report_path, report)
    revised = dict(previous, generated_at=now(), code_sha256=active_code,
                   normalization_producer_code_sha256=previous["code_sha256"],
                   label_producer_code_sha256=active_code, label_generation=lineage,
                   labels=labels, daily_labels=daily_labels, report=artifact(report_path))
    write_json(manifest_path, revised)
    verification = {"stage": "VERIFIED", "verified_at": now(), "source_manifest_sha256": sha256(manifest_path),
                    "archive_count": len(previous["archives"]), "prepared_dates": len(previous["dates"]),
                    "retained_artifact_count": len(verified), "normalization_artifacts_unchanged": True,
                    "daily_label_parity": "ONLY_APPROVED_RAW_PREFIX_FLAG_AND_DERIVED_USABILITY_CHANGED",
                    "label_rebuild_elapsed_seconds": elapsed, "label_generation": lineage}
    write_json(ROOT / "data/reports/october-source-verification.json", verification)
    print(json.dumps({"stage": "PREPARED", "normalization_rerun": False, "elapsed_seconds": elapsed,
                      "label_quality": quality, "quality_changes": lineage["quality_changes"]}), flush=True)
    return revised


if __name__ == "__main__":
    rebuild()
