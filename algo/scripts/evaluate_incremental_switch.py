#!/usr/bin/env python3
"""Freeze and score a denser, separate Google-corridor checkpoint supplement."""

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
from itertools import chain
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo"), str(ROOT / "algo/scripts")]

from data.delay_profiles import IncidentIndex, ProfileEstimator
from data.october import read_labels, read_snapshots
from stayorswitch.google_corridor_replay import apply_review, representatives, select_encounter
from stayorswitch.incremental_switch_replay import POLICY, approved_scopes, dense_plans, policy_comparison, qualify, summary
from stayorswitch.october_evaluation import latest_at_cutoffs, project_snapshot
from stayorswitch.preincident_replay import local_time, score_modes
from stayorswitch.severe import MODES
from evaluate_google_corridors import CONFIG, _merge_labels, _verify_source, predict, provenance as google_provenance
from evaluate_preincident import artifact, dump, load, sha

LOCAL = ROOT / "algo/local/incremental-switch"
REPORTS = ROOT / "algo/reports"
BASE_FREEZE = REPORTS / "google-corridors-selection-frozen.json"
FREEZE = REPORTS / "incremental-switch-selection-frozen.json"
PREPARED = LOCAL / "prepared-inputs.json.gz"


def provenance():
    return {"base_google_freeze": artifact(BASE_FREEZE), "google_implementation": google_provenance(load(CONFIG)),
        "policy": POLICY, "new_producer_hashes": {name: sha(ROOT / name) for name in
            ("algo/scripts/evaluate_incremental_switch.py", "algo/stayorswitch/incremental_switch_replay.py")}}


def prepare():
    if FREEZE.exists() or PREPARED.exists():
        raise ValueError("Preserve existing prepared/frozen supplement instead of overwriting it.")
    started = time.monotonic()
    initial = provenance()
    frozen = load(BASE_FREEZE)
    for key in ("prepared_inputs", "text_review"):
        item = frozen[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Original frozen input changed.")
    base = load(ROOT / frozen["prepared_inputs"]["path"])
    review = load(ROOT / frozen["text_review"]["path"])
    original_cases, _ = apply_review(base["cases"], review)
    allowed = {(c["corridor_id"], c["incident_ids"][0]) for c in original_cases}
    plans = dense_plans(base["plans"], allowed)
    approved = approved_scopes(review)
    config = load(CONFIG)
    corridors = config["corridors"]
    by_date = defaultdict(set)
    for values in plans.values():
        for plan in values:
            for cutoff in plan["decision_times"]:
                by_date[local_time(cutoff)[:10]].add(cutoff)
    sources = dict(base["input_sources"])
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError("Original input source changed: " + name)
    source = load(ROOT / "data/manifests/october.json")
    days = {r["date"]: r for r in source["days"]}
    supplements = [(spec, {r["date"]: r for r in load(ROOT / spec["manifest"])["days"]})
                   for spec in config["supplemental_sources"]]
    replacement = {feed: i for i, (spec, _) in enumerate(supplements) for feed in spec["replace_feeds"]}
    def alerts():
        for day in sorted(days):
            item = days[day]["outputs"]["alerts"]
            _verify_source(item, sources)
            yield from read_snapshots(ROOT / item["path"])
    index = IncidentIndex(alerts(), max_age_seconds=POLICY["alerts_max_age_seconds"])
    print({"stage": "INPUT_GRID", "corridor_incidents": len(allowed), "unique_cutoffs": sum(map(len, by_date.values())),
           "planned_corridor_checkpoints": sum(len(p["decision_times"]) for v in plans.values() for p in v)}, flush=True)
    all_routes = list(chain.from_iterable(c["routes"] for c in corridors))
    captured, carry = {}, {}
    day = date.fromisoformat(POLICY["test_dates"][0]) - timedelta(days=1)
    while day <= date.fromisoformat(POLICY["test_dates"][1]):
        key = day.isoformat()
        item = days[key]["outputs"]["snapshots"]
        _verify_source(item, sources)
        streams = [(s for s in read_snapshots(ROOT / item["path"]) if s["feed_id"] not in replacement)]
        for i, (_, extra_days) in enumerate(supplements):
            feeds = {f for f, owner in replacement.items() if owner == i}
            if feeds:
                item = extra_days[key]["outputs"]["snapshots"]
                _verify_source(item, sources)
                def filtered(filename, allowed_feeds):
                    return (s for s in read_snapshots(filename) if s["feed_id"] in allowed_feeds)
                streams.append(filtered(ROOT / item["path"], feeds))
        selected, carry = latest_at_cutoffs((project_snapshot(s, all_routes) for s in chain(*streams)),
                                            sorted(by_date.get(key, [])), carry)
        captured.update(selected)
        print({"stage": "INPUT_DAY", "date": key, "seconds": round(time.monotonic()-started, 1)}, flush=True)
        day += timedelta(days=1)
    estimator = ProfileEstimator(ROOT / "data/artifacts/october-2026-profiles-train.json.gz")
    cases, rejected = [], []
    for corridor in corridors:
        cache = {}
        for plan in plans[corridor["id"]]:
            for cutoff in plan["decision_times"]:
                if cutoff not in cache:
                    cache[cutoff] = predict(captured[cutoff], corridor, cutoff, index)
                case, reason = select_encounter(plan, corridor, cache[cutoff], index, POLICY)
                if case is not None:
                    qualified = qualify(case, approved)
                    reason = "UNREVIEWED_EXACT_SCOPE" if qualified is None else None
                    case = qualified
                if case is None:
                    rejected.append({"corridor_id": corridor["id"], "incident_id": plan["incident_id"],
                                     "decision_at": cutoff, "reason": reason})
                    continue
                case["predictions"] = {mode: cache[cutoff] if mode == "mta" else
                    predict(captured[cutoff], corridor, cutoff, index, estimator, mode) for mode in MODES}
                cases.append(case)
        print({"stage": "INPUT_PREDICTIONS", "corridor": corridor["id"], "selected_so_far": len(cases),
               "seconds": round(time.monotonic()-started, 1)}, flush=True)
    baseline = {c["id"]: c for c in original_cases}
    lookup = {c["id"]: c for c in cases}
    if not set(baseline).issubset(lookup):
        raise ValueError("Dense supplement failed to retain every original confirmed checkpoint.")
    for key, previous in baseline.items():
        if previous["predictions"] != lookup[key]["predictions"]:
            raise ValueError("Original checkpoint prediction changed: " + key)
    if provenance() != initial:
        raise ValueError("Producer or configuration changed during preparation.")
    selected_snapshots = LOCAL / "selected-input-snapshots.json.gz"
    dump(selected_snapshots, [{"cutoff": t, "snapshots": captured[t]} for t in sorted({c["decision_at"] for c in cases})])
    value = {"provenance": initial, "config": config, "plans": plans, "input_sources": sources,
        "original_confirmed_case_ids": sorted(baseline), "cases": cases, "rejected_checkpoints": rejected,
        "selected_input_snapshots": artifact(selected_snapshots), "selection_reads_outcome_labels": False}
    dump(PREPARED, value)
    freeze = {"schema_version": "incremental-switch-freeze-v1", "provenance": initial,
        "prepared_inputs": artifact(PREPARED), "selected_input_snapshots": artifact(selected_snapshots),
        "selection_reads_outcome_labels": False, "confirmed_case_ids": [c["id"] for c in cases],
        "primary_case_ids": [c["id"] for c in representatives(cases)],
        "original_confirmed_case_ids": sorted(baseline),
        "selection_counts": {"planned": sum(len(p["decision_times"]) for v in plans.values() for p in v),
            "confirmed": len(cases), "rejected": dict(Counter(r["reason"] for r in rejected))}}
    dump(FREEZE, freeze)
    print({"stage": "FROZEN_WITHOUT_LABELS", "cases": len(cases), "baseline_parity": len(baseline),
           "seconds": round(time.monotonic()-started, 1)}, flush=True)


def verify():
    frozen = load(FREEZE)
    if provenance() != frozen["provenance"]:
        raise ValueError("Frozen code, policy or base inputs changed.")
    for key in ("prepared_inputs", "selected_input_snapshots"):
        item = frozen[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen input artifact changed.")
    prepared = load(ROOT / frozen["prepared_inputs"]["path"])
    for name, expected in prepared["input_sources"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Frozen input source changed: " + name)
    if [c["id"] for c in prepared["cases"]] != frozen["confirmed_case_ids"]:
        raise ValueError("Frozen cases changed.")
    return frozen, prepared


def score():
    frozen, prepared = verify()
    original = load(ROOT / "data/manifests/october.json")
    labels, label_sources = {}, {}
    for day in sorted({local_time(c["decision_at"])[:10] for c in prepared["cases"]}):
        for service_day in ((date.fromisoformat(day) - timedelta(days=1)).isoformat(), day):
            item = original["daily_labels"][service_day]
            if item["path"] not in label_sources:
                _verify_source(item, label_sources)
                _merge_labels(labels, read_labels(ROOT / item["path"]))
    for spec in prepared["config"]["extra_label_sources"]:
        manifest = load(ROOT / spec["manifest"])
        item = manifest[spec.get("key", "labels")]
        _verify_source(item, label_sources)
        _merge_labels(labels, read_labels(ROOT / item["path"]))
    evaluated = []
    for case in prepared["cases"]:
        value = score_modes(case, case["predictions"], labels, POLICY)
        value["policy_comparison"] = policy_comparison(value)
        evaluated.append(value)
    scored = LOCAL / "scored-cases.json.gz"
    dump(scored, evaluated)
    primary_ids = set(frozen["primary_case_ids"])
    old_ids = set(frozen["original_confirmed_case_ids"])
    compact = []
    for case in evaluated:
        modes = {}
        for mode in MODES:
            value = case["modes"][mode]
            selected = {case["reference_route_id"], value["strict_decision"]["recommended_itinerary_id"]}
            modes[mode] = {"strict_decision": value["strict_decision"], "scores": value["scores"]["strict_decision"],
                "selected_routes": [{"id": r["id"], "name": r["name"], "predicted_duration_seconds": r.get("total_duration_seconds"),
                    "selected_train_ids": [leg["trip_id"] for leg in r.get("selected_legs", [])],
                    "outcome": value["outcomes"][r["id"]]} for r in value["routes"] if r["id"] in selected]}
        compact.append({k: case[k] for k in ("id", "corridor_id", "incident_ids", "local_time", "decision_at",
            "reference_route_id", "official_text_review", "exposure", "policy_comparison")} | {
                "primary": case["id"] in primary_ids, "original_checkpoint": case["id"] in old_ids, "modes": modes})
    report = {"schema_version": "incremental-switch-results-v1", "policy": POLICY, "selection_freeze": artifact(FREEZE),
        "scored_artifact": artifact(scored), "label_sources": label_sources,
        "corridors": prepared["config"]["corridors"], "all_summary": summary(evaluated),
        "primary_summary": summary([c for c in evaluated if c["id"] in primary_ids]),
        "original_checkpoint_summary": summary([c for c in evaluated if c["id"] in old_ids]),
        "per_corridor_summary": {c["id"]: summary([r for r in evaluated if r["corridor_id"] == c["id"]])
            for c in prepared["config"]["corridors"]}, "cases": compact}
    dump(REPORTS / "incremental-switch-test.json", report)
    print({"stage": "SCORED", "all_summary": report["all_summary"], "original_summary": report["original_checkpoint_summary"]}, flush=True)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prepare-inputs", action="store_true")
    group.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_inputs:
        prepare()
    elif args.verify_only:
        frozen, _ = verify()
        print({"stage": "VERIFIED", "cases": len(frozen["confirmed_case_ids"])}, flush=True)
    else:
        score()


if __name__ == "__main__":
    main()
