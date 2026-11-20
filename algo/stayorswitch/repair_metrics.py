"""Keep route execution outcomes distinct from selected-train diagnostics.

These helpers summarize a post-hoc repair benchmark. An eventually completed
route does not erase an infeasible train originally selected by its predictor.
Unknown route durations never become zero, practical ties or successful advice.
"""

from collections import Counter
import math

from .incremental_switch_replay import classify
from .october_evaluation import _label_endpoint, epoch
from .severe import MODES


CONCRETE_ACTIONS = frozenset(("STAY", "SWITCH"))
NO_SELECTED_JOURNEY = "NO_SELECTED_JOURNEY"
MISSED_SELECTED_TRAIN = "MISSED_SELECTED_TRAIN"


def _counter(value):
    return dict(sorted(value.items()))


def _status(outcome):
    return outcome.get("status", NO_SELECTED_JOURNEY)


def _duration(outcome):
    if _status(outcome) != "INFERRED":
        return None
    value = outcome.get("total_duration_seconds")
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError("An inferred route requires a finite nonnegative duration.")
    return value


def _selected(case, mode):
    value = case["modes"][mode]
    decision = value["strict_decision"]
    action = decision["action"]
    identity = decision.get("recommended_itinerary_id")
    if action not in CONCRETE_ACTIONS:
        return decision, {}, {}
    if not identity or identity not in value["outcomes"]:
        raise ValueError("A concrete action must have its selected route outcome.")
    fixed = case["fixed_train_diagnostics"][mode]
    if identity not in fixed:
        raise ValueError("A concrete action must retain its fixed-train diagnostic.")
    outcome = value["outcomes"][identity]
    _duration(outcome)
    return decision, outcome, fixed[identity]


def operational_summary(cases):
    """Count route coverage and exact-train failures on separate denominators.

    Unknown Switch rows are partitioned by the chosen route first. Only when
    that route completes does an incomplete Stay become the exclusive cause.
    Status-pair counts preserve cases with evidence gaps on both sides.
    """
    cases = list(cases)
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Operational cases contain duplicate identifiers.")
    by_mode = {}
    for mode in MODES:
        actions, fixed_statuses, switch_fixed_statuses = Counter(), Counter(), Counter()
        execution_statuses, switch_execution_statuses = Counter(), Counter()
        unknown_pairs, unknown_reasons = Counter(), Counter()
        recovered_misses = recovered_switch_misses = 0
        chosen_incomplete = stay_incomplete = 0
        for case in cases:
            decision, outcome, fixed = _selected(case, mode)
            action = decision["action"]
            actions[action] += 1
            execution_statuses[_status(outcome)] += 1
            fixed_statuses[_status(fixed)] += 1
            recovered = (_status(fixed) == MISSED_SELECTED_TRAIN
                         and _status(outcome) == "INFERRED")
            recovered_misses += recovered
            if action != "SWITCH":
                continue
            switch_fixed_statuses[_status(fixed)] += 1
            switch_execution_statuses[_status(outcome)] += 1
            recovered_switch_misses += recovered
            values = case["modes"][mode]["outcomes"]
            if case["reference_route_id"] not in values:
                raise ValueError("A Switch comparison must retain its Stay route outcome.")
            stay = values[case["reference_route_id"]]
            _duration(stay)
            chosen_status, stay_status = _status(outcome), _status(stay)
            if chosen_status == stay_status == "INFERRED":
                continue
            unknown_pairs[(chosen_status, stay_status)] += 1
            if chosen_status != "INFERRED":
                chosen_incomplete += 1
                unknown_reasons["chosen:" + chosen_status + ":"
                                + str(outcome.get("reason", "UNSPECIFIED"))] += 1
            else:
                stay_incomplete += 1
                unknown_reasons["stay:" + stay_status + ":"
                                + str(stay.get("reason", "UNSPECIFIED"))] += 1
        concrete = sum(actions[action] for action in CONCRETE_ACTIONS)
        switches = actions["SWITCH"]
        misses = fixed_statuses[MISSED_SELECTED_TRAIN]
        switch_misses = switch_fixed_statuses[MISSED_SELECTED_TRAIN]
        by_mode[mode] = {
            "actions": _counter(actions),
            "concrete_actions": concrete,
            "fixed_train_statuses": _counter(fixed_statuses),
            "known_missed_selected_journeys": misses,
            "known_misses_per_concrete_action": misses / concrete if concrete else None,
            "switch_fixed_train_statuses": _counter(switch_fixed_statuses),
            "known_missed_selected_switches": switch_misses,
            "known_misses_per_switch_action": switch_misses / switches if switches else None,
            "route_execution_statuses": _counter(execution_statuses),
            "switch_route_execution_statuses": _counter(switch_execution_statuses),
            "fixed_train_missed_but_route_complete": recovered_misses,
            "switch_fixed_train_missed_but_route_complete": recovered_switch_misses,
            "unknown_switches": {
                "count": sum(unknown_pairs.values()),
                "chosen_incomplete": chosen_incomplete,
                "stay_incomplete_when_chosen_complete": stay_incomplete,
                "status_pairs": [
                    {"chosen_status": chosen, "stay_status": stay, "count": count}
                    for (chosen, stay), count in sorted(unknown_pairs.items())
                ],
                "reason_counts": _counter(unknown_reasons),
            },
        }
    return {
        "case_count": len(cases),
        "known_misses_are_not_complete_failure_rates": True,
        "route_completion_does_not_erase_selected_train_failure": True,
        "by_mode": by_mode,
    }


def compare_versions(old_cases, new_cases, mode="incident_profile"):
    """Compare old/new choices using the same route execution evidence.

    Positive gain means the new recommendation completes sooner. Cases with
    only one concrete action remain outside the paired outcome denominator,
    but every action transition remains in the records and action-pair counts.
    """
    if mode not in MODES:
        raise ValueError("Unknown policy mode.")
    old_cases, new_cases = list(old_cases), list(new_cases)
    if len(old_cases) != len(new_cases):
        raise ValueError("Version comparisons require identical case membership.")
    if (len({case["id"] for case in old_cases}) != len(old_cases)
            or len({case["id"] for case in new_cases}) != len(new_cases)):
        raise ValueError("Version comparison contains duplicate identifiers.")
    records = []
    action_pairs, classes = Counter(), Counter()
    old_fixed_statuses, new_fixed_statuses = Counter(), Counter()
    eligible_count = comparable_count = same_route_count = 0
    fixed_status_pairs = Counter()
    for old, new in zip(old_cases, new_cases):
        for key in ("id", "corridor_id", "decision_at", "reference_route_id", "incident_ids"):
            if old[key] != new[key]:
                raise ValueError("Version comparison changes ordered case inputs: " + key)
        left, left_out, left_fixed = _selected(old, mode)
        right, right_out, right_fixed = _selected(new, mode)
        left_id, right_id = left.get("recommended_itinerary_id"), right.get("recommended_itinerary_id")
        old_outcomes, new_outcomes = old["modes"][mode]["outcomes"], new["modes"][mode]["outcomes"]
        # A shared cache must produce exactly the same event identities and
        # uncertainty flags, not merely equal elapsed minutes.
        for identity in set(old_outcomes).intersection(new_outcomes):
            if old_outcomes[identity] != new_outcomes[identity]:
                raise ValueError("The same route has different execution evidence: " + identity)
        eligible = left["action"] in CONCRETE_ACTIONS and right["action"] in CONCRETE_ACTIONS
        comparable = eligible and _status(left_out) == _status(right_out) == "INFERRED"
        same_route = eligible and left_id == right_id
        gain = _duration(left_out) - _duration(right_out) if comparable else None
        result = classify(gain)
        action_pairs[left["action"] + "->" + right["action"]] += 1
        old_fixed_statuses[_status(left_fixed)] += 1
        new_fixed_statuses[_status(right_fixed)] += 1
        eligible_count += eligible
        comparable_count += comparable
        same_route_count += same_route
        if eligible:
            classes[result] += 1
            fixed_status_pairs[(_status(left_fixed), _status(right_fixed))] += 1
        records.append({
            "case_id": old["id"], "corridor_id": old["corridor_id"],
            "decision_at": old["decision_at"],
            "old_action": left["action"], "new_action": right["action"],
            "old_route_id": left_id, "new_route_id": right_id,
            "old_outcome_status": _status(left_out), "new_outcome_status": _status(right_out),
            "old_fixed_train_status": _status(left_fixed), "new_fixed_train_status": _status(right_fixed),
            "old_duration_seconds": _duration(left_out), "new_duration_seconds": _duration(right_out),
            "eligible_actions": eligible, "comparable": comparable,
            "same_recommended_route": same_route,
            "gain_seconds": gain, "classification": result if eligible else "NOT_A_PAIRED_DECISION",
        })
    return {
        "mode": mode, "case_count": len(records),
        "eligible_actions": eligible_count, "comparable": comparable_count,
        "unknown_paired_outcomes": eligible_count - comparable_count,
        "classes": _counter(classes), "action_pairs": _counter(action_pairs),
        "same_recommended_route_pairs": same_route_count,
        "old_fixed_train_statuses": _counter(old_fixed_statuses),
        "new_fixed_train_statuses": _counter(new_fixed_statuses),
        "old_known_missed_selected_journeys": old_fixed_statuses[MISSED_SELECTED_TRAIN],
        "new_known_missed_selected_journeys": new_fixed_statuses[MISSED_SELECTED_TRAIN],
        "paired_fixed_train_statuses": [
            {"old_status": left, "new_status": right, "count": count}
            for (left, right), count in sorted(fixed_status_pairs.items())
        ],
        "records": records,
    }


def boarding_diagnostic(route, labels, cutoff):
    """Check selected boardings without requiring the final destination label.

    ``labels`` must already have the benchmark's identity and endpoint-quality
    screen applied. A usable departure is sufficient to establish a missed
    boarding. A prior arrival is needed only to establish readiness for the
    following transfer, so a missing destination arrival cannot hide an already
    departed first train. No forecast boarding margin is added to actual walks.
    """
    selected = route.get("selected_legs") or []
    result = {
        "status": "UNVERIFIABLE", "reason": "NO_COMPLETE_FORECAST_SELECTED_JOURNEY",
        "first_boarding_status": "UNVERIFIABLE", "total_boardings": len(selected),
        "checked_boarding_count": 0, "catchable_boarding_count": 0,
        "checked_boardings": [],
    }
    if not selected or not route.get("timing_eligible"):
        return result
    transfers = route.get("transfer_walk_seconds", [])
    if len(transfers) != len(selected) - 1:
        raise ValueError("Selected journey transfer walking is incomplete.")
    walks = [route.get("access_walk_seconds"), *transfers]
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) or value < 0 for value in walks):
        raise ValueError("Boarding walks must be finite and nonnegative.")
    start = epoch(cutoff)
    if start is None:
        raise ValueError("A boarding diagnostic requires a valid cutoff.")
    ready = start + walks[0]
    for position, chosen in enumerate(selected):
        identity = chosen["trip_id"]
        trip_labels = labels.get(identity, {})
        boarding = trip_labels.get(chosen["from_stop_id"])
        departure = _label_endpoint(boarding, "departure")
        location = {
            "leg_index": position, "trip_id": identity,
            "from_stop_id": chosen["from_stop_id"], "to_stop_id": chosen["to_stop_id"],
            "platform_ready_at": ready,
        }
        if departure is None or not math.isfinite(departure):
            result.update(location, reason="MISSING_OR_UNUSABLE_BOARDING_DEPARTURE")
            return result
        missed = departure < ready
        status = MISSED_SELECTED_TRAIN if missed else "CATCHABLE"
        result["checked_boardings"].append(dict(location, departure_at=departure, status=status))
        result["checked_boarding_count"] += 1
        result["catchable_boarding_count"] += not missed
        if position == 0:
            result["first_boarding_status"] = status
        if missed:
            result.update(location, status=MISSED_SELECTED_TRAIN,
                          reason="INFERRED_DEPARTURE_BEFORE_PLATFORM_READY",
                          departure_at=departure, missed_boarding_seconds=ready - departure)
            return result
        if position + 1 == len(selected):
            result.update(status="ALL_BOARDINGS_CATCHABLE",
                          reason="ALL_SELECTED_DEPARTURES_AT_OR_AFTER_PLATFORM_READY")
            return result
        alighting = trip_labels.get(chosen["to_stop_id"])
        arrival = _label_endpoint(alighting, "arrival")
        if arrival is None or not math.isfinite(arrival):
            result.update(location, reason="MISSING_OR_UNUSABLE_PREVIOUS_ARRIVAL",
                          departure_at=departure)
            return result
        if arrival < departure:
            result.update(location, reason="NONMONOTONIC_PREVIOUS_ENDPOINTS",
                          departure_at=departure, arrival_at=arrival)
            return result
        ready = arrival + transfers[position]
    raise AssertionError("Every selected-boarding path must return a diagnostic.")


def _boarding_counts(statuses, *, first):
    statuses = Counter(statuses)
    allowed = {"CATCHABLE" if first else "ALL_BOARDINGS_CATCHABLE",
               MISSED_SELECTED_TRAIN, "UNVERIFIABLE"}
    if set(statuses) - allowed:
        raise ValueError("Unexpected supplemental boarding status.")
    catchable = statuses["CATCHABLE" if first else "ALL_BOARDINGS_CATCHABLE"]
    missed = statuses[MISSED_SELECTED_TRAIN]
    concrete = sum(statuses.values())
    evaluable = catchable + missed
    return {
        "concrete_actions": concrete, "evaluable": evaluable, "denominator": evaluable,
        "catchable": catchable, "missed": missed, "unknown": statuses["UNVERIFIABLE"],
        "known_miss_fraction_all_concrete": missed / concrete if concrete else None,
        "miss_fraction_among_evaluable": missed / evaluable if evaluable else None,
    }


def supplementalboarding_summary(cases):
    """Summarize departure-first diagnostics separately from frozen metrics.

    Each table reports all concrete actions, evaluable catchable/missed cases,
    and unknowns. ``denominator`` means the evaluable subset, not all actions.
    """
    cases = list(cases)
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Supplemental boarding cases contain duplicate identifiers.")
    by_mode = {}
    for mode in MODES:
        all_rows, switch_rows = [], []
        reasons = Counter()
        for case in cases:
            decision = case["modes"][mode]["strict_decision"]
            if decision["action"] not in CONCRETE_ACTIONS:
                continue
            identity = decision.get("recommended_itinerary_id")
            diagnostics = case["boarding_diagnostics"][mode]
            if not identity or identity not in diagnostics:
                raise ValueError("A concrete action must retain its supplemental boarding diagnostic.")
            row = diagnostics[identity]
            all_rows.append(row)
            reasons[row.get("reason", "UNSPECIFIED")] += 1
            if decision["action"] == "SWITCH":
                switch_rows.append(row)
        by_mode[mode] = {
            "concrete_actions": len(all_rows), "switch_actions": len(switch_rows),
            "first_boarding": _boarding_counts([r["first_boarding_status"] for r in all_rows], first=True),
            "all_boardings": _boarding_counts([r["status"] for r in all_rows], first=False),
            "switch_first_boarding": _boarding_counts([r["first_boarding_status"] for r in switch_rows], first=True),
            "switch_all_boardings": _boarding_counts([r["status"] for r in switch_rows], first=False),
            "reason_counts": _counter(reasons),
        }
    return {
        "case_count": len(cases),
        "final_destination_arrival_not_required_for_boarding_diagnosis": True,
        "original_fixed_train_metric_unchanged": True,
        "by_mode": by_mode,
    }
