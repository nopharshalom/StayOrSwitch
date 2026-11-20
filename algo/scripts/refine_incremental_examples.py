#!/usr/bin/env python3
"""Expand authorized illustrative departure times without changing cohort metrics."""

import argparse
import json
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, timedelta
from itertools import chain
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo"), str(ROOT / "algo/scripts")]

from data.delay_profiles import IncidentIndex, ProfileEstimator
from data.october import read_labels, read_snapshots
from stayorswitch.google_corridor_replay import POLICY as BASE_POLICY, select_encounter
from stayorswitch.incremental_switch_replay import approved_scopes, policy_comparison, qualify, summary
from stayorswitch.october_evaluation import latest_at_cutoffs, project_snapshot
from stayorswitch.preincident_replay import local_time, score_modes
from stayorswitch.severe import MODES
from evaluate_google_corridors import _merge_labels, _verify_source, predict
from evaluate_incremental_switch import provenance as original_grid_provenance
from evaluate_extra_corridor_switch import provenance as extra_provenance
from evaluate_preincident import artifact, dump, load, sha

LOCAL = ROOT / "algo/local/incremental-example-refinement"
REPORTS = ROOT / "algo/reports"
PREPARED = LOCAL / "prepared-inputs.json.gz"
FREEZE = REPORTS / "incremental-example-refinement-selection-frozen.json"
FAMILIES = {("grandcentral_boroughhall", "lmm:alert:274016"),
            ("grandcentral_boroughhall", "lmm:alert:274022"),
            ("portauthority_tandon", "lmm:alert:273900")}
POLICY = dict(BASE_POLICY, schema_version="posthoc-incremental-example-refinement-v1",
    decision_lags_seconds=list(range(0, 7201, 30)),
    family_selection_uses_previous_outcomes=True,
    selection_uses_outcomes_or_recommendations=True,
    new_checkpoint_selection_uses_outcomes=False,
    grid_revision_before_freeze_and_new_labels="FIXED_30_SECONDS_TO_COVER_SHORT_BOARDING_WINDOWS; NO_ADAPTIVE_POST_SCORE_REFINEMENT",
    original_overall_metrics_unchanged=True,
    repeated_selected_train_pairs_are_allowed_examples=True,
    repeated_examples_are_independent_evidence=False,
    purpose="POST_HOC_DEPARTURE_TIME_ILLUSTRATIONS_ONLY; NEVER_POOL_WITH_OVERALL_1132_CHECKPOINT_OR_94_EVENT_RESULTS",
    walking_policy="UNCHANGED_BASELINE; PORT_AUTHORITY_A_C_ACCESS_120_SECONDS",
    walking_sensitivity_selection="NO_NEW_VARIANTS_IN_THIS_ILLUSTRATIVE_REFINEMENT")


def provenance():
    return {"policy": POLICY, "producer": artifact(Path(__file__)),
        "original_grid": original_grid_provenance(), "extra_grid": extra_provenance(),
        "base_freezes": [artifact(REPORTS / name) for name in
            ("incremental-switch-selection-frozen.json", "extra-corridor-switch-selection-frozen.json")],
        "unchanged_base_results": [artifact(REPORTS / name) for name in
            ("incremental-switch-test.json", "extra-corridor-switch-test.json")]}


def selected_plans(bases):
    result = []
    for base in bases:
        for cid, plans in base["plans"].items():
            for plan in plans:
                if (cid, plan["incident_id"]) not in FAMILIES:
                    continue
                value = deepcopy(plan)
                times = set(plan["decision_times"])
                times.update(plan["first_problem_receipt"] + lag for lag in POLICY["decision_lags_seconds"])
                value["decision_times"] = sorted(t for t in times if
                    POLICY["test_dates"][0] <= local_time(t)[:10] <= POLICY["test_dates"][1])
                result.append(value)
    if {(r["corridor_id"], r["incident_id"]) for r in result} != FAMILIES or len(result) != len(FAMILIES):
        raise ValueError("Exactly the three explicitly authorized illustrative families are required.")
    return result


def prepare():
    if FREEZE.exists() or PREPARED.exists():
        raise ValueError("Do not overwrite an existing illustrative refinement.")
    started = time.monotonic()
    initial = provenance()
    frozen = [load(ROOT / item["path"]) for item in initial["base_freezes"]]
    if frozen[0]["provenance"] != initial["original_grid"] or frozen[1]["provenance"] != initial["extra_grid"]:
        raise ValueError("Previously frozen producer/configuration changed.")
    bases = []
    for item in frozen:
        source = item["prepared_inputs"]
        if sha(ROOT / source["path"]) != source["sha256"]:
            raise ValueError("Previously frozen prepared inputs changed.")
        bases.append(load(ROOT / source["path"]))
    reviews = [load(REPORTS / "google-corridors-text-review.json"),
               load(REPORTS / "extra-corridor-switch-text-review.json")]
    approved = {}
    for review in reviews:
        approved.update(approved_scopes(review))
    plans = selected_plans(bases)
    corridors = {c["id"]: c for base in bases for c in base["config"]["corridors"]
                 if c["id"] in {key[0] for key in FAMILIES}}
    config = bases[1]["config"]
    sources = {name: value for base in bases for name, value in base["input_sources"].items()}
    sources.update({str(REPORTS.joinpath(name).relative_to(ROOT)): sha(REPORTS / name) for name in
                   ("google-corridors-text-review.json", "extra-corridor-switch-text-review.json")})
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError("Original source changed: " + name)
    original = load(ROOT / "data/manifests/october.json")
    days = {r["date"]: r for r in original["days"]}
    by_date = defaultdict(set)
    for plan in plans:
        for t in plan["decision_times"]:
            by_date[local_time(t)[:10]].add(t)
    def alerts():
        for day in sorted(days):
            item = days[day]["outputs"]["alerts"]
            _verify_source(item, sources)
            yield from read_snapshots(ROOT / item["path"])
    index = IncidentIndex(alerts(), max_age_seconds=POLICY["alerts_max_age_seconds"])
    print({"stage": "ILLUSTRATIVE_INPUT_GRID", "families": len(plans),
           "planned_checkpoints": sum(len(p["decision_times"]) for p in plans)}, flush=True)
    captured = {}
    # Preserve each parent study's complete projection, not merely the two
    # illustrated corridors. Projection affects segment/candidate diagnostics.
    for group_index, base in enumerate(bases):
        original_corridor_ids = {c["id"] for c in base["config"]["corridors"]}
        group_dates = defaultdict(set)
        for plan in plans:
            if plan["corridor_id"] in original_corridor_ids:
                for t in plan["decision_times"]:
                    group_dates[local_time(t)[:10]].add(t)
        supplements = [(spec, {r["date"]: r for r in load(ROOT / spec["manifest"])["days"]})
                       for spec in base["config"]["supplemental_sources"]]
        replacement = {feed: i for i, (spec, _) in enumerate(supplements) for feed in spec["replace_feeds"]}
        all_routes = list(chain.from_iterable(c["routes"] for c in base["config"]["corridors"]))
        carry = {}
        day = date.fromisoformat(min(group_dates)) - timedelta(days=1)
        while day <= date.fromisoformat(max(group_dates)):
            key = day.isoformat()
            item = days[key]["outputs"]["snapshots"]
            _verify_source(item, sources)
            streams = [(s for s in read_snapshots(ROOT / item["path"]) if s["feed_id"] not in replacement)]
            for i, (_, extra_days) in enumerate(supplements):
                feeds = {f for f, owner in replacement.items() if owner == i}
                if feeds:
                    item = extra_days[key]["outputs"]["snapshots"]
                    _verify_source(item, sources)
                    def filtered(filename, allowed):
                        return (s for s in read_snapshots(filename) if s["feed_id"] in allowed)
                    streams.append(filtered(ROOT / item["path"], feeds))
            selected, carry = latest_at_cutoffs((project_snapshot(s, all_routes) for s in chain(*streams)),
                                                sorted(group_dates.get(key, [])), carry)
            if set(selected).intersection(captured):
                raise ValueError("Parent-study cutoffs overlap; retain separate projection keys before extending scope.")
            captured.update(selected)
            print({"stage": "INPUT_DAY", "parent_group": group_index, "date": key,
                   "seconds": round(time.monotonic()-started, 1)}, flush=True)
            day += timedelta(days=1)
    estimator = ProfileEstimator(ROOT / "data/artifacts/october-2026-profiles-train.json.gz")
    cases, rejected = [], []
    for plan in plans:
        corridor = corridors[plan["corridor_id"]]
        for cutoff in plan["decision_times"]:
            raw = predict(captured[cutoff], corridor, cutoff, index)
            case, reason = select_encounter(plan, corridor, raw, index, POLICY)
            if case is not None:
                case = qualify(case, approved)
                if case is None:
                    reason = "UNREVIEWED_EXACT_SCOPE"
            if case is None:
                rejected.append({"corridor_id": corridor["id"], "incident_id": plan["incident_id"],
                                 "decision_at": cutoff, "reason": reason})
                continue
            case["predictions"] = {mode: raw if mode == "mta" else predict(captured[cutoff], corridor,
                cutoff, index, estimator, mode) for mode in MODES}
            case["asof_snapshot_receipts"] = [{k: s.get(k) for k in ("feed_id", "captured_at", "sha256")}
                                              for s in captured[cutoff]]
            cases.append(case)
    previous = {case["id"]: case for base, freeze in zip(bases, frozen) for case in base["cases"]
                if case["id"] in set(freeze["confirmed_case_ids"]) and
                (case["corridor_id"], case["incident_ids"][0]) in FAMILIES}
    lookup = {c["id"]: c for c in cases}
    if not set(previous).issubset(lookup):
        raise ValueError("A previously confirmed checkpoint in the chosen events was lost.")
    for key, old in previous.items():
        if old["predictions"] != lookup[key]["predictions"]:
            raise ValueError("Prior input predictions changed: " + key)
    if provenance() != initial:
        raise ValueError("Producer changed during input preparation.")
    snapshots = LOCAL / "selected-input-snapshots.json.gz"
    dump(snapshots, [{"cutoff": t, "snapshots": captured[t]} for t in sorted({c["decision_at"] for c in cases})])
    value = {"provenance": initial, "policy": POLICY, "corridors": corridors, "plans": plans,
        "input_sources": sources, "cases": cases, "rejected_checkpoints": rejected,
        "extra_label_sources": config["extra_label_sources"], "selected_input_snapshots": artifact(snapshots),
        "new_preparation_reads_outcome_labels": False, "previous_confirmed_case_ids": sorted(previous)}
    dump(PREPARED, value)
    dump(FREEZE, {"schema_version": "incremental-example-refinement-freeze-v1", "provenance": initial,
        "prepared_inputs": artifact(PREPARED), "selected_input_snapshots": artifact(snapshots),
        "confirmed_case_ids": [c["id"] for c in cases], "previous_confirmed_case_ids": sorted(previous),
        "selection_counts": {"planned": sum(len(p["decision_times"]) for p in plans), "confirmed": len(cases),
                             "rejected": dict(Counter(r["reason"] for r in rejected))},
        "new_preparation_reads_outcome_labels": False, "family_selection_uses_previous_outcomes": True,
        "not_for_overall_performance_estimation": True})
    print({"stage": "FROZEN_ILLUSTRATIONS_BEFORE_NEW_LABELS", "cases": len(cases),
           "previous_prediction_parity": len(previous), "seconds": round(time.monotonic()-started, 1)}, flush=True)


def verify():
    frozen = load(FREEZE)
    if provenance() != frozen["provenance"]:
        raise ValueError("Frozen refinement or original experiment changed.")
    for key in ("prepared_inputs", "selected_input_snapshots"):
        if sha(ROOT / frozen[key]["path"]) != frozen[key]["sha256"]:
            raise ValueError("Frozen illustrative input artifact changed.")
    prepared = load(ROOT / frozen["prepared_inputs"]["path"])
    for name, expected in prepared["input_sources"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Frozen source changed: " + name)
    return frozen, prepared


def score():
    frozen, prepared = verify()
    original = load(ROOT / "data/manifests/october.json")
    labels, label_sources = {}, {}
    for day in sorted({local_time(c["decision_at"])[:10] for c in prepared["cases"]}):
        for service_day in ((date.fromisoformat(day)-timedelta(days=1)).isoformat(), day):
            item = original["daily_labels"][service_day]
            if item["path"] not in label_sources:
                _verify_source(item, label_sources)
                _merge_labels(labels, read_labels(ROOT / item["path"]))
    for spec in prepared["extra_label_sources"]:
        item = load(ROOT / spec["manifest"])[spec.get("key", "labels")]
        _verify_source(item, label_sources)
        _merge_labels(labels, read_labels(ROOT / item["path"]))
    evaluated = []
    for case in prepared["cases"]:
        value = score_modes(case, case["predictions"], labels, POLICY)
        value["policy_comparison"] = policy_comparison(value)
        evaluated.append(value)
    output = LOCAL / "scored-cases.json.gz"
    dump(output, evaluated)
    rows = []
    for case in evaluated:
        value = case["policy_comparison"]
        if not value["mta_stay_model_switch"]:
            continue
        ids = {case["reference_route_id"], value["model_recommended_route_id"]}
        modes = {}
        for mode in MODES:
            source = case["modes"][mode]
            modes[mode] = {"strict_decision": source["strict_decision"], "routes": [
                {k: r.get(k) for k in ("id", "name", "total_duration_seconds", "selected_legs", "context")} |
                {"outcome": source["outcomes"][r["id"]]} for r in source["routes"] if r["id"] in ids]}
        signature = [case["corridor_id"]]
        selected_feeds = set()
        for mode, route_id in (("mta", value["raw_mta_recommended_route_id"]),
                               ("incident_profile", value["model_recommended_route_id"])):
            route = next(r for r in case["modes"][mode]["routes"] if r["id"] == route_id)
            signature.append(tuple(leg["trip_id"] for leg in route["selected_legs"]))
            selected_feeds.update(leg["feed_id"] for leg in route["selected_legs"])
        rows.append({k: case[k] for k in ("id", "corridor_id", "local_time", "decision_at", "incident_ids",
            "reference_route_id", "official_text_review", "exposure", "policy_comparison")} | {
                "modes": modes, "train_pair_signature": signature,
                "incident_train_pair_signature": [tuple(case["incident_ids"])] + signature,
                "selected_feed_capture_signature": sorted([s for s in case["asof_snapshot_receipts"]
                    if s["feed_id"] in selected_feeds], key=lambda s: s["feed_id"]),
                "previous_confirmed_checkpoint": case["id"] in set(frozen["previous_confirmed_case_ids"])})
    repeated_pairs, repeated_captures = defaultdict(list), defaultdict(list)
    for row in rows:
        repeated_pairs[json.dumps(row["train_pair_signature"], sort_keys=True)].append(row["id"])
        repeated_captures[json.dumps(row["selected_feed_capture_signature"], sort_keys=True)].append(row["id"])
    for row in rows:
        row["same_train_pair_as_case_ids"] = [identity for identity in
            repeated_pairs[json.dumps(row["train_pair_signature"], sort_keys=True)] if identity != row["id"]]
        row["same_selected_feed_captures_as_case_ids"] = [identity for identity in
            repeated_captures[json.dumps(row["selected_feed_capture_signature"], sort_keys=True)] if identity != row["id"]]
    positive = [r for r in rows if r["policy_comparison"]["classification"] == "MEANINGFUL_GAIN"]
    report = {"schema_version": "incremental-example-refinement-results-v1", "policy": POLICY,
        "selection_freeze": artifact(FREEZE), "scored_artifact": artifact(output), "label_sources": label_sources,
        "corridors": prepared["corridors"], "illustrative_only_summary": summary(evaluated),
        "not_for_overall_performance_estimation": True, "disagreement_cases": rows,
        "meaningful_gain_case_ids": [r["id"] for r in positive]}
    dump(REPORTS / "incremental-example-refinement-test.json", report)
    print({"stage": "ILLUSTRATIONS_SCORED", "summary": report["illustrative_only_summary"],
           "positive_examples": len(positive)}, flush=True)


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
