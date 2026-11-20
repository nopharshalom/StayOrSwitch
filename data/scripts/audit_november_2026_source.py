#!/usr/bin/env python3
"""Independently check November source provenance and sampled raw-field parity."""

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.october.sources import dates_between, iter_raw_snapshots, read_labels, read_snapshots, sha256, stamp, write_json
from stayorswitch.mta import parse_train_feed


MANIFEST = ROOT / "data/manifests/november-2026.json"
INPUT_MANIFEST = ROOT / "data/manifests/november-2026-inputs.json"
ANALYSIS_WINDOW = ROOT / "data/manifests/november-analysis-window.json"
DESTINATION = ROOT / "data/manifests/november-2026-source-audit.json"
SAMPLED_DATES = ("2026-11-01", "2026-11-10", "2026-11-19")
ZONE = ZoneInfo("America/New_York")


class Checks:
    def __init__(self):
        self.counts = Counter()

    def require(self, condition, category, explanation):
        self.counts[category] += 1
        if not condition:
            raise ValueError(category + ": " + explanation)

    def artifact(self, item, category):
        path = Path(item["path"])
        if not path.is_absolute():
            path = ROOT / path
        self.require(path.is_file(), category, "Missing artifact: " + str(path))
        self.require(path.stat().st_size == item["bytes"], category, "Size mismatch: " + str(path))
        self.require(sha256(path) == item["sha256"], category, "Hash mismatch: " + str(path))
        return path


def path_coverage(config, checks):
    pairs = {(leg["feed_id"], route_id, leg["from_stop_id"], leg["to_stop_id"])
             for route in config["routes"] for leg in route["legs"]
             for route_id in leg.get("route_ids", [leg["route_id"]])}
    route_count, corridor_ids, path_pairs = 0, [], set()
    for name in ("google-corridors.json", "incremental-extra-corridors.json"):
        document = json.loads((ROOT / "data/config" / name).read_text())
        for corridor in document["corridors"]:
            corridor_ids.append(corridor["id"])
            route_count += len(corridor["routes"])
            for route in corridor["routes"]:
                for leg in route["legs"]:
                    checks.require(leg["feed_id"] in config["feed_ids"], "path_scope", "Missing feed")
                    for stop_id in (leg["from_stop_id"], leg["to_stop_id"]):
                        checks.require(stop_id in config["stop_ids"], "path_scope", "Missing endpoint")
                    for route_id in leg.get("route_ids", [leg["route_id"]]):
                        pair = (leg["feed_id"], route_id, leg["from_stop_id"], leg["to_stop_id"])
                        path_pairs.add(pair)
                        checks.require(pair in pairs, "path_scope", "Missing full leg span")
    checks.require(len(corridor_ids) == len(set(corridor_ids)) == 5, "path_scope", "Five distinct corridors required")
    return {"corridor_ids": corridor_ids, "usable_path_count": route_count,
            "unique_feed_route_endpoint_pairs": len(path_pairs), "configured_endpoint_count": len(config["stop_ids"])}


def receipt_audit(report, config, checks):
    receipts = read_labels(ROOT / report["outputs"]["receipts"]["path"])
    checks.require(set(receipts) == set(config["feed_ids"]), "receipt_scope", "Receipt feed coverage")
    total, fold_counts = 0, {}
    for feed, records in receipts.items():
        prior, folds = None, Counter()
        for row in records:
            captured = row["captured_at"]
            local = datetime.fromtimestamp(captured, ZONE)
            checks.require(local.date().isoformat() == report["date"], "receipt_local_day", "Capture outside local archive day")
            checks.require(prior is None or captured > prior, "receipt_order", "Non-increasing unique capture")
            if row["status"] == "AVAILABLE":
                checks.require(row["source_updated_at"] is not None and row["source_updated_at"] <= captured,
                               "receipt_source_time", "Available receipt has future or missing source")
            if report["date"] == "2026-11-01" and local.hour == 1:
                folds[str(local.fold)] += 1
            prior = captured
            total += 1
        bounds = report["raw_train_capture_bounds"][feed]
        checks.require(bool(records), "receipt_bounds", "No feed receipts")
        checks.require(len(records) == bounds["captures"], "receipt_bounds", "Receipt count mismatch")
        checks.require(records[0]["captured_at"] == bounds["first_captured_at"], "receipt_bounds", "First receipt mismatch")
        checks.require(records[-1]["captured_at"] == bounds["last_captured_at"], "receipt_bounds", "Last receipt mismatch")
        if report["date"] == "2026-11-01":
            checks.require(folds["0"] > 0 and folds["1"] > 0, "dst_folds", "Both repeated 01:00 hours required")
            fold_counts[feed] = dict(folds)
    return {"date": report["date"], "receipt_count": total, "repeated_hour_receipts": fold_counts}


def sample_snapshots(report, checks):
    selected, first_feeds, folds = {}, set(), set()
    for snapshot in read_snapshots(ROOT / report["outputs"]["snapshots"]["path"]):
        if snapshot.get("status") != "AVAILABLE":
            continue
        feed, captured = snapshot["feed_id"], snapshot["captured_at"]
        keep = feed not in first_feeds
        if keep:
            first_feeds.add(feed)
        local = datetime.fromtimestamp(captured, ZONE)
        if report["date"] == "2026-11-01" and feed != "subway-alerts" and local.hour == 1 and local.minute >= 30:
            key = (feed, local.fold)
            if key not in folds:
                folds.add(key)
                keep = True
        if keep:
            selected[(feed, captured)] = snapshot
    checks.require(len(first_feeds) == 6, "raw_sample_coverage", "Five train feeds and alert feed required")
    if report["date"] == "2026-11-01":
        checks.require(len(folds) == 10, "raw_sample_coverage", "Both 01:30 hours across all five feeds required")
    return selected


def expected_stops(trip, config):
    original = trip["stop_updates"]
    pairs = [(leg["from_stop_id"], leg["to_stop_id"])
             for route in config["routes"] for leg in route["legs"]
             if leg["feed_id"] == trip["feed_id"]
             and trip["route_id"] in leg.get("route_ids", [leg["route_id"]])]
    if not pairs:
        return original
    positions, keep = {}, set()
    for index, stop in enumerate(original):
        positions.setdefault(stop["stop_id"], []).append(index)
        if (stop["stop_id"] in config["stop_ids"] or (stop.get("scheduled_track") and
                stop.get("actual_track") and stop["scheduled_track"] != stop["actual_track"])):
            keep.add(index)
    for origin, destination in pairs:
        if origin in positions and destination in positions:
            endpoints = positions[origin] + positions[destination]
            keep.update(range(min(endpoints), max(endpoints) + 1))
    return [stop for index, stop in enumerate(original) if index in keep]


def raw_parity(report, archive, config, checks):
    selected = sample_snapshots(report, checks)
    found, trip_count, stop_count = set(), 0, 0
    samples = []
    for raw in iter_raw_snapshots(archive["path"], config["feed_ids"], 1):
        key = (raw["feed_id"], raw["captured_at"])
        if key not in selected:
            continue
        stored = selected[key]
        original = parse_train_feed(raw["payload"], raw["feed_id"], stamp(raw["captured_at"]))
        if raw["feed_id"] == "subway-alerts":
            original["kind"] = "alerts"
        original["trips"] = [trip for trip in original["trips"] if trip["route_id"] in config["route_ids"]]
        identities = {trip["id"] for trip in original["trips"] if trip.get("id")}
        original["vehicles"] = [vehicle for vehicle in original["vehicles"] if vehicle.get("trip_identity") in identities]
        for name, value in original.items():
            if name == "trips":
                continue
            checks.require(stored.get(name) == value, "raw_metadata_parity", name + " changed")
        checks.require(stored["archive_provenance"]["sha256"] == raw["sha256"], "raw_metadata_parity", "Raw hash changed")
        checks.require(stored["archive_provenance"]["archive_member"] == raw["archive_member"], "raw_metadata_parity", "Member changed")
        checks.require(len(original["trips"]) == len(stored["trips"]), "raw_trip_parity", "Trip coverage changed")
        for full, projected in zip(original["trips"], stored["trips"]):
            before = {name: value for name, value in full.items() if name != "stop_updates"}
            after = {name: value for name, value in projected.items() if name != "stop_updates"}
            checks.require(before == after, "raw_trip_parity", "Trip metadata or order changed")
            required = expected_stops(full, config)
            checks.require(projected["stop_updates"] == required, "raw_stop_parity", "Original stop values or complete span changed")
            trip_count += 1
            stop_count += len(required)
        found.add(key)
        samples.append({"feed_id": key[0], "captured_at": key[1],
                        "local_time": datetime.fromtimestamp(key[1], ZONE).isoformat(),
                        "raw_sha256": raw["sha256"], "trip_count": len(original["trips"])})
    checks.require(found == set(selected), "raw_sample_coverage", "Prepared sample missing from raw archive")
    return {"date": report["date"], "sampled_captures": len(found),
            "compared_trip_observations": trip_count, "compared_stop_updates": stop_count,
            "samples": samples}


def main():
    checks = Checks()
    stable_paths = (MANIFEST, INPUT_MANIFEST, ANALYSIS_WINDOW, Path(__file__).resolve())
    stable_hashes = {path: sha256(path) for path in stable_paths}
    manifest = json.loads(MANIFEST.read_text())
    checks.require(manifest["stage"] == "PREPARED", "manifest_scope", "Final preparation required")
    dates = list(dates_between("2026-11-01", "2026-11-19"))
    checks.require(manifest["dates"] == dates, "manifest_scope", "Expected exactly November 1–19")
    checks.require(manifest["input_carry_dates"] == ["2026-10-31"], "manifest_scope", "Unexpected input carry")
    checks.require(sorted(row["date"] for row in manifest["days"]) == ["2026-10-31", *dates],
                   "manifest_scope", "Daily inputs missing or duplicated")
    window = json.loads(ANALYSIS_WINDOW.read_text())
    analysis_dates = list(dates_between("2026-11-01", "2026-11-18"))
    checks.require(window["prepared_source_dates"] == dates, "analysis_scope", "Prepared source range differs")
    checks.require(window["analysis_dates"] == analysis_dates, "analysis_scope", "Formal exposure must end November 18")
    checks.require(window["input_carry_dates"] == ["2026-10-31"], "analysis_scope", "Input carry differs")
    checks.require(window["outcome_boundary_dates"] == ["2026-11-19"], "analysis_scope", "November 19 is outcome boundary only")
    checks.require(window["source_config"]["sha256"] == manifest["config"]["sha256"], "analysis_scope", "Window source config differs")
    checks.require(window["source_manifest_path"] == str(MANIFEST.relative_to(ROOT)), "analysis_scope", "Window points to another manifest")
    input_manifest = json.loads(INPUT_MANIFEST.read_text())
    checks.require(input_manifest["stage"] == "INPUTS_PREPARED", "input_freeze", "Stable input-only manifest required")
    checks.require(not {"labels", "daily_labels"} & set(input_manifest), "input_freeze", "Outcome metadata leaked into input manifest")
    for name in ("config", "code_sha256", "acquisition", "archives", "dates", "input_carry_dates", "days"):
        checks.require(input_manifest[name] == manifest[name], "input_freeze", "Inputs changed before label construction: " + name)
    config_path = checks.artifact(manifest["config"], "configuration_hash")
    config = json.loads(config_path.read_text())
    checks.require(config["timezone"] == "America/New_York", "manifest_scope", "Unexpected calendar timezone")
    coverage = path_coverage(config, checks)
    checks.artifact(manifest["acquisition"], "acquisition_hash")
    checks.artifact(manifest["report"], "report_hash")
    for name, digest in manifest["code_sha256"].items():
        checks.require(sha256(ROOT / name) == digest, "producer_hash", "Producer changed: " + name)
    for item in manifest["archives"]:
        checks.artifact(item, "raw_archive_hash")
    receipts, sampled, source_metadata = [], [], []
    indexed = {(item["archive_date"], item["kind"]): item for item in manifest["archives"]}
    for report in manifest["days"]:
        metadata_path = (ROOT / report["outputs"]["snapshots"]["path"]).parent / (report["date"] + ".source.json")
        metadata = json.loads(metadata_path.read_text())
        for name in ("date", "stage", "fingerprint", "outputs", "counts", "by_feed", "raw_counts",
                     "raw_train_capture_bounds", "trip_count", "ordering"):
            checks.require(metadata[name] == report[name], "source_metadata_parity", "Daily source metadata differs: " + name)
        source_metadata.append({"date": report["date"], "path": str(metadata_path.relative_to(ROOT)),
                                "sha256": sha256(metadata_path)})
        checks.require(report["fingerprint"]["config_sha256"] == manifest["config"]["sha256"],
                       "source_fingerprint", "Daily config differs")
        checks.require(report["fingerprint"]["code_sha256"] == manifest["code_sha256"],
                       "source_fingerprint", "Daily producer differs")
        checks.require(report["fingerprint"]["archive_sha256"] == indexed[(report["date"], "gtfsrt")]["sha256"],
                       "source_fingerprint", "Daily raw archive differs")
        for item in report["outputs"].values():
            checks.artifact(item, "normalized_artifact_hash")
        receipts.append(receipt_audit(report, config, checks))
        if report["date"] in SAMPLED_DATES:
            sampled.append(raw_parity(report, indexed[(report["date"], "gtfsrt")], config, checks))
        print(json.dumps({"stage": "AUDITED_DAY", "date": report["date"], "checks": sum(checks.counts.values())}), flush=True)
    checks.require(set(manifest["daily_labels"]) == {"2026-10-31", *dates}, "label_scope", "Daily label scope differs")
    checks.artifact(manifest["labels"], "label_artifact_hash")
    for item in manifest["daily_labels"].values():
        checks.artifact(item, "label_artifact_hash")
    old_profile = ROOT / "data/artifacts/october-2026-profiles-train.json.gz"
    checks.require(sha256(old_profile) == "ee9620bdba17412c2b55aaa919a781a855f84e37e4efc8f3016b2fe9212ff31c",
                   "old_profile_preserved", "Original training artifact changed")
    publisher = ROOT / "data/manifests/november-2026-publisher-status.json"
    for path, digest in stable_hashes.items():
        checks.require(sha256(path) == digest, "audit_stability", "Audit input changed during execution: " + str(path))
    for name, digest in manifest["code_sha256"].items():
        checks.require(sha256(ROOT / name) == digest, "audit_stability", "Source producer changed during audit: " + name)
    result = {"schema_version": "november-2026-source-independent-audit-v1", "status": "PASS",
        "source_manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": sha256(MANIFEST)},
        "auditor": {"path": str(Path(__file__).resolve().relative_to(ROOT)), "sha256": sha256(__file__)},
        "checks": sum(checks.counts.values()), "checks_by_category": dict(checks.counts),
        "prepared_source_dates": dates, "analysis_dates": analysis_dates,
        "input_carry_dates": manifest["input_carry_dates"], "outcome_boundary_dates": window["outcome_boundary_dates"],
        "analysis_window": {"path": str(ANALYSIS_WINDOW.relative_to(ROOT)), "sha256": sha256(ANALYSIS_WINDOW)},
        "input_manifest": {"path": str(INPUT_MANIFEST.relative_to(ROOT)), "sha256": sha256(INPUT_MANIFEST)},
        "projection_scope": coverage, "raw_archive_count": len(manifest["archives"]),
        "normalized_days_verified": len(manifest["days"]), "daily_label_files_verified": len(manifest["daily_labels"]),
        "source_metadata": source_metadata, "receipt_checks": receipts, "raw_parity_samples": sampled,
        "following_boundary": manifest["following_boundary"],
        "publisher_status": {"path": str(publisher.relative_to(ROOT)), "sha256": sha256(publisher)},
        "original_training_profile_unchanged": True, "outcome_performance_read_or_computed": False,
        "limitations": ["Raw field comparisons sample three days; artifact hashes and receipt bounds cover every prepared day.",
            "Outcome files were hash-verified without reading endpoint outcome timestamps or computing performance.",
            "This establishes archive provenance and transformations, not independently observed passenger arrival truth."]}
    write_json(DESTINATION, result)
    print(json.dumps({"status": "PASS", "checks": result["checks"], "path": str(DESTINATION.relative_to(ROOT))}), flush=True)


if __name__ == "__main__":
    main()
