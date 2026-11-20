"""Select unchanged physical trains whose destination forecasts move later."""

from copy import deepcopy
import hashlib
import json

from data.october.labels import canonical_event_trip_id
from .preincident_replay import POLICY as COURT_POLICY, local_time


POLICY = dict(deepcopy(COURT_POLICY),
    schema_version="same-train-forecast-revision-v1",
    reference_policy="FRESH_NORMAL_FASTEST_AT_T0_SAME_PHYSICAL_STAY_TRAIN_AT_T1",
    decision_grid_seconds=300,
    reassessment_lags_seconds=[300, 600, 900, 1800],
    minimum_absolute_arrival_revision_seconds=300,
    remaining_duration_increase_required=False,
    official_delay_notice_required=False,
    anchor_candidate_gate="ALL_TIMING_AND_COMPARISON_ELIGIBLE; WINNER_FRESH_NORMAL",
    deduplication="EARLIEST_T1_THEN_EARLIEST_T0_PER_ORDERED_CANONICAL_TRAIN_AND_STOP_PAIR",
    no_independent_holdout_claim=True,
)
for _obsolete in ("anchor_lookback_seconds", "decision_window_seconds", "minimum_duration_deterioration_seconds"):
    POLICY.pop(_obsolete, None)


def physical_sequence(route):
    """Ignore normalized start-time aliases, but retain actual service and stops."""
    output = []
    for leg in route.get("selected_legs", []):
        physical = canonical_event_trip_id({"feed_id": leg.get("feed_id"),
            "start_date": leg.get("service_date"), "route_id": leg.get("route_id"),
            "trip_id": leg.get("raw_trip_id")})
        if physical is None or not leg.get("from_stop_id") or not leg.get("to_stop_id"):
            return None
        output.append((physical, leg["from_stop_id"], leg["to_stop_id"]))
    return tuple(output) if output else None


def choose_pair(before, after, policy=POLICY):
    """Use forecasts only; absolute endpoint revision is distinct from clock time."""
    t0, t1 = before["cutoff"], after["cutoff"]
    if t1 - t0 not in policy["reassessment_lags_seconds"]:
        return None, "OUTSIDE_FIXED_LAGS"
    expected = {r["id"] for r in policy["routes"]}
    routes = before["routes"]
    if len(routes) != len(expected) or {r["id"] for r in routes} != expected:
        return None, "INCOMPLETE_BASELINE_CANDIDATE_SET"
    if not all(r.get("timing_eligible") and r.get("comparison_eligible") for r in routes):
        return None, "BASELINE_CANDIDATE_TIMING_OR_SERVICE_UNVERIFIED"
    ordered = sorted(routes, key=lambda r: (r["total_duration_seconds"], r["id"]))
    original = ordered[0]
    context = original.get("context", {})
    if context.get("state") != "NORMAL" or context.get("evidence_status") != "FRESH":
        return None, "BASELINE_WINNER_NOT_FRESH_NORMAL"
    current = next((r for r in after["routes"] if r["id"] == original["id"]), None)
    if current is None or not current.get("timing_eligible"):
        return None, "STAY_NO_COMPLETE_CATCHABLE_TIMING_AT_T1"
    identity = physical_sequence(original)
    if identity is None:
        return None, "UNRESOLVED_PHYSICAL_IDENTITY"
    if identity != physical_sequence(current):
        return None, "STAY_SELECTED_PHYSICAL_TRAIN_CHANGED"
    for leg in current["selected_legs"]:
        if leg["departure_at"] < leg["platform_ready_at"]:
            return None, "SAME_TRAIN_NOT_CATCHABLE_AT_T1"
    changes = [{"from_stop_id": a["from_stop_id"], "to_stop_id": a["to_stop_id"],
                "baseline_normalized_trip_id": a["trip_id"], "current_normalized_trip_id": b["trip_id"],
                "departure_shift_seconds": b["departure_at"] - a["departure_at"],
                "arrival_shift_seconds": b["arrival_at"] - a["arrival_at"],
                "baseline_departure_at": a["departure_at"], "current_departure_at": b["departure_at"],
                "baseline_arrival_at": a["arrival_at"], "current_arrival_at": b["arrival_at"]}
               for a, b in zip(original["selected_legs"], current["selected_legs"])]
    revision = changes[-1]["arrival_shift_seconds"]
    if revision < policy["minimum_absolute_arrival_revision_seconds"]:
        return None, "ABSOLUTE_ARRIVAL_REVISION_BELOW_FIVE_MINUTES"
    lead = ordered[1]["total_duration_seconds"] - original["total_duration_seconds"]
    encoded = json.dumps(identity, separators=(",", ":"))
    key = hashlib.sha256(encoded.encode()).hexdigest()[:20]
    return {"id": "same-run-{}-{}-{}".format(key, int(t0), int(t1)),
            "physical_sequence": [list(row) for row in identity], "physical_sequence_key": key,
            "incident_ids": list(current.get("context", {}).get("incident_ids", [])),
            "decision_at": t1, "local_time": local_time(t1), "split": "test",
            "reference_route_id": original["id"], "planning_interval_seconds": t1 - t0,
            "anchor": {"status": "ELIGIBLE", "decision_at": t0, "local_time": local_time(t0),
                "reference_route_id": original["id"], "winner_lead_seconds": lead,
                "baseline_near_tie": lead <= policy["baseline_near_tie_seconds"],
                "prediction": deepcopy(before)},
            "absolute_arrival_revision_seconds": revision, "leg_forecast_revisions": changes,
            "duration_deterioration_seconds": current["total_duration_seconds"] - original["total_duration_seconds"],
            "asof_mta_prediction": deepcopy(after), "selection_uses_outcomes": False}, None


def representatives(cases):
    """Retain one predetermined earliest observed pair per physical train run."""
    chosen = {}
    for row in sorted(cases, key=lambda c: (c["decision_at"], c["anchor"]["decision_at"], c["id"])):
        chosen.setdefault(row["physical_sequence_key"], row)
    return list(chosen.values())
