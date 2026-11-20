#!/usr/bin/env python3
"""Prepare, qualify, freeze and score the fixed November five-corridor study."""

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
from data.november_outcomes import screen_labels
from data.october import read_labels, read_snapshots
from stayorswitch.google_corridor_replay import apply_review, representatives, review_groups, validate_corridors
from stayorswitch.november_replay import POLICY, asof_problem_notices, cohort_summary, date_subset, plan_incidents, score_annotations, select_applicable_windows, select_encounter
from stayorswitch.october_evaluation import latest_at_cutoffs, outcome_for, project_snapshot
from stayorswitch.preincident_replay import local_time, score_modes
from stayorswitch.severe import MODES, decide
from evaluate_google_corridors import _merge_labels, _verify_source, predict
from evaluate_preincident import artifact, code_provenance, dump, load, sha


LOCAL = ROOT / "algo/local/november-2026"
REPORTS = ROOT / "algo/reports"
SOURCE = ROOT / "data/manifests/november-2026.json"
INPUT_SOURCE = ROOT / "data/manifests/november-2026-inputs.json"
PROFILE = ROOT / "data/artifacts/october-2026-profiles-full-train.json.gz"
TRAINING_FREEZE = ROOT / "data/manifests/full-october-fit-frozen.json"
CONFIGS = (ROOT / "data/config/google-corridors.json", ROOT / "data/config/incremental-extra-corridors.json")
PREPARED = LOCAL / "prepared-inputs.json.gz"
REVIEW = REPORTS / "november-2026-text-review.json"
FREEZE = REPORTS / "november-2026-selection-frozen.json"
RESULT = REPORTS / "november-2026-test.json"
PROTOCOL = ROOT / "algo/docs/november-five-corridor-plan.md"


def corridors():
    output = list(chain.from_iterable(validate_corridors(load(p)) for p in CONFIGS))
    if len(output) != 5 or len({c["id"] for c in output}) != 5:
        raise ValueError("This study requires exactly the five existing corridors.")
    return output


def provenance():
    names = ("algo/scripts/evaluate_november.py", "algo/stayorswitch/november_replay.py",
             "algo/stayorswitch/google_corridor_replay.py", "algo/stayorswitch/incremental_switch_replay.py",
             "algo/scripts/evaluate_google_corridors.py", "data/november_outcomes.py")
    result = {"preserved_original_implementation": code_provenance(), "policy": POLICY,
        "corridor_configs": [artifact(p) for p in CONFIGS],
        "input_source_manifest": artifact(INPUT_SOURCE),
        "producer_code_sha256": {name: sha(ROOT / name) for name in names}}
    result["analysis_protocol"] = artifact(PROTOCOL)
    return result


def training_provenance():
    profile = load(PROFILE)
    frozen = load(TRAINING_FREEZE)
    if (frozen.get("stage") != "FROZEN_BEFORE_NOVEMBER_OUTCOME_ANALYSIS"
            or frozen.get("training_dates") != POLICY["fit_dates"]
            or frozen.get("artifact") != artifact(PROFILE)
            or frozen.get("profile_seal") != profile.get("seal")
            or frozen.get("november_outcomes_used_for_fit") is not False):
        raise ValueError("A completed and verified full-October training freeze is required.")
    if (profile.get("fit_split") != "train"
            or profile.get("configuration", {}).get("splits", {}).get("train") != POLICY["fit_dates"]):
        raise ValueError("The November replay requires the new full-October training artifact.")
    return {"training_profile": artifact(PROFILE), "training_profile_seal": profile["seal"],
            "training_freeze": artifact(TRAINING_FREEZE),
            "fit_dates": profile["configuration"]["splits"]["train"]}


def source_days():
    source = load(INPUT_SOURCE)
    days = {r["date"]: r for r in source["days"]}
    expected = []
    day = date.fromisoformat(POLICY["input_boundary_date"])
    while day <= date.fromisoformat(POLICY["test_dates"][1]):
        expected.append(day.isoformat())
        day += timedelta(days=1)
    if set(expected) - set(days):
        raise ValueError("November input source is missing dates: " + str(sorted(set(expected) - set(days))))
    return source, {key: days[key] for key in expected}


def incident_index(days, sources=None):
    def alerts():
        for key in sorted(days):
            item = days[key]["outputs"]["alerts"]
            if sources is not None:
                _verify_source(item, sources)
            yield from read_snapshots(ROOT / item["path"])
    return IncidentIndex(alerts(), max_age_seconds=POLICY["alerts_max_age_seconds"])


def pack_snapshots(selected, cutoffs):
    """Store shared immutable feed records once per day instead of per cutoff."""
    records, identity_to_index, rows = [], {}, []
    for cutoff in sorted(set(cutoffs)):
        indices = []
        for snapshot in selected[cutoff]:
            identity = id(snapshot)
            if identity not in identity_to_index:
                identity_to_index[identity] = len(records)
                records.append(snapshot)
            indices.append(identity_to_index[identity])
        rows.append({"cutoff": cutoff, "snapshot_indices": indices})
    return {"schema_version": "shared-cutoff-snapshots-v1", "records": records, "cutoffs": rows}


def predict_stay_scope(snapshots, corridor, cutoff, index):
    """Notice scope needs only the fixed Stay train, not alternative forecasts."""
    reference = corridor["reference_route_id"]
    scoped = dict(corridor, routes=[r for r in corridor["routes"] if r["id"] == reference],
                  unavailable_candidates=[])
    return predict(snapshots, scoped, cutoff, index)


def assert_stay_parity(full, scoped, reference):
    before = next(r for r in scoped["routes"] if r["id"] == reference)
    after = next(r for r in full["routes"] if r["id"] == reference)
    if before != after:
        raise ValueError("The fixed Stay forecast changed after input-only scope preparation.")
    if {k: v for k, v in full.items() if k != "routes"} != {k: v for k, v in scoped.items() if k != "routes"}:
        raise ValueError("As-of feed evidence changed after input-only scope preparation.")


def prepare():
    if any(p.exists() for p in (PREPARED, REVIEW, FREEZE)):
        raise ValueError("Preserve existing November prepared/review/frozen artifacts.")
    started = time.monotonic()
    initial = provenance()
    config = corridors()
    _, days = source_days()
    # Binding actual immutable daily input files avoids coupling input selection
    # to the source manifest's later addition of separate outcome-label hashes.
    sources = {}
    index = incident_index(days, sources)
    inventory = index.inventory()
    inventory_path = LOCAL / "input-only-incidents.json.gz"
    dump(inventory_path, inventory)
    plans, excluded, by_date = {}, {}, defaultdict(set)
    for corridor in config:
        key = corridor["id"]
        plans[key], excluded[key] = plan_incidents(inventory, corridor)
        for plan in plans[key]:
            for cutoff in plan["decision_times"]:
                by_date[local_time(cutoff)[:10]].add(cutoff)
    print({"stage": "INPUT_GRID", "families": {k: len(v) for k, v in plans.items()},
        "unique_cutoffs": sum(map(len, by_date.values()))}, flush=True)
    all_routes = list(chain.from_iterable(c["routes"] for c in config))
    cases, rejected, snapshot_artifacts, carry = [], [], [], {}
    for key, day in sorted(days.items()):
        item = day["outputs"]["snapshots"]
        _verify_source(item, sources)
        selected, carry = latest_at_cutoffs(
            (project_snapshot(s, all_routes) for s in read_snapshots(ROOT / item["path"])),
            sorted(by_date.get(key, [])), carry)
        day_cases = []
        for corridor in config:
            cache = {}
            stay_template = next(r for r in corridor["routes"] if r["id"] == corridor["reference_route_id"])
            for plan in plans[corridor["id"]]:
                for cutoff in plan["decision_times"]:
                    if local_time(cutoff)[:10] != key:
                        continue
                    # This prefilter uses only active family/line membership;
                    # exact direction and segment qualification still follows
                    # forecast selection and independent notice review.
                    recorded = any(asof_problem_notices(index, cutoff, line,
                        [leg["from_stop_id"], leg["to_stop_id"]], plan["incident_id"], POLICY)
                        for leg in stay_template["legs"] for line in leg.get("route_ids", [leg["route_id"]]))
                    if not recorded:
                        rejected.append({"corridor_id": corridor["id"], "incident_id": plan["incident_id"],
                            "decision_at": cutoff, "incident_origin": plan["incident_origin"],
                            "reason": "NO_ASOF_RECORDED_PROBLEM_FOR_FIXED_STAY"})
                        continue
                    if cutoff not in cache:
                        cache[cutoff] = predict_stay_scope(selected[cutoff], corridor, cutoff, index)
                    case, reason = select_encounter(plan, corridor, cache[cutoff], index, POLICY)
                    if case is None:
                        rejected.append({"corridor_id": corridor["id"], "incident_id": plan["incident_id"],
                            "decision_at": cutoff, "incident_origin": plan["incident_origin"], "reason": reason})
                        continue
                    case.update(incident_origin=plan["incident_origin"], evaluation_anchor=plan["evaluation_anchor"])
                    day_cases.append(case)
        cases.extend(day_cases)
        if day_cases:
            daily_path = LOCAL / "selected-input-snapshots" / (key + ".json.gz")
            dump(daily_path, pack_snapshots(selected, [c["decision_at"] for c in day_cases]))
            snapshot_artifacts.append(dict(artifact(daily_path), date=key))
        print({"stage": "INPUT_DAY", "date": key,
            "cases_so_far": len(cases), "seconds": round(time.monotonic() - started, 1)}, flush=True)
    if provenance() != initial:
        raise ValueError("Implementation or configuration changed during preparation.")
    selected_path = LOCAL / "selected-input-snapshots.json"
    dump(selected_path, {"days": snapshot_artifacts})
    prepared = {"provenance": initial, "corridors": config, "plans": plans,
        "excluded_family_counts": excluded, "rejected_checkpoints": rejected,
        "input_sources": sources, "cases": cases, "selection_reads_outcome_labels": False,
        "incident_inventory": artifact(inventory_path), "selected_input_snapshots": artifact(selected_path)}
    dump(PREPARED, prepared)
    groups = review_groups(cases)
    dump(REVIEW, {"prepared_inputs": artifact(PREPARED), "selection_uses_outcomes": False, "groups": groups})
    dump(REPORTS / "november-2026-candidate-selection.json", {
        "policy": POLICY, "prepared_inputs": artifact(PREPARED), "corridors": config,
        "planned_checkpoint_count": sum(len(p["decision_times"]) for v in plans.values() for p in v),
        "candidate_count": len(cases), "review_group_count": len(groups),
        "excluded_family_counts": excluded, "rejected_checkpoints": rejected,
        "case_ids": [c["id"] for c in cases], "review_groups": groups})
    print({"stage": "PREPARED_WITHOUT_LABELS", "cases": len(cases), "review_groups": len(groups),
        "seconds": round(time.monotonic() - started, 1)}, flush=True)


def verify_prepared():
    prepared = load(PREPARED)
    if provenance() != prepared["provenance"]:
        raise ValueError("Prepared implementation or configuration changed.")
    for name, expected in prepared["input_sources"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Prepared input changed: " + name)
    for key in ("incident_inventory", "selected_input_snapshots"):
        item = prepared[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Prepared input changed: " + key)
    for item in load(ROOT / prepared["selected_input_snapshots"]["path"])["days"]:
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Prepared daily snapshots changed.")
    return prepared


def selected_snapshots(prepared, cutoffs):
    """Read daily stores but retain only the requested frozen cutoffs."""
    requested = set(cutoffs)
    days = {local_time(t)[:10] for t in requested}
    for item in load(ROOT / prepared["selected_input_snapshots"]["path"])["days"]:
        if item["date"] not in days:
            continue
        daily = load(ROOT / item["path"])
        for row in daily["cutoffs"]:
            if row["cutoff"] in requested:
                yield {"cutoff": row["cutoff"], "snapshots": [daily["records"][i] for i in row["snapshot_indices"]]}


def prepare_forecasts(prepared, cases):
    output = LOCAL / "frozen-forecast-cases.json.gz"
    binding = {"prepared_inputs": artifact(PREPARED), "review": artifact(REVIEW),
               "training": training_provenance()}
    if output.exists():
        saved_file = load(output)
        if saved_file["binding"] != binding:
            raise ValueError("Existing forecasts belong to another model or input selection.")
        previous = saved_file["cases"]
        if len(previous) != len(cases):
            raise ValueError("Existing forecasts belong to another selection.")
        for case, saved in zip(cases, previous):
            if {k: v for k, v in saved.items() if k != "predictions"} != case:
                raise ValueError("Existing forecasts belong to another selection.")
            assert_stay_parity(saved["predictions"]["mta"], case["asof_mta_prediction"], case["reference_route_id"])
            case["predictions"] = saved["predictions"]
        return artifact(output)
    _, days = source_days()
    index = incident_index(days)
    estimator = ProfileEstimator(PROFILE)
    lookup = {c["id"]: c for c in prepared["corridors"]}
    by_cutoff = defaultdict(list)
    for case in cases:
        by_cutoff[case["decision_at"]].append(case)
    seen = set()
    for row in selected_snapshots(prepared, by_cutoff):
        cache = {}
        for case in by_cutoff[row["cutoff"]]:
            corridor = lookup[case["corridor_id"]]
            if corridor["id"] not in cache:
                cache[corridor["id"]] = {mode: predict(row["snapshots"], corridor, row["cutoff"], index,
                    None if mode == "mta" else estimator, mode) for mode in MODES}
            case["predictions"] = cache[corridor["id"]]
            assert_stay_parity(case["predictions"]["mta"], case["asof_mta_prediction"], case["reference_route_id"])
            seen.add(case["id"])
    if seen != {c["id"] for c in cases}:
        raise ValueError("Missing snapshots for selected forecast cases.")
    if training_provenance() != binding["training"]:
        raise ValueError("Training profile changed during prediction.")
    dump(output, {"binding": binding, "cases": cases})
    return artifact(output)


def prepare_sensitivity(prepared, primary, review_artifact):
    output = LOCAL / "walking-sensitivity-inputs.json.gz"
    binding = {"provenance": prepared["provenance"], "primary_case_ids": [c["id"] for c in primary],
        "review": review_artifact, "training": training_provenance(), "selection_uses_outcomes": False}
    if output.exists():
        if load(output)["binding"] != binding:
            raise ValueError("Existing sensitivity inputs belong to another selection.")
        return artifact(output)
    snapshots = {r["cutoff"]: r["snapshots"] for r in selected_snapshots(prepared,
        [c["decision_at"] for c in primary])}
    _, days = source_days()
    index = incident_index(days)
    estimator = ProfileEstimator(PROFILE)
    lookup = {c["id"]: c for c in prepared["corridors"]}
    rows = []
    for case in primary:
        corridor = lookup[case["corridor_id"]]
        alternatives = [r for r in case["predictions"]["incident_profile"]["routes"]
                        if r["id"] != case["reference_route_id"] and r.get("timing_eligible")]
        best = min(alternatives, key=lambda r: (r["total_duration_seconds"], r["id"])) if alternatives else None
        selected = [case["reference_route_id"]] + ([best["id"]] if best else [])
        variants, skipped = [], []
        for route_id in selected:
            route = next(r for r in corridor["routes"] if r["id"] == route_id)
            components = [("access_walk_seconds", None), ("egress_walk_seconds", None)]
            components += [("transfer_walk_seconds", i) for i in range(len(route["transfer_walk_seconds"]))]
            for component, position in components:
                original = route[component] if position is None else route[component][position]
                for delta in POLICY["walking_sensitivity_seconds"]:
                    spec = {"route_id": route_id, "component": component, "transfer_index": position,
                        "delta_seconds": delta, "original_walk_seconds": original}
                    if original + delta < 0:
                        skipped.append(dict(spec, reason="NEGATIVE_WALK_NOT_ALLOWED"))
                        continue
                    adjusted = deepcopy(corridor)
                    target = next(r for r in adjusted["routes"] if r["id"] == route_id)
                    if position is None:
                        target[component] += delta
                    else:
                        target[component][position] += delta
                    forecast = predict(snapshots[case["decision_at"]], adjusted, case["decision_at"], index,
                        estimator, "incident_profile")
                    variants.append(dict(spec, prediction=forecast))
        if corridor["id"] == "portauthority_tandon":
            for seconds in (0, 240):
                adjusted = deepcopy(corridor)
                targets = [r for r in adjusted["routes"] if len(r["legs"]) == 1
                    and r["legs"][0]["route_id"] in ("A", "C")
                    and r["legs"][0]["from_stop_id"] == "A27S"]
                if len(targets) != 2 or any(r["access_walk_seconds"] != 120 for r in targets):
                    raise ValueError("Port Authority coupled sensitivity requires declared A/C access.")
                for target in targets:
                    target["access_walk_seconds"] = seconds
                forecast = predict(snapshots[case["decision_at"]], adjusted, case["decision_at"], index,
                    estimator, "incident_profile")
                variants.append({"component": "COUPLED_A_C_ACCESS", "platform_access_seconds": seconds,
                    "route_ids": [r["id"] for r in targets], "prediction": forecast})
        rows.append({"case_id": case["id"], "selected_route_ids": selected, "variants": variants,
                     "skipped_negative_variants": skipped})
    dump(output, {"binding": binding, "cases": rows})
    print({"stage": "INPUT_ONLY_WALK_SENSITIVITY", "primary_cases": len(rows),
        "variants": sum(len(r["variants"]) for r in rows)}, flush=True)
    return artifact(output)


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
    confirmed, excluded = apply_review(prepared["cases"], review)
    if any(c["official_text_review"]["confirmed_impact"] == "SEVERE"
            and c["official_text_review"].get("severity_basis") not in
                ("EXPLICIT_SEVERE_TEXT", "COMPLETE_FIXED_PATH_INTERRUPTION") for c in confirmed):
        raise ValueError("Severe notice qualification requires its explicit evidence basis.")
    cases, window_excluded, anchors = select_applicable_windows(confirmed, prepared["plans"])
    forecasts = prepare_forecasts(prepared, cases)
    primary = representatives(cases)
    sensitivity = prepare_sensitivity(prepared, primary, artifact(REVIEW))
    value = {"schema_version": "november-five-corridor-freeze-v1", "provenance": prepared["provenance"],
        "training": training_provenance(),
        "prepared_inputs": artifact(PREPARED), "text_review": artifact(REVIEW),
        "selected_input_snapshots": prepared["selected_input_snapshots"], "independent_input_audits": audits,
        "walking_sensitivity_inputs": sensitivity, "selection_reads_outcome_labels": False,
        "frozen_forecast_cases": forecasts,
        "confirmed_case_ids": [c["id"] for c in cases], "excluded_case_ids": [c["id"] for c in excluded],
        "window_excluded": window_excluded, "first_applicable_anchors": anchors,
        "primary_case_ids": [c["id"] for c in primary],
        "selection_counts": {"raw_prepared": len(prepared["cases"]),
            "text_confirmed_before_applicable_window": len(confirmed),
            "confirmed": len(cases), "excluded_or_unresolved": len(excluded),
            "outside_applicable_window_or_no_anchor": len(window_excluded),
            "window_exclusion_reasons": dict(Counter(r["reason"] for r in window_excluded)),
            "input_rejected_checkpoints": len(prepared["rejected_checkpoints"]),
            "review_statuses": dict(Counter(g["status"] for g in review["groups"]))}}
    if FREEZE.exists() and load(FREEZE) != value:
        raise ValueError("Existing freeze differs; do not overwrite.")
    dump(FREEZE, value)
    print({"stage": "FROZEN_WITHOUT_LABELS", "cases": len(cases), "primary": len(primary)}, flush=True)


def verify():
    frozen = load(FREEZE)
    prepared = verify_prepared()
    if frozen["provenance"] != prepared["provenance"]:
        raise ValueError("Frozen provenance differs.")
    if frozen["training"] != training_provenance():
        raise ValueError("Frozen training profile differs.")
    for key in ("prepared_inputs", "text_review", "selected_input_snapshots", "walking_sensitivity_inputs", "frozen_forecast_cases"):
        item = frozen[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen artifact changed: " + key)
    for item in frozen["independent_input_audits"]:
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen input audit changed.")
    confirmed, excluded = apply_review(prepared["cases"], load(REVIEW))
    cases, window_excluded, anchors = select_applicable_windows(confirmed, prepared["plans"])
    if ([c["id"] for c in cases] != frozen["confirmed_case_ids"]
            or [c["id"] for c in excluded] != frozen["excluded_case_ids"]
            or window_excluded != frozen["window_excluded"] or anchors != frozen["first_applicable_anchors"]
            or [c["id"] for c in representatives(cases)] != frozen["primary_case_ids"]):
        raise ValueError("Frozen selection changed.")
    forecast_file = load(ROOT / frozen["frozen_forecast_cases"]["path"])
    if forecast_file["binding"]["training"] != frozen["training"]:
        raise ValueError("Frozen forecast model binding differs.")
    forecast_cases = forecast_file["cases"]
    if len(cases) != len(forecast_cases):
        raise ValueError("Frozen forecast case count changed.")
    for case, predicted in zip(cases, forecast_cases):
        if {k: v for k, v in predicted.items() if k != "predictions"} != case:
            raise ValueError("Frozen forecast case differs from reviewed selection.")
        assert_stay_parity(predicted["predictions"]["mta"], case["asof_mta_prediction"], case["reference_route_id"])
    return frozen, prepared, forecast_cases


def read_outcomes():
    source = load(SOURCE)
    if source.get("stage") != "PREPARED":
        raise ValueError("November labels are not completely prepared.")
    labels, sources = {}, {}
    for key, item in sorted(source["daily_labels"].items()):
        _verify_source(item, sources)
        _merge_labels(labels, read_labels(ROOT / item["path"]))
    screened, screening = screen_labels(labels, POLICY["outcome_endpoint_max_absolute_observation_age_seconds"])
    return screened, sources, screening


def compact_case(case, primary_ids):
    modes = {}
    for mode in MODES:
        value = case["modes"][mode]
        selected = {case["reference_route_id"], value["strict_decision"]["recommended_itinerary_id"]}
        modes[mode] = {"strict_decision": value["strict_decision"], "scores": value["scores"]["strict_decision"],
            "selected_routes": [{"id": r["id"], "name": r["name"],
                "predicted_duration_seconds": r.get("total_duration_seconds"),
                "selected_train_ids": [leg["trip_id"] for leg in r.get("selected_legs", [])],
                "outcome": value["outcomes"][r["id"]]} for r in value["routes"] if r["id"] in selected]}
    return {k: case[k] for k in ("id", "corridor_id", "incident_ids", "local_time", "decision_at",
        "reference_route_id", "incident_origin", "official_text_review", "exposure", "policy_comparison",
        "paired_policies")} | {"primary": case["id"] in primary_ids, "modes": modes}


def score_sensitivity(frozen, cases, labels):
    source = load(ROOT / frozen["walking_sensitivity_inputs"]["path"])
    lookup = {c["id"]: c for c in cases}
    rows = []
    for record in source["cases"]:
        case = lookup[record["case_id"]]
        for variant in record["variants"]:
            prediction = variant["prediction"]
            decisions = decide(prediction, case["reference_route_id"], switch_margin_seconds=300, require_severe=False)
            decision = decisions["strict_decision"]
            outcomes = {r["id"]: outcome_for(r, labels, case["decision_at"]) for r in prediction["routes"]}
            current, chosen = outcomes.get(case["reference_route_id"], {}), outcomes.get(decision["recommended_itinerary_id"], {})
            gain = (current["total_duration_seconds"] - chosen["total_duration_seconds"]
                    if current.get("status") == chosen.get("status") == "INFERRED" else None)
            rows.append({k: deepcopy(v) for k, v in variant.items() if k != "prediction"} | {
                "case_id": case["id"], "strict_decision": decision, "chosen_outcome": chosen,
                "stay_outcome": current, "inferred_savings_seconds": gain})
    return rows


def score():
    frozen, prepared, cases = verify()
    labels, sources, screening = read_outcomes()
    evaluated = [score_annotations(score_modes({k: v for k, v in c.items() if k != "predictions"},
        c["predictions"], labels, POLICY)) for c in cases]
    scored = LOCAL / "scored-cases.json.gz"
    dump(scored, evaluated)
    sensitivity = score_sensitivity(frozen, evaluated, labels)
    sensitivity_path = LOCAL / "scored-walking-sensitivity.json.gz"
    dump(sensitivity_path, sensitivity)
    primary_ids = set(frozen["primary_case_ids"])
    primary = [c for c in evaluated if c["id"] in primary_ids]
    report = {"schema_version": "november-five-corridor-results-v1", "policy": POLICY,
        "selection_freeze": artifact(FREEZE), "scored_artifact": artifact(scored),
        "walking_sensitivity_artifact": artifact(sensitivity_path), "label_sources": sources,
        "selection_counts": frozen["selection_counts"],
        "endpoint_screening": screening, "corridors": prepared["corridors"],
        "all_summary": cohort_summary(evaluated), "primary_summary": cohort_summary(primary),
        "newly_unused_dates_summary": cohort_summary([c for c in evaluated if date_subset(c)]),
        "newly_unused_dates_primary_summary": cohort_summary([c for c in primary if date_subset(c)]),
        "newly_unused_incident_primary_summary": cohort_summary([c for c in primary
            if date_subset(c) and local_time(c["first_family_receipt"])[:10] >= "2026-11-16"]),
        "origin_summaries": {origin: cohort_summary([c for c in evaluated if c["incident_origin"] == origin])
            for origin in sorted({c["incident_origin"] for c in evaluated})},
        "severe_summary": cohort_summary([c for c in evaluated
            if c["official_text_review"]["confirmed_impact"] == "SEVERE"]),
        "planned_through_service_unavailable_summary": cohort_summary([c for c in evaluated
            if c["official_text_review"].get("planned_through_service_unavailable") is True]),
        "without_planned_through_service_loss_summary": cohort_summary([c for c in evaluated
            if c["official_text_review"].get("planned_through_service_unavailable") is not True]),
        "per_corridor_summary": {c["id"]: cohort_summary([r for r in evaluated if r["corridor_id"] == c["id"]])
            for c in prepared["corridors"]},
        "per_corridor_primary_summary": {c["id"]: cohort_summary([r for r in primary if r["corridor_id"] == c["id"]])
            for c in prepared["corridors"]},
        "cases": [compact_case(c, primary_ids) for c in evaluated]}
    dump(RESULT, report)
    write_report(report)
    print({"stage": "SCORED", "all_summary": report["all_summary"],
           "primary_summary": report["primary_summary"]}, flush=True)


def write_report(report):
    lines = ["# November five-corridor Stay/Switch analysis", "",
        "The predictive model was fitted on October 1–31, 2026 and frozen before November outcome scoring. "
        "The old October experiment is unchanged. November 2–15 overlaps dates used in earlier project exploration; "
        "November 16–18 is reported separately. November 19 is boundary evidence only. No November outcomes were used to refit this model.", "",
        "Google's previously captured current recommended paths define Stay. Current Google minutes are not historical outcomes. "
        "All decisions use the exact archived same-cutoff trains, the existing supplied alternatives and declared walking times. "
        "A raw-MTA Stay/Switch action is the project's five-minute rule, not an official MTA routing recommendation.", "",
        "The cohort requires an applicable unplanned service-problem notice on the Stay path; it may include short turns, "
        "unplanned express running or other service changes. Notice exposure alone does not establish that the exact selected "
        "train's ETA worsened. Route/direction text qualification and proxy outcome comparisons are reported separately. "
        "Qualified severe exposure includes explicit severe wording or a complete unplanned interruption of the fixed Stay through "
        "path; these evidence bases remain distinct in the JSON summaries. Cases lacking a forecast during a closure remain counted. "
        "Mixed notices can also contain a separate planned through-service closure; those cases retain a separate flag/summary, "
        "and planned path loss is not attributed to the unplanned delay or labeled an unplanned severe interruption.", "",
        "Outcomes are screened final-MTA-prediction proxies, not measured passenger trips. Each needed boarding/departure and "
        "alighting/arrival endpoint must have a last observation within 180 seconds. Missing labels, uncertain outcomes and missed "
        "selected trains remain unknown. Differences within ±3 minutes are ties; predicted savings of at least 5 minutes trigger Switch.", "",
        "## Cohort and model decisions", "",
        "| Scope | Checkpoints | Corridor–incident pairs | Unique incident IDs | Model Switch | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    scopes = [("All checkpoints", report["all_summary"]), ("Primary representatives", report["primary_summary"]),
              ("November 16–18 checkpoints", report["newly_unused_dates_summary"]),
              ("November 16–18 representatives", report["newly_unused_dates_primary_summary"]),
              ("Qualified severe checkpoints", report["severe_summary"])]
    for name, item in scopes:
        counts = item["model_switch_vs_model_stay"]
        kinds = counts["classes"]
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(name, item["cases"],
            item["corridor_incidents"], item["unique_incident_count"], counts["recommendations"],
            kinds.get("MEANINGFUL_GAIN", 0), kinds.get("PRACTICAL_TIE", 0), kinds.get("MEANINGFUL_LOSS", 0), kinds.get("UNKNOWN", 0)))
    lines += ["", "Primary representatives are selected from inputs alone, once per corridor–incident pair. "
        "The same incident can affect several corridors; the all-checkpoint rows contain repeated incidents and trains. "
        "Neither count represents independent passenger journeys.", "", "## Comparisons between actual policies", "",
        "| Scope / comparison | Eligible decisions | Comparable | Model faster >3 min | Tie | Model slower >3 min | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for name, item in scopes[:4]:
        for key in ("time_vs_mta", "incident_vs_mta", "incident_vs_time"):
            row = item["paired_policies"][key]
            kinds = row["classes"]
            lines.append("| {} / {} | {} | {} | {} | {} | {} | {} |".format(name, key,
                row["eligible_actions"], row["comparable"], kinds.get("MEANINGFUL_GAIN", 0),
                kinds.get("PRACTICAL_TIE", 0), kinds.get("MEANINGFUL_LOSS", 0), kinds.get("UNKNOWN", 0)))
    lines += ["", "These compare each policy's actual recommended route and selected trains. "
        "They do not compare against an unconditional fastest raw-MTA alternative.", "", "## Five-corridor detail", "",
        "| Corridor | Checkpoints | Events | Switch | Gain | Tie | Loss | Unknown | Stay with known missed opportunity | Acceptable Stay | Unknown Stay |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for corridor in report["corridors"]:
        item = report["per_corridor_summary"][corridor["id"]]
        switches = item["model_switch_vs_model_stay"]
        kinds = switches["classes"]
        stays = item["by_mode"]["incident_profile"]["stay_outcomes"]
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            corridor.get("name", corridor["id"]), item["cases"], item["corridor_incidents"], switches["recommendations"],
            kinds.get("MEANINGFUL_GAIN", 0), kinds.get("PRACTICAL_TIE", 0), kinds.get("MEANINGFUL_LOSS", 0),
            kinds.get("UNKNOWN", 0), stays.get("MEANINGFUL_MISSED_ALTERNATIVE", 0),
            stays.get("ACCEPTABLE_STAY", 0), stays.get("UNKNOWN", 0)))
    lines += ["", "An acceptable Stay requires complete outcomes for all forecast-eligible supplied candidates. "
        "A known faster alternative establishes a missed opportunity even if other outcomes are unknown. "
        "This does not prove optimality over every possible route or an adaptive passenger who changes trains after the cutoff.", "",
        "## Raw MTA Stay / model Switch subset", "",
        "| Scope | Recommendations | Comparable | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for name, item in scopes[:4]:
        narrow = item["mta_stay_model_switch"]
        kinds = narrow["classes"]
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(name, narrow["cases"],
            narrow["comparable"], kinds.get("MEANINGFUL_GAIN", 0), kinds.get("PRACTICAL_TIE", 0),
            kinds.get("MEANINGFUL_LOSS", 0), kinds.get("UNKNOWN", 0)))
    lines += ["", "## Decision and missing-outcome coverage", "",
        "| Scope / mode | Stay | Switch | Other / abstain | Known missed selected journeys |",
        "|---|---:|---:|---:|---:|"]
    for name, item in scopes[:2]:
        for mode, value in item["by_mode"].items():
            actions = value["actions"]
            lines.append("| {} / {} | {} | {} | {} | {} |".format(name, mode,
                actions.get("STAY", 0), actions.get("SWITCH", 0),
                sum(v for k, v in actions.items() if k not in ("STAY", "SWITCH")),
                value["known_missed_selected_journeys"]))
    lines += ["", "A known missed selected train is an operational failure of that frozen journey, "
        "while its complete journey duration remains unknown. It is not a successful Switch or a practical tie.", "",
        "## Reproduction", "", "```sh",
        ".venv/bin/python algo/scripts/evaluate_november.py --prepare-inputs",
        "# Complete the independent input-only notice review, then:",
        ".venv/bin/python algo/scripts/evaluate_november.py --freeze-only",
        ".venv/bin/python algo/scripts/evaluate_november.py --verify-only",
        ".venv/bin/python algo/scripts/evaluate_november.py", "```", "",
        "Full denominators, per-mode actions, narrow raw-Stay/model-Switch comparisons, carried-in origins, "
        "new-date subsets, label quality counts and source hashes are in [the JSON report](november-2026-test.json). "
        "Walking sensitivity uses predeclared ±120-second perturbations of primary-event Stay/best-alternative walking components "
        "and is stored separately; it does not enlarge the performance denominator.", ""]
    (REPORTS / "november-2026-test.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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
        frozen, _, _ = verify()
        print({"stage": "VERIFIED", "cases": len(frozen["confirmed_case_ids"])}, flush=True)
    else:
        score()


if __name__ == "__main__":
    main()
