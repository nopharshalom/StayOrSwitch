#!/usr/bin/env python3
"""Freeze and report the user-requested weekday view of November predictions."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from datetime import date
from pathlib import Path
import multiprocessing
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo"), str(ROOT / "algo/scripts")]

import evaluate_november as base
from evaluate_preincident import artifact, dump, load, sha
from stayorswitch.google_corridor_replay import apply_review
from stayorswitch.november_replay import cohort_summary, date_subset
from stayorswitch.preincident_replay import local_time
from stayorswitch.severe import MODES


POLICY_PATH = ROOT / "data/manifests/november-weekday-reporting.json"
FREEZE = ROOT / "algo/reports/november-weekday-selection-frozen.json"
RESULT = ROOT / "algo/reports/november-weekday-test.json"
REPORT = ROOT / "algo/reports/november-weekday-test.md"
SELF = ROOT / "algo/scripts/report_november_weekdays.py"
LOCAL = ROOT / "algo/local/november-weekdays"
_FORECAST_RUNTIME = None


def read_policy():
    policy = load(POLICY_PATH)
    dates = policy["analysis_dates"]
    bounds = policy["original_analysis_bounds"]
    if (policy.get("stage") != "DECLARED_BEFORE_NOVEMBER_OUTCOME_SCORING"
            or policy.get("selection_uses_outcomes") is not False
            or len(dates) != policy["analysis_date_count"] or len(dates) != len(set(dates))
            or any(date.fromisoformat(day).weekday() >= 5 for day in dates)
            or any(not bounds[0] <= day <= bounds[1] for day in dates)
            or policy.get("timezone") != "America/New_York"
            or policy.get("training_dates") != base.POLICY["fit_dates"]
            or dates != sorted(dates)):
        raise ValueError("The weekday reporting policy is not a valid input-only calendar selection.")
    for key in ("addendum", "inherited_base_protocol"):
        item = policy[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Reporting protocol changed: " + key)
    return policy


def select_view(cases, dates):
    """Filter whole local dates, then recompute representatives from inputs."""
    allowed = set(dates)
    selected = [c for c in cases if local_time(c["decision_at"])[:10] in allowed]
    first = {}
    for case in sorted(selected, key=lambda c: (c["decision_at"], c["id"])):
        first.setdefault((case["corridor_id"], tuple(case["incident_ids"])), case)
    return selected, list(first.values())


def planned_timing(case):
    """Read input-reviewed case-specific timing; missing evidence stays unknown."""
    review = case["official_text_review"]
    active = set(review.get("planned_closure_active_case_ids") or [])
    inactive = set(review.get("planned_closure_inactive_case_ids") or [])
    if active.intersection(inactive):
        raise ValueError("Reviewed planned closure timing has conflicting case identities.")
    if case["id"] in active:
        return "CONFIRMED_ACTIVE"
    if case["id"] in inactive:
        return "CONFIRMED_INACTIVE"
    if review.get("planned_through_service_unavailable") is True:
        return "CONFIRMED_ACTIVE"
    if review.get("planned_closure_mentioned"):
        return "MENTIONED_TIMING_UNKNOWN"
    return "NO_PLANNED_CLOSURE_MENTION"


def provenance(policy, prepared):
    return {"base_prepared_inputs": artifact(base.PREPARED), "base_producer_provenance": prepared["provenance"],
        "text_review": artifact(base.REVIEW), "weekday_policy": artifact(POLICY_PATH),
        "addendum": policy["addendum"], "producer": artifact(SELF),
        "base_prediction_implementation_changed": False, "selection_reads_outcomes": False}


def qualified_inputs():
    """Reuse the existing all-date qualification and fixed two-hour windows."""
    prepared = base.verify_prepared()
    review = load(base.REVIEW)
    if review["prepared_inputs"] != artifact(base.PREPARED):
        raise ValueError("Notice review is bound to different raw inputs.")
    audits = review.get("audit_sources", [])
    if not audits:
        raise ValueError("Independent input notice audits must precede weekday forecasts.")
    for item in audits:
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("A bound input notice audit changed.")
    confirmed, excluded = apply_review(prepared["cases"], review)
    if any(c["official_text_review"]["confirmed_impact"] == "SEVERE"
            and c["official_text_review"].get("severity_basis") not in
                ("EXPLICIT_SEVERE_TEXT", "COMPLETE_FIXED_PATH_INTERRUPTION") for c in confirmed):
        raise ValueError("Qualified severe exposure requires its input-reviewed evidence basis.")
    cases, window_excluded, anchors = base.select_applicable_windows(confirmed, prepared["plans"])
    selection = {"raw_prepared": len(prepared["cases"]), "text_confirmed": len(confirmed),
        "text_excluded_or_unresolved": len(excluded), "all_date_fixed_window_cases": len(cases),
        "outside_applicable_window_or_no_anchor": len(window_excluded),
        "window_exclusion_reasons": dict(Counter(r["reason"] for r in window_excluded)),
        "review_group_statuses": dict(Counter(g["status"] for g in review["groups"]))}
    return prepared, review, cases, selection, window_excluded, anchors


def _forecast_day(day):
    """Fork worker: pure forecasts for one day, writing only its own shard."""
    started = time.monotonic()
    runtime = _FORECAST_RUNTIME
    cases = deepcopy(runtime["by_day"][day])
    by_cutoff = {}
    for case in cases:
        by_cutoff.setdefault(case["decision_at"], []).append(case)
    seen = set()
    for row in base.selected_snapshots(runtime["prepared"], by_cutoff):
        cache = {}
        for case in by_cutoff[row["cutoff"]]:
            corridor = runtime["corridors"][case["corridor_id"]]
            if corridor["id"] not in cache:
                cache[corridor["id"]] = {mode: base.predict(row["snapshots"], corridor, row["cutoff"], runtime["index"],
                    None if mode == "mta" else runtime["estimator"], mode) for mode in MODES}
            case["predictions"] = cache[corridor["id"]]
            base.assert_stay_parity(case["predictions"]["mta"], case["asof_mta_prediction"], case["reference_route_id"])
            seen.add(case["id"])
    if seen != {c["id"] for c in cases}:
        raise ValueError("A forecast worker is missing exact selected snapshots.")
    output = LOCAL / "forecast-shards" / (day + ".json.gz")
    dump(output, {"binding": runtime["binding"], "date": day, "cases": cases})
    return {"date": day, "artifact": artifact(output), "cases": len(cases),
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def prepare_parallel_forecasts(prepared, cases, workers=3):
    """Reuse fixed predictors across date workers, with deterministic parity."""
    global _FORECAST_RUNTIME
    output = LOCAL / "frozen-forecast-cases.json.gz"
    execution_path = LOCAL / "forecast-execution.json"
    binding = {"prepared_inputs": artifact(base.PREPARED), "review": artifact(base.REVIEW),
               "training": base.training_provenance()}
    if output.exists():
        # The original helper verifies the same metadata and exact Stay parity.
        result = base.prepare_forecasts(prepared, cases)
        execution = load(execution_path)
        if execution["binding"] != binding or execution["wrapper"] != artifact(SELF):
            raise ValueError("Existing parallel forecasts belong to different producer evidence.")
        return result, artifact(execution_path)
    started = time.monotonic()
    _, days = base.source_days()
    index = base.incident_index(days)
    estimator = base.ProfileEstimator(base.PROFILE)
    by_day = {}
    for case in cases:
        by_day.setdefault(local_time(case["decision_at"])[:10], []).append(case)
    _FORECAST_RUNTIME = {"prepared": prepared, "by_day": by_day,
        "corridors": {c["id"]: c for c in prepared["corridors"]},
        "index": index, "estimator": estimator, "binding": binding}
    worker_count = min(workers, max(1, len(by_day)))
    shards = []
    try:
        with ProcessPoolExecutor(max_workers=worker_count, mp_context=multiprocessing.get_context("fork")) as pool:
            futures = {pool.submit(_forecast_day, day): day for day in sorted(by_day)}
            for future in as_completed(futures):
                row = future.result()
                shards.append(row)
                print({"stage": "WEEKDAY_FORECAST_DAY", **row}, flush=True)
        saved = {}
        for row in sorted(shards, key=lambda r: r["date"]):
            item = row["artifact"]
            if sha(ROOT / item["path"]) != item["sha256"]:
                raise ValueError("Forecast shard changed before merge.")
            shard = load(ROOT / item["path"])
            if shard["binding"] != binding:
                raise ValueError("Forecast shard uses a different model or input selection.")
            for case in shard["cases"]:
                if case["id"] in saved:
                    raise ValueError("Duplicate forecast case across date workers.")
                saved[case["id"]] = case
        if set(saved) != {c["id"] for c in cases}:
            raise ValueError("Parallel forecasts do not exactly cover the selected weekdays.")
        for case in cases:
            forecast = saved[case["id"]]
            if {k: v for k, v in forecast.items() if k != "predictions"} != case:
                raise ValueError("A forecast worker changed input case evidence.")
            base.assert_stay_parity(forecast["predictions"]["mta"], case["asof_mta_prediction"], case["reference_route_id"])
            case["predictions"] = forecast["predictions"]
        # Select one case per local date using inputs only, and reconstruct all
        # three modes serially to verify the fork/cache execution path.
        parity_cases = [min(values, key=lambda c: (c["decision_at"], c["id"])) for _, values in sorted(by_day.items())]
        parity_by_time = {}
        for case in parity_cases:
            parity_by_time.setdefault(case["decision_at"], []).append(case)
        parity_count = 0
        for row in base.selected_snapshots(prepared, parity_by_time):
            for case in parity_by_time[row["cutoff"]]:
                corridor = _FORECAST_RUNTIME["corridors"][case["corridor_id"]]
                for mode in MODES:
                    predicted = base.predict(row["snapshots"], corridor, row["cutoff"], index,
                        None if mode == "mta" else estimator, mode)
                    if predicted != case["predictions"][mode]:
                        raise ValueError("Parallel and serial forecasts disagree.")
                    parity_count += 1
        if parity_count != len(parity_cases) * len(MODES):
            raise ValueError("Serial parity evidence does not cover every preselected date/mode pair.")
        if base.training_provenance() != binding["training"]:
            raise ValueError("Training profile changed during parallel forecasts.")
        execution = {"schema_version": "november-weekday-forecast-execution-v1", "binding": binding,
            "wrapper": artifact(SELF), "worker_count": worker_count, "partition": "LOCAL_CALENDAR_DATE",
            "merge": "EXACT_FROZEN_CASE_ID_ORDER", "selected_cases": len(cases),
            "serial_parity_case_ids": [c["id"] for c in parity_cases], "serial_mode_parity_checks": parity_count,
            "all_selected_stay_forecasts_match_input_scope": True, "outcomes_read": False,
            "shards": sorted(shards, key=lambda r: r["date"]),
            "elapsed_seconds": round(time.monotonic() - started, 3)}
        dump(execution_path, execution)
        dump(output, {"binding": binding, "execution": artifact(execution_path), "cases": cases})
    finally:
        _FORECAST_RUNTIME = None
    return artifact(output), artifact(execution_path)


def freeze_view():
    policy = read_policy()
    prepared, review, cases, selection, window_excluded, anchors = qualified_inputs()
    selected, primary = select_view(cases, policy["analysis_dates"])
    original_provenance = provenance(policy, prepared)
    training = base.training_provenance()
    # Only output destinations change. The imported prediction/scoring code,
    # input cases and all 29 supplied paths remain unchanged.
    base.LOCAL = LOCAL
    print({"stage": "WEEKDAY_FORECAST_START", "cases": len(selected), "primary": len(primary)}, flush=True)
    forecasts, execution = prepare_parallel_forecasts(prepared, selected)
    sensitivity = base.prepare_sensitivity(prepared, primary, artifact(base.REVIEW))
    if provenance(policy, prepared) != original_provenance or base.training_provenance() != training:
        raise ValueError("Weekday forecast provenance changed during generation.")
    selected_ids = {c["id"] for c in selected}
    value = {"schema_version": "november-weekday-view-freeze-v1",
        "stage": "FROZEN_BEFORE_NOVEMBER_OUTCOME_SCORING", "provenance": original_provenance,
        "analysis_dates": policy["analysis_dates"], "all_date_input_cases": len(cases),
        "selected_case_ids": [c["id"] for c in selected], "primary_case_ids": [c["id"] for c in primary],
        "excluded_weekend_case_ids": [c["id"] for c in cases if c["id"] not in selected_ids],
        "planned_closure_timing": {c["id"]: planned_timing(c) for c in selected},
        "per_corridor_counts": dict(Counter(c["corridor_id"] for c in selected)),
        "training": training, "frozen_forecast_cases": forecasts, "walking_sensitivity_inputs": sensitivity,
        "forecast_execution": execution,
        "independent_input_audits": review["audit_sources"], "selection_counts": selection,
        "window_excluded": window_excluded, "first_applicable_anchors": anchors,
        "selection_uses_outcomes": False, "weekend_three_mode_predictions_generated": False}
    if FREEZE.exists() and load(FREEZE) != value:
        raise ValueError("An existing weekday view freeze must not be overwritten.")
    dump(FREEZE, value)
    print({"stage": value["stage"], "weekday_cases": len(selected), "weekday_primary": len(primary),
           "calendar_dates": len(policy["analysis_dates"])}, flush=True)


def verify_view():
    policy = read_policy()
    frozen = load(FREEZE)
    prepared, review, cases, selection, window_excluded, anchors = qualified_inputs()
    if frozen["provenance"] != provenance(policy, prepared):
        raise ValueError("Weekday view provenance changed.")
    selected, primary = select_view(cases, policy["analysis_dates"])
    if (frozen["selected_case_ids"] != [c["id"] for c in selected]
            or frozen["primary_case_ids"] != [c["id"] for c in primary]
            or frozen["planned_closure_timing"] != {c["id"]: planned_timing(c) for c in selected}
            or frozen["training"] != base.training_provenance()
            or frozen["selection_counts"] != selection
            or frozen["first_applicable_anchors"] != anchors
            or frozen["window_excluded"] != window_excluded):
        raise ValueError("The calendar view or its input-only representatives changed.")
    for key in ("frozen_forecast_cases", "walking_sensitivity_inputs", "forecast_execution"):
        item = frozen[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen weekday predictions changed: " + key)
    forecast_file = load(ROOT / frozen["frozen_forecast_cases"]["path"])
    if forecast_file["binding"] != {"prepared_inputs": artifact(base.PREPARED),
            "review": artifact(base.REVIEW), "training": frozen["training"]}:
        raise ValueError("Weekday prediction binding changed.")
    execution = load(ROOT / frozen["forecast_execution"]["path"])
    if (forecast_file.get("execution") != frozen["forecast_execution"]
            or execution["wrapper"] != artifact(SELF)
            or execution["binding"] != forecast_file["binding"]
            or execution["selected_cases"] != len(selected)
            or execution["serial_mode_parity_checks"] != len(MODES) * len({local_time(c["decision_at"])[:10] for c in selected})):
        raise ValueError("Parallel forecast execution evidence does not match the frozen view.")
    forecasts = forecast_file["cases"]
    if len(forecasts) != len(selected):
        raise ValueError("Frozen weekday forecasts have a different case count.")
    for expected, actual in zip(selected, forecasts):
        if {k: v for k, v in actual.items() if k != "predictions"} != expected:
            raise ValueError("Frozen forecast differs from the input-qualified weekday case.")
        base.assert_stay_parity(actual["predictions"]["mta"], expected["asof_mta_prediction"], expected["reference_route_id"])
    return frozen, policy, prepared, forecasts


def score_view():
    frozen, policy, prepared, forecasts = verify_view()
    labels, label_sources, screening = base.read_outcomes()
    rows = [base.score_annotations(base.score_modes({k: v for k, v in c.items() if k != "predictions"},
        c["predictions"], labels, base.POLICY)) for c in forecasts]
    # The timing adjustment is itself frozen from inputs, not inferred from
    # missing Stay forecasts or selected-journey outcomes.
    for case in rows:
        case["planned_closure_timing"] = frozen["planned_closure_timing"][case["id"]]
        case["official_text_review"]["planned_through_service_unavailable"] = (
            case["planned_closure_timing"] == "CONFIRMED_ACTIVE")
    scored_path = LOCAL / "scored-cases.json.gz"
    dump(scored_path, rows)
    sensitivity_path = LOCAL / "scored-walking-sensitivity.json.gz"
    dump(sensitivity_path, base.score_sensitivity(frozen, rows, labels))
    primary_ids = set(frozen["primary_case_ids"])
    primary = [c for c in rows if c["id"] in primary_ids]
    report = {"schema_version": "november-weekday-results-v1", "policy": policy,
        "view_freeze": artifact(FREEZE), "all_date_input_preparation": artifact(base.PREPARED),
        "text_review": artifact(base.REVIEW), "scored_artifact": artifact(scored_path),
        "walking_sensitivity_artifact": artifact(sensitivity_path), "label_sources": label_sources,
        "endpoint_screening": screening, "training": frozen["training"],
        "selection_counts": frozen["selection_counts"], "weekend_outcomes_scored": False,
        "corridors": prepared["corridors"], "all_summary": cohort_summary(rows),
        "primary_summary": cohort_summary(primary),
        "newly_unused_dates_summary": cohort_summary([c for c in rows if date_subset(c)]),
        "newly_unused_dates_primary_summary": cohort_summary([c for c in primary if date_subset(c)]),
        "newly_unused_incident_primary_summary": cohort_summary([c for c in primary
            if date_subset(c) and local_time(c["first_family_receipt"])[:10] >= "2026-11-16"]),
        "severe_summary": cohort_summary([c for c in rows if c["official_text_review"]["confirmed_impact"] == "SEVERE"]),
        "planned_closure_timing_summaries": {status: cohort_summary([c for c in rows
            if c["planned_closure_timing"] == status]) for status in sorted({c["planned_closure_timing"] for c in rows})},
        "per_corridor_summary": {c["id"]: cohort_summary([r for r in rows if r["corridor_id"] == c["id"]])
            for c in prepared["corridors"]},
        "per_corridor_primary_summary": {c["id"]: cohort_summary([r for r in primary if r["corridor_id"] == c["id"]])
            for c in prepared["corridors"]},
        "per_date_summary": {day: cohort_summary([c for c in rows if local_time(c["decision_at"])[:10] == day])
            for day in policy["analysis_dates"]},
        "cases": [dict(base.compact_case(c, primary_ids), planned_closure_timing=c["planned_closure_timing"]) for c in rows]}
    dump(RESULT, report)
    write_report(report)
    print({"stage": "WEEKDAY_VIEW_SCORED", "all_summary": report["all_summary"],
           "primary_summary": report["primary_summary"]}, flush=True)


def write_report(report):
    lines = ["# November weekday Stay/Switch results", "",
        "Primary reporting dates: **November 2–6, 9–13 and 16–18, 2026**, 13 Monday–Friday dates in New York. "
        "The user requested this calendar view before outcome scoring. The October 1–31 model, five fixed Google Stay paths, "
        "29 supplied paths in total, thresholds, original two-hour incident windows and prediction method are unchanged. "
        "November 19 is outcome boundary evidence only.", "",
        "November 2–15 overlaps prior project exploration. November 16–18 is shown separately; the complete period is not "
        "claimed to be an untouched final test. Current Google minutes are not historical outcomes or proof that Stay was "
        "historically fastest. Raw-MTA actions are this project's rule applied to unmodified forecasts, not official MTA routing advice.", "",
        "Exposure means a text-qualified unplanned service problem on Stay, including some unplanned service changes; "
        "it does not establish that the particular selected train's ETA worsened. Severe exposure distinguishes explicit severe "
        "wording from an official notice describing complete unplanned loss of the fixed through path. This is notice evidence, "
        "not independent proof of physical closure; through-service forecast conflicts remain recorded in the notice review. "
        "Closure cases with no usable Stay forecast remain unknown. "
        "Mixed planned closure mentions retain input-reviewed active/inactive/unknown timing and are not attributed to an unplanned cause.", "",
        "Outcomes use exact forecast-selected trains, screened final MTA prediction proxies and declared walking times. "
        "Every needed endpoint requires a matching identity, archived confirmation and last observation within 180 seconds. "
        "A missed selected train is an operational failure with unknown complete travel time. A predicted gain of at least "
        "5 minutes triggers Switch; outcome differences within ±3 minutes are practical ties.", "",
        "## Main outcome counts", "",
        "| Scope | Checkpoints | Corridor/publisher families | Unique publisher IDs | Switch | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    scopes = [("All weekday checkpoints", report["all_summary"]), ("Weekday representatives", report["primary_summary"]),
        ("November 16–18", report["newly_unused_dates_summary"]),
        ("November 16–18 representatives", report["newly_unused_dates_primary_summary"]),
        ("Qualified severe weekday checkpoints", report["severe_summary"])]
    for name, summary in scopes:
        switches = summary["model_switch_vs_model_stay"]
        kinds = switches["classes"]
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(name, summary["cases"],
            summary["corridor_incidents"], summary["unique_incident_count"], switches["recommendations"],
            kinds.get("MEANINGFUL_GAIN", 0), kinds.get("PRACTICAL_TIE", 0), kinds.get("MEANINGFUL_LOSS", 0), kinds.get("UNKNOWN", 0)))
    lines += ["", "The primary representative is recomputed from weekday inputs for each corridor/publisher incident family; "
        "it is not a filtered copy of the old all-date primary list. Repeated checkpoints, train pairs and publisher IDs are "
        "not independent causal incidents or passenger journeys. Different publisher families can describe a shared underlying "
        "problem; the input notice audit records such links without changing frozen grouping.", "",
        "## Comparison against the raw-MTA policy", "",
        "| Scope / comparison | Eligible actions | Comparable | Faster >3 min | Tie | Slower >3 min | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for name, summary in scopes[:4]:
        for key in ("time_vs_mta", "incident_vs_mta", "incident_vs_time"):
            row = summary["paired_policies"][key]
            kinds = row["classes"]
            lines.append("| {} / {} | {} | {} | {} | {} | {} | {} |".format(name, key, row["eligible_actions"],
                row["comparable"], kinds.get("MEANINGFUL_GAIN", 0), kinds.get("PRACTICAL_TIE", 0),
                kinds.get("MEANINGFUL_LOSS", 0), kinds.get("UNKNOWN", 0)))
    lines += ["", "Each comparison uses the actual journey selected by each policy, including its chosen train sequence. "
        "It does not substitute the unconditional fastest raw-MTA candidate.", "",
        "## Raw-MTA Stay / model Switch", "",
        "| Scope | Recommendations | Comparable | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for name, summary in scopes[:4]:
        row = summary["mta_stay_model_switch"]
        kinds = row["classes"]
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(name, row["cases"], row["comparable"],
            kinds.get("MEANINGFUL_GAIN", 0), kinds.get("PRACTICAL_TIE", 0), kinds.get("MEANINGFUL_LOSS", 0), kinds.get("UNKNOWN", 0)))
    lines += ["", "## Five-corridor weekday detail", "",
        "| Corridor | Checkpoints | Families | Model Switch | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for corridor in report["corridors"]:
        row = report["per_corridor_summary"][corridor["id"]]
        switch = row["model_switch_vs_model_stay"]
        kinds = switch["classes"]
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(corridor.get("name", corridor["id"]),
            row["cases"], row["corridor_incidents"], switch["recommendations"], kinds.get("MEANINGFUL_GAIN", 0),
            kinds.get("PRACTICAL_TIE", 0), kinds.get("MEANINGFUL_LOSS", 0), kinds.get("UNKNOWN", 0)))
    lines += ["", "| Corridor | Acceptable Stay | Stay with known missed opportunity | Unknown Stay | Known missed selected journeys |",
        "|---|---:|---:|---:|---:|"]
    for corridor in report["corridors"]:
        row = report["per_corridor_summary"][corridor["id"]]["by_mode"]["incident_profile"]
        stays = row["stay_outcomes"]
        lines.append("| {} | {} | {} | {} | {} |".format(corridor.get("name", corridor["id"]),
            stays.get("ACCEPTABLE_STAY", 0), stays.get("MEANINGFUL_MISSED_ALTERNATIVE", 0),
            stays.get("UNKNOWN", 0), row["known_missed_selected_journeys"]))
    lines += ["", "Acceptable Stay requires complete outcomes for all forecast-eligible supplied candidates. A known faster "
        "alternative establishes a missed opportunity even when other outcomes are missing. These are fixed-selected-journey "
        "comparisons, not exhaustive navigation or proof against an adaptive passenger taking another earlier train on Stay.", "",
        "The [machine-readable weekday report](november-weekday-test.json) includes every case, all three modes, primary and "
        "date-specific counts, severe evidence bases and planned-closure timing strata. The [calendar view freeze](november-weekday-selection-frozen.json) "
        "binds the exact input-selected case IDs. The [all-date input inventory](november-2026-candidate-selection.json) "
        "and full notice review remain secondary audit evidence. Weekend raw Stay forecasts exist for scope auditing only; "
        "weekend three-mode performance and outcomes were not scored.", ""]
    REPORT.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--freeze-only", action="store_true")
    group.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.freeze_only:
        freeze_view()
    elif args.verify_only:
        frozen, _, _, _ = verify_view()
        print({"stage": "WEEKDAY_VIEW_VERIFIED", "cases": len(frozen["selected_case_ids"])}, flush=True)
    else:
        score_view()


if __name__ == "__main__":
    main()
