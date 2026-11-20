"""Separate dense-checkpoint analysis of raw-MTA and historical-profile advice."""

from collections import Counter
from copy import deepcopy
import json

from .google_corridor_replay import POLICY as BASE_POLICY
from .preincident_replay import local_time


POLICY = dict(BASE_POLICY, schema_version="incremental-switch-grid-v1",
    decision_lags_seconds=list(range(0, 7201, 300)),
    family_policy="EXACT_49_PREVIOUSLY_TEXT_CONFIRMED_CORRIDOR_INCIDENT_PAIRS",
    notice_policy="EXACT_PREVIOUSLY_CONFIRMED_CORRIDOR_INCIDENT_LINE_DIRECTION_SEGMENT_VERSION_SIGNATURE",
    previous_results_known=True,
    input_freeze_precedes_new_outcome_scoring=True,
    comparison_policy="RAW_MTA_STRICT_SELECTED_JOURNEY_VS_INCIDENT_PROFILE_STRICT_SELECTED_JOURNEY",
    walking_sensitivity_selection="NO_NEW_WALK_VARIANTS; FIXED_ORIGINAL_GOOGLE_RESEARCH_WALKS",
    selection_uses_outcomes_or_recommendations=False)


def scope_signature(corridor_id, incident_ids, exposure):
    """Reuse only an already reviewed physical scope and exact notice versions."""
    rows = []
    for leg in exposure:
        rows.append({key: deepcopy(leg.get(key)) for key in
            ("leg_index", "route_id", "from_stop_id", "to_stop_id", "platform_direction",
             "segment_stop_ids", "exposure_source")} | {
                "versions": sorted(a["version_id"] for a in leg["notices"])})
    return json.dumps({"corridor_id": corridor_id, "incident_ids": sorted(incident_ids),
                       "exposure": sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))}, sort_keys=True)


def approved_scopes(review):
    result = {}
    for group in review["groups"]:
        if group["status"] != "CONFIRMED":
            continue
        for corridor in group["corridor_ids"]:
            key = scope_signature(corridor, group["incident_ids"], group["exposure"])
            row = {k: deepcopy(v) for k, v in group.items() if k not in ("case_ids", "exposure")}
            if key in result and result[key]["confirmed_impact"] != row["confirmed_impact"]:
                raise ValueError("Conflicting reviewed severity for exact same scope.")
            result.setdefault(key, row)
    return result


def dense_plans(base_plans, allowed_pairs):
    result = {}
    for corridor, plans in base_plans.items():
        result[corridor] = []
        for plan in plans:
            if (corridor, plan["incident_id"]) not in allowed_pairs:
                continue
            row = deepcopy(plan)
            times = set(plan["decision_times"])
            times.update(plan["first_problem_receipt"] + lag for lag in POLICY["decision_lags_seconds"])
            row["decision_times"] = sorted(t for t in times if
                POLICY["test_dates"][0] <= local_time(t)[:10] <= POLICY["test_dates"][1])
            result[corridor].append(row)
    return result


def qualify(case, approved):
    key = scope_signature(case["corridor_id"], case["incident_ids"], case["exposure"])
    if key not in approved:
        return None
    result = deepcopy(case)
    result["official_text_review"] = deepcopy(approved[key])
    result["review_reuse_policy"] = POLICY["notice_policy"]
    return result


def classify(gain):
    if gain is None:
        return "UNKNOWN"
    if gain > POLICY["tie_margin_seconds"]:
        return "MEANINGFUL_GAIN"
    if gain < -POLICY["tie_margin_seconds"]:
        return "MEANINGFUL_LOSS"
    return "PRACTICAL_TIE"


def policy_comparison(case):
    modes = case["modes"]
    baseline, model = modes["mta"], modes["incident_profile"]
    raw_decision, decision = baseline["strict_decision"], model["strict_decision"]
    eligible = raw_decision["action"] in ("STAY", "SWITCH") and decision["action"] in ("STAY", "SWITCH")
    raw = baseline["outcomes"].get(raw_decision["recommended_itinerary_id"], {})
    chosen = model["outcomes"].get(decision["recommended_itinerary_id"], {})
    comparable = eligible and raw.get("status") == chosen.get("status") == "INFERRED"
    gain = raw["total_duration_seconds"] - chosen["total_duration_seconds"] if comparable else None
    return {"eligible_actions": eligible,
        "raw_mta_action": raw_decision["action"], "model_action": decision["action"],
        "raw_mta_recommended_route_id": raw_decision["recommended_itinerary_id"],
        "model_recommended_route_id": decision["recommended_itinerary_id"],
        "raw_mta_selected_outcome": deepcopy(raw), "model_selected_outcome": deepcopy(chosen),
        "comparable": comparable, "gain_seconds": gain, "classification": classify(gain),
        "mta_stay_model_switch": raw_decision["action"] == "STAY" and decision["action"] == "SWITCH"}


def summary(cases):
    comparisons = [c["policy_comparison"] for c in cases]
    def counts(values):
        return {"cases": len(values), "comparable": sum(v["comparable"] for v in values),
                "classes": dict(Counter(v["classification"] for v in values))}
    switches = [c for c in cases if c["modes"]["incident_profile"]["strict_decision"]["action"] == "SWITCH"]
    return {"cases": len(cases),
        "corridor_incidents": len({(c["corridor_id"], tuple(c["incident_ids"])) for c in cases}),
        "action_pairs": dict(Counter(v["raw_mta_action"] + "->" + v["model_action"] for v in comparisons)),
        "qualified_impact_counts": dict(Counter(c["official_text_review"]["confirmed_impact"] for c in cases)),
        "all_action_eligible_policy_comparisons": counts([v for v in comparisons if v["eligible_actions"]]),
        "mta_stay_model_switch": counts([v for v in comparisons if v["mta_stay_model_switch"]]),
        "model_switch_vs_model_stay": {"recommendations": len(switches), "classes": dict(Counter(
            c["modes"]["incident_profile"]["scores"]["strict_decision"]["classification"] for c in switches))}}
