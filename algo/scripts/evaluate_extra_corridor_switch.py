#!/usr/bin/env python3
"""Freeze and replay at most two additional current-Google Stay corridors."""

import argparse
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
from stayorswitch.google_corridor_replay import POLICY as BASE_POLICY
from stayorswitch.google_corridor_replay import apply_review, plan_incidents, representatives, review_groups, select_encounter, validate_corridors
from stayorswitch.incremental_switch_replay import policy_comparison, summary
from stayorswitch.october_evaluation import latest_at_cutoffs, project_snapshot
from stayorswitch.preincident_replay import local_time, score_modes
from stayorswitch.severe import MODES, decide
from evaluate_google_corridors import _merge_labels, _verify_source, predict
from evaluate_preincident import artifact, code_provenance, dump, load, sha

LOCAL = ROOT / "algo/local/extra-corridor-switch"
REPORTS = ROOT / "algo/reports"
CONFIG = ROOT / "data/config/incremental-extra-corridors.json"
PREPARED = LOCAL / "prepared-inputs.json.gz"
REVIEW = REPORTS / "extra-corridor-switch-text-review.json"
FREEZE = REPORTS / "extra-corridor-switch-selection-frozen.json"
POLICY = dict(BASE_POLICY, schema_version="extra-corridor-switch-v1",
    decision_lags_seconds=list(range(0, 7201, 300)), maximum_total_corridors=5,
    maximum_extra_corridors=2,
    family_policy="ALL_TEST_FIRST_OBSERVED_UNPLANNED_PROBLEMS_APPLICABLE_TO_EXACT_GOOGLE_STAY",
    comparison_policy="RAW_MTA_STRICT_SELECTED_JOURNEY_VS_INCIDENT_PROFILE_STRICT_SELECTED_JOURNEY",
    raw_mta_advice_is_official_mta_recommendation=False,
    walking_sensitivity_selection="PORT_AUTHORITY_COUPLED_A_C_ACCESS_0_240_SECONDS; BASE_OR_VARIANT_RAW_STAY_MODEL_SWITCH; INPUT_ONLY",
    walking_sensitivity_uses_asof_recommendations=True,
    walking_sensitivity_uses_outcomes=False,
    previous_test_exploration_disclosed=True,
    selection_uses_outcomes_or_recommendations=False)


def validate_extra(config, existing):
    corridors = validate_corridors(config)
    ids = {c["id"] for c in corridors}
    previous = {c["id"] for c in existing["corridors"]}
    if len(corridors) > POLICY["maximum_extra_corridors"] or ids.intersection(previous):
        raise ValueError("Only two distinct additional corridors are authorized.")
    if len(ids | previous) > POLICY["maximum_total_corridors"]:
        raise ValueError("Combined study exceeds the five-corridor cap.")
    return corridors


def cohort_summary(cases):
    result = summary(cases)
    result["unique_incident_ids"] = sorted({incident for case in cases for incident in case["incident_ids"]})
    result["unique_incident_count"] = len(result["unique_incident_ids"])
    return result


def input_discrepancy(predictions, reference):
    actions = {mode: decide(predictions[mode], reference, switch_margin_seconds=300,
                           require_severe=False)["strict_decision"]["action"]
               for mode in ("mta", "incident_profile")}
    return actions["mta"] == "STAY" and actions["incident_profile"] == "SWITCH"


def platform_variant(corridor, seconds):
    adjusted = deepcopy(corridor)
    changed = []
    for route in adjusted["routes"]:
        if (len(route["legs"]) == 1 and route["legs"][0]["route_id"] in ("A", "C")
                and route["legs"][0]["from_stop_id"] == "A27S"):
            if route["access_walk_seconds"] != 120:
                raise ValueError("Port Authority baseline must retain the declared 120-second access.")
            route["access_walk_seconds"] = seconds
            changed.append(route["id"])
    if len(changed) != 2:
        raise ValueError("Coupled sensitivity requires both exact A and C paths.")
    return adjusted, changed


def provenance():
    names = ("algo/scripts/evaluate_extra_corridor_switch.py",
             "algo/stayorswitch/google_corridor_replay.py",
             "algo/stayorswitch/incremental_switch_replay.py",
             "algo/scripts/evaluate_google_corridors.py")
    return {"unchanged_original_implementation": code_provenance(),
        "policy": POLICY, "corridor_config": artifact(CONFIG),
        "existing_three_corridors": artifact(ROOT / "data/config/google-corridors.json"),
        "producer_code_sha256": {name: sha(ROOT / name) for name in names}}


def prepare():
    if PREPARED.exists() or REVIEW.exists() or FREEZE.exists():
        raise ValueError("Preserve existing prepared/reviewed/frozen evidence; do not overwrite it.")
    started = time.monotonic()
    initial = provenance()
    config = load(CONFIG)
    corridors = validate_extra(config, load(ROOT / "data/config/google-corridors.json"))
    inventory_path = ROOT / "data/processed/october/incidents.json.gz"
    inventory = load(inventory_path)
    plans, excluded, by_date = {}, {}, defaultdict(set)
    for corridor in corridors:
        plans[corridor["id"]], excluded[corridor["id"]] = plan_incidents(inventory, corridor, POLICY)
        for plan in plans[corridor["id"]]:
            for cutoff in plan["decision_times"]:
                by_date[local_time(cutoff)[:10]].add(cutoff)
    source_path = ROOT / "data/manifests/october.json"
    source = load(source_path)
    days = {r["date"]: r for r in source["days"]}
    sources = {str(p.relative_to(ROOT)): sha(p) for p in (CONFIG, inventory_path, source_path)}
    for key in ("capture_manifest", "walking_manifest", "station_metadata", "mapper", "builder"):
        _verify_source(config[key], sources)
    supplements = []
    for spec in config.get("supplemental_sources", []):
        manifest_path = ROOT / spec["manifest"]
        manifest = load(manifest_path)
        if manifest.get("stage") != "PREPARED":
            raise ValueError("Supplemental inputs are incomplete.")
        sources[spec["manifest"]] = sha(manifest_path)
        supplements.append((spec, {r["date"]: r for r in manifest["days"]}))
    replacement = {feed: i for i, (spec, _) in enumerate(supplements) for feed in spec["replace_feeds"]}

    def alerts():
        for day in sorted(days):
            item = days[day]["outputs"]["alerts"]
            _verify_source(item, sources)
            yield from read_snapshots(ROOT / item["path"])

    index = IncidentIndex(alerts(), max_age_seconds=POLICY["alerts_max_age_seconds"])
    print({"stage": "INPUT_GRID", "families": {k: len(v) for k, v in plans.items()},
           "unique_cutoffs": sum(map(len, by_date.values()))}, flush=True)
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

                def filtered(filename, allowed):
                    return (s for s in read_snapshots(filename) if s["feed_id"] in allowed)

                streams.append(filtered(ROOT / item["path"], feeds))
        selected, carry = latest_at_cutoffs((project_snapshot(s, all_routes) for s in chain(*streams)),
                                            sorted(by_date.get(key, [])), carry)
        captured.update(selected)
        print({"stage": "INPUT_DAY", "date": key, "seconds": round(time.monotonic()-started, 1)}, flush=True)
        day += timedelta(days=1)
    estimator = ProfileEstimator(ROOT / "data/artifacts/october-2026-profiles-train.json.gz")
    cases, rejected, sensitivity_cases, sensitivity_selection = [], [], [], []
    for corridor in corridors:
        cache, variant_cache = {}, {}
        for plan in plans[corridor["id"]]:
            for cutoff in plan["decision_times"]:
                if cutoff not in cache:
                    cache[cutoff] = predict(captured[cutoff], corridor, cutoff, index)
                case, reason = select_encounter(plan, corridor, cache[cutoff], index, POLICY)
                if case is None:
                    rejected.append({"corridor_id": corridor["id"], "incident_id": plan["incident_id"],
                                     "decision_at": cutoff, "reason": reason})
                    continue
                case["predictions"] = {mode: cache[cutoff] if mode == "mta" else
                    predict(captured[cutoff], corridor, cutoff, index, estimator, mode) for mode in MODES}
                cases.append(case)
                if corridor["id"] == "portauthority_tandon":
                    if cutoff not in variant_cache:
                        variant_cache[cutoff] = []
                        for seconds in config["portauthority_access_policy"]["predeclared_coupled_sensitivity_platform_seconds"]:
                            adjusted, changed = platform_variant(corridor, seconds)
                            predictions = {mode: predict(captured[cutoff], adjusted, cutoff, index,
                                None if mode == "mta" else estimator, mode) for mode in MODES}
                            variant_cache[cutoff].append((seconds, adjusted, changed, predictions))
                    baseline_difference = input_discrepancy(case["predictions"], corridor["reference_route_id"])
                    differences = [seconds for seconds, _, _, prediction in variant_cache[cutoff]
                                   if input_discrepancy(prediction, corridor["reference_route_id"])]
                    if baseline_difference or differences:
                        selection = {"base_case_id": case["id"], "baseline_discrepancy": baseline_difference,
                                     "variant_discrepancy_platform_seconds": differences, "variant_case_ids": []}
                        for seconds, adjusted, changed, predictions in variant_cache[cutoff]:
                            variant, reason = select_encounter(plan, adjusted, predictions["mta"], index, POLICY)
                            if variant is None:
                                raise ValueError("Coupled access lost the input notice scope: " + str(reason))
                            variant["id"] = case["id"] + "--platform-" + str(seconds)
                            variant["walking_sensitivity"] = {"base_case_id": case["id"],
                                "platform_access_seconds": seconds, "coupled_route_ids": changed,
                                "selection_uses_outcomes": False}
                            variant["predictions"] = predictions
                            sensitivity_cases.append(variant)
                            selection["variant_case_ids"].append(variant["id"])
                        sensitivity_selection.append(selection)
        print({"stage": "INPUT_PREDICTIONS", "corridor": corridor["id"], "candidates_so_far": len(cases),
               "seconds": round(time.monotonic()-started, 1)}, flush=True)
    if provenance() != initial:
        raise ValueError("Producer or configuration changed during input preparation.")
    selected_path = LOCAL / "selected-input-snapshots.json.gz"
    dump(selected_path, [{"cutoff": t, "snapshots": captured[t]} for t in sorted({c["decision_at"] for c in cases})])
    prepared = {"provenance": initial, "config": config, "plans": plans,
        "excluded_family_counts": excluded, "rejected_checkpoints": rejected,
        "input_sources": sources, "cases": cases, "walking_sensitivity_cases": sensitivity_cases,
        "walking_sensitivity_selection": sensitivity_selection, "selection_reads_outcome_labels": False,
        "selected_input_snapshots": artifact(selected_path)}
    dump(PREPARED, prepared)
    groups = review_groups(cases + sensitivity_cases)
    dump(REVIEW, {"prepared_inputs": artifact(PREPARED), "selection_uses_outcomes": False, "groups": groups})
    dump(REPORTS / "extra-corridor-switch-candidate-selection.json", {
        "policy": POLICY, "prepared_inputs": artifact(PREPARED), "corridors": corridors,
        "planned_checkpoint_count": sum(len(p["decision_times"]) for values in plans.values() for p in values),
        "candidate_count": len(cases), "walking_sensitivity_case_count": len(sensitivity_cases),
        "review_group_count": len(groups),
        "excluded_family_counts": excluded, "rejected_checkpoints": rejected,
        "case_ids": [c["id"] for c in cases], "walking_sensitivity_case_ids": [c["id"] for c in sensitivity_cases],
        "review_groups": groups})
    print({"stage": "PREPARED_WITHOUT_LABELS", "cases": len(cases), "review_groups": len(groups),
           "seconds": round(time.monotonic()-started, 1)}, flush=True)


def verify_prepared():
    prepared = load(PREPARED)
    if provenance() != prepared["provenance"]:
        raise ValueError("Prepared implementation or configuration changed.")
    for name, expected in prepared["input_sources"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Prepared source changed: " + name)
    item = prepared["selected_input_snapshots"]
    if sha(ROOT / item["path"]) != item["sha256"]:
        raise ValueError("Selected input snapshots changed.")
    return prepared


def freeze():
    prepared = verify_prepared()
    review = load(REVIEW)
    if review["prepared_inputs"] != artifact(PREPARED):
        raise ValueError("Notice review is bound to different inputs.")
    audits = review.get("audit_sources", [])
    if not audits:
        raise ValueError("Independent input notice audit must be bound by hash.")
    for item in audits:
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Input notice audit changed.")
    all_cases = prepared["cases"] + prepared["walking_sensitivity_cases"]
    all_confirmed, all_excluded = apply_review(all_cases, review)
    confirmed = [c for c in all_confirmed if "walking_sensitivity" not in c]
    variants = [c for c in all_confirmed if "walking_sensitivity" in c]
    excluded = [c for c in all_excluded if "walking_sensitivity" not in c]
    value = {"schema_version": "extra-corridor-switch-freeze-v1", "provenance": prepared["provenance"],
        "prepared_inputs": artifact(PREPARED), "text_review": artifact(REVIEW),
        "selected_input_snapshots": prepared["selected_input_snapshots"], "independent_input_audits": audits,
        "selection_reads_outcome_labels": False, "confirmed_case_ids": [c["id"] for c in confirmed],
        "excluded_case_ids": [c["id"] for c in excluded],
        "walking_sensitivity_confirmed_ids": [c["id"] for c in variants],
        "walking_sensitivity_excluded_ids": [c["id"] for c in all_excluded if "walking_sensitivity" in c],
        "primary_case_ids": [c["id"] for c in representatives(confirmed)],
        "selection_counts": {"confirmed": len(confirmed), "excluded_or_unresolved": len(excluded),
                             "review_statuses": dict(Counter(g["status"] for g in review["groups"]))}}
    if FREEZE.exists() and load(FREEZE) != value:
        raise ValueError("Frozen selection differs; do not overwrite it.")
    dump(FREEZE, value)
    print({"stage": "FROZEN_WITHOUT_LABELS", "cases": len(confirmed), "primary": len(value["primary_case_ids"])}, flush=True)


def verify():
    frozen = load(FREEZE)
    prepared = verify_prepared()
    if frozen["provenance"] != prepared["provenance"]:
        raise ValueError("Frozen provenance differs.")
    for key in ("prepared_inputs", "text_review", "selected_input_snapshots"):
        item = frozen[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen artifact changed: " + key)
    for item in frozen["independent_input_audits"]:
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen notice audit changed.")
    all_confirmed, all_excluded = apply_review(prepared["cases"] + prepared["walking_sensitivity_cases"], load(REVIEW))
    cases = [c for c in all_confirmed if "walking_sensitivity" not in c]
    variants = [c for c in all_confirmed if "walking_sensitivity" in c]
    excluded = [c for c in all_excluded if "walking_sensitivity" not in c]
    if [c["id"] for c in cases] != frozen["confirmed_case_ids"] or [c["id"] for c in excluded] != frozen["excluded_case_ids"]:
        raise ValueError("Frozen selected cases changed.")
    if [c["id"] for c in representatives(cases)] != frozen["primary_case_ids"]:
        raise ValueError("Frozen primary representatives changed.")
    if ([c["id"] for c in variants] != frozen["walking_sensitivity_confirmed_ids"] or
            [c["id"] for c in all_excluded if "walking_sensitivity" in c] != frozen["walking_sensitivity_excluded_ids"]):
        raise ValueError("Frozen walking-sensitivity scope changed.")
    return frozen, prepared, cases, variants


def score():
    frozen, prepared, cases, variants = verify()
    original = load(ROOT / "data/manifests/october.json")
    labels, label_sources = {}, {}
    for day in sorted({local_time(c["decision_at"])[:10] for c in cases + variants}):
        for service_day in ((date.fromisoformat(day) - timedelta(days=1)).isoformat(), day):
            item = original["daily_labels"][service_day]
            if item["path"] not in label_sources:
                _verify_source(item, label_sources)
                _merge_labels(labels, read_labels(ROOT / item["path"]))
    for spec in prepared["config"].get("extra_label_sources", []):
        item = load(ROOT / spec["manifest"])[spec.get("key", "labels")]
        _verify_source(item, label_sources)
        _merge_labels(labels, read_labels(ROOT / item["path"]))
    evaluated = []
    for case in cases:
        value = score_modes(case, case["predictions"], labels, POLICY)
        value["policy_comparison"] = policy_comparison(value)
        evaluated.append(value)
    scored = LOCAL / "scored-cases.json.gz"
    dump(scored, evaluated)
    variant_results = []
    for case in variants:
        value = score_modes(case, case["predictions"], labels, POLICY)
        value["policy_comparison"] = policy_comparison(value)
        variant_results.append(value)
    sensitivity_path = LOCAL / "scored-walking-sensitivity.json.gz"
    dump(sensitivity_path, variant_results)
    primary_ids = set(frozen["primary_case_ids"])
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
                "primary": case["id"] in primary_ids, "modes": modes})
    report = {"schema_version": "extra-corridor-switch-results-v1", "policy": POLICY,
        "selection_freeze": artifact(FREEZE), "scored_artifact": artifact(scored), "label_sources": label_sources,
        "walking_sensitivity_artifact": artifact(sensitivity_path),
        "walking_sensitivity_input_selection": prepared["walking_sensitivity_selection"],
        "walking_sensitivity_results": [{"id": c["id"], "walking_sensitivity": c["walking_sensitivity"],
            "policy_comparison": c["policy_comparison"],
            "mode_decisions": {mode: c["modes"][mode]["strict_decision"] for mode in MODES}}
            for c in variant_results],
        "corridors": prepared["config"]["corridors"], "all_summary": cohort_summary(evaluated),
        "primary_summary": cohort_summary([c for c in evaluated if c["id"] in primary_ids]),
        "per_corridor_summary": {c["id"]: cohort_summary([r for r in evaluated if r["corridor_id"] == c["id"]])
            for c in prepared["config"]["corridors"]}, "cases": compact}
    dump(REPORTS / "extra-corridor-switch-test.json", report)
    print({"stage": "SCORED", "summary": report["all_summary"]}, flush=True)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prepare-inputs", action="store_true")
    group.add_argument("--freeze-only", action="store_true")
    group.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_inputs:
        prepare()
    elif args.freeze_only:
        freeze()
    elif args.verify_only:
        frozen, _, _, _ = verify()
        print({"stage": "VERIFIED", "cases": len(frozen["confirmed_case_ids"])}, flush=True)
    else:
        score()


if __name__ == "__main__":
    main()
