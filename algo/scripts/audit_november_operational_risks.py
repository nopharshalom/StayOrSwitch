#!/usr/bin/env python3
"""Describe operational risks in frozen November weekday replay results.

This is a post-scoring diagnostic, not a new experiment, model fit or outcome
screen. It reads only the sealed scored artifact and its published report.
"""

from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "algo/reports/november-weekday-test.json"
OUTPUT = ROOT / "algo/reports/november-weekday-operational-diagnostics.json"
MODES = ("mta", "time_profile", "incident_profile")
CONCRETE = {"STAY", "SWITCH"}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def selected(case, mode):
    value = case["modes"][mode]
    decision = value["strict_decision"]
    outcome = value["outcomes"].get(decision["recommended_itinerary_id"], {})
    return value, decision, outcome


def status(outcome):
    return outcome.get("status", "NO_SELECTED_JOURNEY")


def make_diagnostics(report, cases):
    primary_ids = {case["id"] for case in report["cases"] if case["primary"]}
    if {case["id"] for case in cases} != {case["id"] for case in report["cases"]}:
        raise ValueError("Scored and published case membership differ.")
    modes = {}
    for mode in MODES:
        actions, statuses, reasons = Counter(), Counter(), Counter()
        missed_corridors, missed_actions, missed_legs = Counter(), Counter(), Counter()
        unavailable_reasons, unavailable_flags = Counter(), Counter()
        missed_pairs, missed_publishers, misses = set(), set(), []
        for case in cases:
            value, decision, outcome = selected(case, mode)
            actions[decision["action"]] += 1
            statuses[status(outcome)] += 1
            if decision["action"] == "UNDETERMINED":
                reasons.update(decision["reason_codes"])
            if status(outcome) == "UNAVAILABLE":
                unavailable_reasons[outcome.get("reason", "UNKNOWN_REASON")] += 1
                for endpoint, flags in outcome.get("endpoint_flags", {}).items():
                    unavailable_flags.update(endpoint + ":" + flag for flag in flags)
            if status(outcome) == "MISSED_SELECTED_TRAIN":
                missed_corridors[case["corridor_id"]] += 1
                missed_actions[decision["action"]] += 1
                missed_legs[str(outcome["leg_index"])] += 1
                missed_pairs.add((case["corridor_id"], tuple(case["incident_ids"])))
                missed_publishers.update(case["incident_ids"])
                misses.append(outcome["platform_ready_at"] - outcome["departure_at"])
        expected = report["all_summary"]["by_mode"][mode]
        if dict(actions) != expected["actions"] or dict(statuses) != expected["selected_journey_statuses"]:
            raise ValueError("Regenerated actions/statuses differ from the frozen report.")
        if len(misses) != expected["known_missed_selected_journeys"]:
            raise ValueError("Regenerated missed selected journeys differ from the report.")
        concrete = sum(actions[action] for action in CONCRETE)
        ordered = sorted(misses)
        modes[mode] = {
            "actions": dict(actions),
            "concrete_actions": concrete,
            "selected_journey_statuses": dict(statuses),
            "undetermined_reasons": dict(reasons),
            "known_missed_selected_journeys": len(misses),
            "known_misses_per_concrete_action": len(misses) / concrete if concrete else None,
            "missed_by_corridor": dict(missed_corridors),
            "missed_by_action": dict(missed_actions),
            "missed_by_zero_based_leg_index": dict(missed_legs),
            "missed_corridor_publisher_families": len(missed_pairs),
            "missed_distinct_publisher_ids": len(missed_publishers),
            "missed_boarding_seconds": {
                "minimum": min(misses) if misses else None,
                "median": (ordered[len(ordered) // 2] if len(ordered) % 2 else
                           sum(ordered[len(ordered) // 2 - 1:len(ordered) // 2 + 1]) / 2)
                          if ordered else None,
                "maximum": max(misses) if misses else None,
            },
            "unavailable_selected_journey_reasons": dict(unavailable_reasons),
            "unavailable_endpoint_flags_nonexclusive": dict(unavailable_flags),
        }

    paired_statuses, model_miss_raw_statuses = Counter(), Counter()
    unknown_switches, correction_levels = Counter(), Counter()
    correction_enabled, model_misses, same_route_raw_statuses = [], [], Counter()
    for case in cases:
        value, decision, outcome = selected(case, "incident_profile")
        raw, raw_decision, raw_outcome = selected(case, "mta")
        if decision["action"] in CONCRETE and raw_decision["action"] in CONCRETE:
            paired_statuses[(status(raw_outcome), status(outcome))] += 1
        if (decision["action"] == "SWITCH" and
                value["scores"]["strict_decision"]["classification"] == "UNKNOWN"):
            stay = value["outcomes"][case["reference_route_id"]]
            unknown_switches[(status(outcome), status(stay))] += 1
        if status(outcome) != "MISSED_SELECTED_TRAIN":
            continue
        model_miss_raw_statuses[status(raw_outcome)] += 1
        route = next(route for route in value["routes"]
                     if route["id"] == decision["recommended_itinerary_id"])
        leg = route["selected_legs"][outcome["leg_index"]]
        correction = leg["corrections"]["departure"]
        if not math.isclose(leg["baseline_departure_at"] + correction["correction_seconds"],
                            leg["departure_at"], abs_tol=0.000001, rel_tol=0):
            raise ValueError("Departure correction arithmetic differs from frozen selected leg.")
        correction_levels[correction["level"]] += 1
        raw_same_route = raw["outcomes"].get(decision["recommended_itinerary_id"], {})
        same_route_raw_statuses[status(raw_same_route)] += 1
        enabled = leg["baseline_departure_at"] < leg["platform_ready_at"] <= leg["departure_at"]
        row = {
            "case_id": case["id"], "corridor_id": case["corridor_id"],
            "incident_ids": case["incident_ids"], "local_time": case["local_time"],
            "primary": case["id"] in primary_ids,
            "model_action": decision["action"],
            "model_route_id": decision["recommended_itinerary_id"],
            "selected_trip_id": outcome["trip_id"],
            "failed_leg_index": outcome["leg_index"],
            "from_stop_id": outcome["from_stop_id"], "to_stop_id": outcome["to_stop_id"],
            "raw_departure_at": leg["baseline_departure_at"],
            "corrected_departure_at": leg["departure_at"],
            "forecast_platform_ready_at": leg["platform_ready_at"],
            "final_proxy_departure_at": outcome["departure_at"],
            "outcome_platform_ready_at": outcome["platform_ready_at"],
            "missed_boarding_seconds": outcome["platform_ready_at"] - outcome["departure_at"],
            "departure_correction_seconds": correction["correction_seconds"],
            "departure_profile_level": correction["level"],
            "raw_departure_ineligible_corrected_eligible": enabled,
            "raw_policy_action": raw_decision["action"],
            "raw_policy_selected_journey_status": status(raw_outcome),
            "raw_mode_same_route_outcome_status": status(raw_same_route),
        }
        if enabled:
            correction_enabled.append(row)
        model_misses.append(row)

    eligible = report["all_summary"]["paired_policies"]["incident_vs_mta"]["eligible_actions"]
    if sum(paired_statuses.values()) != eligible:
        raise ValueError("Paired concrete-action denominator differs from the report.")
    expected_unknown = report["all_summary"]["by_mode"]["incident_profile"]["switch_outcomes"]["UNKNOWN"]
    if sum(unknown_switches.values()) != expected_unknown:
        raise ValueError("Unknown Switch denominator differs from the report.")

    pilot_id = "pilot_hayden_tandon"
    pilot = next(corridor for corridor in report["corridors"] if corridor["id"] == pilot_id)
    pilot_cases = [case for case in cases if case["corridor_id"] == pilot_id]
    pilot_modes = {}
    for mode in MODES:
        reasons, actions, unavailable = Counter(), Counter(), defaultdict(Counter)
        for case in pilot_cases:
            value, decision, _ = selected(case, mode)
            reasons.update(decision["reason_codes"])
            actions[decision["action"]] += 1
            for route in value["routes"]:
                if not route.get("comparison_eligible"):
                    unavailable[route["id"]].update(route.get("reason_codes", []))
        pilot_modes[mode] = {
            "actions": dict(actions), "decision_reasons": dict(reasons),
            "unavailable_route_reasons": {key: dict(counter) for key, counter in unavailable.items()},
        }
    return {
        "schema_version": "november-weekday-operational-diagnostics-v1",
        "stage": "POST_SCORING_DIAGNOSTIC_OF_FROZEN_RESULTS",
        "analysis_dates": report["policy"]["analysis_dates"],
        "case_count": len(cases),
        "mutates_predictions_labels_or_selection": False,
        "findings_are_exploratory": True,
        "interpretation": [
            "Counts are repeated decision checkpoints, not independent passengers or causal incidents.",
            "Missed selected trains are observed operational failures under fixed walking and proxy-label assumptions; full alternative travel times remain unknown.",
            "Known-miss fractions use all concrete actions and are not complete failure rates because other selected outcomes are unavailable.",
            "Correction-enabled rows show a positive departure correction crossing the forecast boarding boundary; they do not by themselves establish a final destination-time loss.",
            "For transfer legs, forecast and outcome platform-ready times can differ; first-leg cases share the same fixed access-walk ready time.",
            "An unresolved provider candidate blocks complete-comparison Stay, but a sufficiently faster assessed alternative can still trigger Switch.",
            "The original predictor, cohort, advice, outcome screening and reports remain unchanged.",
        ],
        "by_mode": modes,
        "paired_concrete_actions": {
            "denominator": eligible,
            "raw_complete_model_missed": paired_statuses[("INFERRED", "MISSED_SELECTED_TRAIN")],
            "raw_missed_model_complete": paired_statuses[("MISSED_SELECTED_TRAIN", "INFERRED")],
            "both_missed": paired_statuses[("MISSED_SELECTED_TRAIN", "MISSED_SELECTED_TRAIN")],
            "raw_vs_model_status_counts": [
                {"raw_status": raw_status, "model_status": model_status, "count": count}
                for (raw_status, model_status), count in sorted(paired_statuses.items())],
        },
        "model_misses": {
            "count": len(model_misses),
            "raw_policy_selected_statuses": dict(model_miss_raw_statuses),
            "raw_mode_same_route_outcome_statuses": dict(same_route_raw_statuses),
            "positive_departure_correction_count": sum(row["departure_correction_seconds"] > 0 for row in model_misses),
            "departure_profile_levels": dict(correction_levels),
            "cases": model_misses,
        },
        "raw_departure_ineligible_corrected_eligible_misses": {
            "count": len(correction_enabled),
            "first_leg_count": sum(row["failed_leg_index"] == 0 for row in correction_enabled),
            "transfer_leg_count": sum(row["failed_leg_index"] > 0 for row in correction_enabled),
            "cases": correction_enabled,
        },
        "unknown_model_switches": {
            "count": sum(unknown_switches.values()),
            "selected_switch_missed": sum(count for (chosen_status, _), count in unknown_switches.items()
                                          if chosen_status == "MISSED_SELECTED_TRAIN"),
            "selected_switch_endpoint_unusable": sum(count for (chosen_status, _), count in unknown_switches.items()
                                                     if chosen_status == "UNAVAILABLE"),
            "selected_switch_complete_but_stay_unknown": sum(count for (chosen_status, stay_status), count in unknown_switches.items()
                                                             if chosen_status == "INFERRED" and stay_status != "INFERRED"),
            "chosen_vs_stay_status_counts": [
                {"chosen_status": chosen_status, "stay_status": stay_status, "count": count}
                for (chosen_status, stay_status), count in sorted(unknown_switches.items())],
        },
        "pilot_no_stay": {
            "corridor_id": pilot_id, "case_count": len(pilot_cases),
            "unresolved_provider_candidates": pilot.get("unavailable_candidates", []),
            "by_mode": pilot_modes,
            "interpretation": "The retained provider E-to-A candidate lacks a transfer walk and is comparison-ineligible at every pilot checkpoint. Complete-comparison Stay is therefore impossible in this frozen configuration; zero Stay is not evidence that all pilot Stay choices would be wrong.",
        },
    }


def main():
    report_sha = sha(REPORT)
    with REPORT.open() as handle:
        report = json.load(handle)
    scored = ROOT / report["scored_artifact"]["path"]
    if sha(scored) != report["scored_artifact"]["sha256"]:
        raise ValueError("The scored artifact does not match the report's frozen reference.")
    with gzip.open(scored, "rt") as handle:
        cases = json.load(handle)
    result = make_diagnostics(report, cases)
    result["provenance"] = {
        "published_report": {"path": str(REPORT.relative_to(ROOT)), "sha256": report_sha},
        "scored_artifact": report["scored_artifact"],
        "weekday_view_freeze": report["view_freeze"],
        "training": report["training"],
        "producer": artifact(Path(__file__).resolve()),
    }
    if sha(REPORT) != report_sha or sha(scored) != report["scored_artifact"]["sha256"]:
        raise ValueError("Frozen inputs changed during the diagnostic.")
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"artifact": artifact(OUTPUT),
        "cases": len(cases),
        "model_misses": result["model_misses"]["count"],
        "correction_enabled_misses": result["raw_departure_ineligible_corrected_eligible_misses"]["count"]}))


if __name__ == "__main__":
    main()
