#!/usr/bin/env python3
"""Independently check frozen repair predictions, outcomes and report counts.

This audit uses only the Python standard library. It does not import prediction,
execution, classification, or report-summarization helpers from the project.
"""

from collections import Counter
from datetime import datetime, timezone
import gzip
import gc
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "algo/reports/november-repair-test.json"
OUTPUT = ROOT / "algo/reports/november-repair-independent-audit.json"
MODES = ("mta", "time_profile", "incident_profile")
CONCRETE = {"STAY", "SWITCH"}
CHECKS = Counter()


def read(path):
    path = Path(path)
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as handle:
        return json.load(handle)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def object_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def check(value, message, category="arithmetic"):
    CHECKS[category] += 1
    if not value:
        raise AssertionError(message)


def equal(actual, expected, message, category="counts"):
    if actual != expected:
        check(False, message + ": " + repr(actual)[:1500] + " != " + repr(expected)[:1500], category)
    check(True, message, category)


def near(actual, expected, message):
    check(isinstance(actual, (int, float)) and not isinstance(actual, bool)
          and math.isfinite(actual)
          and math.isclose(actual, expected, rel_tol=0, abs_tol=0.000001), message)


def artifact(item):
    path = ROOT / item["path"]
    equal(sha(path), item["sha256"], "Artifact changed: " + item["path"], "provenance")
    return read(path)


def classification(gain):
    if gain is None:
        return "UNKNOWN"
    return "MEANINGFUL_GAIN" if gain > 180 else "MEANINGFUL_LOSS" if gain < -180 else "PRACTICAL_TIE"


def decision(case, mode):
    return case["modes"][mode]["strict_decision"]


def selected(case, mode, *, fixed=False):
    item = decision(case, mode)
    if item["action"] not in CONCRETE:
        return {}
    values = (case["fixed_train_diagnostics"][mode] if fixed else
              case["modes"][mode]["outcomes"])
    return values.get(item["recommended_itinerary_id"], {})


def status(outcome):
    return outcome.get("status", "NO_SELECTED_JOURNEY")


def gain(left, right):
    if status(left) == status(right) == "INFERRED":
        return left["total_duration_seconds"] - right["total_duration_seconds"]
    return None


def pair(case, left_mode, right_mode):
    eligible = (decision(case, left_mode)["action"] in CONCRETE
                and decision(case, right_mode)["action"] in CONCRETE)
    saving = gain(selected(case, left_mode), selected(case, right_mode)) if eligible else None
    return eligible, saving


def check_summary(cases, summary, label):
    equal(summary["cases"], len(cases), label + " case count")
    equal(summary["corridor_incidents"], len({(c["corridor_id"], tuple(c["incident_ids"]))
                                              for c in cases}), label + " families")
    equal(summary["unique_incident_count"], len({i for c in cases for i in c["incident_ids"]}),
          label + " publisher IDs")
    for mode in MODES:
        actions = Counter(decision(c, mode)["action"] for c in cases)
        selected_statuses = Counter(status(selected(c, mode)) for c in cases)
        switch_classes = Counter()
        for case in cases:
            if decision(case, mode)["action"] != "SWITCH":
                continue
            saving = gain(case["modes"][mode]["outcomes"][case["reference_route_id"]],
                          selected(case, mode))
            kind = classification(saving)
            score = case["modes"][mode]["scores"]["strict_decision"]
            equal(score["classification"], kind, label + " Switch classification", "case_results")
            equal(score["inferred_switch_savings_seconds"], saving,
                  label + " Switch arithmetic", "case_results")
            switch_classes[kind] += 1
        item = summary["by_mode"][mode]
        equal(item["actions"], dict(actions), label + " actions " + mode)
        equal(item["selected_journey_statuses"], dict(selected_statuses), label + " statuses " + mode)
        equal(item["switch_outcomes"], dict(switch_classes), label + " Switch counts " + mode)
        if mode == "incident_profile":
            equal(summary["model_switch_vs_model_stay"],
                  {"recommendations": actions["SWITCH"], "classes": dict(switch_classes)},
                  label + " model own-Stay counts")
    pairs = (("time_vs_mta", "mta", "time_profile"),
             ("incident_vs_mta", "mta", "incident_profile"),
             ("incident_vs_time", "time_profile", "incident_profile"))
    for name, left, right in pairs:
        eligible_count = comparable = 0
        classes = Counter()
        for case in cases:
            eligible, saving = pair(case, left, right)
            record = case["paired_policies"][name]
            equal(record["eligible_actions"], eligible, label + " pair eligibility", "case_results")
            equal(record["comparable"], eligible and saving is not None,
                  label + " pair completeness", "case_results")
            equal(record["gain_seconds"], saving, label + " pair saving", "case_results")
            equal(record["classification"], classification(saving),
                  label + " pair classification", "case_results")
            if eligible:
                eligible_count += 1
                comparable += saving is not None
                classes[classification(saving)] += 1
        equal(summary["paired_policies"][name], {"eligible_actions": eligible_count,
              "comparable": comparable, "classes": dict(classes)}, label + " " + name)
    narrow = [c for c in cases if decision(c, "mta")["action"] == "STAY"
              and decision(c, "incident_profile")["action"] == "SWITCH"]
    savings = [gain(selected(c, "mta"), selected(c, "incident_profile")) for c in narrow]
    equal(summary["mta_stay_model_switch"], {"cases": len(narrow),
          "comparable": sum(v is not None for v in savings),
          "classes": dict(Counter(classification(v) for v in savings))}, label + " narrow comparison")


def check_operational(cases, report, label):
    equal(report["case_count"], len(cases), label + " operational cases")
    for mode in MODES:
        item = report["by_mode"][mode]
        actions = Counter(decision(c, mode)["action"] for c in cases)
        fixed = Counter(status(selected(c, mode, fixed=True)) for c in cases)
        switches = [c for c in cases if decision(c, mode)["action"] == "SWITCH"]
        switch_fixed = Counter(status(selected(c, mode, fixed=True)) for c in switches)
        equal(item["actions"], dict(actions), label + " operational actions")
        equal(item["concrete_actions"], actions["STAY"] + actions["SWITCH"], label + " concrete")
        equal(item["fixed_train_statuses"], dict(fixed), label + " original selected-train statuses")
        equal(item["known_missed_selected_journeys"], fixed["MISSED_SELECTED_TRAIN"], label + " misses")
        equal(item["known_missed_selected_switches"], switch_fixed["MISSED_SELECTED_TRAIN"],
              label + " Switch misses")
        recovered = sum(status(selected(c, mode, fixed=True)) == "MISSED_SELECTED_TRAIN"
                        and status(selected(c, mode)) == "INFERRED" for c in cases)
        equal(item["fixed_train_missed_but_route_complete"], recovered, label + " route recovery")
        pairs = Counter()
        reasons = Counter()
        chosen_incomplete = stay_incomplete = 0
        for case in switches:
            chosen = selected(case, mode)
            stay = case["modes"][mode]["outcomes"][case["reference_route_id"]]
            if status(chosen) == status(stay) == "INFERRED":
                continue
            pairs[(status(chosen), status(stay))] += 1
            if status(chosen) != "INFERRED":
                chosen_incomplete += 1
                reasons["chosen:" + status(chosen) + ":" + str(chosen.get("reason", "UNSPECIFIED"))] += 1
            else:
                stay_incomplete += 1
                reasons["stay:" + status(stay) + ":" + str(stay.get("reason", "UNSPECIFIED"))] += 1
        equal(item["unknown_switches"], {"count": sum(pairs.values()),
            "chosen_incomplete": chosen_incomplete, "stay_incomplete_when_chosen_complete": stay_incomplete,
            "status_pairs": [{"chosen_status": a, "stay_status": b, "count": n}
                             for (a, b), n in sorted(pairs.items())],
            "reason_counts": dict(sorted(reasons.items()))}, label + " unknown reasons")


def check_matched(old, new, reports, label):
    for mode in MODES:
        result = reports[mode]
        classes, action_pairs = Counter(), Counter()
        concrete = comparable = same = 0
        for left, right, saved in zip(old, new, result["records"]):
            equal(left["id"], right["id"], label + " same case", "membership")
            equal(saved["case_id"], left["id"], label + " same record", "membership")
            ld, rd = decision(left, mode), decision(right, mode)
            eligible = ld["action"] in CONCRETE and rd["action"] in CONCRETE
            saving = gain(selected(left, mode), selected(right, mode)) if eligible else None
            action_pairs[ld["action"] + "->" + rd["action"]] += 1
            concrete += eligible
            comparable += eligible and saving is not None
            same += eligible and ld["recommended_itinerary_id"] == rd["recommended_itinerary_id"]
            equal(saved["gain_seconds"], saving, label + " version saving", "case_results")
            equal(saved["classification"], classification(saving) if eligible else "NOT_A_PAIRED_DECISION",
                  label + " version classification", "case_results")
            if eligible:
                classes[classification(saving)] += 1
        equal(len(result["records"]), len(old), label + " matched records")
        equal(result["eligible_actions"], concrete, label + " matched eligible")
        equal(result["comparable"], comparable, label + " matched complete")
        equal(result["classes"], dict(classes), label + " matched classes")
        equal(result["action_pairs"], dict(action_pairs), label + " action transitions")
        equal(result["same_recommended_route_pairs"], same, label + " same route pairs")


def check_boarding(cases, report, label):
    equal(report["case_count"], len(cases), label + " boarding cases")
    for mode in MODES:
        rows, switches = [], []
        for case in cases:
            advice = decision(case, mode)
            if advice["action"] not in CONCRETE:
                continue
            path = advice["recommended_itinerary_id"]
            row = case["boarding_diagnostics"][mode][path]
            route = next(r for r in case["modes"][mode]["routes"] if r["id"] == path)
            checked = row["checked_boardings"]
            equal(row["checked_boarding_count"], len(checked), label + " checked boardings")
            equal(row["catchable_boarding_count"], sum(b["status"] == "CATCHABLE" for b in checked),
                  label + " catchable boardings")
            for index, boarding in enumerate(checked):
                equal(boarding["leg_index"], index, label + " boarding sequence", "case_results")
                expected = "MISSED_SELECTED_TRAIN" if boarding["departure_at"] < boarding["platform_ready_at"] else "CATCHABLE"
                equal(boarding["status"], expected, label + " boarding arithmetic", "case_results")
                if index == 0:
                    near(boarding["platform_ready_at"], case["decision_at"] + route["access_walk_seconds"],
                         "Actual boarding readiness excludes forecast margin")
            if checked:
                equal(row["first_boarding_status"], checked[0]["status"], label + " first boarding")
            if row["status"] == "ALL_BOARDINGS_CATCHABLE":
                equal(len(checked), len(route["selected_legs"]), label + " all boardings checked")
                check(all(b["status"] == "CATCHABLE" for b in checked), "Catchable sequence has a miss", "case_results")
            elif row["status"] == "MISSED_SELECTED_TRAIN":
                equal(checked[-1]["status"], "MISSED_SELECTED_TRAIN", label + " missed sequence")
            rows.append(row)
            if advice["action"] == "SWITCH":
                switches.append(row)
        saved = report["by_mode"][mode]
        equal(saved["concrete_actions"], len(rows), label + " boarding concrete")
        equal(saved["switch_actions"], len(switches), label + " boarding Switch")
        equal(saved["reason_counts"], dict(Counter(r.get("reason", "UNSPECIFIED") for r in rows)),
              label + " boarding reasons")
        for name, values, first in (("first_boarding", rows, True), ("all_boardings", rows, False),
                                     ("switch_first_boarding", switches, True), ("switch_all_boardings", switches, False)):
            statuses = Counter(r["first_boarding_status" if first else "status"] for r in values)
            catchable = statuses["CATCHABLE" if first else "ALL_BOARDINGS_CATCHABLE"]
            missed = statuses["MISSED_SELECTED_TRAIN"]
            evaluable = catchable + missed
            expected = {"concrete_actions": len(values), "evaluable": evaluable, "denominator": evaluable,
                "catchable": catchable, "missed": missed, "unknown": statuses["UNVERIFIABLE"],
                "known_miss_fraction_all_concrete": missed / len(values) if values else None,
                "miss_fraction_among_evaluable": missed / evaluable if evaluable else None}
            equal(saved[name], expected, label + " " + name)


def check_scopes(cases, report, primary_ids, label):
    check_summary(cases, report["all_summary"], label + " all")
    check_summary([c for c in cases if c["id"] in primary_ids], report["primary_summary"], label + " primary")
    check_summary([c for c in cases if c["official_text_review"]["confirmed_impact"] == "SEVERE"],
                  report["severe_summary"], label + " severe")
    recent = [c for c in cases if "2026-11-16" <= c["local_time"][:10] <= "2026-11-18"]
    check_summary(recent, report["november_16_18_summary"], label + " Nov16-18")
    check_summary([c for c in recent if c["id"] in primary_ids],
                  report["november_16_18_primary_summary"], label + " Nov16-18 primary")
    for corridor in sorted({c["corridor_id"] for c in cases}):
        subset = [c for c in cases if c["corridor_id"] == corridor]
        check_summary(subset, report["per_corridor_summary"][corridor], label + " " + corridor)
        check_summary([c for c in subset if c["id"] in primary_ids],
                      report["per_corridor_primary_summary"][corridor], label + " primary " + corridor)


def check_forecasts(payload, expected_margin):
    cases = payload["cases"] if "cases" in payload else payload
    for case in cases:
        cutoff = case["decision_at"]
        for mode in MODES:
            value = case["predictions"][mode]
            equal(value["policy"]["boarding_margin_seconds"], expected_margin, "Prediction margin", "forecast")
            for route in value["routes"]:
                if not route.get("selected_legs"):
                    continue
                expected_ready = conservative_ready = cutoff + route["access_walk_seconds"]
                waits = rides = 0
                for index, leg in enumerate(route["selected_legs"]):
                    if index:
                        expected_ready += route["transfer_walk_seconds"][index - 1]
                        conservative_ready += route["transfer_walk_seconds"][index - 1]
                    gate = leg["boarding_gate"]
                    near(leg["departure_at"], leg["baseline_departure_at"] + leg["corrections"]["departure"]["correction_seconds"], "Departure correction")
                    near(leg["arrival_at"], leg["baseline_arrival_at"] + leg["corrections"]["arrival"]["correction_seconds"], "Arrival correction")
                    near(gate["expected_platform_ready_at"], expected_ready, "Expected readiness")
                    near(gate["conservative_platform_ready_at"], conservative_ready, "Conservative readiness")
                    safe_departure = min(leg["baseline_departure_at"], leg["departure_at"])
                    near(gate["departure_at"], safe_departure, "Earlier departure gate")
                    check(safe_departure >= conservative_ready + expected_margin, "Selected train violates margin", "forecast")
                    check(conservative_ready >= expected_ready, "Transfer readiness became optimistic", "forecast")
                    check(leg["arrival_at"] >= leg["departure_at"] >= expected_ready, "Nonmonotonic selected times", "forecast")
                    waits += leg["departure_at"] - expected_ready
                    rides += leg["arrival_at"] - leg["departure_at"]
                    expected_ready = leg["arrival_at"]
                    conservative_ready = max(leg["baseline_arrival_at"], leg["arrival_at"])
                if route["timing_eligible"]:
                    near(route["eta"], expected_ready + route["egress_walk_seconds"], "Final expected ETA")
                    near(route["total_duration_seconds"], route["eta"] - cutoff, "Predicted duration")
                    near(route["components"]["waiting_seconds"], waits, "Expected waiting")
                    near(route["components"]["riding_seconds"], rides, "Expected riding")
                    near(sum(route["components"].values()), route["total_duration_seconds"], "Buffer not added as duration")


def compact_scored(cases, shared_hashes, old_decisions=None):
    """Validate detailed shared evidence, then release it before loading a peer.

    Full prediction/outcome artifacts are large. Keeping only the fields needed
    for independent arithmetic avoids holding multiple full archives in memory.
    The files are never edited; every full route outcome is hash-checked first.
    """
    for case in cases:
        case["exposure"] = object_hash(case["exposure"])
        review = case["official_text_review"]
        case["official_text_review"] = {"confirmed_impact": review["confirmed_impact"],
                                        "complete_review_sha256": object_hash(review)}
        for mode in MODES:
            if old_decisions is not None:
                equal(decision(case, mode), old_decisions[case["id"]][mode], "Old advice preserved", "case_results")
            value = case["modes"][mode]
            for path, outcome in value["outcomes"].items():
                if path in shared_hashes[case["id"]]:
                    equal(object_hash(outcome), shared_hashes[case["id"]][path],
                          "Shared execution is mode/version independent", "case_results")
                if status(outcome) == "INFERRED":
                    near(sum(outcome["components"].values()), outcome["total_duration_seconds"], "Execution components")
                    near(outcome["destination_arrival_at"] - case["decision_at"], outcome["total_duration_seconds"], "Execution elapsed")
                    check(outcome["total_duration_seconds"] <= 7200, "Execution exceeded horizon", "case_results")
            value["outcomes"] = {path: {k: outcome[k] for k in ("status", "reason", "total_duration_seconds") if k in outcome}
                                 for path, outcome in value["outcomes"].items()}
            value["routes"] = [{"id": route["id"], "access_walk_seconds": route.get("access_walk_seconds"),
                                "selected_legs": [None] * len(route.get("selected_legs", []))}
                               for route in value["routes"]]
            case["fixed_train_diagnostics"][mode] = {path: {"status": status(outcome)}
                                                     for path, outcome in case["fixed_train_diagnostics"][mode].items()}
    gc.collect()
    return cases


def main():
    report = read(REPORT)
    frozen = artifact(report["freeze"])
    preserved = read(ROOT / "data/manifests/november-repair-preservation.json")
    for path, expected in preserved["files"].items():
        equal(sha(ROOT / path), expected, "Preserved file " + path, "preservation")
    for path, expected in frozen["producer_code_sha256"].items():
        equal(sha(ROOT / path), expected, "Frozen producer " + path, "provenance")
    for name in ("policy_artifact", "protocol", "margin_sensitivity", "forecast_execution", "old_input_freeze"):
        item = frozen[name]
        equal(sha(ROOT / item["path"]), item["sha256"], "Frozen input " + name, "provenance")
    expected_ids = frozen["selected_case_ids"]
    primary_ids = set(frozen["primary_case_ids"])
    equal(len(expected_ids), 2306, "Unchanged cohort size", "membership")
    equal(len(primary_ids), 197, "Unchanged primary size", "membership")
    equal([c["id"] for c in report["cases"]], expected_ids, "Published ordered membership", "membership")
    equal({c["id"] for c in report["cases"] if c["primary"]}, primary_ids, "Published primary IDs", "membership")
    del report["cases"]
    original_forecasts = artifact(frozen["old_forecast_cases"])
    equal([c["id"] for c in original_forecasts["cases"]], expected_ids, "Original forecast membership", "membership")
    initial_hashes = {c["id"]: object_hash({k: v for k, v in c.items() if k != "predictions"})
                      for c in original_forecasts["cases"]}
    del original_forecasts
    gc.collect()
    forecasts = artifact(frozen["forecast_cases"])
    equal([c["id"] for c in forecasts["cases"]], expected_ids, "New forecast membership", "membership")
    for revised in forecasts["cases"]:
        equal(object_hash({k: v for k, v in revised.items() if k != "predictions"}), initial_hashes[revised["id"]],
              "Initial cutoff and incident metadata unchanged", "membership")
    check_forecasts(forecasts, 120)
    cutoff_by_id = {c["id"]: c["decision_at"] for c in forecasts["cases"]}
    del forecasts
    gc.collect()
    variants = artifact(frozen["margin_sensitivity"])["variants"]
    equal({(c["case_id"], c["boarding_margin_seconds"]) for c in variants},
          {(identity, margin) for identity in primary_ids for margin in (60, 180)},
          "Sensitivity membership", "membership")
    for row in variants:
        check_forecasts([{"decision_at": cutoff_by_id[row["case_id"]], "predictions": row["predictions"]}],
                        row["boarding_margin_seconds"])
    variant_count = len(variants)
    del variants
    gc.collect()
    execution = artifact(report["shared_route_execution"])
    shared_hashes = {c["case_id"]: {path: object_hash(outcome) for path, outcome in c["outcomes"].items()}
                     for c in execution["cases"]}
    equal(set(shared_hashes), set(expected_ids), "Shared route outcome membership", "membership")
    del execution
    gc.collect()
    original_report = artifact(report["original_fixed_train_result"])
    old_decisions = {c["id"]: {mode: c["modes"][mode]["strict_decision"] for mode in MODES}
                     for c in original_report["cases"]}
    del original_report
    gc.collect()
    scored = compact_scored(artifact(report["scored_artifact"]), shared_hashes)
    old = compact_scored(artifact(report["old_policy_route_scored_artifact"]), shared_hashes, old_decisions)
    for values in (scored, old):
        equal([c["id"] for c in values], expected_ids, "Identical ordered result membership", "membership")
    for before, after in zip(old, scored):
        for key in ("id", "corridor_id", "decision_at", "reference_route_id", "incident_ids",
                    "official_text_review", "planned_closure_timing", "exposure"):
            equal(before[key], after[key], "Outcome-independent scope preserved: " + key, "membership")
    zone = ZoneInfo("America/New_York")
    dates = set(report["policy"]["analysis_dates"])
    for case in scored:
        local = datetime.fromtimestamp(case["decision_at"], zone)
        check(local.weekday() < 5 and local.date().isoformat() in dates, "Nonweekday/out-of-scope case", "membership")
    check_scopes(scored, report, primary_ids, "new")
    check_scopes(old, report["old_policy_under_route_execution"], primary_ids, "old/new executor")
    check_operational(scored, report["operational"], "new")
    check_operational([c for c in scored if c["id"] in primary_ids], report["primary_operational"], "new primary")
    check_operational(old, report["old_policy_operational"], "old")
    check_boarding(scored, report["boarding"], "new")
    check_boarding([c for c in scored if c["id"] in primary_ids], report["primary_boarding"], "new primary")
    check_boarding(old, report["old_policy_boarding"], "old")
    check_matched(old, scored, report["matched_version_comparisons"], "all versions")
    check_matched([c for c in old if c["id"] in primary_ids], [c for c in scored if c["id"] in primary_ids],
                  report["primary_matched_version_comparisons"], "primary versions")
    sensitivity = artifact(report["margin_sensitivity_artifact"])
    for variant in sensitivity:
        margin = str(variant["boarding_margin_seconds"])
        values = compact_scored(variant["cases"], shared_hashes)
        equal({c["id"] for c in values}, primary_ids, "Scored sensitivity cohort", "membership")
        summary = report["margin_sensitivity_primary"][margin]
        check_summary(values, summary["summary"], "margin " + margin)
        check_operational(values, summary["operational"], "margin " + margin)
        check_boarding(values, summary["boarding"], "margin " + margin)
    result = {"schema_version": "november-repair-independent-audit-v1", "status": "PASS",
        "audit_method": "Independent standard-library arithmetic, membership, gate and hash checks; no project scoring helpers imported.",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": {"path": str(REPORT.relative_to(ROOT)), "sha256": sha(REPORT)},
        "checks": dict(sorted(CHECKS.items())), "total_checks_passed": sum(CHECKS.values()),
        "preserved_original_files": len(preserved["files"]), "cases": len(scored),
        "primary_cases": len(primary_ids), "sensitivity_forecasts": variant_count,
        "limits": ["Arithmetic and provenance checks do not independently observe physical passenger arrivals.",
                   "Archive first-train evidence and unknown-candidate behavior also require the separate source/execution review.",
                   "The November data were already examined; this remains a post-hoc repair comparison."]}
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
