"""Post-hoc affected-route references over immutable October predictions."""

from collections import Counter
from copy import deepcopy

from .october_evaluation import MODES, _decision_scores, reference_service_context, summarize
from .severe import decide


REFERENCE_POLICY = "ASOF_DEFINITE_SEVERE_MTA_ROUTE_AS_STAY"
SCOPES = ("strict_decision", "conditional_timing_decision")


def selection_view(record):
    """Project only identification and contemporaneous exposure, never outcomes."""
    if record.get("kind") != "BASELINE_REPLAY":
        return None
    case = record["case"]
    routes = []
    for route in case["modes"]["mta"]["routes"]:
        context = reference_service_context(route)
        alerts = {}
        for leg in route.get("selected_legs", []):
            item = leg.get("incident_context") or {}
            if item.get("state") != "SEVERE" or item.get("applicable") is not True:
                continue
            for alert in item.get("alerts", []):
                if alert.get("incident_id") in context["severe_incident_ids"]:
                    alerts[alert["version_id"]] = deepcopy(alert)
        routes.append({"id": route["id"], "family": route.get("family", route["id"]),
                       "name": route.get("name", route["id"]), "context": context,
                       "alerts": sorted(alerts.values(), key=lambda row: (row["incident_id"], row["version_id"])),
                       "timing_eligible": bool(route.get("timing_eligible")),
                       "reason_codes": list(route.get("reason_codes", [])),
                       "rejection_reasons": sorted({item["reason"] for item in route.get("rejected", [])})})
    return {key: deepcopy(case[key]) for key in ("id", "split", "date", "local_time", "decision_at", "incident_ids")} | {"routes": routes}


def select_affected(views):
    """Include every definite exposure; freshness and outcomes do not filter it."""
    selected = []
    coverage = Counter()
    unavailable = []
    for case in sorted((view for view in views if view is not None), key=lambda row: (row["decision_at"], row["id"])):
        coverage["primary_checkpoints"] += 1
        for route in case["routes"]:
            coverage["candidate_route_observations"] += 1
            if not route["timing_eligible"]:
                unavailable.append({"checkpoint_id": case["id"], "local_time": case["local_time"],
                                    "route_id": route["id"], "family": route["family"],
                                    "reason_codes": route["reason_codes"], "rejection_reasons": route["rejection_reasons"]})
            if route["context"]["category"] != "DEFINITE_APPLICABLE_SEVERE":
                continue
            selected.append({"id": case["id"] + "--stay-" + route["id"],
                             "checkpoint_id": case["id"], "split": case["split"],
                             "decision_at": case["decision_at"], "local_time": case["local_time"],
                             "reference_route_id": route["id"], "reference_family": route["family"],
                             "reference_name": route["name"], "reference_service_context": route["context"],
                             "incident_ids": route["context"]["severe_incident_ids"],
                             "checkpoint_incident_ids": case["incident_ids"], "alerts": route["alerts"]})
    selected.sort(key=lambda row: (row["decision_at"], row["reference_route_id"], row["id"]))
    seen = set()
    example_ids = []
    for row in selected:
        keys = {(row["split"], identity, row["reference_family"]) for identity in row["incident_ids"]}
        if keys - seen:
            example_ids.append(row["id"])
            seen.update(keys)
    return {"reference_policy": REFERENCE_POLICY, "selection_uses_outcomes": False,
            "selection_uses_recommendations_or_savings": False,
            "example_policy": "FIRST_CHRONOLOGICAL_ROUTE_PER_SPLIT_AFFECTING_INCIDENT_AND_ROUTE_FAMILY; ROUTE_ID_BREAKS_TIES",
            "cases": selected, "example_ids": example_ids, "input_coverage": dict(coverage),
            "unavailable_candidates": unavailable,
            "scope_limit": "Only existing baseline checkpoint routes with a complete as-of selected journey can establish segment exposure; unavailable routes remain reported but cannot be assigned definite exposure from the cached records."}


def apply_text_review(selection, review_pairs, split):
    """Narrow classifier exposure using a separately frozen input-only audit."""
    matching_reviews = [row for row in review_pairs if row["split"] == split]
    reviews = {(row["source_case_id"], row["reference_route_id"]): row for row in matching_reviews}
    if len(reviews) != len(matching_reviews):
        raise ValueError("Official text review contains duplicate route/checkpoint pairs.")
    identities = {(row["checkpoint_id"], row["reference_route_id"]) for row in selection["cases"]}
    if identities != set(reviews):
        raise ValueError("Official text review does not cover exactly the classifier candidates.")
    result = deepcopy(selection)
    result["classifier_candidates"] = deepcopy(selection["cases"])
    result["cases"], result["excluded_classifier_candidates"] = [], []
    for row in selection["cases"]:
        review = reviews[(row["checkpoint_id"], row["reference_route_id"])]
        if review["decision_at"] != row["decision_at"] or review["classifier_incident_ids"] != row["incident_ids"]:
            raise ValueError("Official text review identity or contemporaneous exposure differs.")
        revised = dict(deepcopy(row), official_text_review=deepcopy(review))
        if review["status"] == "CONFIRMED":
            if not review["confirmed_incident_ids"] or not set(review["confirmed_incident_ids"]).issubset(row["incident_ids"]):
                raise ValueError("Confirmed exposure must be supported by the as-of selected route.")
            revised["incident_ids"] = deepcopy(review["confirmed_incident_ids"])
            result["cases"].append(revised)
        else:
            result["excluded_classifier_candidates"].append(revised)
    seen, example_ids = set(), []
    for row in result["cases"]:
        keys = {(row["split"], identity, row["reference_family"]) for identity in row["incident_ids"]}
        if keys - seen:
            example_ids.append(row["id"])
            seen.update(keys)
    result["example_ids"] = example_ids
    return result


def re_reference(case, selected, config):
    """Change only the user-selected route; preserve every forecast and train."""
    reference_id = selected["reference_route_id"]
    reference = next(route for route in case["modes"]["mta"]["routes"] if route["id"] == reference_id)
    actual_context = reference_service_context(reference)
    if actual_context != selected["reference_service_context"]:
        raise ValueError("Selected exposure no longer matches the archived as-of evidence.")
    result = {key: deepcopy(value) for key, value in case.items() if key != "modes"}
    result.update(id=selected["id"], checkpoint_id=case["id"],
                  checkpoint_incident_ids=deepcopy(case["incident_ids"]),
                  incident_ids=deepcopy(selected["incident_ids"]),
                  original_reference_route_id=case["reference_route_id"],
                  original_reference_outcome=deepcopy(case["reference_outcome"]),
                  reference_route_id=reference_id, reference=deepcopy(reference),
                  reference_outcome=deepcopy(case["modes"]["mta"]["outcomes"][reference_id]),
                  reference_service_context=actual_context, reference_policy=REFERENCE_POLICY,
                  affecting_alerts=deepcopy(selected["alerts"]),
                  official_text_review=deepcopy(selected.get("official_text_review")), modes={})
    if selected.get("official_text_review", {}).get("status") == "CONFIRMED":
        result["classifier_reference_service_context"] = deepcopy(actual_context)
        result["reference_service_context"] = dict(actual_context, severe_incident_ids=deepcopy(selected["incident_ids"]))
    for mode in MODES:
        value = deepcopy(case["modes"][mode])
        value.update(decide(value, reference_id, switch_margin_seconds=config["switch_margin_seconds"], require_severe=True))
        value["scores"] = {scope: _decision_scores(value, reference_id, case["reference_outcome"], scope,
                              config["tie_margin_seconds"], config["switch_margin_seconds"]) for scope in SCOPES}
        result["modes"][mode] = value
    return result


def _replace_reference_policy(summary):
    summary["reference_service_context"]["policy"] = REFERENCE_POLICY + "; LAST_OBSERVED_SEVERE_IS_NOT_FRESH_ADVICE_EVIDENCE"
    for field in ("by_split", "by_day_type", "by_period", "by_incident"):
        for child in summary.get(field, {}).values():
            _replace_reference_policy(child)


def unknown_switch_reasons(cases):
    result = {}
    for mode in MODES:
        result[mode] = {}
        for scope in SCOPES:
            counts, flags, catchability = Counter(), Counter(), Counter()
            rows = []
            for case in cases:
                value = case["modes"][mode]
                decision = value[scope]
                if decision["action"] != "SWITCH" or value["scores"][scope]["inferred_switch_savings_seconds"] is not None:
                    continue
                endpoints = {}
                for side, route_id in (("stay", case["reference_route_id"]), ("switch", decision.get("recommended_itinerary_id"))):
                    outcome = value["outcomes"].get(route_id, {"status": "UNAVAILABLE", "reason": "NO_RECOMMENDED_ROUTE"})
                    if outcome["status"] != "INFERRED":
                        counts[side + ":" + outcome.get("reason", outcome["status"])] += 1
                        endpoints[side] = deepcopy(outcome)
                        if outcome["status"] == "MISSED_SELECTED_TRAIN":
                            catchability[side + (":INITIAL_BOARDING_MISSED" if outcome.get("leg_index") == 0 else ":TRANSFER_MISSED")] += 1
                        for endpoint, reasons in outcome.get("endpoint_flags", {}).items():
                            for reason in reasons:
                                flags[side + ":" + endpoint + ":" + reason] += 1
                rows.append({"id": case["id"], "unavailable_sides": endpoints})
            result[mode][scope] = {"unknown_switch_count": len(rows), "side_reason_counts": dict(counts),
                                  "endpoint_flag_counts": dict(flags), "known_catchability_failures": dict(catchability), "cases": rows}
    return result


def summarize_affected(cases):
    result = summarize(cases)
    _replace_reference_policy(result)
    result["unique_primary_checkpoints"] = len({case["checkpoint_id"] for case in cases})
    result["unknown_switch_reasons"] = unknown_switch_reasons(cases)
    return result


def example_view(case):
    result = {key: deepcopy(case[key]) for key in ("id", "local_time", "incident_ids", "reference_route_id", "reference_service_context", "affecting_alerts")}
    result["modes"] = {}
    for mode in MODES:
        value = case["modes"][mode]
        routes = {route["id"]: route for route in value["routes"]}
        stay = routes[case["reference_route_id"]]
        result["modes"][mode] = {"stay_predicted_seconds": stay["total_duration_seconds"],
                                "stay_outcome": deepcopy(value["outcomes"][stay["id"]])}
        for scope in SCOPES:
            decision = value[scope]
            chosen = routes.get(decision.get("recommended_itinerary_id"))
            result["modes"][mode][scope] = {"decision": deepcopy(decision), "score": deepcopy(value["scores"][scope]),
                "recommended_predicted_seconds": chosen["total_duration_seconds"] if chosen else None,
                "recommended_outcome": deepcopy(value["outcomes"].get(chosen["id"])) if chosen else None}
    return result
