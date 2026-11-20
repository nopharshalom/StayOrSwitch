"""Label-separated October incident replay and exact selected-train scoring.

Case selection reads only archived alert observations. Predictions never receive
outcomes. Later journal endpoints score exactly the forecast-selected train
sequence, including every boarding and transfer, without hindsight replacement.
"""

from collections import Counter, defaultdict
from bisect import bisect_right
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from zoneinfo import ZoneInfo


MODES = ("mta", "time_profile", "incident_profile")


def epoch(value):
    if isinstance(value, bool):
        raise ValueError("Boolean timestamps are invalid.")
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("A timestamp needs an explicit timezone.")
        result = parsed.timestamp()
    if not math.isfinite(result):
        raise ValueError("Timestamp must be finite.")
    return result


def iso(value):
    return datetime.fromtimestamp(epoch(value), timezone.utc).isoformat().replace("+00:00", "Z")


def captured_at(snapshot):
    value = snapshot.get("captured_at")
    return epoch(snapshot.get("fetched_at") if value is None else value)


def local_context(cutoff, config):
    local = datetime.fromtimestamp(epoch(cutoff), ZoneInfo(config["timezone"]))
    day_type = "SATURDAY" if local.weekday() == 5 else "SUNDAY" if local.weekday() == 6 else "WEEKDAY"
    period = next(item["id"] for item in config["periods"]
                  if item["start_hour"] <= local.hour < item["end_hour"])
    day = local.date().isoformat()
    split = next((key for key, bounds in config["splits"].items() if bounds[0] <= day <= bounds[1]), None)
    return {"local_time": local.isoformat(), "date": day, "day_type": day_type,
            "period": period, "split": split}


def select_incident_checkpoints(index, config):
    """Prespecify severe-event checkpoints using alert history only.

    Include first applicable severe visibility, fixed five-minute checkpoints,
    severity changes, and observed recovery/removal. A failed latest capture
    does not end an event. Shared cutoffs combine incident IDs. Families observed
    across chronological splits are explicitly purged from evaluation selection.
    """
    zone = ZoneInfo(config["timezone"])
    start = datetime.fromisoformat(config["start_date"]).replace(tzinfo=zone).timestamp()
    last = datetime.fromisoformat(config["end_date"]).replace(tzinfo=zone)
    from datetime import timedelta
    end = (last + timedelta(days=1)).timestamp()
    interval = config["incident_checkpoint_seconds"]
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval <= 0:
        raise ValueError("Incident checkpoint interval must be positive.")
    inventory = index.inventory()["incidents"]
    route_ids = set(config["route_ids"])
    families, purged = {}, []
    for item in inventory:
        if "SEVERE" not in item["states"] or (item["route_ids"] and not route_ids.intersection(item["route_ids"])):
            continue
        first_split = local_context(item["first_observed_at"], config)["split"]
        last_split = local_context(item["last_observed_at"], config)["split"]
        if first_split != last_split:
            purged.append(item["incident_id"])
            continue
        families[item["incident_id"]] = item
    lines = sorted({line for route in config["routes"] for leg in route["legs"]
                    for line in leg.get("route_ids", [leg["route_id"]])})
    boundaries = set()
    previous_signature = None
    for entry in index.entries:
        signature = (entry["valid"], tuple(entry["version_ids"]))
        if signature != previous_signature and start <= entry["captured_at"] < end:
            boundaries.add(entry["captured_at"])
        previous_signature = signature
    for version in index.versions.values():
        for period in version["alert"].get("active_periods") or []:
            for key in ("start", "end"):
                value = period.get(key)
                if value is not None:
                    try:
                        at = epoch(value)
                    except (ValueError, TypeError):
                        continue
                    if start <= at < end:
                        boundaries.add(at)
    active, selected = {}, {}

    def add(at, identity, reason):
        if not start <= at < end:
            return
        entry = selected.setdefault(at, {"decision_at": at, "incident_ids": set(), "checkpoint_reasons": defaultdict(set)})
        entry["incident_ids"].add(identity)
        entry["checkpoint_reasons"][identity].add(reason)

    def scheduled(until, inclusive=False):
        for identity, item in active.items():
            while item["next"] < until or inclusive and item["next"] == until:
                add(item["next"], identity, "FIXED_INTERVAL")
                item["next"] += interval

    for at in sorted(boundaries):
        scheduled(at)
        pointer = bisect_right(index.times, at) - 1
        valid_capture = pointer >= 0 and index.entries[pointer]["valid"]
        current = {}
        for line in lines:
            # Broad input-only selection retains intermediate-stop and uncertain
            # notices; actual selected-train paths gate strict recommendations.
            context = index.context_at(at, line)
            for detail in context["alerts"] + context["possible_alerts"]:
                identity = detail["incident_id"]
                if identity not in families:
                    continue
                previous = current.get(identity)
                rank = {"NORMAL": 0, "UNKNOWN": 1, "PLANNED": 2, "DISRUPTION": 3, "SEVERE": 4}
                if previous is None or rank[detail["state"]] > rank[previous]:
                    current[identity] = detail["state"]
        for identity in list(active):
            state = current.get(identity)
            if valid_capture and (state is None or state == "NORMAL"):
                add(at, identity, "OBSERVED_RECOVERY_OR_NOTICE_END")
                del active[identity]
            elif state is not None and state != active[identity]["state"]:
                add(at, identity, "OBSERVED_SEVERITY_CHANGE")
                active[identity]["state"] = state
        for identity, state in current.items():
            if state == "SEVERE" and identity not in active:
                add(at, identity, "FIRST_SEVERE_VISIBILITY")
                active[identity] = {"next": at + interval, "state": state}
        scheduled(at, inclusive=True)
    scheduled(end)
    effective_splits = defaultdict(set)
    for at, item in selected.items():
        for identity in item["incident_ids"]:
            effective_splits[identity].add(local_context(at, config)["split"])
    purged = sorted(set(purged) | {identity for identity, splits in effective_splits.items() if len(splits) > 1})
    purged_set = set(purged)
    cases = []
    for at, item in sorted(selected.items()):
        item["incident_ids"] -= purged_set
        if not item["incident_ids"]:
            continue
        item["id"] = "october-" + datetime.fromtimestamp(at, timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + hashlib.sha256(str(at).encode()).hexdigest()[:8]
        item["incident_ids"] = sorted(item["incident_ids"])
        item["checkpoint_reasons"] = {key: sorted(value) for key, value in sorted(item["checkpoint_reasons"].items()) if key not in purged_set}
        item.update(local_context(at, config))
        cases.append(item)
    return {"schema_version": "october-case-selection-v1", "cases": cases,
            "incident_candidates": len(families), "purged_cross_split_incident_ids": sorted(purged),
            "right_censored_active_incidents": sorted(active), "selection_uses_outcomes": False,
            "selection_uses_model_predictions": False,
            "policy": "FIRST_ROUTE_RELEVANT_SEVERE_VISIBILITY_FIXED_INTERVAL_AND_OBSERVED_TRANSITIONS",
            "scope_policy": "ROUTE_ALIASES_AND_POSSIBLE_STOP_SCOPE_RETAINED; ADVICE_REQUIRES_ACTUAL_PATH_APPLICABILITY",
            "checkpoint_interval_seconds": interval}


def latest_at_cutoffs(records, cutoffs, initial=None):
    """Stream feed-grouped records; choose the latest observation at each cutoff.

    Records must be chronological within each feed, not globally. A newer
    missing capture remains missing, and equal-capture conflicts are unusable.
    The returned carry contains last observations for the following day.
    """
    times = sorted(set(epoch(value) for value in cutoffs))
    result = {value: {} for value in times}
    latest = dict(initial or {})
    pointers = defaultdict(int)
    seen_times = {}
    for snapshot in records:
        feed = snapshot["feed_id"]
        capture = captured_at(snapshot)
        if capture < seen_times.get(feed, capture):
            raise ValueError("Replay snapshots are not chronological within a feed.")
        seen_times[feed] = capture
        pointer = pointers[feed]
        while pointer < len(times) and times[pointer] < capture:
            previous = latest.get(feed)
            if previous is not None and captured_at(previous) <= times[pointer]:
                result[times[pointer]][feed] = previous
            pointer += 1
        pointers[feed] = pointer
        previous = latest.get(feed)
        if previous is not None and captured_at(previous) == capture:
            before = previous.get("sha256") or json.dumps(previous, sort_keys=True)
            after = snapshot.get("sha256") or json.dumps(snapshot, sort_keys=True)
            if before != after or "CONFLICTING_EQUAL_CAPTURE_OBSERVATIONS" in previous.get("reason_codes", []):
                snapshot = dict(snapshot, status="MISSING", trips=[], alerts=[],
                                reason_codes=["CONFLICTING_EQUAL_CAPTURE_OBSERVATIONS"])
        latest[feed] = snapshot
    for feed, snapshot in latest.items():
        for cutoff in times[pointers[feed]:]:
            if captured_at(snapshot) <= cutoff:
                result[cutoff][feed] = snapshot
    return {cutoff: [items[key] for key in sorted(items)] for cutoff, items in result.items()}, latest


def _label_endpoint(label, endpoint):
    if not label or label.get(endpoint + "_usable") is not True:
        return None
    if label.get("quality_flags") or label.get(endpoint + "_quality_flags"):
        return None
    try:
        return epoch(label[endpoint + "_at"])
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


def outcome_for(route, labels, cutoff):
    """Follow every chosen train; a missed connection is unknown, not repaired."""
    selected = route.get("selected_legs") or []
    if not selected or not route.get("timing_eligible"):
        return {"status": "UNAVAILABLE", "reason": "NO_COMPLETE_FORECAST_SELECTED_JOURNEY"}
    transfers = route.get("transfer_walk_seconds", [])
    if len(transfers) != len(selected) - 1:
        raise ValueError("Selected journey transfer walking is incomplete.")
    walks = [route["access_walk_seconds"], *transfers, route["egress_walk_seconds"]]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
           not math.isfinite(value) or value < 0 for value in walks):
        raise ValueError("Walking durations must be finite and nonnegative.")
    ready = epoch(cutoff) + route["access_walk_seconds"]
    waiting = riding = 0.0
    legs = []
    for position, chosen in enumerate(selected):
        identity = chosen["trip_id"]
        trip_labels = labels.get(identity, {})
        boarding = trip_labels.get(chosen["from_stop_id"])
        alighting = trip_labels.get(chosen["to_stop_id"])
        departure = _label_endpoint(boarding, "departure")
        arrival = _label_endpoint(alighting, "arrival")
        base = {"leg_index": position, "trip_id": identity,
                "from_stop_id": chosen["from_stop_id"], "to_stop_id": chosen["to_stop_id"]}
        if departure is None or arrival is None:
            flags = {}
            for name, label, endpoint in (("boarding", boarding, "departure"),
                                          ("alighting", alighting, "arrival")):
                flags[name] = sorted(set((label or {}).get("quality_flags", []) +
                                         (label or {}).get(endpoint + "_quality_flags", [])))
                if label is None:
                    flags[name].append("MISSING_LABEL_RECORD")
            return dict(base, status="UNAVAILABLE", reason="MISSING_OR_UNUSABLE_ENDPOINT_LABEL",
                        endpoint_flags=flags, completed_legs=legs)
        if arrival < departure:
            return dict(base, status="UNAVAILABLE", reason="NONMONOTONIC_ENDPOINT_LABEL",
                        completed_legs=legs)
        if departure < ready:
            return dict(base, status="MISSED_SELECTED_TRAIN",
                        reason="INFERRED_DEPARTURE_BEFORE_PLATFORM_READY",
                        departure_at=departure, platform_ready_at=ready, completed_legs=legs)
        waiting += departure - ready
        riding += arrival - departure
        legs.append(dict(base, departure_at=departure, arrival_at=arrival, platform_ready_at=ready))
        ready = arrival + (transfers[position] if position < len(transfers) else route["egress_walk_seconds"])
    return {"status": "INFERRED", "destination_arrival_at": ready,
            "total_duration_seconds": ready - epoch(cutoff), "selected_legs": legs,
            "components": {"walking_seconds": sum(walks), "waiting_seconds": waiting,
                           "riding_seconds": riding},
            "evidence": "SCREENED_FINAL_PREDICTION_ENDPOINTS_PLUS_AUTHORED_WALKS"}


def _decision_scores(value, reference_id, reference_outcome, decision_key, tie_margin, missed_margin):
    decision = value[decision_key]
    action = decision.get("action")
    recommended_id = decision.get("recommended_itinerary_id")
    outcomes = value["outcomes"]
    current = outcomes.get(reference_id)
    chosen = outcomes.get(recommended_id)
    valid = {key: item for key, item in outcomes.items() if item["status"] == "INFERRED"}
    predicted_ids = {route["id"] for route in value["routes"] if route.get("timing_eligible")}
    complete = bool(predicted_ids) and predicted_ids.issubset(valid)
    comparable = current and chosen and current["status"] == chosen["status"] == "INFERRED"
    gain = current["total_duration_seconds"] - chosen["total_duration_seconds"] if comparable else None
    strategy_gain = None
    if (reference_outcome and chosen and reference_outcome["status"] == chosen["status"] == "INFERRED"):
        strategy_gain = reference_outcome["total_duration_seconds"] - chosen["total_duration_seconds"]
    known_regret = None
    if chosen and chosen["status"] == "INFERRED" and valid:
        known_regret = chosen["total_duration_seconds"] - min(item["total_duration_seconds"] for item in valid.values())
    missed_gain = None
    alternatives = [item for key, item in valid.items() if key != reference_id]
    if current and current["status"] == "INFERRED" and alternatives:
        missed_gain = current["total_duration_seconds"] - min(item["total_duration_seconds"] for item in alternatives)
    classification = "NOT_A_DECISION" if action not in ("STAY", "SWITCH") else "UNKNOWN"
    if action == "SWITCH" and gain is not None:
        classification = "MEANINGFUL_GAIN" if gain > tie_margin else "MEANINGFUL_LOSS" if gain < -tie_margin else "PRACTICAL_TIE"
    if action == "STAY":
        if missed_gain is not None and missed_gain > tie_margin:
            classification = "MEANINGFUL_MISSED_ALTERNATIVE"
        elif complete and len(predicted_ids) >= 2 and current and current["status"] == "INFERRED":
            classification = "ACCEPTABLE_STAY"
    return {"classification": classification, "inferred_switch_savings_seconds": gain,
            "inferred_strategy_gain_vs_original_mta_seconds": strategy_gain,
            "known_candidate_regret_seconds": known_regret,
            "complete_candidate_regret_seconds": known_regret if complete else None,
            "all_forecast_selected_candidate_outcomes_available": complete,
            "comparable_forecast_selected_routes": len(valid),
            "known_alternative_advantage_seconds": missed_gain,
            "missed_more_than_switch_margin": action == "STAY" and missed_gain is not None and missed_gain > missed_margin}


def evaluate_case(case, templates, labels, config, *, estimator=None, incident_index=None,
                  predict=None, decide=None):
    """Freeze the unmodified MTA reference before all correction-mode scoring."""
    if predict is None or decide is None:
        from .severe import predict_routes, decide as decide_routes
        predict = predict or predict_routes
        decide = decide or decide_routes
    cutoff = epoch(case["decision_at"])
    arguments = {"estimator": estimator, "incident_index": incident_index,
                 "train_max_age_seconds": config["train_max_age_seconds"],
                 "alerts_max_age_seconds": config["alerts_max_age_seconds"]}
    baseline = predict(case["snapshots"], templates, cutoff, mode="mta", **arguments)
    candidates = [route for route in baseline["routes"] if route.get("timing_eligible")]
    reference = min(candidates, key=lambda route: (route["total_duration_seconds"], route["id"])) if candidates else None
    reference_id = reference["id"] if reference else None
    reference_outcome = outcome_for(reference, labels, cutoff) if reference else None
    result = {key: deepcopy(value) for key, value in case.items() if key != "snapshots"}
    result.update(decision_at=cutoff, **local_context(cutoff, config), reference_route_id=reference_id,
                  reference=reference, reference_outcome=reference_outcome,
                  reference_service_context=reference_service_context(reference),
                  reference_policy="SAME_CUTOFF_FASTEST_UNMODIFIED_MTA", modes={})
    for mode in MODES:
        prediction = baseline if mode == "mta" else predict(case["snapshots"], templates, cutoff,
                                                             mode=mode, **arguments)
        decisions = decide(prediction, reference_id, switch_margin_seconds=config["switch_margin_seconds"],
                           require_severe=True)
        value = dict(prediction, **decisions)
        value["outcomes"] = {route["id"]: outcome_for(route, labels, cutoff) for route in prediction["routes"]}
        value["scores"] = {scope: _decision_scores(value, reference_id, reference_outcome, scope,
                              config["tie_margin_seconds"], config["switch_margin_seconds"])
                           for scope in ("strict_decision", "conditional_timing_decision")}
        result["modes"][mode] = value
    return result


def reference_service_context(route):
    """Describe the chosen MTA reference's as-of exposure without using outcomes."""
    if not route or not route.get("timing_eligible"):
        return {"category": "REFERENCE_UNAVAILABLE", "evidence_status": "UNKNOWN",
                "comparison_eligible": False, "severe_incident_ids": []}
    context = route.get("context") or {}
    definite = set()
    for leg in route.get("selected_legs", []):
        item = leg.get("incident_context") or {}
        # IncidentIndex puts only definitely matched notices in severe IDs.
        # An additional ambiguous notice does not erase an established match;
        # freshness and comparison eligibility remain separate denominators.
        if item.get("state") == "SEVERE" and item.get("applicable") is True:
            definite.update(item.get("severe_incident_ids", []))
    evidence = context.get("evidence_status", "UNKNOWN")
    unambiguous = not any(context.get(key, False) for key in ("ambiguous_scope", "scope_ambiguous", "scope_uncertain"))
    if definite:
        category = "DEFINITE_APPLICABLE_SEVERE"
    elif evidence == "FRESH" and unambiguous and context.get("state") == "NORMAL":
        category = "UNAFFECTED_FRESH_NORMAL"
    elif evidence == "FRESH" and unambiguous and context.get("state") in ("PLANNED", "DISRUPTION"):
        category = "OTHER_KNOWN_NON_SEVERE"
    else:
        category = "UNKNOWN_OR_AMBIGUOUS"
    return {"category": category, "evidence_status": evidence,
            "comparison_eligible": bool(route.get("comparison_eligible")),
            "severe_incident_ids": sorted(definite)}


def decision_margin_case(case, config, margin, *, decide=None):
    """Rescore a validation margin without changing forecasts or selected trains."""
    if decide is None:
        from .severe import decide
    result = dict(case, modes={})
    for mode, value in case["modes"].items():
        decisions = decide(value, case["reference_route_id"], switch_margin_seconds=margin, require_severe=True)
        changed = dict(value, **decisions)
        changed["scores"] = {scope: _decision_scores(changed, case["reference_route_id"], case["reference_outcome"],
                                scope, config["tie_margin_seconds"], config["switch_margin_seconds"])
                             for scope in ("strict_decision", "conditional_timing_decision")}
        result["modes"][mode] = changed
    result["predicted_switch_margin_seconds"] = margin
    return result


def summarize(cases, *, grouped=True):
    """Preserve recommendation, outcome, event, and candidate denominators."""
    output = {"case_count": len(cases), "incident_count": len({identity for case in cases for identity in case.get("incident_ids", [])}),
              "reference_route_counts": dict(Counter(case["reference_route_id"] or "UNAVAILABLE" for case in cases)),
              "modes": {}, "route_families": {}}
    reference_contexts = [case.get("reference_service_context") or reference_service_context(case.get("reference")) for case in cases]
    output["reference_service_context"] = {
        "checkpoints_by_category": dict(Counter(item["category"] for item in reference_contexts)),
        "checkpoints_by_evidence_status": dict(Counter(item["evidence_status"] for item in reference_contexts)),
        "definite_severe_checkpoints_by_evidence_status": dict(Counter(item["evidence_status"] for item in reference_contexts
                                                                       if item["category"] == "DEFINITE_APPLICABLE_SEVERE")),
        "definite_severe_comparison_eligible_checkpoints": sum(item["category"] == "DEFINITE_APPLICABLE_SEVERE" and item["comparison_eligible"]
                                                               for item in reference_contexts),
        "distinct_definite_severe_incidents": len({identity for item in reference_contexts for identity in item["severe_incident_ids"]}),
        "policy": "ASOF_FASTEST_MTA_REFERENCE_EXPOSURE; LAST_OBSERVED_SEVERE_IS_NOT_FRESH_ADVICE_EVIDENCE"}
    for mode in MODES:
        values = [case["modes"][mode] for case in cases]
        mode_result = {}
        for scope in ("strict_decision", "conditional_timing_decision"):
            actions = Counter(value[scope]["action"] for value in values)
            classes = Counter(value["scores"][scope]["classification"] for value in values)
            switches = [value for value in values if value[scope]["action"] == "SWITCH"]
            valid_switches = [value for value in switches if value["scores"][scope]["inferred_switch_savings_seconds"] is not None]
            gains = sum(value["scores"][scope]["classification"] == "MEANINGFUL_GAIN" for value in valid_switches)
            incident_switches = defaultdict(list)
            for case in cases:
                value = case["modes"][mode]
                if value[scope]["action"] == "SWITCH" and value["scores"][scope]["inferred_switch_savings_seconds"] is not None:
                    for identity in case.get("incident_ids", []):
                        incident_switches[identity].append(value["scores"][scope]["classification"] == "MEANINGFUL_GAIN")
            incident_rates = [sum(items) / len(items) for items in incident_switches.values()]
            strategy_gains = [value["scores"][scope]["inferred_strategy_gain_vs_original_mta_seconds"] for value in values
                              if value[scope]["action"] in ("STAY", "SWITCH") and
                              value["scores"][scope]["inferred_strategy_gain_vs_original_mta_seconds"] is not None]
            switch_gains = [value["scores"][scope]["inferred_switch_savings_seconds"] for value in valid_switches]
            mode_result[scope] = {"actions": dict(actions), "outcome_classes": dict(classes),
                "switches": len(switches), "switches_with_comparable_outcomes": len(valid_switches),
                "switches_without_comparable_outcomes": len(switches) - len(valid_switches),
                "meaningful_switch_gain_rate": gains / len(valid_switches) if valid_switches else None,
                "incident_weighted_meaningful_switch_gain_rate": sum(incident_rates) / len(incident_rates) if incident_rates else None,
                "incidents_with_comparable_switch_outcomes": len(incident_rates),
                "mean_comparable_switch_savings_seconds": sum(switch_gains) / len(switch_gains) if switch_gains else None,
                "strategy_comparable_outcomes_vs_original_mta": len(strategy_gains),
                "mean_strategy_gain_vs_original_mta_seconds": sum(strategy_gains) / len(strategy_gains) if strategy_gains else None,
                "reason_counts": dict(Counter(reason for value in values for reason in value[scope].get("reason_codes", []))),
                "missed_more_than_switch_margin": sum(value["scores"][scope]["missed_more_than_switch_margin"] for value in values)}
        mode_result["route_outcome_statuses"] = dict(Counter(outcome["status"] for value in values for outcome in value["outcomes"].values()))
        mode_result["route_outcome_reasons"] = dict(Counter(outcome.get("reason", "INFERRED") for value in values for outcome in value["outcomes"].values()))
        output["modes"][mode] = mode_result
    for case in cases:
        for route in case["modes"]["mta"]["routes"]:
            family = route.get("family", route["id"])
            counters = output["route_families"].setdefault(family, Counter())
            counters["candidate_variant_observations"] += 1
            counters["timing_estimated" if route.get("timing_eligible") else "timing_unavailable"] += 1
            counters["outcome_" + case["modes"]["mta"]["outcomes"][route["id"]]["status"]] += 1
    output["route_families"] = {key: dict(value) for key, value in sorted(output["route_families"].items())}
    if grouped:
        for field in ("split", "day_type", "period"):
            output["by_" + field] = {value: summarize([case for case in cases if case[field] == value], grouped=False)
                                     for value in sorted({case[field] for case in cases})}
        output["by_incident"] = {identity: summarize([case for case in cases if identity in case.get("incident_ids", [])], grouped=False)
                                  for identity in sorted({identity for case in cases for identity in case.get("incident_ids", [])})}
    return output


def selection_digest(selection):
    return hashlib.sha256(json.dumps(selection, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sensitivity_selection(cases, config):
    """Choose first checkpoints by time, before any outcomes or predictions."""
    first = {}
    for case in sorted(cases, key=lambda item: (item["decision_at"], item["id"])):
        for identity in case.get("incident_ids", []):
            first.setdefault((case["split"], identity), case)
    selections = []
    for split in ("validation", "test"):
        candidates = sorted(((identity, case) for (part, identity), case in first.items() if part == split),
                            key=lambda item: (item[1]["decision_at"], item[0]))
        for identity, case in candidates[:config["sensitivity_incident_limit_per_split"]]:
            selections.append({"split": split, "incident_id": identity, "case_id": case["id"],
                               "decision_at": case["decision_at"]})
    return selections


def walking_variations(templates, config):
    """Vary one candidate's one walk component, recomputing the full comparison."""
    for position, route in enumerate(templates):
        fields = [("access_walk_seconds", None), ("egress_walk_seconds", None)]
        fields.extend(("transfer_walk_seconds", index) for index in range(len(route["transfer_walk_seconds"])))
        for field, index in fields:
            original = route[field] if index is None else route[field][index]
            for delta in config["walking_sensitivity_seconds"]:
                changed = deepcopy(templates)
                revised = max(0, original + delta)
                if index is None:
                    changed[position][field] = revised
                else:
                    changed[position][field][index] = revised
                yield {"route_id": route["id"], "component": field, "transfer_index": index,
                       "requested_delta_seconds": delta, "actual_delta_seconds": revised - original}, changed


def project_snapshot(snapshot, templates):
    """Retain all potentially usable trains and every conflicting duplicate ID.

    Full observed stop paths remain intact for alert applicability. Rejected
    trains lacking both leg endpoints cannot become selected in any mode.
    """
    if snapshot.get("feed_id") == "subway-alerts":
        return snapshot
    from data.october.labels import canonical_event_trip_id
    endpoints = defaultdict(list)
    for route in templates:
        for leg in route["legs"]:
            if leg["feed_id"] == snapshot.get("feed_id"):
                for line in leg.get("route_ids", [leg["route_id"]]):
                    endpoints[line].append((leg["from_stop_id"], leg["to_stop_id"]))
    identities, physical_identities = set(), set()
    for trip in snapshot.get("trips", []):
        stops = {stop.get("stop_id") for stop in trip.get("stop_updates", [])}
        if any(origin in stops and destination in stops for origin, destination in endpoints[trip.get("route_id")]):
            identities.add(trip.get("id"))
            physical = canonical_event_trip_id(trip)
            if physical is not None:
                physical_identities.add(physical)
    return dict(snapshot, trips=[trip for trip in snapshot.get("trips", []) if trip.get("id") in identities
                                 or canonical_event_trip_id(trip) in physical_identities])


def summary_case(case):
    """Keep summary inputs small after full selected-path evidence is persisted."""
    result = {key: case[key] for key in ("id", "decision_at", "split", "day_type", "period",
                                        "incident_ids", "reference_route_id")}
    result["modes"] = {}
    result["reference_service_context"] = case.get("reference_service_context") or reference_service_context(case.get("reference"))
    for mode, value in case["modes"].items():
        result["modes"][mode] = {key: value[key] for key in ("strict_decision", "conditional_timing_decision", "scores")}
        result["modes"][mode]["outcomes"] = {identity: {key: outcome[key] for key in ("status", "reason", "total_duration_seconds") if key in outcome}
                                             for identity, outcome in value["outcomes"].items()}
        result["modes"][mode]["routes"] = [{key: route.get(key) for key in ("id", "family", "timing_eligible")}
                                         for route in value["routes"]]
    return result
