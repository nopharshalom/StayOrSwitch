"""Input-only service-problem cohorts with a current Google-defined Stay path."""

from collections import Counter
from bisect import bisect_right
from copy import deepcopy
import hashlib
import json

from data.delay_profiles.incidents import _active, _scope
from .preincident_replay import local_time
from .severe import validate_templates


POLICY = {
    "schema_version": "google-defined-corridor-replay-v1",
    "study_status": "POST_HOC_EXPLORATORY_TEST_REPLAY",
    "test_dates": ["2026-10-25", "2026-10-31"],
    "reference_policy": "CURRENT_GOOGLE_RECOMMENDED_PATH_WITH_HISTORICAL_ASOF_TRAINS",
    "current_google_duration_is_historical_outcome": False,
    "current_google_path_claimed_historically_fastest": False,
    "decision_lags_seconds": [0, 300, 600, 900, 1800, 3600, 7200],
    "decision_window_seconds": 7200,
    "include_problem_version_receipts_within_window": True,
    "problem_states": ["DISRUPTION", "SEVERE"],
    "planned_only_in_main_cohort": False,
    "cross_split_incident_families_in_main_cohort": False,
    "switch_margin_seconds": 300,
    "tie_margin_seconds": 180,
    "require_severe": False,
    "train_max_age_seconds": 180,
    "alerts_max_age_seconds": 300,
    "planning_state": "UNBOARDED_NEW_DEPARTURE_AT_EACH_HISTORICAL_CUTOFF",
    "representative_rule": "EARLIEST_TEXT_CONFIRMED_CHECKPOINT_WITH_USABLE_STAY_TIMING_PER_CORRIDOR_INCIDENT; OTHERWISE_EARLIEST_CONFIRMED_UNKNOWN",
    "selection_uses_outcomes_or_recommendations": False,
    "walking_policy": "FIXED_CURRENT_PROVIDER_OR_EXPLICIT_RESEARCH_WALKS_NOT_HISTORICALLY_OBSERVED",
    "walking_sensitivity_seconds": [-120, 120],
    "walking_sensitivity_selection": "PRIMARY_EVENT_STAY_AND_INCIDENT_PROFILE_FORECAST_BEST_ALTERNATIVE; ONE_COMPONENT_AT_A_TIME; SKIP_NEGATIVE_WALKS",
}


def validate_corridors(config):
    corridors = config["corridors"]
    if not corridors or len({c["id"] for c in corridors}) != len(corridors):
        raise ValueError("Corridor identities must be nonempty and unique.")
    for corridor in corridors:
        validate_templates(corridor["routes"])
        ids = {r["id"] for r in corridor["routes"]}
        if corridor["reference_route_id"] not in ids:
            raise ValueError("Google Stay must identify a supplied route.")
        if not corridor.get("google"):
            raise ValueError("Every corridor requires current Google provenance.")
    return corridors


def plan_incidents(inventory, corridor, policy=POLICY):
    """Select first-test-week incident families and fixed future checkpoints."""
    stay = next(r for r in corridor["routes"] if r["id"] == corridor["reference_route_id"])
    allowed = {line for leg in stay["legs"] for line in leg.get("route_ids", [leg["route_id"]])}
    plans, excluded = [], Counter()
    for family in inventory["incidents"]:
        if not allowed.intersection(family["route_ids"]):
            continue
        def relevant_version(version):
            selectors = version["alert"].get("informed_entities", [])
            lines = {str(s["route_id"]) for s in selectors if s.get("route_id") is not None}
            # Empty line selectors are not exclusion evidence; segment/direction review follows.
            return not lines or bool(lines.intersection(allowed))
        problems = [v for v in family["versions"] if v["state"] in policy["problem_states"]
                    and relevant_version(v)]
        if not problems:
            excluded["NO_UNPLANNED_CLASSIFIED_SERVICE_PROBLEM"] += 1
            continue
        first_family = family["first_observed_at"]
        if not policy["test_dates"][0] <= local_time(first_family)[:10] <= policy["test_dates"][1]:
            excluded["FAMILY_FIRST_OBSERVED_OUTSIDE_TEST_WEEK"] += 1
            continue
        first = min(v["first_observed_at"] for v in problems)
        cutoffs = {first + lag for lag in policy["decision_lags_seconds"]}
        cutoffs.update(v["first_observed_at"] for v in problems
                       if first <= v["first_observed_at"] <= first + policy["decision_window_seconds"])
        cutoffs = sorted(t for t in cutoffs
                         if policy["test_dates"][0] <= local_time(t)[:10] <= policy["test_dates"][1])
        if not cutoffs:
            excluded["PROBLEM_FIRST_OBSERVED_OUTSIDE_TEST_WEEK"] += 1
            continue
        plans.append({"corridor_id": corridor["id"], "incident_id": family["incident_id"],
                      "first_family_receipt": first_family, "first_problem_receipt": first,
                      "decision_times": cutoffs, "route_ids": family["route_ids"]})
    return sorted(plans, key=lambda p: (p["first_problem_receipt"], p["incident_id"])), dict(excluded)


def _scope_rows(route, template, cutoff, index):
    """Keep unavailable-path exposure explicit instead of dropping the encounter."""
    output = []
    selected = route.get("selected_legs", [])
    for position, leg in enumerate(template["legs"]):
        observed = next((x for x in selected if x.get("leg_index") == position), None)
        if observed is not None:
            output.append({"leg_index": position, "route_id": observed["route_id"],
                "from_stop_id": observed["from_stop_id"], "to_stop_id": observed["to_stop_id"],
                "platform_direction": observed.get("platform_direction"),
                "segment_stop_ids": observed.get("segment_stop_ids", []),
                "exposure_source": "ASOF_SELECTED_TRAIN_SEGMENT",
                "context": deepcopy(observed["incident_context"])})
        else:
            for line in leg.get("route_ids", [leg["route_id"]]):
                stops = [leg["from_stop_id"], leg["to_stop_id"]]
                output.append({"leg_index": position, "route_id": line,
                    "from_stop_id": stops[0], "to_stop_id": stops[1],
                    "platform_direction": stops[0][-1] if stops[0][-1] in "NS" else None,
                    "segment_stop_ids": stops, "exposure_source": "FIXED_GOOGLE_PATH_ENDPOINTS_ONLY",
                    "context": index.context_at(cutoff, line, stop_ids=stops)})
    return output


def asof_problem_notices(index, cutoff, line, stops, incident_id, policy=POLICY):
    """Expose active raw notices for review even when frozen direction logic errs.

    This changes cohort qualification only. It never alters predictor context,
    timing, severity, or decision eligibility.
    """
    position = bisect_right(index.times, cutoff) - 1
    if position < 0:
        return []
    entry = index.entries[position]
    if not entry["valid"]:
        return []
    output = []
    for key in entry["version_ids"]:
        version = index.versions[key]
        if version["incident_id"] != incident_id or version["state"] not in policy["problem_states"]:
            continue
        alert = version["alert"]
        active = _active(alert, cutoff)
        if active is False:
            continue
        selectors = alert.get("informed_entities", [])
        lines = {str(s["route_id"]) for s in selectors if s.get("route_id") is not None}
        if lines and line not in lines:
            continue
        model_relevant, model_scope = _scope(alert, line, stops, version)
        family = index.families[incident_id]
        output.append({"id": alert.get("id"), "incident_id": incident_id, "version_id": key,
            "state": version["state"], "cause": version["cause"],
            "classification_rule": version["classification_rule"],
            "header": alert.get("header"), "description": alert.get("description"),
            "informed_entities": deepcopy(selectors), "active_periods": deepcopy(alert.get("active_periods", [])),
            "captured_at": entry["captured_at"], "first_observed_at": family["first_observed_at"],
            "age_seconds": cutoff - family["first_observed_at"], "active_status": active,
            "model_scope_matches": model_relevant, "model_scope": model_scope,
            "frozen_classifier_and_scope_are_unchanged": True})
    return output


def select_encounter(plan, corridor, prediction, index, policy=POLICY):
    cutoff = prediction["cutoff"]
    if cutoff not in plan["decision_times"]:
        return None, "OUTSIDE_PREDECLARED_CHECKPOINTS"
    reference = corridor["reference_route_id"]
    current = next((r for r in prediction["routes"] if r["id"] == reference), None)
    template = next(r for r in corridor["routes"] if r["id"] == reference)
    if current is None:
        raise ValueError("The frozen Google Stay route is absent from predictions.")
    scope = _scope_rows(current, template, cutoff, index)
    exposed = []
    for leg in scope:
        context = leg["context"]
        notices = asof_problem_notices(index, cutoff, leg["route_id"], leg["segment_stop_ids"],
                                      plan["incident_id"], policy)
        if notices:
            projected = {k: deepcopy(v) for k, v in leg.items() if k != "context"}
            projected.update(notices=deepcopy(notices), evidence_status=context.get("evidence_status"),
                             applicable=context.get("applicable"), ambiguous_scope=context.get("ambiguous_scope", False))
            exposed.append(projected)
    if not exposed:
        return None, "NO_ASOF_RECORDED_PROBLEM_FOR_FIXED_STAY"
    key = json.dumps(exposed, sort_keys=True, separators=(",", ":"))
    # A review group strips receipt age; exact notices/case cutoffs are still retained.
    semantic = [{k: v for k, v in leg.items() if k not in ("evidence_status",)} for leg in exposed]
    for leg in semantic:
        leg["notices"] = [{k: v for k, v in a.items() if k not in ("captured_at", "age_seconds")}
                          for a in leg["notices"]]
    group = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]
    case_id = "{}--{}--{}".format(corridor["id"], plan["incident_id"].replace(":", "-"), int(cutoff * 1000))
    return {"id": case_id, "corridor_id": corridor["id"], "incident_ids": [plan["incident_id"]],
            "decision_at": cutoff, "local_time": local_time(cutoff), "split": "test",
            "reference_route_id": reference, "first_family_receipt": plan["first_family_receipt"],
            "first_problem_receipt": plan["first_problem_receipt"],
            "lag_seconds": cutoff - plan["first_problem_receipt"],
            "asof_mta_prediction": deepcopy(prediction), "exposure": exposed,
            "review_group_id": group, "exposure_sha256": hashlib.sha256(key.encode()).hexdigest(),
            "selection_uses_outcomes": False}, None


def review_groups(cases):
    groups = {}
    for case in cases:
        key = case["review_group_id"]
        if key not in groups:
            groups[key] = {"review_group_id": key, "case_ids": [], "corridor_ids": [],
                           "incident_ids": case["incident_ids"], "exposure": deepcopy(case["exposure"]),
                           "status": "PENDING", "confirmed_impact": None, "planning_status": None,
                           "reason": None}
        groups[key]["case_ids"].append(case["id"])
        if case["corridor_id"] not in groups[key]["corridor_ids"]:
            groups[key]["corridor_ids"].append(case["corridor_id"])
    return list(groups.values())


def apply_review(cases, review):
    expected = {c["id"]: c for c in cases}
    original_groups = {g["review_group_id"]: g for g in review_groups(cases)}
    group_ids = [g["review_group_id"] for g in review["groups"]]
    if len(group_ids) != len(set(group_ids)) or set(group_ids) != set(original_groups):
        raise ValueError("Review groups do not cover the prepared scope groups exactly once.")
    seen, confirmed, excluded = set(), [], []
    for row in review["groups"]:
        original = original_groups[row["review_group_id"]]
        for field in ("case_ids", "corridor_ids", "incident_ids", "exposure"):
            if row[field] != original[field]:
                raise ValueError("Review modified the prepared input evidence: " + field)
        if row["status"] not in ("CONFIRMED", "EXCLUDED", "UNRESOLVED"):
            raise ValueError("Every notice scope must be reviewed before outcome scoring.")
        if row["status"] == "CONFIRMED" and (row.get("confirmed_impact") not in POLICY["problem_states"]
                                             or row.get("planning_status") not in ("UNPLANNED", "NOT_IDENTIFIED_AS_PLANNED")):
            raise ValueError("Confirmed exposure requires impact and non-planned qualification.")
        if not row.get("reason"):
            raise ValueError("A text-review rationale is required.")
        for key in row["case_ids"]:
            if key in seen or key not in expected:
                raise ValueError("Review cases are duplicate or outside the prepared cohort.")
            seen.add(key)
            case = expected[key]
            if case["review_group_id"] != row["review_group_id"] or case["incident_ids"] != row["incident_ids"]:
                raise ValueError("Review identity differs from prepared exposure.")
            value = dict(deepcopy(case), official_text_review={k: deepcopy(v) for k, v in row.items()
                                                             if k not in ("case_ids", "exposure")})
            (confirmed if row["status"] == "CONFIRMED" else excluded).append(value)
    if seen != set(expected):
        raise ValueError("Every prepared encounter must be reviewed exactly once.")
    return confirmed, excluded


def representatives(cases):
    grouped = {}
    for case in sorted(cases, key=lambda c: (c["decision_at"], c["id"])):
        grouped.setdefault((case["corridor_id"], tuple(case["incident_ids"])), []).append(case)
    result = []
    for values in grouped.values():
        timed = [c for c in values if next(r for r in c["asof_mta_prediction"]["routes"]
                                         if r["id"] == c["reference_route_id"]).get("timing_eligible")]
        result.append((timed or values)[0])
    return sorted(result, key=lambda c: (c["decision_at"], c["corridor_id"], c["id"]))
