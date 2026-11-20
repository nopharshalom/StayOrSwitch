"""Input-only pre-incident route selection and unchanged-predictor scoring."""

from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

from .october_evaluation import _decision_scores, epoch, outcome_for
from .severe import MODES, decide


POLICY = {
    "schema_version": "preincident-fastest-v1",
    "study_status": "POST_HOC_EXPLORATORY_TEST_CASE_SEARCH",
    "test_dates": ["2026-10-25", "2026-10-31"],
    "origin": "Court Square subway complex street entrance, Long Island City",
    "destination": "Times Square, West 42nd Street at Seventh Avenue",
    "reference_policy": "LATEST_ELIGIBLE_PRE_PROBLEM_FASTEST_UNMODIFIED_MTA_ROUTE",
    "anchor_lookback_seconds": [60, 300, 600, 900, 1800],
    "decision_grid_seconds": 300,
    "decision_window_seconds": 7200,
    "minimum_duration_deterioration_seconds": 300,
    "switch_margin_seconds": 300,
    "require_severe": False,
    "tie_margin_seconds": 180,
    "baseline_near_tie_seconds": 180,
    "walking_sensitivity_seconds": [-120, 120],
    "walking_policy": "AUTHORED_STREET_ACCESS_AND_EGRESS_ASSUMPTIONS_NOT_MEASURED_OR_HISTORICAL_PROVIDER_ROUTES",
    "planning_state": "NOT_BOARDED_AT_EITHER_CUTOFF; NEW_DEPARTURE_FROM_SAME_ORIGIN_AT_DECISION_TIME",
    "routes": [
        {"id": "7_times_square", "family": "7_DIRECT", "name": "7 Court Sq to Times Sq",
         "access_walk_seconds": 120, "egress_walk_seconds": 120, "transfer_walk_seconds": [],
         "legs": [{"route_id": "7", "route_ids": ["7", "7X"], "feed_id": "numbered", "from_stop_id": "719S", "to_stop_id": "725S"}]},
        {"id": "e_times_square", "family": "E_DIRECT", "name": "E Court Sq to Port Authority, walk to Times Sq",
         "access_walk_seconds": 300, "egress_walk_seconds": 420, "transfer_walk_seconds": [],
         "legs": [{"route_id": "E", "route_ids": ["E"], "feed_id": "ace", "from_stop_id": "F09S", "to_stop_id": "A27S"}]},
        {"id": "f_times_square", "family": "F_DIRECT", "name": "F Court Sq to Bryant Park, walk to Times Sq",
         "access_walk_seconds": 300, "egress_walk_seconds": 420, "transfer_walk_seconds": [],
         "legs": [{"route_id": "F", "route_ids": ["F", "FX"], "feed_id": "bdfm", "from_stop_id": "F09S", "to_stop_id": "D16S"}]},
    ],
}

BROOKLYN_POLICY = dict(deepcopy(POLICY),
    schema_version="preincident-fastest-brooklyn-v1",
    origin="Grand Central street entrance at East 42nd Street and Lexington Avenue",
    destination="Brooklyn Borough Hall street corner at Court Street and Joralemon Street",
    route_family_policy="Treat interchangeable same-platform 4/5 and 2/3 services as route families; do not count 4-to-5 as a route Switch.",
    routes=[
        {"id": "lexington_direct", "family": "LEXINGTON_DIRECT", "name": "4 or 5 Grand Central to Borough Hall",
         "access_walk_seconds": 180, "egress_walk_seconds": 120, "transfer_walk_seconds": [],
         "legs": [{"route_id": "4", "route_ids": ["4", "5"], "feed_id": "numbered", "from_stop_id": "631S", "to_stop_id": "423S"}]},
        {"id": "broadway_via_7", "family": "BROADWAY_VIA_7", "name": "7 to 2 or 3 via Times Square",
         "access_walk_seconds": 300, "egress_walk_seconds": 180, "transfer_walk_seconds": [360],
         "legs": [{"route_id": "7", "route_ids": ["7", "7X"], "feed_id": "numbered", "from_stop_id": "723S", "to_stop_id": "725S"},
                  {"route_id": "2", "route_ids": ["2", "3"], "feed_id": "numbered", "from_stop_id": "127S", "to_stop_id": "232S"}]},
        {"id": "walk_broadway", "family": "BROADWAY_ON_FOOT", "name": "Walk to Times Square, then 2 or 3 to Borough Hall",
         "access_walk_seconds": 960, "egress_walk_seconds": 180, "transfer_walk_seconds": [],
         "legs": [{"route_id": "2", "route_ids": ["2", "3"], "feed_id": "numbered", "from_stop_id": "127S", "to_stop_id": "232S"}]},
        {"id": "walk_f", "family": "SIXTH_AVENUE_F", "name": "Walk to Bryant Park, F to Jay Street, walk to Borough Hall",
         "access_walk_seconds": 600, "egress_walk_seconds": 480, "transfer_walk_seconds": [],
         "legs": [{"route_id": "F", "route_ids": ["F", "FX"], "feed_id": "bdfm", "from_stop_id": "D16S", "to_stop_id": "A41S"}]}
    ])


def local_time(value):
    return datetime.fromtimestamp(epoch(value), ZoneInfo("America/New_York")).isoformat()


def plan_incidents(inventory, policy=POLICY):
    """Declare every test-week candidate using alert metadata only."""
    allowed = {line for route in policy["routes"] for leg in route["legs"] for line in leg["route_ids"]}
    result = []
    for family in inventory["incidents"]:
        if not set(family["route_ids"]) & allowed:
            continue
        problems = [v for v in family["versions"] if v["state"] in ("DISRUPTION", "SEVERE")]
        if not problems:
            continue
        first_problem = min(v["first_observed_at"] for v in problems)
        first_family = family["first_observed_at"]
        if not policy["test_dates"][0] <= local_time(first_family)[:10] <= policy["test_dates"][1]:
            continue
        initial = [v for v in family["versions"] if v["first_observed_at"] == first_family]
        starts = [epoch(period["start"]) for version in initial
                  for period in version["alert"].get("active_periods", [])
                  if period.get("start") is not None]
        boundary = min([first_family] + starts)
        anchors = [boundary - lag for lag in policy["anchor_lookback_seconds"]
                   if policy["test_dates"][0] <= local_time(boundary - lag)[:10] <= policy["test_dates"][1]]
        latest = first_problem + policy["decision_window_seconds"]
        decisions = {first_problem + lag for lag in range(0, policy["decision_window_seconds"] + 1,
                                                        policy["decision_grid_seconds"])}
        decisions.update(v["first_observed_at"] for v in family["versions"]
                         if first_problem <= v["first_observed_at"] <= latest)
        decisions = sorted(t for t in decisions if local_time(t)[:10] <= policy["test_dates"][1])
        result.append({"incident_id": family["incident_id"], "first_family_receipt": first_family,
                       "first_problem_receipt": first_problem, "anchor_boundary": boundary,
                       "anchor_times": anchors, "decision_times": decisions,
                       "initial_notices": initial, "route_ids": family["route_ids"]})
    return sorted(result, key=lambda row: (row["first_problem_receipt"], row["incident_id"]))


def choose_anchor(plan, predictions, policy=POLICY):
    """Choose the latest valid anchor without consulting later predictions."""
    attempts = []
    expected_ids = {r["id"] for r in policy["routes"]}
    for when in sorted(plan["anchor_times"], reverse=True):
        prediction = predictions.get(when)
        routes = [] if prediction is None else prediction["routes"]
        reason = None
        if when >= plan["anchor_boundary"]:
            reason = "ANCHOR_NOT_BEFORE_FIRST_PROBLEM_BOUNDARY"
        elif {r["id"] for r in routes} != expected_ids:
            reason = "INCOMPLETE_CANDIDATE_SET"
        elif not all(r.get("timing_eligible") and r.get("comparison_eligible") for r in routes):
            reason = "ANCHOR_CANDIDATE_TIMING_OR_SERVICE_UNVERIFIED"
        else:
            ordered = sorted(routes, key=lambda r: (r["total_duration_seconds"], r["id"]))
            winner = ordered[0]
            context = winner.get("context", {})
            if context.get("state") != "NORMAL" or context.get("evidence_status") != "FRESH":
                reason = "FASTEST_ROUTE_NOT_FRESH_NORMAL"
            else:
                lead = ordered[1]["total_duration_seconds"] - winner["total_duration_seconds"]
                return {"status": "ELIGIBLE", "decision_at": when, "local_time": local_time(when),
                        "reference_route_id": winner["id"], "winner_lead_seconds": lead,
                        "baseline_near_tie": lead <= policy["baseline_near_tie_seconds"],
                        "prediction": deepcopy(prediction), "attempts": attempts}
        attempts.append({"decision_at": when, "reason": reason})
    return {"status": "UNAVAILABLE", "attempts": attempts}


def select_delayed(plan, anchor, prediction, cutoff, policy=POLICY):
    """A route must become slower in remaining duration and carry this notice."""
    if anchor.get("status") != "ELIGIBLE":
        return None, "NO_VALID_PRE_PROBLEM_ANCHOR"
    if cutoff < plan["first_problem_receipt"] or cutoff > plan["first_problem_receipt"] + policy["decision_window_seconds"]:
        return None, "OUTSIDE_PREDECLARED_DECISION_WINDOW"
    original = next(r for r in anchor["prediction"]["routes"] if r["id"] == anchor["reference_route_id"])
    current = next((r for r in prediction["routes"] if r["id"] == original["id"]), None)
    if current is None or not current.get("timing_eligible"):
        return None, "FROZEN_STAY_HAS_NO_COMPLETE_TIMING"
    context = current.get("context", {})
    if context.get("state") not in ("DISRUPTION", "SEVERE") or plan["incident_id"] not in context.get("incident_ids", []):
        return None, "NO_APPLICABLE_CURRENT_PROBLEM_NOTICE"
    change = current["total_duration_seconds"] - original["total_duration_seconds"]
    if change < policy["minimum_duration_deterioration_seconds"]:
        return None, "REMAINING_DURATION_DID_NOT_INCREASE_FIVE_MINUTES"
    components = {key: current["components"].get(key, 0) - original["components"].get(key, 0)
                  for key in set(current["components"]) | set(original["components"])}
    row = {"id": plan["incident_id"].replace(":", "-") + "-" + str(int(cutoff)),
           "incident_ids": [plan["incident_id"]], "decision_at": cutoff, "local_time": local_time(cutoff),
           "split": "test", "reference_route_id": original["id"], "anchor": deepcopy(anchor),
           "planning_interval_seconds": cutoff - anchor["decision_at"],
           "problem_anchor_boundary": plan["anchor_boundary"],
           "first_problem_receipt": plan["first_problem_receipt"],
           "first_family_receipt": plan.get("first_family_receipt"),
           "duration_deterioration_seconds": change, "component_deterioration_seconds": components,
           "asof_mta_prediction": deepcopy(prediction), "selection_uses_outcomes": False,
           "official_text_review": {"status": "PENDING"}}
    return row, None


def score_modes(case, predictions, labels, policy=POLICY):
    """Score exact forecast-selected trains with the original outcome rules."""
    result = deepcopy(case)
    result["modes"] = {}
    baseline = predictions["mta"]
    available = [r for r in baseline["routes"] if r.get("timing_eligible")]
    current_best = min(available, key=lambda r: (r["total_duration_seconds"], r["id"])) if available else None
    reference_outcome = outcome_for(current_best, labels, case["decision_at"]) if current_best else None
    result["same_cutoff_fastest_mta_route_id"] = current_best["id"] if current_best else None
    for mode in MODES:
        prediction = predictions[mode]
        value = dict(prediction, **decide(prediction, case["reference_route_id"],
                                          switch_margin_seconds=policy["switch_margin_seconds"], require_severe=policy["require_severe"]))
        value["outcomes"] = {r["id"]: outcome_for(r, labels, case["decision_at"]) for r in prediction["routes"]}
        value["scores"] = {scope: _decision_scores(value, case["reference_route_id"], reference_outcome,
                                                  scope, policy["tie_margin_seconds"], policy["switch_margin_seconds"])
                           for scope in ("strict_decision", "conditional_timing_decision")}
        current = next(r for r in prediction["routes"] if r["id"] == case["reference_route_id"])
        alternatives = [r for r in prediction["routes"] if r["id"] != case["reference_route_id"] and r.get("timing_eligible")]
        alternative = min(alternatives, key=lambda r: (r["total_duration_seconds"], r["id"])) if alternatives else None
        current_outcome = value["outcomes"].get(case["reference_route_id"], {})
        alternative_outcome = value["outcomes"].get(alternative["id"], {}) if alternative else {}
        comparable = current_outcome.get("status") == alternative_outcome.get("status") == "INFERRED"
        known = [(identity, item) for identity, item in value["outcomes"].items()
                 if identity != case["reference_route_id"] and item.get("status") == "INFERRED"]
        known_best = min(known, key=lambda item: (item[1]["total_duration_seconds"], item[0])) if known else None
        value["alternative_counterfactual"] = {
            "selection_uses_outcomes": False,
            "predicted_alternative_route_id": alternative["id"] if alternative else None,
            "predicted_alternative_duration_seconds": alternative["total_duration_seconds"] if alternative else None,
            "predicted_savings_seconds": current["total_duration_seconds"] - alternative["total_duration_seconds"]
                if alternative and current.get("timing_eligible") else None,
            "alternative_outcome": alternative_outcome,
            "outcomes_comparable": comparable,
            "inferred_savings_seconds": current_outcome["total_duration_seconds"] - alternative_outcome["total_duration_seconds"]
                if comparable else None,
            "hindsight_best_known_alternative_route_id": known_best[0] if known_best else None,
            "hindsight_best_known_savings_seconds": current_outcome["total_duration_seconds"] - known_best[1]["total_duration_seconds"]
                if known_best and current_outcome.get("status") == "INFERRED" else None,
            "hindsight_values_are_not_recommendations": True,
        }
        result["modes"][mode] = value
    return result
