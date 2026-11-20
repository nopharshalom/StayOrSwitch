#!/usr/bin/env python3
"""Prepare, review, freeze, and replay Google-defined Stay corridors separately."""

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, timedelta
from itertools import chain
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo"), str(ROOT / "algo/scripts")]

from data.delay_profiles import IncidentIndex, ProfileEstimator
from data.october import read_labels, read_snapshots
from stayorswitch.google_corridor_replay import POLICY, apply_review, plan_incidents, representatives, review_groups, select_encounter, validate_corridors
from stayorswitch.october_evaluation import latest_at_cutoffs, local_context, outcome_for, project_snapshot, reference_service_context, summarize
from stayorswitch.preincident_replay import local_time, score_modes
from stayorswitch.severe import MODES, decide, predict_routes
from evaluate_preincident import artifact, code_provenance, dump, load, sha

LOCAL = ROOT / "algo/local/google-corridors"
REPORTS = ROOT / "algo/reports"
CONFIG = ROOT / "data/config/google-corridors.json"


def path(suffix):
    return REPORTS / ("google-corridors" + suffix)


def provenance(config):
    names = ("algo/stayorswitch/google_corridor_replay.py", "algo/scripts/evaluate_google_corridors.py")
    return {"unchanged_original_implementation": code_provenance(), "policy": POLICY,
            "corridor_config": artifact(CONFIG),
            "new_code_sha256": {name: sha(ROOT / name) for name in names}}


def predict(snapshots, corridor, cutoff, index, estimator=None, mode="mta"):
    value = predict_routes(snapshots, corridor["routes"], cutoff, mode=mode, estimator=estimator,
        incident_index=index, train_max_age_seconds=POLICY["train_max_age_seconds"],
        alerts_max_age_seconds=POLICY["alerts_max_age_seconds"])
    # Invalid provider candidates remain visible, rather than becoming slower by omission.
    for candidate in corridor.get("unavailable_candidates", []):
        value["routes"].append({"id": candidate["id"], "name": candidate.get("name", candidate["id"]),
            "family": candidate.get("family", "UNRESOLVED_GOOGLE_PATH"), "status": "UNAVAILABLE",
            "mode": mode, "eta": None, "total_duration_seconds": None,
            "timing_eligible": False, "comparison_eligible": False,
            "selected_legs": [], "rejected": [], "leg_candidate_counts": [], "components": None,
            "reason_codes": candidate.get("reason_codes", ["PROVIDER_PATH_NORMALIZATION_FAILED"]),
            "context": {"state": "UNKNOWN", "evidence_status": "UNKNOWN", "incident_ids": [],
                        "severe_incident_ids": [], "ambiguous_scope": True},
            "severe_incident_ids": [], "provider_unavailable_candidate": deepcopy(candidate)})
    return value


def _verify_source(item, sources):
    if sha(ROOT / item["path"]) != item["sha256"]:
        raise ValueError("Input source changed: " + item["path"])
    sources[item["path"]] = item["sha256"]


def prepare():
    started = time.monotonic()
    config = load(CONFIG)
    corridors = validate_corridors(config)
    initial = provenance(config)
    source_path = ROOT / "data/manifests/october.json"
    source = load(source_path)
    inventory_path = ROOT / "data/processed/october/incidents.json.gz"
    inventory = load(inventory_path)
    sources = {str(p.relative_to(ROOT)): sha(p) for p in (source_path, inventory_path, CONFIG)}
    plans, excluded = {}, {}
    by_date = defaultdict(set)
    all_routes = []
    for corridor in corridors:
        plans[corridor["id"]], excluded[corridor["id"]] = plan_incidents(inventory, corridor)
        all_routes.extend(corridor["routes"])
        for plan in plans[corridor["id"]]:
            for cutoff in plan["decision_times"]:
                by_date[local_time(cutoff)[:10]].add(cutoff)
    days = {row["date"]: row for row in source["days"]}
    supplements = []
    for spec in config.get("supplemental_sources", [
            {"manifest": "data/manifests/preincident-inputs.json", "replace_feeds": ["bdfm", "numbered"]}]):
        manifest_path = ROOT / spec["manifest"]
        manifest = load(manifest_path)
        if manifest.get("stage") != "PREPARED":
            raise ValueError("Supplemental input preparation is incomplete: " + spec["manifest"])
        sources[spec["manifest"]] = sha(manifest_path)
        supplements.append((spec, {row["date"]: row for row in manifest["days"]}))
    replacement = {}
    for i, (spec, _) in enumerate(supplements):
        for feed in spec["replace_feeds"]:
            replacement[feed] = i

    def alerts():
        for day in sorted(days):
            item = days[day]["outputs"]["alerts"]
            _verify_source(item, sources)
            yield from read_snapshots(ROOT / item["path"])

    index = IncidentIndex(alerts(), max_age_seconds=POLICY["alerts_max_age_seconds"])
    print({"stage": "INPUT_PLAN", "incidents": {k: len(v) for k, v in plans.items()},
           "cutoffs": sum(map(len, by_date.values()))}, flush=True)
    # Only event cutoffs are retained; all normalized source captures are streamed once.
    captured, carry = {}, {}
    day = date.fromisoformat(POLICY["test_dates"][0]) - timedelta(days=1)
    while day <= date.fromisoformat(POLICY["test_dates"][1]):
        key = day.isoformat()
        original_item = days[key]["outputs"]["snapshots"]
        _verify_source(original_item, sources)
        streams = [(s for s in read_snapshots(ROOT / original_item["path"]) if s["feed_id"] not in replacement)]
        for i, (spec, extra_days) in enumerate(supplements):
            feeds = {feed for feed, owner in replacement.items() if owner == i}
            if not feeds:
                continue
            item = extra_days[key]["outputs"]["snapshots"]
            _verify_source(item, sources)
            # Bind feed ownership inside the generator; the loop variable must not drift.
            def filtered(filename, allowed):
                return (s for s in read_snapshots(filename) if s["feed_id"] in allowed)
            streams.append(filtered(ROOT / item["path"], feeds))
        cutoffs = sorted(by_date.get(key, []))
        selected, carry = latest_at_cutoffs((project_snapshot(s, all_routes) for s in chain(*streams)), cutoffs, carry)
        captured.update(selected)
        print({"stage": "INPUT_DAY", "date": key, "cutoffs": len(cutoffs),
               "seconds": round(time.monotonic() - started, 1)}, flush=True)
        day += timedelta(days=1)
    estimator = ProfileEstimator(ROOT / "data/artifacts/october-2026-profiles-train.json.gz")
    candidates, rejection_counts = [], {}
    for corridor in corridors:
        cache, failed = {}, Counter()
        for plan in plans[corridor["id"]]:
            for cutoff in plan["decision_times"]:
                if cutoff not in cache:
                    cache[cutoff] = predict(captured[cutoff], corridor, cutoff, index)
                case, reason = select_encounter(plan, corridor, cache[cutoff], index)
                if case is None:
                    failed[reason] += 1
                    continue
                case["predictions"] = {mode: cache[cutoff] if mode == "mta" else
                    predict(captured[cutoff], corridor, cutoff, index, estimator, mode) for mode in MODES}
                candidates.append(case)
        rejection_counts[corridor["id"]] = dict(failed)
    if provenance(config) != initial:
        raise ValueError("Code or configuration changed during input selection.")
    snapshot_path = LOCAL / "selected-input-snapshots.json.gz"
    dump(snapshot_path, [{"cutoff": t, "snapshots": captured[t]}
                         for t in sorted({c["decision_at"] for c in candidates})])
    prepared = {"provenance": initial, "config": config, "input_sources": sources,
                "plans": plans, "excluded_family_counts": excluded,
                "selection_rejection_counts": rejection_counts, "cases": candidates,
                "selection_reads_outcome_labels": False,
                "previous_test_exploration_disclosed": True, "selected_input_snapshots": artifact(snapshot_path)}
    prepared_path = LOCAL / "prepared-inputs.json.gz"
    dump(prepared_path, prepared)
    review = {"prepared_inputs": artifact(prepared_path), "selection_uses_outcomes": False,
              "groups": review_groups(candidates)}
    dump(path("-candidate-selection.json"), {"policy": POLICY, "prepared_inputs": artifact(prepared_path),
        "corridors": config["corridors"], "excluded_family_counts": excluded,
        "selection_rejection_counts": rejection_counts,
        "candidate_count": len(candidates), "review_group_count": len(review["groups"]),
        "cases": [{k: c[k] for k in ("id", "corridor_id", "incident_ids", "local_time", "decision_at",
                    "reference_route_id", "review_group_id", "exposure_sha256")} for c in candidates],
        "review_groups": review["groups"]})
    draft = path("-text-review.json")
    if draft.exists():
        if load(draft)["prepared_inputs"] != review["prepared_inputs"]:
            raise ValueError("An earlier review exists for different inputs; preserve it before rerunning.")
    else:
        dump(draft, review)
    print({"stage": "PREPARED_WITHOUT_OUTCOMES", "candidates": len(candidates),
           "review_groups": len(review["groups"]), "seconds": round(time.monotonic() - started, 1)}, flush=True)


def prepare_sensitivity(prepared, primary, review_artifact):
    """Freeze walk perturbations from primary input-selected cases, without labels."""
    output = LOCAL / "walking-sensitivity-inputs.json.gz"
    binding = {"provenance": prepared["provenance"], "primary_case_ids": [c["id"] for c in primary],
               "review": review_artifact, "selection_uses_outcomes": False}
    if output.exists():
        previous = load(output)
        if previous["binding"] != binding:
            raise ValueError("Earlier sensitivity inputs belong to another selection.")
        return artifact(output)
    snapshot_item = prepared["selected_input_snapshots"]
    if sha(ROOT / snapshot_item["path"]) != snapshot_item["sha256"]:
        raise ValueError("Selected input snapshots changed.")
    snapshots = {row["cutoff"]: row["snapshots"] for row in load(ROOT / snapshot_item["path"])}
    original = load(ROOT / "data/manifests/october.json")
    index = IncidentIndex(chain.from_iterable(read_snapshots(ROOT / day["outputs"]["alerts"]["path"])
                          for day in sorted(original["days"], key=lambda d: d["date"])), max_age_seconds=300)
    estimator = ProfileEstimator(ROOT / "data/artifacts/october-2026-profiles-train.json.gz")
    corridors = {c["id"]: c for c in prepared["config"]["corridors"]}
    cases = []
    for case in primary:
        corridor = corridors[case["corridor_id"]]
        alternatives = [r for r in case["predictions"]["incident_profile"]["routes"]
                        if r["id"] != case["reference_route_id"] and r.get("timing_eligible")]
        best = min(alternatives, key=lambda r: (r["total_duration_seconds"], r["id"])) if alternatives else None
        selected = [case["reference_route_id"]] + ([best["id"]] if best else [])
        variants, skipped = [], []
        for route_id in selected:
            route = next(r for r in corridor["routes"] if r["id"] == route_id)
            components = [("access_walk_seconds", None), ("egress_walk_seconds", None)]
            components += [("transfer_walk_seconds", i) for i in range(len(route["transfer_walk_seconds"]))]
            for component, position in components:
                original_walk = route[component] if position is None else route[component][position]
                for delta in POLICY["walking_sensitivity_seconds"]:
                    spec = {"route_id": route_id, "component": component, "transfer_index": position,
                            "delta_seconds": delta, "original_walk_seconds": original_walk}
                    if original_walk + delta < 0:
                        skipped.append(dict(spec, reason="NEGATIVE_WALK_NOT_ALLOWED"))
                        continue
                    adjusted = deepcopy(corridor)
                    target = next(r for r in adjusted["routes"] if r["id"] == route_id)
                    if position is None:
                        target[component] += delta
                    else:
                        target[component][position] += delta
                    forecast = predict(snapshots[case["decision_at"]], adjusted, case["decision_at"], index,
                                       estimator, "incident_profile")
                    variants.append(dict(spec, prediction=forecast,
                        decisions=decide(forecast, case["reference_route_id"], switch_margin_seconds=300, require_severe=False)))
        cases.append({"case_id": case["id"], "selected_route_ids": selected,
                      "variants": variants, "skipped_negative_variants": skipped})
    dump(output, {"binding": binding, "cases": cases})
    print({"stage": "INPUT_ONLY_WALK_SENSITIVITY", "primary_cases": len(cases),
           "variants": sum(len(c["variants"]) for c in cases)}, flush=True)
    return artifact(output)


def freeze():
    prepared_path = LOCAL / "prepared-inputs.json.gz"
    prepared = load(prepared_path)
    if provenance(load(CONFIG)) != prepared["provenance"]:
        raise ValueError("Prepared code/configuration changed.")
    for name, expected in prepared["input_sources"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Prepared source changed: " + name)
    review_path = path("-text-review.json")
    review = load(review_path)
    if review["prepared_inputs"] != artifact(prepared_path):
        raise ValueError("Text review is bound to different inputs.")
    audit_sources = review.get("audit_sources", [])
    if not audit_sources:
        raise ValueError("The independent input notice audits must be bound by hash.")
    for audit in audit_sources:
        if sha(ROOT / audit["path"]) != audit["sha256"]:
            raise ValueError("Input audit changed: " + audit["path"])
    confirmed, excluded = apply_review(prepared["cases"], review)
    primary = representatives(confirmed)
    sensitivity = prepare_sensitivity(prepared, primary, artifact(review_path))
    value = {"schema_version": "google-corridors-selection-freeze-v1", "selection_uses_outcomes": False,
        "provenance": prepared["provenance"], "prepared_inputs": artifact(prepared_path),
        "candidate_inventory": artifact(path("-candidate-selection.json")), "text_review": artifact(review_path),
        "confirmed_case_ids": [c["id"] for c in confirmed], "excluded_case_ids": [c["id"] for c in excluded],
        "primary_representative_ids": [c["id"] for c in primary], "walking_sensitivity_inputs": sensitivity,
        "independent_input_audits": audit_sources}
    target = path("-selection-frozen.json")
    if target.exists() and load(target) != value:
        raise ValueError("Published freeze differs; do not overwrite it.")
    dump(target, value)
    print({"stage": "FROZEN", "all_confirmed_checkpoints": len(confirmed), "primary_events": len(primary)}, flush=True)


def _merge_labels(target, extra):
    for identity, endpoints in extra.items():
        existing = target.setdefault(identity, {})
        for stop_id, value in endpoints.items():
            if stop_id in existing and existing[stop_id] != value:
                raise ValueError("Supplemental labels conflict with existing endpoint: " + identity + " " + stop_id)
            existing[stop_id] = value


def _path_signature(route):
    return tuple((leg["from_stop_id"], leg["to_stop_id"]) for leg in route.get("legs", []))


def compact_case(case, corridor):
    stay_template = next(r for r in corridor["routes"] if r["id"] == case["reference_route_id"])
    same_path = {r["id"] for r in corridor["routes"] if _path_signature(r) == _path_signature(stay_template)}
    modes = {}
    for mode, value in case["modes"].items():
        rows = []
        for route in value["routes"]:
            outcome = value["outcomes"][route["id"]]
            rows.append({"id": route["id"], "name": route["name"],
                "same_station_path_as_stay": route["id"] in same_path,
                "predicted_duration_seconds": route.get("total_duration_seconds"),
                "timing_eligible": route["timing_eligible"], "comparison_eligible": route["comparison_eligible"],
                "context": route["context"], "reason_codes": route.get("reason_codes", []),
                "selected_train_ids": [leg["trip_id"] for leg in route.get("selected_legs", [])],
                "outcome": {k: deepcopy(outcome[k]) for k in ("status", "reason", "total_duration_seconds",
                    "destination_arrival_at", "leg_index", "trip_id", "endpoint_flags", "departure_at", "platform_ready_at") if k in outcome}})
        decision = value["strict_decision"]
        modes[mode] = {"strict_decision": decision, "conditional_timing_decision": value["conditional_timing_decision"],
            "strict_switch_is_same_station_path": decision["action"] == "SWITCH" and decision["recommended_itinerary_id"] in same_path,
            "alternative_counterfactual": {k: v for k, v in value["alternative_counterfactual"].items() if k != "alternative_outcome"}, "routes": rows,
            "scores": value["scores"]}
    return {"id": case["id"], "corridor_id": case["corridor_id"], "local_time": case["local_time"],
        "incident_ids": case["incident_ids"], "lag_seconds": case["lag_seconds"],
        "reference_route_id": case["reference_route_id"], "official_text_review": case["official_text_review"],
        "exposure": [{k: deepcopy(v) for k, v in leg.items() if k != "notices"} | {
            "notices": [{k: a[k] for k in ("version_id", "state", "header", "active_status", "model_scope_matches", "model_scope") if k in a}
                        for a in leg["notices"]]} for leg in case["exposure"]],
        "walking_sensitivity_summary": case.get("walking_sensitivity_summary"),
        "modes": modes}


def score_sensitivity(source, cases, labels):
    lookup = {c["id"]: c for c in cases}
    result = []
    for group in source["cases"]:
        case = lookup[group["case_id"]]
        baseline = case["modes"]["incident_profile"]["strict_decision"]
        rows = []
        for variant in group["variants"]:
            forecast = variant["prediction"]
            outcomes = {r["id"]: outcome_for(r, labels, case["decision_at"]) for r in forecast["routes"]}
            stay = outcomes[case["reference_route_id"]]
            alternatives = [r for r in forecast["routes"] if r["id"] != case["reference_route_id"] and r.get("timing_eligible")]
            best = min(alternatives, key=lambda r: (r["total_duration_seconds"], r["id"])) if alternatives else None
            other = outcomes.get(best["id"], {}) if best else {}
            saving = stay["total_duration_seconds"] - other["total_duration_seconds"] if stay.get("status") == other.get("status") == "INFERRED" else None
            strict = variant["decisions"]["strict_decision"]
            recommendation = outcomes.get(strict["recommended_itinerary_id"], {})
            strict_saving = stay["total_duration_seconds"] - recommendation["total_duration_seconds"] if strict["action"] == "SWITCH" and stay.get("status") == recommendation.get("status") == "INFERRED" else None
            rows.append({k: deepcopy(v) for k, v in variant.items() if k != "prediction"} | {
                "selected_train_ids": {r["id"]: [leg["trip_id"] for leg in r.get("selected_legs", [])] for r in forecast["routes"]},
                "outcomes": outcomes, "forecast_best_alternative_id": best["id"] if best else None,
                "best_alternative_proxy_saving_seconds": saving, "strict_switch_proxy_saving_seconds": strict_saving,
                "same_strict_advice": (strict["action"], strict["recommended_itinerary_id"]) == (baseline["action"], baseline["recommended_itinerary_id"])})
        known = [r["best_alternative_proxy_saving_seconds"] for r in rows if r["best_alternative_proxy_saving_seconds"] is not None]
        switches = [r["strict_switch_proxy_saving_seconds"] for r in rows if r["strict_switch_proxy_saving_seconds"] is not None]
        summary = {"variants": len(rows), "skipped_negative_variants": len(group["skipped_negative_variants"]),
            "same_strict_advice": sum(r["same_strict_advice"] for r in rows),
            "strict_actions": dict(Counter(r["decisions"]["strict_decision"]["action"] for r in rows)),
            "comparable_best_alternative_variants": len(known),
            "best_alternative_proxy_saving_range_seconds": [min(known), max(known)] if known else None,
            "comparable_strict_switch_variants": len(switches),
            "strict_switch_proxy_saving_range_seconds": [min(switches), max(switches)] if switches else None}
        case["walking_sensitivity_summary"] = summary
        result.append({"case_id": case["id"], "summary": summary, "variants": rows,
                       "skipped_negative_variants": group["skipped_negative_variants"]})
    return result


def _summary(cases):
    value = summarize(cases, grouped=False)
    value["reference_service_context"]["policy"] = POLICY["reference_policy"]
    value["counterfactual"] = {}
    value["manually_qualified_impact_counts"] = dict(Counter(c["official_text_review"]["confirmed_impact"] for c in cases))
    for mode in MODES:
        savings = [c["modes"][mode]["alternative_counterfactual"]["inferred_savings_seconds"] for c in cases]
        known = [s for s in savings if s is not None]
        value["counterfactual"][mode] = {"comparable": len(known), "unknown": len(savings) - len(known),
            "meaningful_gains": sum(s > POLICY["tie_margin_seconds"] for s in known),
            "practical_ties": sum(abs(s) <= POLICY["tie_margin_seconds"] for s in known),
            "meaningful_losses": sum(s < -POLICY["tie_margin_seconds"] for s in known)}
        for scope in ("strict_decision", "conditional_timing_decision"):
            for kind in ("same_station_path", "different_path"):
                selected = [c for c in cases if c["modes"][mode][scope]["action"] == "SWITCH" and
                            (c["modes"][mode][scope]["recommended_itinerary_id"] in c["same_station_path_ids"]) == (kind == "same_station_path")]
                scored = [c for c in selected if c["modes"][mode]["scores"][scope]["inferred_switch_savings_seconds"] is not None]
                value["modes"][mode][scope][kind + "_switches"] = {"recommendations": len(selected),
                    "comparable": len(scored), "unknown": len(selected) - len(scored),
                    "outcome_classes": dict(Counter(c["modes"][mode]["scores"][scope]["classification"] for c in scored))}
    return value


def minutes(value):
    return "unknown" if value is None else "{:.2f}".format(value / 60)


def score():
    frozen = load(path("-selection-frozen.json"))
    config = load(CONFIG)
    if provenance(config) != frozen["provenance"]:
        raise ValueError("Frozen code/configuration changed.")
    for key in ("prepared_inputs", "candidate_inventory", "text_review", "walking_sensitivity_inputs"):
        item = frozen[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen selection artifact changed.")
    for item in frozen["independent_input_audits"]:
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen independent input audit changed.")
    prepared = load(ROOT / frozen["prepared_inputs"]["path"])
    cases, _ = apply_review(prepared["cases"], load(ROOT / frozen["text_review"]["path"]))
    if [c["id"] for c in cases] != frozen["confirmed_case_ids"] or [c["id"] for c in representatives(cases)] != frozen["primary_representative_ids"]:
        raise ValueError("Frozen case identities changed.")
    original = load(ROOT / "data/manifests/october.json")
    labels, label_sources = {}, {}
    for day in sorted({local_time(c["decision_at"])[:10] for c in cases}):
        for service_day in ((date.fromisoformat(day) - timedelta(days=1)).isoformat(), day):
            item = original["daily_labels"][service_day]
            if item["path"] not in label_sources:
                _verify_source(item, label_sources)
                _merge_labels(labels, read_labels(ROOT / item["path"]))
    for spec in config.get("extra_label_sources", [{"manifest": "data/manifests/preincident-inputs.json", "key": "labels"}]):
        manifest_path = ROOT / spec["manifest"]
        if spec["manifest"] not in prepared["input_sources"] or sha(manifest_path) != prepared["input_sources"][spec["manifest"]]:
            raise ValueError("Supplemental labels were not bound before scoring.")
        manifest = load(manifest_path)
        item = manifest[spec.get("key", "labels")]
        _verify_source(item, label_sources)
        _merge_labels(labels, read_labels(ROOT / item["path"]))
    corridors = {c["id"]: c for c in config["corridors"]}
    configuration = load(ROOT / "data/config/october.json")
    evaluated = []
    for case in cases:
        row = score_modes(case, case["predictions"], labels, POLICY)
        row.update(local_context(row["decision_at"], configuration))
        row["reference"] = next(r for r in row["asof_mta_prediction"]["routes"] if r["id"] == row["reference_route_id"])
        row["reference_service_context"] = reference_service_context(row["reference"])
        corridor = corridors[case["corridor_id"]]
        stay_template = next(r for r in corridor["routes"] if r["id"] == case["reference_route_id"])
        row["same_station_path_ids"] = [r["id"] for r in corridor["routes"] if _path_signature(r) == _path_signature(stay_template)]
        evaluated.append(row)
    sensitivity_scored = score_sensitivity(load(ROOT / frozen["walking_sensitivity_inputs"]["path"]), evaluated, labels)
    sensitivity_path = LOCAL / "walking-sensitivity-scored.json.gz"
    dump(sensitivity_path, sensitivity_scored)
    scored_path = LOCAL / "scored-cases.json.gz"
    dump(scored_path, evaluated)
    primary_ids = set(frozen["primary_representative_ids"])
    primary = [c for c in evaluated if c["id"] in primary_ids]
    compact = [compact_case(c, corridors[c["corridor_id"]]) for c in evaluated]
    # Display availability-selected examples only after the complete cohort is scored.
    # Their gain sign and recommendation do not participate in illustration selection.
    illustration_keys, illustration_ids = set(), []
    for case in sorted(evaluated, key=lambda c: (c["decision_at"], c["id"])):
        key = (case["corridor_id"], tuple(case["incident_ids"]), case["official_text_review"]["confirmed_impact"])
        if key not in illustration_keys and case["modes"]["incident_profile"]["alternative_counterfactual"]["outcomes_comparable"]:
            illustration_keys.add(key)
            illustration_ids.append(case["id"])
    result = {"policy": POLICY, "selection_freeze": artifact(path("-selection-frozen.json")),
        "scored_artifact": artifact(scored_path), "walking_sensitivity_artifact": artifact(sensitivity_path),
        "source_label_sha256": label_sources,
        "primary_summary": _summary(primary), "all_checkpoint_summary": _summary(evaluated),
        "illustration_policy": "EARLIEST_COMPARABLE_FORECAST_BEST_ALTERNATIVE_PER_CORRIDOR_INCIDENT_MANUAL_IMPACT; AVAILABILITY_SELECTED_NOT_GAIN_OR_ACTION_SELECTED; NOT_THE_PRIMARY_COHORT",
        "illustration_case_ids": illustration_ids,
        "corridors": {}, "all_checkpoint_results": compact}
    for identity, corridor in corridors.items():
        all_rows = [c for c in evaluated if c["corridor_id"] == identity]
        main = [c for c in all_rows if c["id"] in primary_ids]
        result["corridors"][identity] = {"definition": corridor, "primary_summary": _summary(main),
            "all_checkpoint_summary": _summary(all_rows), "primary_case_ids": [c["id"] for c in main],
            "primary_by_manual_impact": {impact: _summary([c for c in main if c["official_text_review"]["confirmed_impact"] == impact]) for impact in POLICY["problem_states"]},
            "all_checkpoints_by_manual_impact": {impact: _summary([c for c in all_rows if c["official_text_review"]["confirmed_impact"] == impact]) for impact in POLICY["problem_states"]}}
    dump(path("-test.json"), result)
    lines = ["# Current Google Stay paths under historical service problems", "",
        "Google's current recommended path defines Stay; its present-day ETA is context only. Every historical journey departs unboarded at the event's own information cutoff. The current path is not claimed to have been the fastest path in October.", "",
        "This post-hoc test uses October 25–31 official service problems and fixed 0/5/10/15/30/60/120-minute checkpoints after the first problem version naming the Stay line, plus the exact receipts of later relevant problem versions inside that two-hour window. All input-selected confirmed encounters are retained. The primary event representative is the earliest confirmed checkpoint with usable Stay timing, or the earliest unknown encounter if none has timing. Selection and text scope were frozen before labels were opened.", "",
        "Final MTA predictions are screened outcome proxies, not independently observed passenger arrivals. Current-provider and explicitly authored walking times are held fixed; they are not historical pedestrian measurements. Unknown or missed selected trains remain unknown. Historical models and the five-minute Switch margin are unchanged.", "",
        "Same boarding/alighting station paths with another line, such as 5 to 4, are marked as same-station-path service substitutions rather than geographic detours. Invalid Google candidates remain unavailable, never silently slower.", ""]
    for identity, item in result["corridors"].items():
        definition = item["definition"]
        stay_definition = next(r for r in definition["routes"] if r["id"] == definition["reference_route_id"])
        google = definition["google"]
        provider_normalized = stay_definition.get("google", {}).get("normalization_provenance", {})
        raw_duration = google["current_duration_seconds"]
        derived_duration = raw_duration + provider_normalized.get("duration_vs_clock_difference_seconds", 0)
        lines += ["## " + identity, "", "{} → {}.".format(definition["origin"], definition["destination"]), "",
            "Google-defined Stay: `{}`. Provider capture metadata and all paths are preserved in the linked configuration and JSON.".format(definition["reference_route_id"]), "",
            "Current Google query: {}. Raw API duration {} min; query-clock to provider destination-arrival-plus-egress {} min. These present-day values differ and neither is used as an October outcome.".format(google["requested_at"], minutes(raw_duration), minutes(derived_duration)), "",
            "Primary event representatives: **{}**; all confirmed checkpoints: **{}**.".format(item["primary_summary"]["case_count"], item["all_checkpoint_summary"]["case_count"]), "",
            "Primary manual impact counts: {}. All-checkpoint manual impact counts: {}.".format(item["primary_summary"]["manually_qualified_impact_counts"], item["all_checkpoint_summary"]["manually_qualified_impact_counts"]), "",
            "| Cohort | Mode | Advice scope | Actions | Scorable Switch | Gains / ties / losses | Unknown Switch | Same-station-path Switch | Different-path Switch |", "|---|---|---|---|---:|---|---:|---:|---:|"]
        for cohort in ("primary_summary", "all_checkpoint_summary"):
            for mode in MODES:
                for scope in ("strict_decision", "conditional_timing_decision"):
                    summary = item[cohort]["modes"][mode][scope]
                    classes = summary["outcome_classes"]
                    lines.append("| {} | {} | {} | {} | {} | {} / {} / {} | {} | {} | {} |".format(cohort, mode, scope, summary["actions"], summary["switches_with_comparable_outcomes"], classes.get("MEANINGFUL_GAIN", 0), classes.get("PRACTICAL_TIE", 0), classes.get("MEANINGFUL_LOSS", 0), summary["switches_without_comparable_outcomes"], summary["same_station_path_switches"]["recommendations"], summary["different_path_switches"]["recommendations"]))
        lines += ["", "### Every primary event: incident-profile mode", "",
            "| Historical cutoff | Official incident | Advice | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |",
            "|---|---|---|---|---|---|---:|"]
        for row in compact:
            if row["id"] not in set(item["primary_case_ids"]):
                continue
            value = row["modes"]["incident_profile"]
            routes = {r["id"]: r for r in value["routes"]}
            stay = routes[row["reference_route_id"]]
            alt = value["alternative_counterfactual"]
            chosen = routes.get(alt["predicted_alternative_route_id"], {})
            lines.append("| {} | {} | {} | {} | {} / {} | {} / {} | {} |".format(row["local_time"], ", ".join(row["incident_ids"]), value["strict_decision"]["action"], alt["predicted_alternative_route_id"], minutes(stay["predicted_duration_seconds"]), minutes(chosen.get("predicted_duration_seconds")), minutes(stay["outcome"].get("total_duration_seconds")), minutes(chosen.get("outcome", {}).get("total_duration_seconds")), minutes(alt["inferred_savings_seconds"])))
        lines += [""]
        lines += ["### Complete per-route comparisons for available illustrations", "",
            "The following are the earliest comparable forecast-best-alternative checkpoints per incident and manually qualified impact. Availability selects illustrations only; all gains, losses, abstentions and unknowns remain in the frozen cohorts above. A later illustration can differ from the primary event checkpoint.", ""]
        for row in compact:
            if row["corridor_id"] != identity or row["id"] not in illustration_ids:
                continue
            value = row["modes"]["incident_profile"]
            lines += ["#### " + row["local_time"], "",
                "Incident {}. Manual impact {}. Strict advice {}; conditional timing advice {}.".format(", ".join(row["incident_ids"]), row["official_text_review"]["confirmed_impact"], value["strict_decision"]["action"], value["conditional_timing_decision"]["action"]), "",
                "| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |", "|---|---|---:|---:|---|"]
            for route in value["routes"]:
                relation = "STAY" if route["id"] == row["reference_route_id"] else "SAME_STATION_PATH" if route["same_station_path_as_stay"] else "OTHER_PATH"
                outcome = route["outcome"]
                lines.append("| {} | {} | {} | {} | {} |".format(route["name"], relation, minutes(route["predicted_duration_seconds"]), minutes(outcome.get("total_duration_seconds")), outcome.get("reason", outcome["status"])))
            if row.get("walking_sensitivity_summary"):
                walk = row["walking_sensitivity_summary"]
                lines += ["", "Primary-case walk sensitivity: {}/{} variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: {}. Full variants retain selected trains and proxy quality in the ignored evidence artifact.".format(walk["same_strict_advice"], walk["variants"], walk["best_alternative_proxy_saving_range_seconds"])]
            else:
                lines += ["", "This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative."]
            lines += [""]
    lines += ["## Reproduce", "", "```sh", ".venv/bin/python algo/scripts/evaluate_google_corridors.py --prepare-inputs", "# Complete the input-only text review before freezing.", ".venv/bin/python algo/scripts/evaluate_google_corridors.py --freeze-only", ".venv/bin/python algo/scripts/evaluate_google_corridors.py", "```", "",
        "Full results: `google-corridors-test.json`; selection, review, source hashes and ignored local evidence paths are retained beside this report. No general success-rate or untouched-test generalization is established by selected exploratory incidents.", ""]
    path("-test.md").write_text("\n".join(lines))
    print({"stage": "COMPLETE", "primary_events": len(primary), "all_checkpoints": len(evaluated),
           "report": str(path("-test.md").relative_to(ROOT))}, flush=True)


def main():
    global CONFIG
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prepare-inputs", action="store_true")
    group.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    CONFIG = args.config.resolve()
    if args.prepare_inputs:
        prepare()
    elif args.freeze_only:
        freeze()
    else:
        score()


if __name__ == "__main__":
    main()
