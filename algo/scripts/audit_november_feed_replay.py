#!/usr/bin/env python3
"""Independently audit visible-feed replay arithmetic, traces and provenance.

Only standard-library code and the preserved independent arithmetic audit are
used. Prediction, execution and report-summarization implementations are not
imported. Full route evidence is validated once and then compacted in memory.
"""

from collections import Counter
from datetime import datetime, timezone
import gc
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "algo/scripts/audit_november_repair_results.py"
spec = importlib.util.spec_from_file_location("preserved_independent_arithmetic", HELPER)
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)
REPORT = ROOT / "algo/reports/november-feed-replay-test.json"
OUTPUT = ROOT / "algo/reports/november-feed-replay-independent-audit.json"
MODES = H.MODES


def trace_check(outcome, template, cutoff):
    """Check every new trace without calling the executor or data adapter."""
    traces = outcome.get("update_trace", [])
    intervals = outcome.get("conditional_wait_intervals", [])
    H.equal(outcome.get("conditional_on_unverified_selected_wait"), bool(intervals),
            "Conditional waiting flag matches evidence", "trace")
    H.equal(outcome.get("conditional_waiting"), bool(intervals),
            "Legacy conditional flag matches evidence", "trace")
    if outcome.get("reason") == "INCOMPLETE_ROUTE_TEMPLATE":
        H.equal(traces, [], "Incomplete template has no invented feed trace", "trace")
        return
    H.equal(outcome["prediction_boarding_buffer_added_to_elapsed_time"], False,
            "No prediction buffer is imposed during execution", "trace")
    active, selections, previous_times, boarded, missed_at = {}, {}, {}, set(), {}
    trace_counts = Counter()
    selections_count = 0
    for row in traces:
        action, leg, at = row["action"], row["leg_index"], row.get("at", row.get("start_at"))
        H.check(0 <= leg < len(template["legs"]), "Trace leg belongs to route", "trace")
        H.check(at >= previous_times.get(leg, cutoff), "Trace chronology", "trace")
        previous_times[leg] = at
        trace_counts[action] += 1
        if action in {"SELECT", "RESELECT", "KEEP", "NO_CANDIDATE"}:
            H.check(leg not in boarded, "No new choice after boarding", "trace")
            if leg in missed_at:
                H.check(at > missed_at[leg], "No instantaneous hindsight fallback", "trace")
            H.check(row["source_at"] <= row["snapshot_at"] <= at,
                    "Selection uses an already captured feed", "trace")
            H.check(at - row["source_at"] <= 120, "Selection source freshness", "trace")
            H.equal(row["selection_reads_endpoint_labels"], False, "Input-only choice marker", "trace")
            candidates = row["candidate_departures"]
            keys = []
            for candidate in candidates:
                H.equal(set(candidate), {"event_key", "canonical_trip_id", "departure_forecast_at",
                                         "effective_departure_at", "due_now"},
                        "Selection candidates exclude final evidence", "trace")
                effective = max(at, candidate["departure_forecast_at"])
                H.near(candidate["effective_departure_at"], effective, "DUE_NOW priority")
                H.equal(candidate["due_now"], candidate["departure_forecast_at"] <= at,
                        "DUE_NOW flag", "trace")
                keys.append((effective, str(candidate.get("canonical_trip_id") or candidate["event_key"]),
                             str(candidate["event_key"])))
            H.equal(keys, sorted(keys), "Candidates ordered by visible departure and stable identity", "trace")
            expected = candidates[0]["event_key"] if candidates else None
            H.equal(row["event_key"], expected, "Earliest visible input selected", "trace")
            old = active.get(leg)
            expected_action = ("NO_CANDIDATE" if expected is None else "KEEP" if old == expected
                               else "SELECT" if old is None else "RESELECT")
            H.equal(action, expected_action, "Selection transition", "trace")
            if expected != old and expected is not None:
                selections[leg] = (expected, at, row["snapshot_at"])
                selections_count += 1
            active[leg] = expected
        elif action == "BOARD":
            H.check(leg not in boarded, "One boarding per leg", "trace")
            H.equal(row["event_key"], active.get(leg), "Only selected service boards", "trace")
            H.equal((row["event_key"], row["selection_at"], row["selection_snapshot_at"]),
                    selections[leg], "Boarding retains causal selection", "trace")
            H.check(at >= row["selection_at"], "Boarding never backdated", "trace")
            H.equal(row["boarding_precedes_equal_time_feed_update"], True, "Equal-time ordering", "trace")
            boarded.add(leg)
        elif action == "MISSED_SELECTED_SERVICE":
            H.equal(row["event_key"], active.get(leg), "Miss diagnoses selected service", "trace")
            H.check(row["departure_at"] < at, "Known selected departure precedes selection", "trace")
            H.equal(row["selection_uses_this_departure"], False, "Miss not a selection input", "trace")
            missed_at[leg] = at
        elif action == "CONDITIONAL_WAIT":
            H.equal(row["event_key"], active.get(leg), "Conditional wait concerns selected service", "trace")
            H.check(row["start_at"] < row["end_at"] < row["forecast_departure_at"],
                    "Unverified waiting ends strictly before forecast boundary", "trace")
        elif action == "UNVERIFIED_BOARDING_BOUNDARY":
            H.equal(row["event_key"], active.get(leg), "Unknown boundary belongs to selected service", "trace")
            H.near(row["at"], row["forecast_departure_at"], "Unknown boarding boundary")
            H.equal(outcome["status"], "UNAVAILABLE", "Unknown selected boarding does not become completion", "trace")
            H.equal(outcome["reason"], "SELECTED_TRAIN_DEPARTURE_UNAVAILABLE", "Unknown selected reason", "trace")
    counter = outcome.get("trace_counters", {})
    H.equal(counter.get("conditional_wait_intervals", 0), len(intervals), "Conditional interval count", "trace")
    H.equal(counter.get("unverified_selected_wait_intervals", 0), len(intervals), "Unverified interval count", "trace")
    H.equal(counter.get("chosen_train_updates", 0), selections_count, "Train choice updates", "trace")
    H.equal(counter.get("known_missed_attempts", 0), trace_counts["MISSED_SELECTED_SERVICE"],
            "Known missed attempt count", "trace")
    H.equal(len(intervals), trace_counts["CONDITIONAL_WAIT"], "Conditional intervals appear in trace", "trace")
    if outcome["status"] == "INFERRED":
        ready = cutoff + template["access_walk_seconds"]
        waiting = riding = 0
        H.equal(len(outcome["selected_legs"]), len(template["legs"]), "All fixed legs completed", "trace")
        for position, leg in enumerate(outcome["selected_legs"]):
            H.near(leg["platform_ready_at"], ready, "Actual platform readiness")
            H.check(leg["departure_at"] >= ready, "Completed route has catchable boarding", "trace")
            H.check(leg["departure_at"] >= leg["selection_at"] >= leg["selection_snapshot_at"],
                    "Completed route boarding follows selection", "trace")
            H.check(leg["arrival_at"] >= leg["departure_at"], "Completed route chronology", "trace")
            waiting += leg["departure_at"] - ready
            riding += leg["arrival_at"] - leg["departure_at"]
            ready = leg["arrival_at"] + (template["transfer_walk_seconds"][position]
                    if position < len(template["transfer_walk_seconds"]) else template["egress_walk_seconds"])
        H.near(outcome["components"]["waiting_seconds"], waiting, "Actual waiting")
        H.near(outcome["components"]["riding_seconds"], riding, "Actual riding")
        H.near(outcome["destination_arrival_at"], ready, "Destination arrival")
        H.near(outcome["total_duration_seconds"], ready - cutoff, "Completed route duration")
        H.check(ready <= cutoff + 7200, "Completed route within horizon", "trace")


def conditional_summary(cases, metadata):
    output = {"conditional_is_not_an_independent_observed_passenger_outcome": True, "by_mode": {}, "paired_policies": {}}
    def chosen(case, mode):
        decision = H.decision(case, mode)
        return metadata[case["id"]].get(decision.get("recommended_itinerary_id"), {})
    for mode in MODES:
        chosen_counts, switch_counts, conditional_classes, other_classes = (Counter() for _ in range(4))
        for case in cases:
            advice = H.decision(case, mode)
            if advice["action"] not in H.CONCRETE:
                continue
            selected = chosen(case, mode)
            if selected.get("status") == "INFERRED":
                chosen_counts["conditional_on_unverified_selected_wait" if selected["conditional"] else "without_unverified_selected_wait"] += 1
            stay = metadata[case["id"]].get(case["reference_route_id"], {})
            if advice["action"] == "SWITCH" and selected.get("status") == stay.get("status") == "INFERRED":
                flag = selected["conditional"] or stay["conditional"]
                switch_counts["conditional_on_unverified_selected_wait" if flag else "without_unverified_selected_wait"] += 1
                (conditional_classes if flag else other_classes)[H.classification(stay["duration"] - selected["duration"])] += 1
        output["by_mode"][mode] = {"inferred_chosen_routes": dict(chosen_counts), "comparable_switch_vs_stay": dict(switch_counts),
            "conditional_switch_classes": dict(conditional_classes), "switch_classes_without_unverified_selected_wait": dict(other_classes)}
    for name, left, right in (("incident_vs_mta", "mta", "incident_profile"), ("time_vs_mta", "mta", "time_profile"),
                              ("incident_vs_time", "time_profile", "incident_profile")):
        counts, conditional_classes, other_classes = Counter(), Counter(), Counter()
        for case in cases:
            eligible, saving = H.pair(case, left, right)
            if not eligible or saving is None:
                continue
            flag = chosen(case, left)["conditional"] or chosen(case, right)["conditional"]
            counts["conditional_on_unverified_selected_wait" if flag else "without_unverified_selected_wait"] += 1
            (conditional_classes if flag else other_classes)[H.classification(saving)] += 1
        output["paired_policies"][name] = {"comparable": dict(counts), "conditional_classes": dict(conditional_classes),
                                           "classes_without_unverified_selected_wait": dict(other_classes)}
    return output


def aggregate_traces(rows):
    rows = list(rows)
    statuses, reasons, counters, events = (Counter() for _ in range(4))
    for row in rows:
        statuses[row["status"]] += 1
        if row.get("reason"):
            reasons[row["reason"]] += 1
        counters.update(row["counters"])
        events.update(row["events"])
    return {"route_query_count": len(rows), "status_counts": dict(statuses), "reason_counts": dict(reasons),
            "trace_counters": dict(counters), "trace_event_counts": dict(events)}


def check_evaluator_comparison(before_cases, after_cases, published):
    for mode in MODES:
        transitions, statuses, records = Counter(), Counter(), []
        recovered = lost = 0
        for before, after in zip(before_cases, after_cases):
            old = before["modes"][mode]
            current = after["modes"][mode]
            advice = H.decision(after, mode)
            H.equal(old["strict_decision"], advice, "Detailed recommendations unchanged", "case_results")
            old_class = old["scores"]["classification"]
            new_class = current["scores"]["strict_decision"]["classification"]
            transitions[old_class + " -> " + new_class] += 1
            recovered += old_class == "UNKNOWN" and new_class != "UNKNOWN"
            lost += old_class != "UNKNOWN" and new_class == "UNKNOWN"
            route = advice.get("recommended_itinerary_id")
            previous_route = next((r for r in old["selected_routes"] if r["id"] == route), {})
            previous = previous_route.get("route_execution_outcome", {})
            present = current["outcomes"].get(route, {})
            old_status, new_status = H.status(previous), H.status(present)
            statuses[old_status + " -> " + new_status] += 1
            records.append({"case_id": before["id"], "corridor_id": before["corridor_id"],
                "action": advice["action"], "selected_route_id": route,
                "old_classification": old_class, "new_classification": new_class,
                "old_selected_status": old_status, "new_selected_status": new_status,
                "old_selected_duration_seconds": previous.get("total_duration_seconds"),
                "new_selected_duration_seconds": present.get("total_duration_seconds")})
        H.equal(published[mode], {"case_count": len(after_cases), "advice_unchanged": True,
            "classification_transitions": dict(transitions), "selected_status_transitions": dict(statuses),
            "unknown_comparison_recovered": recovered, "previous_comparison_now_unknown": lost,
            "records": records}, "Evaluator comparison: " + mode, "evaluator_comparison")


def check_quality_counts(cases, metadata, records, published):
    reason = "SELECTED_OUTCOME_IMPLAUSIBLE_TRAVEL_TIME"
    unique = {(r["selected_event"]["canonical_trip_id"], r["selected_event"]["from_stop_id"],
               r["selected_event"]["to_stop_id"]) for r in records}
    modes = {}
    for mode in MODES:
        counts = {key: 0 for key in ("chosen_route_rejected", "switch_route_rejected",
            "switch_comparison_stay_rejected", "switch_comparison_either_route_rejected")}
        for case in cases:
            advice = H.decision(case, mode)
            if advice["action"] not in H.CONCRETE:
                continue
            chosen_bad = metadata[case["id"]][advice["recommended_itinerary_id"]]["reason"] == reason
            counts["chosen_route_rejected"] += chosen_bad
            if advice["action"] == "SWITCH":
                stay_bad = metadata[case["id"]][case["reference_route_id"]]["reason"] == reason
                counts["switch_route_rejected"] += chosen_bad
                counts["switch_comparison_stay_rejected"] += stay_bad
                counts["switch_comparison_either_route_rejected"] += chosen_bad or stay_bad
        modes[mode] = counts
    H.equal(published, {"selected_route_queries_rejected": len(records),
        "unique_selected_legs_rejected": len(unique), "applied_equally_to_every_route_and_policy": True,
        "rejected_outcomes_trigger_alternate_selection": False, "by_mode": modes, "records": records},
        "Outcome-quality rejection counts", "outcome_quality_counts")


def main():
    report = H.read(REPORT)
    frozen = H.artifact(report["freeze"])
    prior = H.artifact(frozen["prior_repair_freeze"])
    old_report = H.artifact(frozen["prior_repair_result"])
    H.equal(report["outcome_quality_followup_after_initial_score"], True,
            "Physical quality correction disclosed as post-initial-score", "provenance")
    H.equal(report["outcome_quality"], frozen["outcome_quality"], "Quality provenance retained", "provenance")
    for name, item in frozen["outcome_quality"].items():
        H.equal(H.sha(ROOT / item["path"]), item["sha256"], "Quality binding: " + name, "provenance")
    preserved = H.read(ROOT / "data/manifests/november-feed-replay-preservation.json")
    for path, expected in preserved["files"].items():
        H.equal(H.sha(ROOT / path), expected, "Prior file preserved: " + path, "preservation")
    for path, expected in frozen["producer_code_sha256"].items():
        H.equal(H.sha(ROOT / path), expected, "Frozen producer: " + path, "provenance")
    for name in ("policy_artifact", "protocol", "forecast_cases", "margin_sensitivity", "old_forecast_cases",
                 "source_route_archive", "source_route_archive_manifest"):
        item = frozen[name]
        H.equal(H.sha(ROOT / item["path"]), item["sha256"], "Frozen artifact: " + name, "provenance")
    for name in ("forecast_cases", "margin_sensitivity", "old_forecast_cases", "training", "selected_case_ids", "primary_case_ids"):
        H.equal(frozen[name], prior[name], "Forecast and population unchanged: " + name, "provenance")
    ids, primary_ids = frozen["selected_case_ids"], set(frozen["primary_case_ids"])
    H.equal(len(ids), 2306, "Full cohort retained", "membership")
    H.equal(len(primary_ids), 197, "Representatives retained", "membership")
    H.equal([c["id"] for c in report["cases"]], ids, "Published ordered cases", "membership")
    H.equal({c["id"] for c in report["cases"] if c["primary"]}, primary_ids,
            "Published representative IDs", "membership")
    old_advice = {c["id"]: {mode: c["modes"][mode]["strict_decision"] for mode in MODES} for c in old_report["cases"]}
    for case in report["cases"]:
        for mode in MODES:
            H.equal(case["modes"][mode]["strict_decision"], old_advice[case["id"]][mode], "Recommendations unchanged", "membership")
    H.equal(report["boarding"], old_report["boarding"], "Boarding diagnostic unchanged", "provenance")
    corridors = {c["id"]: {r["id"]: r for r in c["routes"]} for c in report["corridors"]}
    case_metadata = {c["id"]: c for c in report["cases"]}
    execution = H.artifact(report["shared_route_execution"])
    shared_hashes, metadata, quality_records = {}, {}, []
    for item in execution["cases"]:
        case = case_metadata[item["case_id"]]
        shared_hashes[item["case_id"]], metadata[item["case_id"]] = {}, {}
        for path, outcome in item["outcomes"].items():
            trace_check(outcome, corridors[case["corridor_id"]][path], case["decision_at"])
            shared_hashes[item["case_id"]][path] = H.object_hash(outcome)
            metadata[item["case_id"]][path] = {"status": outcome["status"], "duration": outcome.get("total_duration_seconds"),
                "conditional": outcome.get("conditional_on_unverified_selected_wait", False),
                "reason": outcome.get("reason"), "counters": outcome.get("trace_counters", {}),
                "events": dict(Counter(row["action"] for row in outcome.get("update_trace", [])))}
            if outcome.get("reason") == "SELECTED_OUTCOME_IMPLAUSIBLE_TRAVEL_TIME":
                quality_records.append({"case_id": item["case_id"], "route_id": path,
                    "status": outcome["status"], "reason": outcome["reason"],
                    "leg_index": outcome.get("leg_index"), "selected_event": outcome.get("event", {}),
                    "outcome_quality": outcome.get("outcome_quality")})
    del execution, case_metadata
    gc.collect()
    cases = H.compact_scored(H.artifact(report["scored_artifact"]), shared_hashes)
    original = H.compact_scored(H.artifact(report["old_policy_route_scored_artifact"]), shared_hashes)
    H.equal([c["id"] for c in cases], ids, "Scored ordered cases", "membership")
    H.equal([c["id"] for c in original], ids, "Original-policy ordered cases", "membership")
    check_evaluator_comparison(old_report["cases"], cases, report["evaluator_comparison"])
    del old_report
    initial_report = H.artifact(frozen["initial_visible_feed_run"]["result"])
    check_evaluator_comparison(initial_report["cases"], cases, report["outcome_quality_evaluator_comparison"])
    H.equal(report["initial_visible_feed_summaries"], {key: initial_report[key] for key in
            ("all_summary", "primary_summary", "severe_summary", "per_corridor_summary")},
            "Superseded initial summaries retained", "provenance")
    del initial_report
    check_quality_counts(cases, metadata, quality_records, report["outcome_quality_screening"])
    H.equal(report["execution_traces"]["all_supplied_paths"],
            aggregate_traces(row for routes in metadata.values() for row in routes.values()),
            "All path trace totals", "execution_traces")
    for mode in MODES:
        selected = [metadata[c["id"]][H.decision(c, mode)["recommended_itinerary_id"]]
                    for c in cases if H.decision(c, mode)["action"] in H.CONCRETE]
        switched = [metadata[c["id"]][H.decision(c, mode)["recommended_itinerary_id"]]
                    for c in cases if H.decision(c, mode)["action"] == "SWITCH"]
        H.equal(report["execution_traces"]["selected_routes_by_mode"][mode], aggregate_traces(selected),
                "Chosen route trace totals: " + mode, "execution_traces")
        H.equal(report["execution_traces"]["switch_routes_by_mode"][mode], aggregate_traces(switched),
                "Switch trace totals: " + mode, "execution_traces")
    H.check_scopes(cases, report, primary_ids, "feed")
    H.check_scopes(original, report["old_policy_under_feed_execution"], primary_ids, "old advice/feed")
    primary = [c for c in cases if c["id"] in primary_ids]
    original_primary = [c for c in original if c["id"] in primary_ids]
    H.check_operational(cases, report["operational"], "feed")
    H.check_operational(primary, report["primary_operational"], "feed primary")
    H.check_operational(original, report["old_policy_operational"], "old advice/feed")
    H.check_boarding(cases, report["boarding"], "feed")
    H.check_boarding(primary, report["primary_boarding"], "feed primary")
    H.check_boarding(original, report["old_policy_boarding"], "old advice/feed")
    H.check_matched(original, cases, report["matched_version_comparisons"], "old/new advice")
    H.check_matched(original_primary, primary, report["primary_matched_version_comparisons"], "primary old/new")
    for name, rows in (("conditional_evidence", cases), ("primary_conditional_evidence", primary),
                       ("severe_conditional_evidence", [c for c in cases if c["official_text_review"]["confirmed_impact"] == "SEVERE"] )):
        H.equal(report[name], conditional_summary(rows, metadata), name, "conditional_evidence")
    sensitivity = H.artifact(report["margin_sensitivity_artifact"])
    for variant in sensitivity:
        margin = str(variant["boarding_margin_seconds"])
        rows = H.compact_scored(variant["cases"], shared_hashes)
        H.equal({c["id"] for c in rows}, primary_ids, "Sensitivity population", "membership")
        published = report["margin_sensitivity_primary"][margin]
        H.check_summary(rows, published["summary"], "margin " + margin)
        H.check_operational(rows, published["operational"], "margin " + margin)
        H.check_boarding(rows, published["boarding"], "margin " + margin)
    result = {"schema_version": "november-feed-replay-independent-audit-v3", "status": "PASS",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": {"path": str(REPORT.relative_to(ROOT)), "sha256": H.sha(REPORT)},
        "audit_method": "Independent standard-library trace, arithmetic, membership, conditional-evidence and hash checks; no prediction/execution/scoring code imported.",
        "preserved_arithmetic_audit": {"path": str(HELPER.relative_to(ROOT)), "sha256": H.sha(HELPER)},
        "checks": dict(sorted(H.CHECKS.items())), "total_checks_passed": sum(H.CHECKS.values()),
        "preserved_original_files": len(preserved["files"]), "cases": len(cases), "primary_cases": len(primary_ids),
        "limits": ["Feed-policy inferred movement is not an independent passenger observation.",
                   "Independent geometry and invalid-outcome trace-prefix checks are recorded separately in november-feed-replay-quality-audit.json.",
                   "Conditional selected waiting is explicitly retained, not reclassified as proven physical waiting.",
                   "The dates were previously examined; unchanged predictions do not create a new untouched test."]}
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "total_checks_passed", "cases", "primary_cases", "preserved_original_files")}, indent=2))


if __name__ == "__main__":
    main()
