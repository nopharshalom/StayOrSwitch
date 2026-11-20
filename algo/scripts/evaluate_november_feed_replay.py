#!/usr/bin/env python3
"""Evaluate unchanged November advice with a causal visible-feed passenger policy.

No forecasts or profiles are refitted. Only the route executor changes, and all
prediction policies share each case/path outcome. Earlier frozen studies stay
unchanged; this is a post-hoc replay on previously examined November records.
"""

import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo"), str(ROOT / "algo/scripts")]

import evaluate_november_repair as repair
from evaluate_preincident import artifact, dump, load, sha
from stayorswitch.november_replay import cohort_summary
from stayorswitch.repair_metrics import compare_versions, operational_summary, supplementalboarding_summary
from stayorswitch.severe import MODES


SELF = ROOT / "algo/scripts/evaluate_november_feed_replay.py"
LOCAL = ROOT / "algo/local/november-feed-replay"
POLICY_PATH = ROOT / "data/config/november-feed-replay-policy.json"
PROTOCOL = ROOT / "algo/docs/november-feed-replay-plan.md"
FREEZE = ROOT / "algo/reports/november-feed-replay-selection-frozen.json"
RESULT = ROOT / "algo/reports/november-feed-replay-test.json"
REPORT = ROOT / "algo/reports/november-feed-replay-test.md"
ARCHIVE_MANIFEST = ROOT / "data/manifests/november-feed-route-archive-v3.json"
QUALITY_CONFIG = ROOT / "data/config/november-feed-outcome-quality.json"
QUALITY_ADDENDUM = ROOT / "algo/docs/november-feed-outcome-quality-addendum.md"
INITIAL_RUN = LOCAL / "superseded/initial-v3"


def initial_run_binding():
    """Bind the already scored run retained before the outcome-quality repair."""
    manifest_path = INITIAL_RUN / "preservation-manifest.json"
    manifest = load(manifest_path)
    for item in manifest["files"]:
        if sha(INITIAL_RUN / item["path"]) != item["sha256"]:
            raise ValueError("Superseded initial feed replay changed: " + item["path"])
    paths = {"selection_freeze": FREEZE, "result": RESULT,
             "shared_route_execution": LOCAL / "shared-route-execution.json.gz",
             "archive_manifest": ARCHIVE_MANIFEST}
    return {"preservation_manifest": artifact(manifest_path),
            **{key: artifact(INITIAL_RUN / path.relative_to(ROOT)) for key, path in paths.items()}}


def quality_binding():
    """Bind a symmetric, post-selection screen and its independent geography."""
    policy = load(QUALITY_CONFIG)
    if (policy.get("max_straight_line_speed_kmh") != 300.0
            or policy.get("scope") != "POST_SELECTION_SELECTED_TRAIN_OUTCOME_ONLY"
            or policy.get("changes_forecasts_or_candidate_selection") is not False
            or policy.get("applies_to_all_routes_modes_and_comparison_signs") is not True
            or policy.get("retain_raw_endpoint_values") is not True):
        raise ValueError("Outcome-quality policy changes the declared symmetric post-selection screen.")
    source = policy["station_source"]
    if artifact(ROOT / source["path"]) != source:
        raise ValueError("Outcome-quality station source differs from the policy binding.")
    return {"config": artifact(QUALITY_CONFIG), "addendum": artifact(QUALITY_ADDENDUM),
            "station_source": source}


def read_policy():
    value = load(POLICY_PATH)
    required = {"boarding_margin_seconds": 120, "execution_horizon_seconds": 7200,
                "switch_margin_seconds": 300, "tie_margin_seconds": 180,
                "max_feed_gap_seconds": 120, "max_endpoint_age_seconds": 180}
    for key, expected in required.items():
        if value.get(key) != expected:
            raise ValueError("The feed replay changes a preserved parameter: " + key)
    if (value.get("retrain") is not False or value.get("regenerate_forecasts") is not False
            or value.get("initial_recommendation_uses_future_outcomes") is not False
            or value.get("execution_selects_on_final_destination_arrival") is not False
            or value.get("unknown_unselected_trains_block_execution") is not False
            or value.get("boarding_margin_sensitivity_seconds") != [60, 180]):
        raise ValueError("The feed replay changes its authorized forecast or selection contract.")
    return value


def producers():
    names = ("algo/scripts/evaluate_november_feed_replay.py", "algo/stayorswitch/feed_execution.py",
        "data/feed_route_archive.py", "data/route_outcome_sanity.py", "algo/scripts/evaluate_november_repair.py",
        "algo/stayorswitch/repair_metrics.py", "algo/stayorswitch/october_evaluation.py",
        "algo/stayorswitch/november_replay.py", "data/november_outcomes.py")
    return {name: sha(ROOT / name) for name in names}


def freeze():
    policy = read_policy()
    previous, prepared, old_cases, cases, variants = repair.verify()
    value = {"schema_version": "november-feed-replay-freeze-v3-outcome-quality",
        "study_status": "POST_HOC_VISIBLE_FEED_EXECUTION_COMPARISON",
        "policy": policy, "policy_artifact": artifact(POLICY_PATH), "protocol": artifact(PROTOCOL),
        "producer_code_sha256": producers(), "training": previous["training"],
        "prior_repair_freeze": artifact(repair.FREEZE), "prior_repair_result": artifact(repair.RESULT),
        "forecast_cases": previous["forecast_cases"], "margin_sensitivity": previous["margin_sensitivity"],
        "old_forecast_cases": previous["old_forecast_cases"],
        "source_route_archive": artifact(repair.ARCHIVE_PATH),
        "source_route_archive_manifest": artifact(repair.ARCHIVE_MANIFEST),
        "selected_case_ids": previous["selected_case_ids"], "primary_case_ids": previous["primary_case_ids"],
        "forecasts_reused_byte_for_byte": True, "model_retrained": False,
        "prior_november_outcomes_known": True, "new_executor_scoring_started": False}
    value.update(initial_visible_feed_run=initial_run_binding(), outcome_quality=quality_binding(),
        initial_visible_feed_results_known=True, outcome_quality_followup_after_initial_score=True,
        new_executor_scoring_started=True, corrected_outcome_scoring_started=False)
    if FREEZE.exists() and load(FREEZE) != value:
        raise ValueError("Existing feed replay freeze differs; preserve it before changing the study.")
    dump(FREEZE, value)
    print({"stage": "FEED_REPLAY_FROZEN", "cases": len(cases), "primary": len(value["primary_case_ids"]),
           "sensitivity_variants": len(variants), "freeze": artifact(FREEZE)}, flush=True)


def verify():
    frozen = load(FREEZE)
    previous, prepared, old_cases, cases, variants = repair.verify()
    if (frozen["policy"] != read_policy() or frozen["policy_artifact"] != artifact(POLICY_PATH)
            or frozen["protocol"] != artifact(PROTOCOL) or frozen["producer_code_sha256"] != producers()
            or frozen["training"] != previous["training"]
            or frozen["selected_case_ids"] != previous["selected_case_ids"]
            or frozen["primary_case_ids"] != previous["primary_case_ids"]):
        raise ValueError("Feed replay code, policy, training or cohort changed after freezing.")
    if (frozen.get("initial_visible_feed_run") != initial_run_binding()
            or frozen.get("outcome_quality") != quality_binding()
            or frozen.get("initial_visible_feed_results_known") is not True
            or frozen.get("outcome_quality_followup_after_initial_score") is not True
            or frozen.get("new_executor_scoring_started") is not True
            or frozen.get("corrected_outcome_scoring_started") is not False):
        raise ValueError("Post-initial-score outcome-quality provenance changed or was omitted.")
    expected_references = {"prior_repair_freeze": artifact(repair.FREEZE),
        "prior_repair_result": artifact(repair.RESULT), "forecast_cases": previous["forecast_cases"],
        "margin_sensitivity": previous["margin_sensitivity"], "old_forecast_cases": previous["old_forecast_cases"],
        "source_route_archive": artifact(repair.ARCHIVE_PATH),
        "source_route_archive_manifest": artifact(repair.ARCHIVE_MANIFEST)}
    if any(frozen[key] != expected for key, expected in expected_references.items()):
        raise ValueError("Feed replay provenance differs from the reused repair artifacts.")
    if (frozen.get("forecasts_reused_byte_for_byte") is not True or frozen.get("model_retrained") is not False
            or frozen.get("prior_november_outcomes_known") is not True):
        raise ValueError("Feed replay provenance must retain the unchanged, previously examined forecast study.")
    for key in ("prior_repair_freeze", "prior_repair_result", "forecast_cases", "margin_sensitivity",
                "old_forecast_cases", "source_route_archive", "source_route_archive_manifest"):
        item = frozen[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Preserved input changed: " + key)
    if len(cases) != 2306 or len(frozen["primary_case_ids"]) != 197 or len(variants) != 394:
        raise ValueError("The visible-feed replay must retain the complete original cohort.")
    return frozen, prepared, old_cases, cases, variants


def assert_advice_unchanged(previous_cases, current_cases):
    if (len({c["id"] for c in previous_cases}) != len(previous_cases)
            or len({c["id"] for c in current_cases}) != len(current_cases)):
        raise ValueError("Executor comparison contains duplicate case identities.")
    if [c["id"] for c in previous_cases] != [c["id"] for c in current_cases]:
        raise ValueError("Executor comparison changes ordered case membership.")
    for before, after in zip(previous_cases, current_cases):
        for key in ("corridor_id", "decision_at", "reference_route_id"):
            if before[key] != after[key]:
                raise ValueError("Executor comparison changes case metadata: " + key)
        for mode in MODES:
            if before["modes"][mode]["strict_decision"] != after["modes"][mode]["strict_decision"]:
                raise ValueError("The new executor changed the frozen route recommendation.")


def evaluator_comparison(previous_cases, current_cases):
    """Describe changed outcome evidence without presenting it as changed advice."""
    assert_advice_unchanged(previous_cases, current_cases)
    result = {}
    for mode in MODES:
        transitions, selected_statuses = Counter(), Counter()
        recovered_unknowns = lost_comparable = 0
        records = []
        for before, after in zip(previous_cases, current_cases):
            old_value, new_value = before["modes"][mode], after["modes"][mode]
            old_class = old_value["scores"]["classification"]
            new_class = new_value["scores"]["strict_decision"]["classification"]
            transitions[old_class + " -> " + new_class] += 1
            recovered_unknowns += old_class == "UNKNOWN" and new_class != "UNKNOWN"
            lost_comparable += old_class != "UNKNOWN" and new_class == "UNKNOWN"
            chosen = new_value["strict_decision"].get("recommended_itinerary_id")
            old_route = next((r for r in old_value["selected_routes"] if r["id"] == chosen), None)
            old_outcome = old_route["route_execution_outcome"] if old_route else {}
            new_outcome = new_value["outcomes"].get(chosen, {})
            old_status, new_status = old_outcome.get("status", "NO_SELECTED_JOURNEY"), new_outcome.get("status", "NO_SELECTED_JOURNEY")
            selected_statuses[old_status + " -> " + new_status] += 1
            records.append({"case_id": before["id"], "corridor_id": before["corridor_id"],
                "action": new_value["strict_decision"]["action"], "selected_route_id": chosen,
                "old_classification": old_class, "new_classification": new_class,
                "old_selected_status": old_status, "new_selected_status": new_status,
                "old_selected_duration_seconds": old_outcome.get("total_duration_seconds"),
                "new_selected_duration_seconds": new_outcome.get("total_duration_seconds")})
        result[mode] = {"case_count": len(current_cases), "advice_unchanged": True,
            "classification_transitions": dict(sorted(transitions.items())),
            "selected_status_transitions": dict(sorted(selected_statuses.items())),
            "unknown_comparison_recovered": recovered_unknowns,
            "previous_comparison_now_unknown": lost_comparable, "records": records}
    return result


def trace_summary(outcomes):
    outcomes = list(outcomes)
    counters, statuses, reasons, trace_events = Counter(), Counter(), Counter(), Counter()
    for outcome in outcomes:
        statuses[outcome.get("status", "UNAVAILABLE")] += 1
        if outcome.get("reason"):
            reasons[outcome["reason"]] += 1
        for key, value in outcome.get("trace_counters", {}).items():
            if isinstance(value, int) and not isinstance(value, bool):
                counters[key] += value
        for row in outcome.get("update_trace", []):
            trace_events[str(row.get("event", row.get("kind", row.get("action", "UNSPECIFIED"))))] += 1
    return {"route_query_count": len(outcomes), "status_counts": dict(sorted(statuses.items())),
        "reason_counts": dict(sorted(reasons.items())), "trace_counters": dict(sorted(counters.items())),
        "trace_event_counts": dict(sorted(trace_events.items()))}


def execution_summaries(shared, evaluated):
    selected, switches = {}, {}
    for mode in MODES:
        all_rows, switch_rows = [], []
        for case in evaluated:
            value = case["modes"][mode]
            decision = value["strict_decision"]
            if decision["action"] not in {"STAY", "SWITCH"}:
                continue
            outcome = value["outcomes"][decision["recommended_itinerary_id"]]
            all_rows.append(outcome)
            if decision["action"] == "SWITCH":
                switch_rows.append(outcome)
        selected[mode], switches[mode] = trace_summary(all_rows), trace_summary(switch_rows)
    return {"all_supplied_paths": trace_summary(outcome for routes in shared.values() for outcome in routes.values()),
            "selected_routes_by_mode": selected, "switch_routes_by_mode": switches}


def quality_summary(shared, evaluated):
    """Count rejected evidence without changing route selection or denominators."""
    reason = "SELECTED_OUTCOME_IMPLAUSIBLE_TRAVEL_TIME"
    rejected, unique = [], set()
    for identity, routes in shared.items():
        for route_id, outcome in routes.items():
            if outcome.get("reason") != reason:
                continue
            event = outcome.get("event", {})
            unique.add((event.get("canonical_trip_id"), event.get("from_stop_id"), event.get("to_stop_id")))
            rejected.append({"case_id": identity, "route_id": route_id,
                "status": outcome["status"], "reason": reason,
                "leg_index": outcome.get("leg_index"), "selected_event": deepcopy(event),
                "outcome_quality": deepcopy(outcome.get("outcome_quality"))})
    modes = {}
    for mode in MODES:
        counts = Counter()
        for case in evaluated:
            value = case["modes"][mode]
            decision = value["strict_decision"]
            if decision["action"] not in {"STAY", "SWITCH"}:
                continue
            chosen_bad = value["outcomes"][decision["recommended_itinerary_id"]].get("reason") == reason
            counts["chosen_route_rejected"] += chosen_bad
            if decision["action"] == "SWITCH":
                stay_bad = value["outcomes"][case["reference_route_id"]].get("reason") == reason
                counts["switch_route_rejected"] += chosen_bad
                counts["switch_comparison_stay_rejected"] += stay_bad
                counts["switch_comparison_either_route_rejected"] += chosen_bad or stay_bad
        modes[mode] = dict(sorted(counts.items()))
    return {"selected_route_queries_rejected": len(rejected), "unique_selected_legs_rejected": len(unique),
        "applied_equally_to_every_route_and_policy": True, "rejected_outcomes_trigger_alternate_selection": False,
        "by_mode": modes, "records": rejected}


def _conditional(outcome):
    return outcome.get("conditional_on_unverified_selected_wait") is True


def conditional_evidence_summary(cases):
    """Separate selected-train records from an unverified earlier waiting interval."""
    by_mode = {}
    for mode in MODES:
        chosen_counts, switch_counts = Counter(), Counter()
        conditional_classes, screened_classes = Counter(), Counter()
        for case in cases:
            value = case["modes"][mode]
            decision = value["strict_decision"]
            if decision["action"] not in {"STAY", "SWITCH"}:
                continue
            chosen = value["outcomes"][decision["recommended_itinerary_id"]]
            if chosen["status"] == "INFERRED":
                chosen_counts["conditional_on_unverified_selected_wait" if _conditional(chosen)
                              else "without_unverified_selected_wait"] += 1
            if decision["action"] != "SWITCH":
                continue
            stay = value["outcomes"][case["reference_route_id"]]
            if chosen["status"] != "INFERRED" or stay["status"] != "INFERRED":
                continue
            conditional = _conditional(chosen) or _conditional(stay)
            key = "conditional_on_unverified_selected_wait" if conditional else "without_unverified_selected_wait"
            switch_counts[key] += 1
            classification = value["scores"]["strict_decision"]["classification"]
            (conditional_classes if conditional else screened_classes)[classification] += 1
        by_mode[mode] = {"inferred_chosen_routes": dict(sorted(chosen_counts.items())),
            "comparable_switch_vs_stay": dict(sorted(switch_counts.items())),
            "conditional_switch_classes": dict(sorted(conditional_classes.items())),
            "switch_classes_without_unverified_selected_wait": dict(sorted(screened_classes.items()))}
    paired = {}
    for comparison, left_mode, right_mode in (("incident_vs_mta", "mta", "incident_profile"),
            ("time_vs_mta", "mta", "time_profile"), ("incident_vs_time", "time_profile", "incident_profile")):
        counts, conditional_classes, screened_classes = Counter(), Counter(), Counter()
        for case in cases:
            pair = case["paired_policies"][comparison]
            if not pair.get("comparable"):
                continue
            outcomes = []
            for mode in (left_mode, right_mode):
                value = case["modes"][mode]
                outcomes.append(value["outcomes"][value["strict_decision"]["recommended_itinerary_id"]])
            conditional = any(_conditional(outcome) for outcome in outcomes)
            counts["conditional_on_unverified_selected_wait" if conditional
                   else "without_unverified_selected_wait"] += 1
            (conditional_classes if conditional else screened_classes)[pair["classification"]] += 1
        paired[comparison] = {"comparable": dict(sorted(counts.items())),
            "conditional_classes": dict(sorted(conditional_classes.items())),
            "classes_without_unverified_selected_wait": dict(sorted(screened_classes.items()))}
    return {"conditional_is_not_an_independent_observed_passenger_outcome": True,
            "by_mode": by_mode, "paired_policies": paired}


def compact_case(case, primary_ids):
    result = repair.compact_case(case, primary_ids)
    for mode in MODES:
        for route in result["modes"][mode]["selected_routes"]:
            outcome = case["modes"][mode]["outcomes"][route["id"]]
            route["route_execution_outcome"].update(
                conditional_on_unverified_selected_wait=_conditional(outcome),
                trace_counters=deepcopy(outcome.get("trace_counters", {})))
            if outcome.get("outcome_quality"):
                route["route_execution_outcome"].update(
                    outcome_quality=deepcopy(outcome["outcome_quality"]),
                    selected_event=deepcopy(outcome.get("event")))
    for key in ("raw_mta_selected_outcome", "model_selected_outcome"):
        if key in result["policy_comparison"]:
            original = case["policy_comparison"][key]
            result["policy_comparison"][key]["conditional_on_unverified_selected_wait"] = _conditional(original)
            if original.get("outcome_quality"):
                result["policy_comparison"][key]["outcome_quality"] = deepcopy(original["outcome_quality"])
    return result


def score():
    from data.feed_route_archive import load_feed_archive
    from stayorswitch.feed_execution import execute_route
    frozen, prepared, old_cases, cases, variants = verify()
    policy = frozen["policy"]
    archive = load_feed_archive(ROOT, source_manifest_path=repair.ARCHIVE_MANIFEST,
        source_archive_path=repair.ARCHIVE_PATH, manifest_output_path=ARCHIVE_MANIFEST,
        progress=lambda row: print(row, flush=True))
    archive_binding = {"source_archive": frozen["source_route_archive"], "manifest": artifact(ARCHIVE_MANIFEST)}
    labels, label_sources, screening = repair.base.read_outcomes()
    corridors = {c["id"]: c for c in prepared["corridors"]}
    shared = {}
    started = time.monotonic()
    for number, case in enumerate(cases, 1):
        shared[case["id"]] = {route["id"]: execute_route(route, archive, case["decision_at"],
            max_elapsed_seconds=policy["execution_horizon_seconds"],
            max_observation_gap_seconds=policy["max_feed_gap_seconds"])
            for route in corridors[case["corridor_id"]]["routes"]}
        for outcome in shared[case["id"]].values():
            if outcome.get("status") == "INFERRED" and not isinstance(
                    outcome.get("conditional_on_unverified_selected_wait"), bool):
                raise ValueError("Inferred execution must declare its waiting-assumption evidence flag.")
        if number % 100 == 0 or number == len(cases):
            print({"stage": "FEED_ROUTE_EXECUTION", "cases": number, "total": len(cases),
                   "elapsed_seconds": round(time.monotonic() - started, 1)}, flush=True)
    shared_path = LOCAL / "shared-route-execution.json.gz"
    dump(shared_path, {"freeze": artifact(FREEZE), "archive": archive_binding,
        "cases": [{"case_id": key, "outcomes": value} for key, value in shared.items()]})
    evaluated = [repair.score_policy(c, c["predictions"], shared[c["id"]], labels, policy) for c in cases]
    original = [repair.score_policy(c, c["predictions"], shared[c["id"]], labels, policy) for c in old_cases]
    strict_report = load(repair.RESULT)
    initial_report = load(ROOT / frozen["initial_visible_feed_run"]["result"]["path"])
    assert_advice_unchanged(strict_report["cases"], evaluated)
    assert_advice_unchanged(initial_report["cases"], evaluated)
    scored_path, old_path = LOCAL / "scored-cases.json.gz", LOCAL / "old-policy-route-scored-cases.json.gz"
    dump(scored_path, evaluated)
    dump(old_path, original)
    primary_ids = set(frozen["primary_case_ids"])
    by_id = {c["id"]: c for c in cases}
    primary_lookup = {c["id"]: c for c in evaluated if c["id"] in primary_ids}
    sensitivity, sensitivity_scored = {}, []
    for margin in policy["boarding_margin_sensitivity_seconds"]:
        selected = [row for row in variants if row["boarding_margin_seconds"] == margin]
        rows = [repair.score_policy(by_id[r["case_id"]], r["predictions"], shared[r["case_id"]], labels, policy) for r in selected]
        sensitivity[str(margin)] = {"summary": cohort_summary(rows), "operational": operational_summary(rows),
            "boarding": supplementalboarding_summary(rows),
            "versus_main_margin": compare_versions([primary_lookup[c["id"]] for c in rows], rows)}
        sensitivity_scored.append({"boarding_margin_seconds": margin, "cases": rows})
    sensitivity_path = LOCAL / "scored-margin-sensitivity.json.gz"
    dump(sensitivity_path, sensitivity_scored)
    boarding = supplementalboarding_summary(evaluated)
    operational = operational_summary(evaluated)
    if boarding != strict_report["boarding"]:
        raise ValueError("Changing execution unexpectedly changed frozen boarding diagnostics.")
    for mode in MODES:
        if operational["by_mode"][mode]["fixed_train_statuses"] != strict_report["operational"]["by_mode"][mode]["fixed_train_statuses"]:
            raise ValueError("Changing execution altered exact-selected-train diagnostics.")
    primary = [c for c in evaluated if c["id"] in primary_ids]
    old_primary = [c for c in original if c["id"] in primary_ids]
    report = {"schema_version": "november-visible-feed-results-v3-outcome-quality",
        "study_status": "POST_HOC_EXECUTION_POLICY_COMPARISON_WITH_UNCHANGED_FORECASTS",
        "policy": policy, "freeze": artifact(FREEZE), "training": frozen["training"],
        "initial_visible_feed_run": frozen["initial_visible_feed_run"],
        "outcome_quality": frozen["outcome_quality"],
        "outcome_quality_followup_after_initial_score": True,
        "initial_visible_feed_summaries": {key: initial_report[key] for key in
            ("all_summary", "primary_summary", "severe_summary", "per_corridor_summary")},
        "corridors": prepared["corridors"], "archive": archive_binding,
        "shared_route_execution": artifact(shared_path), "scored_artifact": artifact(scored_path),
        "old_policy_route_scored_artifact": artifact(old_path), "margin_sensitivity_artifact": artifact(sensitivity_path),
        "label_sources": label_sources, "endpoint_screening": screening,
        "strict_executor_result": artifact(repair.RESULT),
        "strict_executor_summaries": {key: strict_report[key] for key in
            ("all_summary", "primary_summary", "severe_summary", "per_corridor_summary")},
        **repair.scopes(evaluated, primary_ids), "old_policy_under_feed_execution": repair.scopes(original, primary_ids),
        "operational": operational, "primary_operational": operational_summary(primary),
        "old_policy_operational": operational_summary(original),
        "boarding": boarding, "primary_boarding": supplementalboarding_summary(primary),
        "old_policy_boarding": supplementalboarding_summary(original),
        "matched_version_comparisons": {mode: compare_versions(original, evaluated, mode=mode) for mode in MODES},
        "primary_matched_version_comparisons": {mode: compare_versions(old_primary, primary, mode=mode) for mode in MODES},
        "evaluator_comparison": evaluator_comparison(strict_report["cases"], evaluated),
        "outcome_quality_evaluator_comparison": evaluator_comparison(initial_report["cases"], evaluated),
        "outcome_quality_screening": quality_summary(shared, evaluated),
        "execution_traces": execution_summaries(shared, evaluated),
        "conditional_evidence": conditional_evidence_summary(evaluated),
        "primary_conditional_evidence": conditional_evidence_summary(primary),
        "severe_conditional_evidence": conditional_evidence_summary([c for c in evaluated
            if c["official_text_review"]["confirmed_impact"] == "SEVERE"]),
        "margin_sensitivity_primary": sensitivity,
        "cases": [compact_case(c, primary_ids) for c in evaluated]}
    if producers() != frozen["producer_code_sha256"]:
        raise ValueError("Execution or scoring producers changed during the run.")
    dump(RESULT, report)
    write_report(report)
    print({"stage": "FEED_REPLAY_SCORED", "result": artifact(RESULT),
           "all": report["all_summary"]["model_switch_vs_model_stay"],
           "primary": report["primary_summary"]["model_switch_vs_model_stay"]}, flush=True)


def _table_row(values):
    return "| " + " | ".join(map(str, values)) + " |"


def write_report(report):
    lines = ["# November weekday visible-feed execution results", "",
        "This version changes only historical route execution. It reuses the exact frozen two-minute boarding-safe "
        "forecasts, full October model, 2,306 weekday checkpoints, 197 earliest corridor/notice-family representatives "
        "and five corridors. Dates are November 2–6, 9–13 and 16–18, 2026. They have already been examined; this is a "
        "post-hoc replay comparison, not a new untouched test. No advice was regenerated or selected using outcomes.", "",
        "After the initial visible-feed run was scored, source review found a collapsed prediction sequence that "
        "implied a ten-second ride from Port Authority to Jay Street. The initial run is preserved by hash. This "
        "corrected report adds a symmetric selected-leg outcome screen: straight-line station distance divided by "
        "the inferred ride duration must not exceed 300 km/h. This is a deliberately permissive sanity ceiling, "
        "not a claim about subway operating speeds or an estimator of normal travel time. The rule was added "
        "after seeing initial outcomes and is explicitly a post-hoc quality repair. It rejects unusable evidence "
        "for the already selected train; it never picks a different train to obtain a complete or better result.", "",
        "At the platform, the simulated passenger chooses the earliest compatible service using the raw departure "
        "ETA in the currently visible feed. Later visible updates can change that choice. Final endpoint quality and "
        "eventual destination arrival do not rank candidates. Unknown records for unselected trains no longer block "
        "execution. Missing or unusable evidence for the selected train, unresolved selected disappearance and feed "
        "gaps remain explicit. Only the selected train's screened records infer movement; these are MTA prediction "
        "proxies plus authored walks, not independent passenger observations.", "",
        "A compatible service still present in the current feed with an expired departure ETA is treated as due "
        "now. It is selected normally rather than discarded through historical final labels; missing evidence for "
        "that selected due-now train yields an explicit unknown result.", "",
        "If an initially selected train lacks final departure evidence, a later feed update before its currently "
        "predicted boarding time may change the choice. A completed journey after that interval is conditional on "
        "the feed-following waiting assumption; its inferred final train does not independently prove what happened "
        "during the earlier unverified wait. Such comparisons are counted and separated below.", "",
        "The original two-minute boarding gate remains unchanged in all recommendation policies. It is not added "
        "again while the passenger is already at the platform. Predicted Switch savings require five minutes; "
        "outcome differences within ±3 minutes are ties. The execution horizon remains two hours.", "",
        "## Main outcome counts", "",
        "| Scope | Checkpoints | Families | Switch | Gain >3 min | Tie | Loss >3 min | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    rows = [("All weekdays", report["all_summary"]), ("Earliest representatives", report["primary_summary"]),
        ("November 16–18", report["november_16_18_summary"]),
        ("November 16–18 representatives", report["november_16_18_primary_summary"]),
        ("Qualified severe", report["severe_summary"])]
    for title, value in rows:
        lines.append(_table_row([title, value["cases"], value["corridor_incidents"], *repair.count_row(value)]))
    lines += ["", "Repeated checkpoints and publisher IDs are not independent passenger journeys or physical faults.", "",
        "## Evidence for completed Switch comparisons", "",
        "| Scope | Without unverified selected wait | Conditional on an unverified selected wait |",
        "|---|---:|---:|"]
    for title, key in (("All weekdays", "conditional_evidence"),
                       ("Earliest representatives", "primary_conditional_evidence"),
                       ("Qualified severe", "severe_conditional_evidence")):
        value = report[key]["by_mode"]["incident_profile"]["comparable_switch_vs_stay"]
        lines.append(_table_row([title, value.get("without_unverified_selected_wait", 0),
            value.get("conditional_on_unverified_selected_wait", 0)]))
    lines += ["", "Both groups remain historical feed-policy simulations. The second group additionally depends "
        "on waiting through an interval whose selected departure could not be verified; it must not be described "
        "as independently confirmed actual passenger time saving.", "",
        "## Five-corridor detail", "",
        "| Corridor | Checkpoints | Families | Switch | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for corridor in report["corridors"]:
        value = report["per_corridor_summary"][corridor["id"]]
        lines.append(_table_row([corridor.get("name", corridor["id"]), value["cases"],
            value["corridor_incidents"], *repair.count_row(value)]))
    lines += ["", "## Raw-MTA Stay / model Switch", "",
        "| Scope | Cases | Comparable | Gain | Tie | Loss | Unknown |", "|---|---:|---:|---:|---:|---:|---:|"]
    for title, value in rows:
        row, c = value["mta_stay_model_switch"], value["mta_stay_model_switch"]["classes"]
        lines.append(_table_row([title, row["cases"], row["comparable"], c.get("MEANINGFUL_GAIN", 0),
            c.get("PRACTICAL_TIE", 0), c.get("MEANINGFUL_LOSS", 0), c.get("UNKNOWN", 0)]))
    lines += ["", "## Policy comparisons with identical feed-following execution", "",
        "| Scope / comparison | Concrete pairs | Comparable | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for title, summary in rows[:2]:
        for comparison, row in summary["paired_policies"].items():
            c = row["classes"]
            lines.append(_table_row([title + " / " + comparison, row["eligible_actions"], row["comparable"],
                c.get("MEANINGFUL_GAIN", 0), c.get("PRACTICAL_TIE", 0), c.get("MEANINGFUL_LOSS", 0), c.get("UNKNOWN", 0)]))
    lines += ["", "Own-Stay gains do not establish incremental model gains over the raw-MTA policy. All policies "
        "share the same route execution and walking assumptions.", "",
        "## Changed evaluator, unchanged advice", "",
        "| Scope / evaluator | Switch | Gain | Tie | Loss | Unknown |", "|---|---:|---:|---:|---:|---:|"]
    for title, key in (("All weekdays", "all_summary"), ("Earliest representatives", "primary_summary"),
                       ("Qualified severe", "severe_summary")):
        lines.append(_table_row([title + " / strict first-service ordering", *repair.count_row(report["strict_executor_summaries"][key])]))
        lines.append(_table_row([title + " / visible-feed choices", *repair.count_row(report[key])]))
    lines += ["", "Only the evaluator changes between these rows. Route recommendations, selected forecast trains, "
        "model and margins are byte-for-byte reused. Changes in inferred savings or coverage are not new algorithm advice.", "",
        "## Outcome-quality correction after the initial feed replay", "",
        "| Scope / evidence screen | Switch | Gain | Tie | Loss | Unknown |", "|---|---:|---:|---:|---:|---:|"]
    for title, key in (("All weekdays", "all_summary"), ("Earliest representatives", "primary_summary"),
                       ("Qualified severe", "severe_summary")):
        lines.append(_table_row([title + " / superseded initial screen", *repair.count_row(report["initial_visible_feed_summaries"][key])]))
        lines.append(_table_row([title + " / corrected selected-leg screen", *repair.count_row(report[key])]))
    quality = report["outcome_quality_screening"]
    lines += ["", "Across all supplied paths, {} selected route queries involving {} unique train/segment "
        "pairs are rejected by the physical sanity screen. Raw endpoint values and the rejection evidence remain "
        "in the result artifacts. Rejected route evidence becomes unknown and is never replaced with a forecast, "
        "a clamped duration, or another train chosen using final labels.".format(
            quality["selected_route_queries_rejected"], quality["unique_selected_legs_rejected"]), "",
        "[Post-initial-score quality addendum](../docs/november-feed-outcome-quality-addendum.md)", "",
        "## Matched old and boarding-safe advice under the new evaluator", "",
        "| Scope | Concrete pairs | Comparable | Boarding-safe faster | Tie | Boarding-safe slower | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for title, group in (("All weekdays", report["matched_version_comparisons"]),
                         ("Earliest representatives", report["primary_matched_version_comparisons"])):
        row = group["incident_profile"]; c = row["classes"]
        lines.append(_table_row([title, row["eligible_actions"], row["comparable"], c.get("MEANINGFUL_GAIN", 0),
            c.get("PRACTICAL_TIE", 0), c.get("MEANINGFUL_LOSS", 0), c.get("UNKNOWN", 0)]))
    lines += ["", "## Preserved boarding diagnostics", "",
        "| Version / policy | Concrete actions | Evaluable boarding sequences | Missed | Unknown | Switch sequences evaluable | Missed Switch | Unknown Switch |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for title, key in (("Original", "old_policy_boarding"), ("Boarding-safe", "boarding")):
        for mode in MODES:
            row = report[key]["by_mode"][mode]; a, s = row["all_boardings"], row["switch_all_boardings"]
            lines.append(_table_row([title + " / " + mode, row["concrete_actions"], a["evaluable"], a["missed"],
                a["unknown"], s["evaluable"], s["missed"], s["unknown"]]))
    lines += ["", "These independently preserved diagnostics concern the initially forecast-selected trains. "
        "Feed-following execution may select another train; eventual route completion does not erase an initial "
        "boarding-feasibility error.", "", "## Remaining unknown Switch comparisons", "",
        "| Exclusive reason | Count |", "|---|---:|"]
    unknown = report["operational"]["by_mode"]["incident_profile"]["unknown_switches"]
    for reason, count in unknown["reason_counts"].items():
        lines.append(_table_row([reason, count]))
    lines += ["", "There are {} unknown comparisons: {} incomplete chosen routes, and {} completed chosen routes "
        "with incomplete Stay. Unknown or censored duration is never replaced with a forecast or counted as a win.".format(
            unknown["count"], unknown["chosen_incomplete"], unknown["stay_incomplete_when_chosen_complete"]), "",
        "## Selected-route execution traces", "",
        "| Policy | Concrete route queries | Inferred | Unavailable | Censored | Missed selected-service attempts | Reselections |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for mode, row in report["execution_traces"]["selected_routes_by_mode"].items():
        c = row["status_counts"]
        lines.append(_table_row([mode, row["route_query_count"], c.get("INFERRED", 0), c.get("UNAVAILABLE", 0),
            c.get("CENSORED", 0), row["trace_counters"].get("known_missed_attempts", 0),
            row["trace_event_counts"].get("RESELECT", 0)]))
    switch_trace = report["execution_traces"]["switch_routes_by_mode"]["incident_profile"]
    lines += ["", "For model Switch routes specifically, the executor records {} missed selected-service attempts "
        "and {} reselections. These concern choices from the feed after reaching the platform; they are separate "
        "from the unchanged initial forecast-selected boarding diagnostic above. One journey can contain several "
        "attempts, and repeated checkpoints can reuse a train.".format(
            switch_trace["trace_counters"].get("known_missed_attempts", 0),
            switch_trace["trace_event_counts"].get("RESELECT", 0)), "",
        "Full chronological choice updates and selected evidence are retained in the hashed local shared "
        "execution artifact. The JSON report includes update counters; queries across policies are not independent journeys.", "",
        "## Preserved boarding-margin sensitivity", "",
        "| Margin seconds | Switch | Gain | Tie | Loss | Unknown |", "|---|---:|---:|---:|---:|---:|"]
    for margin in (60, 120, 180):
        summary = report["primary_summary"] if margin == 120 else report["margin_sensitivity_primary"][str(margin)]["summary"]
        lines.append(_table_row([margin, *repair.count_row(summary)]))
    lines += ["", "These are the same frozen 197-case margin scenarios, not new cases or newly fitted predictions.", "",
        "## Reproduction", "", "```sh",
        ".venv/bin/python algo/scripts/evaluate_november_feed_replay.py --freeze-only",
        ".venv/bin/python algo/scripts/evaluate_november_feed_replay.py --verify-only",
        ".venv/bin/python algo/scripts/evaluate_november_feed_replay.py", "```", "",
        "[Full results and provenance](november-feed-replay-test.json) · "
        "[Frozen inputs and execution policy](november-feed-replay-selection-frozen.json)", ""]
    REPORT.write_text("\n".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    if args.freeze_only and args.verify_only:
        parser.error("Choose one stage.")
    if args.freeze_only:
        freeze()
    elif args.verify_only:
        values = verify()
        print({"stage": "FEED_REPLAY_VERIFIED", "cases": len(values[3])}, flush=True)
    else:
        score()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
