#!/usr/bin/env python3
"""Freeze same-physical-train forecast revisions before separate proxy scoring."""

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, time as datetime_time, timedelta
from itertools import chain
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo"), str(ROOT / "algo/scripts")]

from data.delay_profiles import IncidentIndex, ProfileEstimator
from data.october import read_labels, read_snapshots
from data.supplemental_endpoints import merge_endpoint_labels
from stayorswitch.feed_revision_replay import POLICY, choose_pair, physical_sequence, representatives
from stayorswitch.october_evaluation import latest_at_cutoffs, local_context, project_snapshot, reference_service_context, summarize
from stayorswitch.preincident_replay import local_time, score_modes
from stayorswitch.severe import MODES, decide, predict_routes
from evaluate_preincident import artifact, code_provenance, dump, load, sha

LOCAL = ROOT / "algo/local/october-feed-revision"
REPORTS = ROOT / "algo/reports"
PREFIX = "feed-revision"


def path(suffix):
    return REPORTS / (PREFIX + suffix)


def provenance():
    names = ("algo/stayorswitch/feed_revision_replay.py", "algo/scripts/evaluate_feed_revision.py",
             "data/supplemental_endpoints.py")
    return {"unchanged_original_and_previous_replay": code_provenance(), "policy": POLICY,
            "new_code_sha256": {name: sha(ROOT / name) for name in names}}


def prediction(snapshots, cutoff, index, estimator=None, mode="mta", routes=None):
    return predict_routes(snapshots, routes or POLICY["routes"], cutoff, mode=mode,
                          estimator=estimator, incident_index=index,
                          train_max_age_seconds=180, alerts_max_age_seconds=300)


def cutoffs():
    zone = ZoneInfo("America/New_York")
    start = datetime.combine(date.fromisoformat(POLICY["test_dates"][0]), datetime_time(), zone).timestamp()
    stop = datetime.combine(date.fromisoformat(POLICY["test_dates"][1]) + timedelta(days=1), datetime_time(), zone).timestamp()
    return list(range(int(start), int(stop), POLICY["decision_grid_seconds"]))


def prepare():
    started = time.monotonic()
    initial_provenance = provenance()
    original_manifest = ROOT / "data/manifests/october.json"
    supplemental_manifest = ROOT / "data/manifests/preincident-inputs.json"
    source, extra = load(original_manifest), load(supplemental_manifest)
    if extra.get("stage") != "PREPARED":
        raise ValueError("Corrected full-span source is not prepared.")
    days = {d["date"]: d for d in source["days"]}
    extra_days = {d["date"]: d for d in extra["days"]}
    sources = {str(p.relative_to(ROOT)): sha(p) for p in (original_manifest, supplemental_manifest)}
    def alerts():
        for day in sorted(days):
            item = days[day]["outputs"]["alerts"]
            p = ROOT / item["path"]
            if sha(p) != item["sha256"]:
                raise ValueError("Original alert source changed.")
            sources[item["path"]] = item["sha256"]
            yield from read_snapshots(p)
    index = IncidentIndex(alerts(), max_age_seconds=300)
    grid = cutoffs()
    snapshots, forecasts, carry = {}, {}, {}
    day = date.fromisoformat(POLICY["test_dates"][0]) - timedelta(days=1)
    final = date.fromisoformat(POLICY["test_dates"][1])
    while day <= final:
        day_text = day.isoformat()
        items = [days[day_text]["outputs"]["snapshots"], extra_days[day_text]["outputs"]["snapshots"]]
        for item in items:
            if sha(ROOT / item["path"]) != item["sha256"]:
                raise ValueError("Snapshot source changed.")
            sources[item["path"]] = item["sha256"]
        old = (s for s in read_snapshots(ROOT / items[0]["path"]) if s["feed_id"] in {"ace", "subway-alerts"})
        new = (s for s in read_snapshots(ROOT / items[1]["path"]) if s["feed_id"] in {"bdfm", "numbered"})
        selected_times = [t for t in grid if local_time(t)[:10] == day_text]
        selected, carry = latest_at_cutoffs((project_snapshot(s, POLICY["routes"]) for s in chain(old, new)), selected_times, carry)
        snapshots.update(selected)
        for cutoff in selected_times:
            forecasts[cutoff] = prediction(selected[cutoff], cutoff, index)
        print({"stage": "INPUT_DAY", "day": day_text, "cutoffs": len(selected_times),
               "elapsed_seconds": round(time.monotonic() - started, 1)}, flush=True)
        day += timedelta(days=1)
    pairs, failures = [], Counter()
    for t0 in grid:
        for lag in POLICY["reassessment_lags_seconds"]:
            if t0 + lag not in forecasts:
                failures["LATER_CUTOFF_OUTSIDE_TEST_WEEK"] += 1
                continue
            candidate, reason = choose_pair(forecasts[t0], forecasts[t0 + lag])
            if candidate is None:
                failures[reason] += 1
            else:
                pairs.append(candidate)
    selected = deepcopy(representatives(pairs))
    estimator = ProfileEstimator(ROOT / "data/artifacts/october-2026-profiles-train.json.gz")
    for case in selected:
        t0, t1 = case["anchor"]["decision_at"], case["decision_at"]
        case["predictions"] = {mode: forecasts[t1] if mode == "mta" else
            prediction(snapshots[t1], t1, index, estimator, mode) for mode in MODES}
        case["walking_sensitivity"] = []
        for template in POLICY["routes"]:
            for component in ("access_walk_seconds", "egress_walk_seconds"):
                for delta in POLICY["walking_sensitivity_seconds"]:
                    routes = deepcopy(POLICY["routes"])
                    next(r for r in routes if r["id"] == template["id"])[component] += delta
                    before = prediction(snapshots[t0], t0, index, routes=routes)
                    after = prediction(snapshots[t1], t1, index, routes=routes)
                    variant_policy = dict(POLICY, routes=routes)
                    variant, reason = choose_pair(before, after, variant_policy)
                    adjusted = prediction(snapshots[t1], t1, index, estimator, "incident_profile", routes)
                    advice = decide(adjusted, case["reference_route_id"], switch_margin_seconds=300, require_severe=False)
                    case["walking_sensitivity"].append({"route_id": template["id"], "component": component,
                        "delta_seconds": delta, "same_qualified_physical_pair": variant is not None and
                            variant["physical_sequence_key"] == case["physical_sequence_key"],
                        "selection_failure": reason, "strict_decision": advice["strict_decision"],
                        "conditional_timing_decision": advice["conditional_timing_decision"]})
    if provenance() != initial_provenance:
        raise ValueError("Code changed during selection.")
    prepared = {"provenance": initial_provenance, "input_sources": sources,
        "selection_stage_reads_outcome_labels": False,
        "earlier_test_explorations_already_scored": True,
        "grid_cutoffs": grid, "attempted_pairs": len(grid) * len(POLICY["reassessment_lags_seconds"]),
        "rejection_counts": dict(failures), "all_qualifying_pairs": pairs, "cases": selected}
    output = LOCAL / "prepared-inputs.json.gz"
    dump(output, prepared)
    proposal = {"policy": POLICY, "prepared_inputs": artifact(output), "grid_cutoffs": len(grid),
        "attempted_pairs": prepared["attempted_pairs"], "rejection_counts": dict(failures),
        "qualifying_pair_count": len(pairs), "distinct_physical_train_runs": len(selected),
        "representative_selection_uses_outcomes": False,
        "representatives": [{k: c[k] for k in ("id", "physical_sequence", "decision_at", "local_time",
            "reference_route_id", "planning_interval_seconds", "absolute_arrival_revision_seconds",
            "duration_deterioration_seconds", "leg_forecast_revisions", "anchor")} for c in selected]}
    dump(path("-candidate-selection.json"), proposal)
    print({"stage": "INPUT_ONLY_PREPARED", "pairs": len(pairs), "runs": len(selected),
           "rejections": dict(failures), "seconds": round(time.monotonic() - started, 1)}, flush=True)


def freeze():
    prepared_path = LOCAL / "prepared-inputs.json.gz"
    prepared = load(prepared_path)
    if provenance() != prepared["provenance"]:
        raise ValueError("Prepared code changed.")
    for name, expected in prepared["input_sources"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Selection source changed: " + name)
    frozen = {"schema_version": "same-train-revision-freeze-v1", "study_status": "POST_HOC_EXPLORATORY_TEST_SEARCH",
        "selection_uses_outcomes": False, "provenance": prepared["provenance"],
        "prepared_inputs": artifact(prepared_path),
        "candidate_inventory": artifact(path("-candidate-selection.json")),
        "supplemental_label_manifest": artifact(ROOT / "data/manifests/preincident-inputs.json"),
        "representative_case_ids": [c["id"] for c in prepared["cases"]]}
    target = path("-selection-frozen.json")
    if target.exists() and load(target) != frozen:
        raise ValueError("Existing freeze differs; do not overwrite.")
    dump(target, frozen)
    print({"stage": "FROZEN", "cases": len(frozen["representative_case_ids"])}, flush=True)


def minutes(value):
    return "unknown" if value is None else "{:.2f}".format(value / 60)


def score():
    frozen = load(path("-selection-frozen.json"))
    if provenance() != frozen["provenance"]:
        raise ValueError("Frozen code changed.")
    for name in ("prepared_inputs", "candidate_inventory", "supplemental_label_manifest"):
        item = frozen[name]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen artifact changed.")
    prepared = load(ROOT / frozen["prepared_inputs"]["path"])
    cases = prepared["cases"]
    if [c["id"] for c in cases] != frozen["representative_case_ids"]:
        raise ValueError("Representative selection changed.")
    source = load(ROOT / "data/manifests/october.json")
    label_sources, labels = {}, {}
    for day in sorted({local_time(c["decision_at"])[:10] for c in cases}):
        for label_day in ((date.fromisoformat(day) - timedelta(days=1)).isoformat(), day):
            item = source["daily_labels"][label_day]
            if item["path"] in label_sources:
                continue
            if sha(ROOT / item["path"]) != item["sha256"]:
                raise ValueError("Original endpoint labels changed.")
            label_sources[item["path"]] = item["sha256"]
            for identity, endpoints in read_labels(ROOT / item["path"]).items():
                if identity in labels and labels[identity] != endpoints:
                    raise ValueError("Conflicting original endpoints.")
                labels[identity] = endpoints
    extra = load(ROOT / frozen["supplemental_label_manifest"]["path"])
    item = extra["labels"]
    if sha(ROOT / item["path"]) != item["sha256"]:
        raise ValueError("Corrected D16 labels changed.")
    label_sources[item["path"]] = item["sha256"]
    labels = merge_endpoint_labels(labels, read_labels(ROOT / item["path"]), "D16S")
    config = load(ROOT / "data/config/october.json")
    evaluated = []
    for case in cases:
        row = score_modes(case, case["predictions"], labels, POLICY)
        row.update(local_context(row["decision_at"], config))
        row["reference"] = next(r for r in row["asof_mta_prediction"]["routes"] if r["id"] == row["reference_route_id"])
        row["reference_service_context"] = reference_service_context(row["reference"])
        evaluated.append(row)
    output = LOCAL / "scored-cases.json.gz"
    dump(output, evaluated)
    result = summarize(evaluated, grouped=False)
    result["reference_service_context"]["policy"] = POLICY["reference_policy"]
    result["distinct_physical_train_runs"] = len(evaluated)
    result["baseline_near_tie_counts"] = dict(Counter(str(c["anchor"]["baseline_near_tie"]) for c in evaluated))
    result["counterfactual"] = {}
    for mode in MODES:
        values = [c["modes"][mode]["alternative_counterfactual"]["inferred_savings_seconds"] for c in evaluated]
        known = [v for v in values if v is not None]
        result["counterfactual"][mode] = {"comparable": len(known), "unknown": len(values) - len(known),
            "meaningful_gains": sum(v > 180 for v in known), "practical_ties": sum(abs(v) <= 180 for v in known),
            "meaningful_losses": sum(v < -180 for v in known)}
    report = {"stage": "COMPLETE_EXPLORATORY_TEST", "policy": POLICY, "summary": result,
        "selection_freeze": artifact(path("-selection-frozen.json")), "source_label_sha256": label_sources,
        "scored_artifact": artifact(output), "all_representatives": evaluated}
    dump(path("-test.json"), report)
    lines = ["# Same-train forecast revision replay", "",
        "This separate post-hoc exploratory search corrects the headway ambiguity in the earlier official-delay cohort. It uses the fixed October 25–31 five-minute clock grid and 5/10/15/30-minute reassessment lags, with no outcome-based case selection. Original models, thresholds and earlier reports are unchanged.", "",
        "Origin: {}. Destination: {}. The three supplied paths are 7, E and F with the already-declared walking assumptions; this is not an exhaustive citywide or historical Google route claim.".format(POLICY["origin"], POLICY["destination"]), "",
        "At T0 all three candidates have complete timing and comparison evidence, and the fastest raw-MTA route is fresh NORMAL. At T1 that route must still select the same physical train and stop pair as its best catchable train, while its absolute destination-arrival forecast has moved at least five minutes later. Remaining duration need not increase by five minutes: elapsed clock time is reported separately. Both decisions mean departing anew from the same street origin, still unboarded.", "",
        "Official notices are displayed as context, but are not required for this direct feed-revision definition. A later forecast is evidence of forecast slippage, not independent proof of its cause or physical arrival. One representative per physical run is frozen using earliest T1 then earliest T0. All qualifying repeated pairs remain in the input artifact; none were selected using final outcomes.", "",
        "Fixed pairs attempted: **{}**; qualifying pairs: **{}**; distinct physical runs: **{}**.".format(prepared["attempted_pairs"], len(prepared["all_qualifying_pairs"]), len(evaluated)), "",
        "| Mode | Strict actions | Conditional timing actions | Scorable strict Switch | Strict gains / ties / losses | Unknown strict Switch |",
        "|---|---|---|---:|---|---:|"]
    for mode in MODES:
        strict = result["modes"][mode]["strict_decision"]
        conditional = result["modes"][mode]["conditional_timing_decision"]
        cls = strict["outcome_classes"]
        lines.append("| {} | {} | {} | {} | {} / {} / {} | {} |".format(mode, strict["actions"], conditional["actions"], strict["switches_with_comparable_outcomes"], cls.get("MEANINGFUL_GAIN", 0), cls.get("PRACTICAL_TIE", 0), cls.get("MEANINGFUL_LOSS", 0), strict["switches_without_comparable_outcomes"]))
    lines += ["", "The forecast-best non-Stay alternative is also compared even when the algorithm says STAY; hindsight does not choose this alternative.", "",
        "| Mode | Comparable alternative pairs | Gains >3 min | Ties | Losses >3 min | Unknown |", "|---|---:|---:|---:|---:|---:|"]
    for mode, row in result["counterfactual"].items():
        lines.append("| {} | {} | {} | {} | {} | {} |".format(mode, row["comparable"], row["meaningful_gains"], row["practical_ties"], row["meaningful_losses"], row["unknown"]))
    lines += ["", "## All input-selected representatives", ""]
    for case in evaluated:
        anchor = case["anchor"]
        lines += ["### {} — {}".format(case["local_time"], case["reference_route_id"]), "",
            "T0 {}; lead {} min; near tie: {}. Planning interval {} min. Same-train absolute arrival revision +{} min; remaining-duration change {} min.".format(anchor["local_time"], minutes(anchor["winner_lead_seconds"]), anchor["baseline_near_tie"], minutes(case["planning_interval_seconds"]), minutes(case["absolute_arrival_revision_seconds"]), minutes(case["duration_deterioration_seconds"])), "",
            "| Route | T0 MTA duration, min | T1 MTA duration, min |", "|---|---:|---:|"]
        for before in anchor["prediction"]["routes"]:
            after = next(r for r in case["asof_mta_prediction"]["routes"] if r["id"] == before["id"])
            lines.append("| {} | {} | {} |".format(before["id"], minutes(before.get("total_duration_seconds")), minutes(after.get("total_duration_seconds"))))
        for revision in case["leg_forecast_revisions"]:
            lines += ["", "Same physical run `{}`: departure forecast {} → {} ({} min); arrival forecast {} → {} ({} min).".format(revision["current_normalized_trip_id"], local_time(revision["baseline_departure_at"]), local_time(revision["current_departure_at"]), minutes(revision["departure_shift_seconds"]), local_time(revision["baseline_arrival_at"]), local_time(revision["current_arrival_at"]), minutes(revision["arrival_shift_seconds"]))]
        lines += ["", "| Mode | Strict / conditional action | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |", "|---|---|---|---|---|---:|"]
        for mode in MODES:
            value = case["modes"][mode]
            cf = value["alternative_counterfactual"]
            current = next(r for r in value["routes"] if r["id"] == case["reference_route_id"])
            alt = next((r for r in value["routes"] if r["id"] == cf["predicted_alternative_route_id"]), {})
            a = value["outcomes"][case["reference_route_id"]]
            b = cf["alternative_outcome"]
            lines.append("| {} | {} / {} | {} | {} / {} | {} / {} | {} |".format(mode, value["strict_decision"]["action"], value["conditional_timing_decision"]["action"], cf["predicted_alternative_route_id"], minutes(current.get("total_duration_seconds")), minutes(alt.get("total_duration_seconds")), minutes(a.get("total_duration_seconds")), minutes(b.get("total_duration_seconds")), minutes(cf["inferred_savings_seconds"])))
        lines += ["", "As-of Stay service context: `{}`. Same pair remains qualified in {}/{} single-component +/-120-second walking variations.".format(case["reference"]["context"], sum(v["same_qualified_physical_pair"] for v in case["walking_sensitivity"]), len(case["walking_sensitivity"])), ""]
    lines += ["## Limits", "", "Outcomes are screened final MTA prediction proxies plus authored walking, not independent actual passenger arrivals. Missed selected trains and missing endpoint evidence remain unknown. The test week was already explored, so this is diagnostic evidence, not a new untouched test or a general success rate. Exact selected trains, official notices, corrections, quality flags and all negative/unknown representatives are preserved in JSON.", ""]
    path("-test.md").write_text("\n".join(lines))
    print({"stage": report["stage"], "runs": len(evaluated), "summary": result}, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-inputs", action="store_true")
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_inputs:
        prepare()
    elif args.freeze_only:
        freeze()
    else:
        score()


if __name__ == "__main__":
    main()
