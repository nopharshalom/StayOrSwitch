#!/usr/bin/env python3
"""Freeze and evaluate the separately versioned November boarding repair.

The old policy and the repaired policy share identical route-execution
outcomes. Exact forecast-selected-train outcomes remain separate diagnostics.
This is a post-hoc regression study of previously examined November dates.
"""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
import multiprocessing
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo"), str(ROOT / "algo/scripts")]

import evaluate_november as base
from evaluate_preincident import artifact, dump, load, sha
from stayorswitch.incremental_switch_replay import classify
from stayorswitch.november_replay import cohort_summary, date_subset, score_annotations
from stayorswitch.october_evaluation import _decision_scores, outcome_for
from stayorswitch.preincident_replay import local_time
from stayorswitch.severe import MODES, decide
from report_november_weekdays import planned_timing


SELF = ROOT / "algo/scripts/evaluate_november_repair.py"
LOCAL = ROOT / "algo/local/november-repair"
POLICY_PATH = ROOT / "data/config/november-repair-policy.json"
PROTOCOL = ROOT / "algo/docs/november-repair-plan.md"
OLD_FREEZE = ROOT / "algo/reports/november-weekday-selection-frozen.json"
OLD_REPORT = ROOT / "algo/reports/november-weekday-test.json"
PREDICTIONS = LOCAL / "frozen-forecast-cases.json.gz"
SENSITIVITY = LOCAL / "frozen-margin-sensitivity.json.gz"
EXECUTION = LOCAL / "forecast-execution.json"
FREEZE = ROOT / "algo/reports/november-repair-selection-frozen.json"
RESULT = ROOT / "algo/reports/november-repair-test.json"
REPORT = ROOT / "algo/reports/november-repair-test.md"
ARCHIVE_PATH = ROOT / "data/processed/november-repair-v2/route-events.json.gz"
ARCHIVE_MANIFEST = ROOT / "data/manifests/november-route-archive-v2.json"
_RUNTIME = None


def read_policy():
    policy = load(POLICY_PATH)
    required = {"boarding_margin_seconds": 120, "execution_horizon_seconds": 7200,
                "switch_margin_seconds": 300, "tie_margin_seconds": 180}
    for key, expected in required.items():
        if policy.get(key) != expected:
            raise ValueError("Repair policy differs from the authorized initial version: " + key)
    if policy.get("boarding_margin_sensitivity_seconds") != [60, 180]:
        raise ValueError("The declared sensitivity margins must be 60 and 180 seconds.")
    if (policy.get("retrain") is not False or policy.get("sensitivity_scope") != "197_PRIMARY_CASES"
            or policy.get("initial_recommendation_uses_future_outcomes") is not False
            or policy.get("execution_selects_on_final_destination_arrival") is not False
            or policy.get("same_executor_for_old_and_new_policies") is not True
            or policy.get("max_feed_gap_seconds") != 120 or policy.get("max_endpoint_age_seconds") != 180):
        raise ValueError("The repair changes its declared model, evidence or execution contract.")
    return policy


def original_inputs():
    """Load prior frozen input-only predictions; no outcome records are read."""
    prepared = base.verify_prepared()
    frozen = load(OLD_FREEZE)
    item = frozen["frozen_forecast_cases"]
    if sha(ROOT / item["path"]) != item["sha256"]:
        raise ValueError("Original frozen input predictions changed.")
    saved = load(ROOT / item["path"])
    cases = saved["cases"]
    if ([c["id"] for c in cases] != frozen["selected_case_ids"]
            or len(cases) != 2306 or len(frozen["primary_case_ids"]) != 197):
        raise ValueError("The repair must retain every original weekday case and representative.")
    if frozen["training"] != base.training_provenance():
        raise ValueError("The repair must retain the full-October model.")
    return prepared, frozen, cases


def prediction_binding(prepared, old_freeze):
    return {"schema_version": "november-repair-prediction-binding-v1",
        "producer": artifact(SELF), "prediction_module": artifact(ROOT / "algo/stayorswitch/boarding_safe.py"),
        "policy": artifact(POLICY_PATH), "protocol": artifact(PROTOCOL),
        "original_input_freeze": artifact(OLD_FREEZE),
        "original_frozen_predictions": old_freeze["frozen_forecast_cases"],
        "prepared_inputs": artifact(base.PREPARED), "training": base.training_provenance(),
        "preserved_original_provenance": prepared["provenance"],
        "prior_november_outcomes_known": True, "new_forecasts_read_outcomes": False}


def scoring_producers():
    names = ("algo/scripts/evaluate_november_repair.py", "algo/stayorswitch/boarding_safe.py",
        "algo/stayorswitch/route_execution.py", "algo/stayorswitch/repair_metrics.py",
        "data/route_archive.py", "data/november_outcomes.py")
    return {name: sha(ROOT / name) for name in names}


def predict(snapshots, corridor, cutoff, index, estimator, mode, margin):
    from stayorswitch.boarding_safe import predict_routes
    value = predict_routes(snapshots, corridor["routes"], cutoff, mode=mode,
        estimator=None if mode == "mta" else estimator, incident_index=index,
        train_max_age_seconds=base.POLICY["train_max_age_seconds"],
        alerts_max_age_seconds=base.POLICY["alerts_max_age_seconds"], boarding_margin_seconds=margin)
    # The repair does not silently complete or discard unresolved provider paths.
    for candidate in corridor.get("unavailable_candidates", []):
        value["routes"].append({"id": candidate["id"], "name": candidate.get("name", candidate["id"]),
            "family": candidate.get("family", "UNRESOLVED_GOOGLE_PATH"), "status": "UNAVAILABLE",
            "mode": mode, "eta": None, "total_duration_seconds": None,
            "timing_eligible": False, "comparison_eligible": False,
            "selected_legs": [], "rejected": [], "leg_candidate_counts": [], "components": None,
            "reason_codes": candidate.get("reason_codes", ["PROVIDER_PATH_NORMALIZATION_FAILED"]),
            "context": {"state": "UNKNOWN", "evidence_status": "UNKNOWN", "incident_ids": [],
                        "severe_incident_ids": [], "ambiguous_scope": True},
            "severe_incident_ids": [], "provider_unavailable_candidate": deepcopy(candidate)})
    return value


def _forecast_day(day):
    runtime = _RUNTIME
    started = time.monotonic()
    day_cases = runtime["by_day"][day]
    target = LOCAL / "forecast-shards-v2" / (day + ".json.gz")
    expected_ids = [c["id"] for c in day_cases]
    if target.exists():
        saved = load(target)
        if saved["binding"] != runtime["binding"] or [c["id"] for c in saved["cases"]] != expected_ids:
            raise ValueError("Existing repair forecast shard uses different inputs or code.")
        return {"date": day, "artifact": artifact(target), "cases": len(day_cases), "reused": True}
    by_cutoff = defaultdict(list)
    for case in day_cases:
        by_cutoff[case["decision_at"]].append(case)
    outputs, sensitivity = {}, []
    for row in base.selected_snapshots(runtime["prepared"], by_cutoff):
        for case in by_cutoff[row["cutoff"]]:
            corridor = runtime["corridors"][case["corridor_id"]]
            predictions = {mode: predict(row["snapshots"], corridor, row["cutoff"], runtime["index"],
                runtime["estimator"], mode, runtime["policy"]["boarding_margin_seconds"]) for mode in MODES}
            outputs[case["id"]] = dict(case, predictions=predictions)
            if case["id"] in runtime["primary_ids"]:
                for margin in runtime["policy"]["boarding_margin_sensitivity_seconds"]:
                    sensitivity.append({"case_id": case["id"], "boarding_margin_seconds": margin,
                        "predictions": {mode: predict(row["snapshots"], corridor, row["cutoff"], runtime["index"],
                            runtime["estimator"], mode, margin) for mode in MODES}})
    if set(outputs) != set(expected_ids):
        raise ValueError("Repair forecast shard is missing exact selected snapshots.")
    dump(target, {"binding": runtime["binding"], "date": day,
                  "cases": [outputs[key] for key in expected_ids], "sensitivity": sensitivity})
    return {"date": day, "artifact": artifact(target), "cases": len(day_cases),
        "sensitivity_variants": len(sensitivity), "elapsed_seconds": round(time.monotonic() - started, 3)}


def prepare_forecasts(workers=3):
    global _RUNTIME
    policy = read_policy()
    prepared, old_freeze, original = original_inputs()
    binding = prediction_binding(prepared, old_freeze)
    if PREDICTIONS.exists():
        saved, variants, execution = load(PREDICTIONS), load(SENSITIVITY), load(EXECUTION)
        if any(value["binding"] != binding for value in (saved, variants, execution)):
            raise ValueError("Existing repair forecasts differ from the current frozen producer.")
        if [c["id"] for c in saved["cases"]] != old_freeze["selected_case_ids"]:
            raise ValueError("Existing repair forecast membership differs.")
        return
    started = time.monotonic()
    cases = [{k: deepcopy(v) for k, v in c.items() if k != "predictions"} for c in original]
    by_day = defaultdict(list)
    for case in cases:
        by_day[local_time(case["decision_at"])[:10]].append(case)
    _, days = base.source_days()
    _RUNTIME = {"prepared": prepared, "policy": policy, "binding": binding,
        "by_day": dict(by_day), "primary_ids": set(old_freeze["primary_case_ids"]),
        "corridors": {c["id"]: c for c in prepared["corridors"]},
        "index": base.incident_index(days), "estimator": base.ProfileEstimator(base.PROFILE)}
    shards = []
    try:
        with ProcessPoolExecutor(max_workers=min(workers, len(by_day)),
                                 mp_context=multiprocessing.get_context("fork")) as pool:
            futures = {pool.submit(_forecast_day, day): day for day in sorted(by_day)}
            for future in as_completed(futures):
                row = future.result()
                shards.append(row)
                print({"stage": "REPAIR_FORECAST_DAY", **row}, flush=True)
        saved, variants = {}, []
        for row in sorted(shards, key=lambda r: r["date"]):
            payload = load(ROOT / row["artifact"]["path"])
            if payload["binding"] != binding or sha(ROOT / row["artifact"]["path"]) != row["artifact"]["sha256"]:
                raise ValueError("Repair shard binding or bytes changed before merge.")
            for case in payload["cases"]:
                if case["id"] in saved:
                    raise ValueError("Duplicate repair case across shards.")
                saved[case["id"]] = case
            variants.extend(payload["sensitivity"])
        if set(saved) != set(old_freeze["selected_case_ids"]):
            raise ValueError("Repair forecasts do not cover the complete original cohort.")
        expected_pairs = {(identity, margin) for identity in old_freeze["primary_case_ids"]
                          for margin in policy["boarding_margin_sensitivity_seconds"]}
        if {(r["case_id"], r["boarding_margin_seconds"]) for r in variants} != expected_pairs or len(variants) != len(expected_pairs):
            raise ValueError("Sensitivity must cover both margins on every original primary case.")
        # One input-selected case per local date checks fork/cache behavior.
        parity_cases = [min(values, key=lambda c: (c["decision_at"], c["id"])) for values in by_day.values()]
        parity_by_cutoff = {c["decision_at"]: c for c in parity_cases}
        parity = 0
        for row in base.selected_snapshots(prepared, parity_by_cutoff):
            case = parity_by_cutoff[row["cutoff"]]
            corridor = _RUNTIME["corridors"][case["corridor_id"]]
            for mode in MODES:
                actual = predict(row["snapshots"], corridor, row["cutoff"], _RUNTIME["index"],
                                 _RUNTIME["estimator"], mode, policy["boarding_margin_seconds"])
                if actual != saved[case["id"]]["predictions"][mode]:
                    raise ValueError("Serial prediction differs from the parallel shard.")
                parity += 1
        if prediction_binding(prepared, old_freeze) != binding:
            raise ValueError("Prediction code or policy changed during the forecast run.")
        ordered = [saved[c["id"]] for c in cases]
        execution = {"binding": binding, "worker_count": min(workers, len(by_day)), "shards": shards,
            "serial_mode_parity_checks": parity, "cases": len(ordered), "sensitivity_variants": len(variants),
            "elapsed_seconds": round(time.monotonic() - started, 3), "new_outcome_records_read": False}
        dump(EXECUTION, execution)
        dump(PREDICTIONS, {"binding": binding, "execution": artifact(EXECUTION), "cases": ordered})
        dump(SENSITIVITY, {"binding": binding, "variants": sorted(variants,
            key=lambda row: (row["case_id"], row["boarding_margin_seconds"]))})
        print({"stage": "REPAIR_PREDICTIONS_COMPLETE", "cases": len(ordered),
            "sensitivity_variants": len(variants), "serial_checks": parity,
            "elapsed_seconds": execution["elapsed_seconds"]}, flush=True)
    finally:
        _RUNTIME = None


def freeze(workers=3):
    prepare_forecasts(workers)
    policy = read_policy()
    prepared, old_freeze, original = original_inputs()
    value = {"schema_version": "november-repair-freeze-v1", "study_status": "POST_HOC_REPAIR_REGRESSION",
        "policy": policy, "policy_artifact": artifact(POLICY_PATH), "protocol": artifact(PROTOCOL),
        "prediction_binding": prediction_binding(prepared, old_freeze),
        "producer_code_sha256": scoring_producers(), "training": base.training_provenance(),
        "forecast_cases": artifact(PREDICTIONS), "margin_sensitivity": artifact(SENSITIVITY),
        "forecast_execution": artifact(EXECUTION), "old_input_freeze": artifact(OLD_FREEZE),
        "old_forecast_cases": old_freeze["frozen_forecast_cases"],
        "selected_case_ids": [c["id"] for c in original], "primary_case_ids": old_freeze["primary_case_ids"],
        "same_calendar_cohort_and_provider_paths": True, "new_forecasts_read_outcomes": False,
        "prior_november_outcomes_known": True, "new_outcome_scoring_started": False}
    if FREEZE.exists() and load(FREEZE) != value:
        raise ValueError("Existing repair freeze differs; preserve the original repair artifacts.")
    dump(FREEZE, value)
    print({"stage": "REPAIR_FROZEN", "cases": len(original), "primary": len(old_freeze["primary_case_ids"]),
           "freeze": artifact(FREEZE)}, flush=True)


def verify():
    frozen = load(FREEZE)
    policy = read_policy()
    prepared, old_freeze, old_cases = original_inputs()
    if (frozen["policy"] != policy or frozen["policy_artifact"] != artifact(POLICY_PATH)
            or frozen["protocol"] != artifact(PROTOCOL) or frozen["producer_code_sha256"] != scoring_producers()
            or frozen["prediction_binding"] != prediction_binding(prepared, old_freeze)
            or frozen["training"] != base.training_provenance()
            or frozen["selected_case_ids"] != old_freeze["selected_case_ids"]
            or frozen["primary_case_ids"] != old_freeze["primary_case_ids"]):
        raise ValueError("Repair inputs, policy, producer or cohort changed after freezing.")
    for key in ("forecast_cases", "margin_sensitivity", "forecast_execution", "old_input_freeze", "old_forecast_cases"):
        item = frozen[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen repair artifact changed: " + key)
    saved, variants = load(PREDICTIONS), load(SENSITIVITY)
    if saved["binding"] != frozen["prediction_binding"] or variants["binding"] != frozen["prediction_binding"]:
        raise ValueError("Repair forecast binding changed.")
    if [c["id"] for c in saved["cases"]] != frozen["selected_case_ids"]:
        raise ValueError("Repair forecast membership changed.")
    for old, new in zip(old_cases, saved["cases"]):
        if {k: v for k, v in old.items() if k != "predictions"} != {k: v for k, v in new.items() if k != "predictions"}:
            raise ValueError("Repair altered original input case metadata.")
    return frozen, prepared, old_cases, saved["cases"], variants["variants"]


def score_policy(case, predictions, route_outcomes, labels, policy):
    """Score fixed route execution while retaining exact selected-train diagnostics."""
    from stayorswitch.repair_metrics import boarding_diagnostic
    result = {k: deepcopy(v) for k, v in case.items() if k not in ("predictions", "asof_mta_prediction")}
    result["planned_closure_timing"] = planned_timing(result)
    result["official_text_review"]["planned_through_service_unavailable"] = (
        result["planned_closure_timing"] == "CONFIRMED_ACTIVE")
    result["modes"], result["fixed_train_diagnostics"], result["boarding_diagnostics"] = {}, {}, {}
    for mode in MODES:
        prediction = predictions[mode]
        value = dict(prediction, **decide(prediction, case["reference_route_id"],
            switch_margin_seconds=policy["switch_margin_seconds"], require_severe=False))
        value["outcomes"] = {route["id"]: route_outcomes.get(route["id"],
            {"status": "UNAVAILABLE", "reason": "PROVIDER_PATH_NOT_EXECUTABLE"}) for route in prediction["routes"]}
        # Shared execution includes physically possible paths that were not
        # forecast-eligible. They cannot become hindsight missed opportunities.
        eligible_ids = {route["id"] for route in prediction["routes"] if route.get("timing_eligible")}
        score_value = dict(value, outcomes={key: outcome for key, outcome in value["outcomes"].items() if key in eligible_ids})
        value["scores"] = {key: _decision_scores(score_value, case["reference_route_id"], None, key,
            policy["tie_margin_seconds"], policy["switch_margin_seconds"])
            for key in ("strict_decision", "conditional_timing_decision")}
        result["fixed_train_diagnostics"][mode] = {route["id"]: outcome_for(route, labels, case["decision_at"])
                                                  for route in prediction["routes"]}
        result["boarding_diagnostics"][mode] = {route["id"]: boarding_diagnostic(route, labels, case["decision_at"])
                                               for route in prediction["routes"]}
        result["modes"][mode] = value
    return score_annotations(result)


def scopes(cases, primary_ids):
    primary = [c for c in cases if c["id"] in primary_ids]
    return {"all_summary": cohort_summary(cases), "primary_summary": cohort_summary(primary),
        "november_16_18_summary": cohort_summary([c for c in cases if date_subset(c)]),
        "november_16_18_primary_summary": cohort_summary([c for c in primary if date_subset(c)]),
        "severe_summary": cohort_summary([c for c in cases if c["official_text_review"]["confirmed_impact"] == "SEVERE"]),
        "per_corridor_summary": {key: cohort_summary([c for c in cases if c["corridor_id"] == key])
                                 for key in sorted({c["corridor_id"] for c in cases})},
        "per_corridor_primary_summary": {key: cohort_summary([c for c in primary if c["corridor_id"] == key])
                                         for key in sorted({c["corridor_id"] for c in cases})}}


def compact_outcome(outcome):
    """Keep case-level evidence readable; full archive traces stay hashed locally."""
    keys = ("status", "reason", "total_duration_seconds", "destination_arrival_at", "leg_index", "trip_id",
            "departure_at", "platform_ready_at", "components", "endpoint_flags")
    value = {key: deepcopy(outcome[key]) for key in keys if key in outcome}
    for key in ("selected_legs", "completed_legs"):
        if key in outcome:
            value[key] = [{name: deepcopy(leg[name]) for name in ("leg_index", "trip_id", "canonical_trip_id",
                "route_id", "from_stop_id", "to_stop_id", "departure_at", "arrival_at", "platform_ready_at")
                if name in leg} for leg in outcome[key]]
    if "possible_earlier_boardings" in outcome:
        value["possible_earlier_boarding_count"] = len(outcome["possible_earlier_boardings"])
    return value


def compact_case(case, primary_ids):
    fields = ("id", "corridor_id", "incident_ids", "local_time", "decision_at", "reference_route_id",
              "incident_origin", "paired_policies", "planned_closure_timing")
    result = {key: deepcopy(case[key]) for key in fields}
    result["official_text_review"] = {key: deepcopy(case["official_text_review"][key]) for key in
        ("status", "confirmed_impact", "severity_basis", "review_group_id", "notice_vs_feed_conflict",
         "planned_through_service_unavailable", "reason") if key in case["official_text_review"]}
    result["exposure"] = [{key: deepcopy(leg[key]) for key in
        ("leg_index", "route_id", "from_stop_id", "to_stop_id", "platform_direction") if key in leg} |
        {"notices": [{key: deepcopy(notice[key]) for key in ("version_id", "header", "state", "captured_at")
                     if key in notice} for notice in leg.get("notices", [])]} for leg in case["exposure"]]
    result["policy_comparison"] = {key: (compact_outcome(value) if key.endswith("selected_outcome") else deepcopy(value))
                                   for key, value in case["policy_comparison"].items()}
    result.update(primary=case["id"] in primary_ids, modes={})
    for mode, value in case["modes"].items():
        selected = {case["reference_route_id"], value["strict_decision"]["recommended_itinerary_id"]}
        result["modes"][mode] = {"strict_decision": value["strict_decision"],
            "scores": value["scores"]["strict_decision"], "selected_routes": [
                {"id": r["id"], "name": r["name"], "predicted_duration_seconds": r.get("total_duration_seconds"),
                 "forecast_selected_train_ids": [leg["trip_id"] for leg in r.get("selected_legs", [])],
                 "route_execution_outcome": compact_outcome(value["outcomes"][r["id"]]),
                 "fixed_train_outcome": compact_outcome(case["fixed_train_diagnostics"][mode][r["id"]]),
                 "boarding_diagnostic": case["boarding_diagnostics"][mode][r["id"]]}
                for r in value["routes"] if r["id"] in selected]}
    return result


def score():
    from data.route_archive import build_archive
    from stayorswitch.route_execution import execute_route
    from stayorswitch.repair_metrics import compare_versions, operational_summary, supplementalboarding_summary
    frozen, prepared, old_cases, cases, variants = verify()
    policy = frozen["policy"]
    templates = [r for c in prepared["corridors"] for r in c["routes"]]
    windows = [(c["decision_at"], c["decision_at"] + policy["execution_horizon_seconds"]) for c in cases]
    archive = build_archive(ROOT, base.SOURCE, templates, windows=windows, cache_path=ARCHIVE_PATH,
                            manifest_output_path=ARCHIVE_MANIFEST, progress=lambda row: print(row, flush=True))
    archive_binding = {"archive": artifact(ARCHIVE_PATH), "manifest": artifact(ARCHIVE_MANIFEST)}
    labels, label_sources, screening = base.read_outcomes()
    corridors = {c["id"]: c for c in prepared["corridors"]}
    shared = {}
    started = time.monotonic()
    for number, case in enumerate(cases, 1):
        shared[case["id"]] = {route["id"]: execute_route(route, archive, case["decision_at"],
            max_elapsed_seconds=policy["execution_horizon_seconds"],
            max_observation_gap_seconds=policy["max_feed_gap_seconds"])
            for route in corridors[case["corridor_id"]]["routes"]}
        if number % 100 == 0 or number == len(cases):
            print({"stage": "REPAIR_ROUTE_EXECUTION", "cases": number, "total": len(cases),
                   "elapsed_seconds": round(time.monotonic() - started, 1)}, flush=True)
    execution_path = LOCAL / "shared-route-execution.json.gz"
    dump(execution_path, {"freeze": artifact(FREEZE), "archive": archive_binding,
                          "cases": [{"case_id": key, "outcomes": value} for key, value in shared.items()]})
    evaluated = [score_policy(c, c["predictions"], shared[c["id"]], labels, policy) for c in cases]
    original_evaluated = [score_policy(c, c["predictions"], shared[c["id"]], labels, policy) for c in old_cases]
    scored_path, old_path = LOCAL / "scored-cases.json.gz", LOCAL / "old-policy-route-scored-cases.json.gz"
    dump(scored_path, evaluated)
    dump(old_path, original_evaluated)
    primary_ids = set(frozen["primary_case_ids"])
    by_id = {c["id"]: c for c in cases}
    sensitivity = {}
    sensitivity_scored = []
    for margin in policy["boarding_margin_sensitivity_seconds"]:
        selected = [row for row in variants if row["boarding_margin_seconds"] == margin]
        rows = [score_policy(by_id[r["case_id"]], r["predictions"], shared[r["case_id"]], labels, policy) for r in selected]
        primary_lookup = {c["id"]: c for c in evaluated if c["id"] in primary_ids}
        aligned = [primary_lookup[c["id"]] for c in rows]
        sensitivity[str(margin)] = {"summary": cohort_summary(rows), "operational": operational_summary(rows),
            "boarding": supplementalboarding_summary(rows),
            "versus_main_margin": compare_versions(aligned, rows)}
        sensitivity_scored.append({"boarding_margin_seconds": margin, "cases": rows})
    sensitivity_path = LOCAL / "scored-margin-sensitivity.json.gz"
    dump(sensitivity_path, sensitivity_scored)
    original_report = load(OLD_REPORT)
    original_by_id = {c["id"]: c for c in original_report["cases"]}
    original_operational = operational_summary(original_evaluated)
    for case in original_evaluated:
        for mode in MODES:
            if case["modes"][mode]["strict_decision"] != original_by_id[case["id"]]["modes"][mode]["strict_decision"]:
                raise ValueError("Reconstructed old policy differs from the frozen original advice.")
    for mode in MODES:
        if original_operational["by_mode"][mode]["fixed_train_statuses"] != original_report["all_summary"]["by_mode"][mode]["selected_journey_statuses"]:
            raise ValueError("Old fixed-train diagnostics do not reproduce the frozen original outcomes.")
    report = {"schema_version": "november-repair-results-v1", "study_status": "POST_HOC_REPAIR_REGRESSION",
        "policy": policy, "freeze": artifact(FREEZE), "training": frozen["training"],
        "corridors": prepared["corridors"], "archive": archive_binding,
        "shared_route_execution": artifact(execution_path), "scored_artifact": artifact(scored_path),
        "old_policy_route_scored_artifact": artifact(old_path), "margin_sensitivity_artifact": artifact(sensitivity_path),
        "label_sources": label_sources, "endpoint_screening": screening,
        "original_fixed_train_result": artifact(OLD_REPORT),
        "original_fixed_train_summaries": {key: original_report[key] for key in
            ("all_summary", "primary_summary", "severe_summary", "per_corridor_summary")},
        **scopes(evaluated, primary_ids), "old_policy_under_route_execution": scopes(original_evaluated, primary_ids),
        "operational": operational_summary(evaluated),
        "primary_operational": operational_summary([c for c in evaluated if c["id"] in primary_ids]),
        "old_policy_operational": original_operational,
        "boarding": supplementalboarding_summary(evaluated),
        "primary_boarding": supplementalboarding_summary([c for c in evaluated if c["id"] in primary_ids]),
        "old_policy_boarding": supplementalboarding_summary(original_evaluated),
        "matched_version_comparisons": {mode: compare_versions(original_evaluated, evaluated, mode=mode) for mode in MODES},
        "primary_matched_version_comparisons": {mode: compare_versions(
            [c for c in original_evaluated if c["id"] in primary_ids],
            [c for c in evaluated if c["id"] in primary_ids], mode=mode) for mode in MODES},
        "margin_sensitivity_primary": sensitivity,
        "cases": [compact_case(c, primary_ids) for c in evaluated]}
    # Verify again before publication so a long run cannot hide producer edits.
    if scoring_producers() != frozen["producer_code_sha256"]:
        raise ValueError("Scoring producers changed during execution; results were not published.")
    dump(RESULT, report)
    write_report(report)
    print({"stage": "REPAIR_SCORED", "result": artifact(RESULT),
           "all": report["all_summary"]["model_switch_vs_model_stay"],
           "primary": report["primary_summary"]["model_switch_vs_model_stay"]}, flush=True)


def count_row(summary):
    value = summary["model_switch_vs_model_stay"]
    c = value["classes"]
    return [value["recommendations"], c.get("MEANINGFUL_GAIN", 0), c.get("PRACTICAL_TIE", 0),
            c.get("MEANINGFUL_LOSS", 0), c.get("UNKNOWN", 0)]


def write_report(report):
    lines = ["# November weekday boarding repair and route-execution results", "",
        "This separately versioned repair uses the same 2,306 checkpoints, 197 earliest weekday corridor/publisher-family "
        "representatives, five corridors and October 1–31 model as the preserved November study. Dates are November "
        "2–6, 9–13 and 16–18, 2026. These dates have already been examined: this is a post-hoc repair regression, "
        "not a new untouched test. No retraining or outcome-based case selection was performed.", "",
        "The main boarding margin is 120 seconds. Positive historical departure correction cannot make an otherwise "
        "uncatchable train eligible. Transfers use conservative platform readiness. The margin is an eligibility rule, "
        "not extra travel time. All three prediction policies use the same rule.", "",
        "The execution evaluator follows the frozen route and boards the first evidenced compatible train after platform "
        "readiness. It uses archived future feed evidence only to reconstruct movement, never to select the earliest "
        "eventual destination arrival. It can continue on a later train after a forecast-selected train is missed. "
        "Ambiguous earlier trains, missing evidence and incomplete coverage remain unknown; the elapsed horizon is 120 minutes. "
        "Times remain screened final-MTA-prediction proxies plus declared walks, not independently measured passenger journeys.", "",
        "## Main outcome counts", "",
        "| Scope | Checkpoints | Families | Switch | Gain >3 min | Tie | Loss >3 min | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    rows = [("All weekdays", report["all_summary"]), ("Earliest representatives", report["primary_summary"]),
        ("November 16–18", report["november_16_18_summary"]),
        ("November 16–18 representatives", report["november_16_18_primary_summary"]),
        ("Qualified severe", report["severe_summary"])]
    for title, value in rows:
        lines.append("| " + " | ".join(map(str, [title, value["cases"], value["corridor_incidents"], *count_row(value)])) + " |")
    lines += ["", "All-checkpoint rows retain repeated times within incidents. Publisher IDs are not necessarily "
        "independent physical faults. Predicted Switch savings must still reach five minutes; outcome differences "
        "within ±3 minutes are ties.", "", "## Five-corridor detail", "",
        "| Corridor | Checkpoints | Families | Switch | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for corridor in report["corridors"]:
        value = report["per_corridor_summary"][corridor["id"]]
        lines.append("| " + " | ".join(map(str, [corridor.get("name", corridor["id"]), value["cases"],
            value["corridor_incidents"], *count_row(value)])) + " |")
    lines += ["", "## Policy comparisons under identical route execution", "",
        "| Scope / comparison | Concrete pairs | Comparable | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for title, value in rows[:2]:
        for comparison, row in value["paired_policies"].items():
            c = row["classes"]
            lines.append("| " + " | ".join(map(str, [title + " / " + comparison, row["eligible_actions"], row["comparable"],
                c.get("MEANINGFUL_GAIN", 0), c.get("PRACTICAL_TIE", 0), c.get("MEANINGFUL_LOSS", 0), c.get("UNKNOWN", 0)])) + " |")
    lines += ["", "These compare the routes actually chosen by each policy. A faster Switch relative to its own Stay "
        "does not automatically imply an improvement over the raw-MTA policy.", "", "## Raw-MTA Stay / model Switch", "",
        "| Scope | Cases | Comparable | Gain | Tie | Loss | Unknown |", "|---|---:|---:|---:|---:|---:|---:|"]
    for title, value in rows:
        row = value["mta_stay_model_switch"]
        c = row["classes"]
        lines.append("| " + " | ".join(map(str, [title, row["cases"], row["comparable"], c.get("MEANINGFUL_GAIN", 0),
            c.get("PRACTICAL_TIE", 0), c.get("MEANINGFUL_LOSS", 0), c.get("UNKNOWN", 0)])) + " |")
    lines += ["", "## Separate evaluator changes from prediction changes", "",
        "| Evaluation / model version | Switch | Gain | Tie | Loss | Unknown |", "|---|---:|---:|---:|---:|---:|"]
    for title, value in [("Original exact-train evaluator / old model", report["original_fixed_train_summaries"]["all_summary"]),
        ("New route executor / old model", report["old_policy_under_route_execution"]["all_summary"]),
        ("New route executor / repaired model", report["all_summary"])]:
        lines.append("| " + " | ".join(map(str, [title, *count_row(value)])) + " |")
    lines += ["", "The second row holds the old recommendations fixed and changes only execution scoring. The third "
        "adds the boarding repair. Exact-train missed-boardings remain diagnostics even when the route later completes.", "",
        "| Matched old/new recommendation | Concrete pairs | Comparable | New faster | Tie | New slower | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for title, group in (("All weekdays", report["matched_version_comparisons"]),
                         ("Earliest representatives", report["primary_matched_version_comparisons"])):
        row = group["incident_profile"]
        c = row["classes"]
        lines.append("| " + " | ".join(map(str, [title, row["eligible_actions"], row["comparable"],
            c.get("MEANINGFUL_GAIN", 0), c.get("PRACTICAL_TIE", 0), c.get("MEANINGFUL_LOSS", 0), c.get("UNKNOWN", 0)])) + " |")
    lines += ["",
        "## Boarding diagnostics and remaining unknowns", "",
        "| Version / policy | Concrete actions | Exact selected-train misses | Switch actions | Missed Switch trains | Missed selected train but route completes |",
        "|---|---:|---:|---:|---:|---:|"]
    for version, key in (("Old", "old_policy_operational"), ("Repaired", "operational")):
        for mode in MODES:
            row = report[key]["by_mode"][mode]
            lines.append("| " + " | ".join(map(str, [version + " / " + mode, row["concrete_actions"],
                row["known_missed_selected_journeys"], row["actions"].get("SWITCH", 0),
                row["known_missed_selected_switches"], row["fixed_train_missed_but_route_complete"]])) + " |")
    lines += ["", "The separate departure-first check below does not require a usable destination-arrival record to "
        "identify a missed first boarding. Later boardings require the preceding leg's arrival to establish platform readiness.", "",
        "| Version / policy | Concrete actions | Evaluable first boardings | Missed first boardings | Unknown first boardings | Evaluable full boarding sequences | Missed sequence | Unknown sequence |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for version, key in (("Old", "old_policy_boarding"), ("Repaired", "boarding")):
        for mode in MODES:
            row = report[key]["by_mode"][mode]
            first, all_legs = row["first_boarding"], row["all_boardings"]
            lines.append("| " + " | ".join(map(str, [version + " / " + mode, row["concrete_actions"],
                first["catchable"] + first["missed"], first["missed"], first["unknown"],
                all_legs["catchable"] + all_legs["missed"], all_legs["missed"], all_legs["unknown"]])) + " |")
    unknown = report["operational"]["by_mode"]["incident_profile"]["unknown_switches"]
    lines += ["", "The repaired model has {} unknown Switch comparisons: {} with an incomplete chosen route and {} "
        "with a completed chosen route but incomplete Stay. These groups are mutually exclusive.".format(
            unknown["count"], unknown["chosen_incomplete"], unknown["stay_incomplete_when_chosen_complete"]), "",
        "| Exclusive unknown reason | Count |", "|---|---:|"]
    for reason, count in unknown["reason_counts"].items():
        lines.append("| {} | {} |".format(reason, count))
    lines += ["", "A missed selected train remains an operational failure under the declared walking assumptions even "
        "if the route eventually completes. Unknown or censored travel time never becomes zero or a successful recommendation.", "",
        "## Boarding-margin sensitivity on the 197 representatives", "",
        "| Margin seconds | Switch | Gain | Tie | Loss | Unknown | Known selected-train misses |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for margin in (60, 120, 180):
        value = (report["primary_summary"] if margin == 120 else
                 report["margin_sensitivity_primary"][str(margin)]["summary"])
        operational = (report["primary_operational"] if margin == 120 else
                       report["margin_sensitivity_primary"][str(margin)]["operational"])
        lines.append("| " + " | ".join(map(str, [margin, *count_row(value),
            operational["by_mode"]["incident_profile"]["known_missed_selected_journeys"]])) + " |")
    lines += ["", "The sensitivity cases are the same original representatives, not additional performance samples. "
        "The main 120-second setting was declared before these repair forecasts; these previously examined dates do not "
        "justify selecting an apparently best margin and calling it independently validated.", "",
        "## Reproduction", "", "```sh",
        ".venv/bin/python algo/scripts/evaluate_november_repair.py --freeze-only",
        ".venv/bin/python algo/scripts/evaluate_november_repair.py --verify-only",
        ".venv/bin/python algo/scripts/evaluate_november_repair.py", "```", "",
        "[Full results and provenance](november-repair-test.json) · [Frozen repair policy and inputs](november-repair-selection-frozen.json)", ""]
    REPORT.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--predict-only", action="store_true")
    group.add_argument("--freeze-only", action="store_true")
    group.add_argument("--verify-only", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("workers must be positive")
    if args.predict_only:
        prepare_forecasts(args.workers)
    elif args.freeze_only:
        freeze(args.workers)
    elif args.verify_only:
        frozen, _, _, _, _ = verify()
        print({"stage": "REPAIR_VERIFIED", "cases": len(frozen["selected_case_ids"])}, flush=True)
    else:
        score()


if __name__ == "__main__":
    main()
