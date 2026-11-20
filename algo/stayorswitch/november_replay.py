"""Frozen-input November evaluation of the existing five Google corridors."""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from zoneinfo import ZoneInfo

from .google_corridor_replay import POLICY as BASE_POLICY, _scope_rows
from .google_corridor_replay import asof_problem_notices as original_problem_notices
from .incremental_switch_replay import classify, policy_comparison, summary
from .preincident_replay import local_time
from .severe import MODES


POLICY = dict(BASE_POLICY,
    schema_version="november-five-corridor-replay-v1",
    study_status="FIXED_FULL_OCTOBER_MODEL_NOVEMBER_ANALYSIS_WITH_PRIOR_DATE_EXPOSURE_DISCLOSED",
    test_dates=["2026-11-01", "2026-11-18"],
    decision_lags_seconds=list(range(0, 7201, 300)),
    input_boundary_date="2026-10-31",
    fit_dates=["2026-10-01", "2026-10-31"],
    newly_unused_date_subset=["2026-11-16", "2026-11-18"],
    outcome_boundary_date="2026-11-19",
    outcome_endpoint_max_absolute_observation_age_seconds=180,
    outcome_missing_observation_time_is_unknown=True,
    prior_november_experiments_disclosed=True,
    cross_month_incident_policy="RETAIN_AS_SEPARATE_CARRIED_IN_OR_BOUNDARY_UNRESOLVED_SUBGROUP",
    comparison_policy="COMPARE_ACTUAL_STRICT_POLICY_SELECTED_JOURNEYS",
    raw_mta_advice_is_official_mta_recommendation=False,
    walking_sensitivity_selection="ALL_PRIMARY_EVENT_SELECTED_STAY_AND_BEST_MODEL_ALTERNATIVE_ONE_COMPONENT_PLUS_OR_MINUS_120_SECONDS",
    cohort_route_aliases={"7X": "7", "FX": "F"},
    selection_uses_outcomes_or_recommendations=False)


def asof_problem_notices(index, cutoff, line, stops, incident_id, policy=POLICY):
    """Qualify base-service alert selectors without hiding the observed variant."""
    output = {v["version_id"]: v for v in original_problem_notices(index, cutoff, line, stops, incident_id, policy)}
    base = policy["cohort_route_aliases"].get(line)
    if base:
        for notice in original_problem_notices(index, cutoff, base, stops, incident_id, policy):
            if notice["version_id"] not in output:
                notice["cohort_base_route_alias"] = {"observed_route_id": line, "selector_route_id": base}
                output[notice["version_id"]] = notice
    return [output[key] for key in sorted(output)]


def select_encounter(plan, corridor, prediction, index, policy=POLICY):
    """November-only exposure selection with explicit 7X/FX base selectors."""
    cutoff = prediction["cutoff"]
    if cutoff not in plan["decision_times"]:
        return None, "OUTSIDE_PREDECLARED_CHECKPOINTS"
    reference = corridor["reference_route_id"]
    current = next((r for r in prediction["routes"] if r["id"] == reference), None)
    template = next(r for r in corridor["routes"] if r["id"] == reference)
    if current is None:
        raise ValueError("The fixed Google Stay route is absent from predictions.")
    exposed = []
    for leg in _scope_rows(current, template, cutoff, index):
        notices = asof_problem_notices(index, cutoff, leg["route_id"], leg["segment_stop_ids"], plan["incident_id"], policy)
        if not notices:
            continue
        context = leg["context"]
        row = {k: deepcopy(v) for k, v in leg.items() if k != "context"}
        row.update(notices=deepcopy(notices), evidence_status=context.get("evidence_status"),
            applicable=context.get("applicable"), ambiguous_scope=context.get("ambiguous_scope", False))
        exposed.append(row)
    if not exposed:
        return None, "NO_ASOF_RECORDED_PROBLEM_FOR_FIXED_STAY"
    encoded = json.dumps(exposed, sort_keys=True, separators=(",", ":"))
    semantic = [{k: deepcopy(v) for k, v in leg.items() if k != "evidence_status"} for leg in exposed]
    for leg in semantic:
        leg["notices"] = [{k: v for k, v in notice.items() if k not in ("captured_at", "age_seconds")}
                          for notice in leg["notices"]]
    group = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]
    identity = "{}--{}--{}".format(corridor["id"], plan["incident_id"].replace(":", "-"), int(cutoff * 1000))
    return {"id": identity, "corridor_id": corridor["id"], "incident_ids": [plan["incident_id"]],
        "decision_at": cutoff, "local_time": local_time(cutoff), "split": "test",
        "reference_route_id": reference, "first_family_receipt": plan["first_family_receipt"],
        "first_problem_receipt": plan["first_problem_receipt"], "lag_seconds": cutoff - plan["first_problem_receipt"],
        "asof_mta_prediction": deepcopy(prediction), "exposure": exposed, "review_group_id": group,
        "exposure_sha256": hashlib.sha256(encoded.encode()).hexdigest(), "selection_uses_outcomes": False}, None


def plan_incidents(inventory, corridor, policy=POLICY):
    """Include fixed checkpoints for new and explicitly carried-in families."""
    zone = ZoneInfo("America/New_York")
    start = datetime.fromisoformat(policy["test_dates"][0]).replace(tzinfo=zone).timestamp()
    end = (datetime.fromisoformat(policy["test_dates"][1]).replace(tzinfo=zone)
           + timedelta(days=1)).timestamp()
    stay = next(r for r in corridor["routes"] if r["id"] == corridor["reference_route_id"])
    allowed = {line for leg in stay["legs"] for line in leg.get("route_ids", [leg["route_id"]])}
    plans, excluded = [], Counter()
    for family in inventory["incidents"]:
        if not allowed.intersection(family["route_ids"]):
            continue
        problems = []
        for version in family["versions"]:
            lines = {str(s["route_id"]) for s in version["alert"].get("informed_entities", [])
                     if s.get("route_id") is not None}
            if version["state"] in policy["problem_states"] and (not lines or lines.intersection(allowed)):
                problems.append(version)
        if not problems:
            excluded["NO_UNPLANNED_CLASSIFIED_SERVICE_PROBLEM"] += 1
            continue
        first_family = family["first_observed_at"]
        first_problem = min(v["first_observed_at"] for v in problems)
        anchor = max(start, first_problem)
        if anchor >= end:
            excluded["PROBLEM_AFTER_EVALUATION_END"] += 1
            continue
        origin = ("CARRIED_IN_FROM_OCTOBER" if first_family < start else
                  "LEFT_BOUNDARY_ORIGIN_UNRESOLVED" if first_family < start + 300 else
                  "FIRST_OBSERVED_DURING_NOVEMBER")
        # Broad input-only preparation must include later direction/segment
        # changes. Review identifies the first actually applicable receipt;
        # the final cohort is trimmed to that receipt's fixed two-hour window.
        anchors = {max(start, v["first_observed_at"]) for v in problems if v["first_observed_at"] < end}
        cutoffs = {at + lag for at in anchors for lag in policy["decision_lags_seconds"]}
        cutoffs = sorted(t for t in cutoffs if start <= t < end)
        plans.append({"corridor_id": corridor["id"], "incident_id": family["incident_id"],
            "first_family_receipt": first_family, "first_problem_receipt": first_problem,
            "evaluation_anchor": anchor, "incident_origin": origin,
            "candidate_receipt_anchors": sorted(anchors),
            "decision_times": cutoffs, "route_ids": family["route_ids"]})
    return sorted(plans, key=lambda p: (p["evaluation_anchor"], p["incident_id"])), dict(excluded)


def select_applicable_windows(confirmed, plans, policy=POLICY):
    """Fix each window from its earliest text-confirmed applicable receipt."""
    lookup = {(p["corridor_id"], p["incident_id"]): p for values in plans.values() for p in values}
    grouped = {}
    for case in confirmed:
        grouped.setdefault((case["corridor_id"], case["incident_ids"][0]), []).append(case)
    selected, excluded, anchors = [], [], []
    for key, values in sorted(grouped.items()):
        plan = lookup[key]
        receipts = set(plan["candidate_receipt_anchors"])
        candidates = [c for c in values if c["decision_at"] in receipts]
        if not candidates:
            # A later path can become applicable without evidence that its
            # original notice receipt was applicable. Keep this explicit and
            # do not invent a first-applicable anchor from later outcomes.
            excluded.extend({"id": c["id"], "reason": "NO_TEXT_CONFIRMED_APPLICABLE_RECEIPT"} for c in values)
            continue
        anchor = min(c["decision_at"] for c in candidates)
        allowed = {anchor + lag for lag in policy["decision_lags_seconds"]}
        allowed.update(at for at in receipts if anchor <= at <= anchor + policy["decision_window_seconds"])
        anchors.append({"corridor_id": key[0], "incident_id": key[1], "first_applicable_receipt": anchor})
        for case in values:
            if case["decision_at"] not in allowed:
                excluded.append({"id": case["id"], "reason": "OUTSIDE_FIRST_APPLICABLE_FIXED_WINDOW"})
                continue
            value = deepcopy(case)
            value["evaluation_anchor"] = anchor
            value["lag_from_first_applicable_seconds"] = case["decision_at"] - anchor
            selected.append(value)
    return sorted(selected, key=lambda c: (c["decision_at"], c["id"])), excluded, anchors


def compare_modes(case, baseline_mode, model_mode):
    """Compare each policy's actual recommendation, including selected trains."""
    baseline, model = case["modes"][baseline_mode], case["modes"][model_mode]
    left, right = baseline["strict_decision"], model["strict_decision"]
    eligible = left["action"] in ("STAY", "SWITCH") and right["action"] in ("STAY", "SWITCH")
    left_out = baseline["outcomes"].get(left["recommended_itinerary_id"], {})
    right_out = model["outcomes"].get(right["recommended_itinerary_id"], {})
    comparable = eligible and left_out.get("status") == right_out.get("status") == "INFERRED"
    gain = left_out["total_duration_seconds"] - right_out["total_duration_seconds"] if comparable else None
    return {"baseline_mode": baseline_mode, "model_mode": model_mode,
        "baseline_action": left["action"], "model_action": right["action"],
        "baseline_route_id": left["recommended_itinerary_id"], "model_route_id": right["recommended_itinerary_id"],
        "eligible_actions": eligible, "comparable": comparable,
        "gain_seconds": gain, "classification": classify(gain)}


def score_annotations(case):
    result = deepcopy(case)
    result["policy_comparison"] = policy_comparison(result)
    result["paired_policies"] = {
        "time_vs_mta": compare_modes(result, "mta", "time_profile"),
        "incident_vs_mta": compare_modes(result, "mta", "incident_profile"),
        "incident_vs_time": compare_modes(result, "time_profile", "incident_profile")}
    return result


def cohort_summary(cases):
    result = summary(cases)
    result["unique_incident_count"] = len({i for c in cases for i in c["incident_ids"]})
    result["incident_origin_counts"] = dict(Counter(c["incident_origin"] for c in cases))
    result["severe_evidence_basis_counts"] = dict(Counter(
        c["official_text_review"].get("severity_basis") or "UNSPECIFIED"
        for c in cases if c["official_text_review"]["confirmed_impact"] == "SEVERE"))
    result["planned_through_service_unavailable_cases"] = sum(
        c["official_text_review"].get("planned_through_service_unavailable") is True for c in cases)
    result["by_mode"] = {}
    for mode in MODES:
        values = [c["modes"][mode] for c in cases]
        switches = [v for v in values if v["strict_decision"]["action"] == "SWITCH"]
        stays = [v for v in values if v["strict_decision"]["action"] == "STAY"]
        selected_status = Counter(v["outcomes"].get(v["strict_decision"]["recommended_itinerary_id"], {})
                                  .get("status", "NO_SELECTED_JOURNEY") for v in values)
        result["by_mode"][mode] = {
            "actions": dict(Counter(v["strict_decision"]["action"] for v in values)),
            "switch_outcomes": dict(Counter(v["scores"]["strict_decision"]["classification"] for v in switches)),
            "stay_outcomes": dict(Counter(v["scores"]["strict_decision"]["classification"] for v in stays)),
            "selected_journey_statuses": dict(selected_status),
            "known_missed_selected_journeys": selected_status["MISSED_SELECTED_TRAIN"],
            "complete_candidate_outcome_cases": sum(v["scores"]["strict_decision"]
                ["all_forecast_selected_candidate_outcomes_available"] for v in values)}
    result["paired_policies"] = {}
    for key in ("time_vs_mta", "incident_vs_mta", "incident_vs_time"):
        rows = [c["paired_policies"][key] for c in cases if c["paired_policies"][key]["eligible_actions"]]
        result["paired_policies"][key] = {"eligible_actions": len(rows),
            "comparable": sum(r["comparable"] for r in rows),
            "classes": dict(Counter(r["classification"] for r in rows))}
    return result


def date_subset(case, first="2026-11-16", last="2026-11-18"):
    return first <= local_time(case["decision_at"])[:10] <= last
