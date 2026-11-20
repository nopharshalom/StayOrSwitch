#!/usr/bin/env python3
"""Find pre-problem fastest routes that deteriorate, then score frozen cases."""

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, timedelta
import gzip
import hashlib
from itertools import chain
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.delay_profiles import IncidentIndex, ProfileEstimator
from data.october import read_labels, read_snapshots
from stayorswitch.october_evaluation import latest_at_cutoffs, local_context, project_snapshot, reference_service_context, summarize
from stayorswitch.preincident_replay import POLICY, BROOKLYN_POLICY, choose_anchor, local_time, plan_incidents, score_modes, select_delayed
from stayorswitch.severe import MODES, decide, predict_routes

LOCAL = ROOT / "algo/local/october-preincident"
REPORTS = ROOT / "algo/reports"
PREFIX = "preincident"


def report_path(suffix):
    return REPORTS / (PREFIX + suffix)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if path.suffix == ".gz":
        with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, filename="", mtime=0, mode="wb") as handle:
            handle.write(encoded)
    else:
        path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def load(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_text())


def artifact(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def code_provenance():
    original = load(REPORTS / "october-evaluation-frozen.json")
    for name, expected in original["code_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Original frozen implementation changed: " + name)
    if sha(ROOT / "data/config/october.json") != original["config_sha256"]:
        raise ValueError("Original configuration changed.")
    if sha(ROOT / "data/manifests/october.json") != original["source_manifest_sha256"]:
        raise ValueError("Original source manifest changed.")
    profile_manifest = load(ROOT / "data/manifests/profiles-frozen.json")
    if sha(ROOT / "data/manifests/profiles-frozen.json") != original["profile_frozen_manifest_sha256"]:
        raise ValueError("Original frozen profile manifest changed.")
    bundle = ROOT / "data/artifacts/october-2026-profiles-train.json.gz"
    bundle_meta = load(ROOT / "data/artifacts/october-2026-profiles-train.manifest.json")
    profile = load(bundle)
    if (sha(bundle) != bundle_meta["sha256"] or profile["seal"] != bundle_meta["profile_seal"]
            or profile["seal"] != profile_manifest["profile_seal"] or profile["fit_split"] != "train"):
        raise ValueError("Training bundle differs from the original frozen profile.")
    names = ("algo/stayorswitch/preincident_replay.py", "algo/scripts/evaluate_preincident.py")
    return {"original_evaluation": artifact(REPORTS / "october-evaluation-frozen.json"),
            "original_code_sha256": original["code_sha256"],
            "new_code_sha256": {name: sha(ROOT / name) for name in names},
            "policy": POLICY, "training_bundle": artifact(bundle),
            "source_manifest": artifact(ROOT / "data/manifests/october.json"),
            "profile_manifest": artifact(ROOT / "data/manifests/profiles-frozen.json")}


def predict(snapshots, cutoff, index, estimator=None, mode="mta", routes=None):
    return predict_routes(snapshots, routes or POLICY["routes"], cutoff, mode=mode,
                          estimator=estimator, incident_index=index,
                          train_max_age_seconds=180, alerts_max_age_seconds=300)


def prepare():
    started = time.monotonic()
    provenance = code_provenance()
    source = load(ROOT / "data/manifests/october.json")
    inventory_path = ROOT / "data/processed/october/incidents.json.gz"
    inventory = load(inventory_path)
    plans = plan_incidents(inventory, POLICY)
    by_date = defaultdict(set)
    for plan in plans:
        for cutoff in plan["anchor_times"] + plan["decision_times"]:
            by_date[local_time(cutoff)[:10]].add(cutoff)
    sources = {str(inventory_path.relative_to(ROOT)): sha(inventory_path)}
    days = {d["date"]: d for d in source["days"]}
    supplemental_manifest_path = ROOT / "data/manifests/preincident-inputs.json"
    supplemental = load(supplemental_manifest_path)
    if supplemental.get("stage") != "PREPARED":
        raise ValueError("Complete new-leg source preparation is required.")
    supplemental_days = {d["date"]: d for d in supplemental["days"]}
    sources[str(supplemental_manifest_path.relative_to(ROOT))] = sha(supplemental_manifest_path)

    def alerts():
        for day in sorted(days):
            item = days[day]["outputs"]["alerts"]
            path = ROOT / item["path"]
            if sha(path) != item["sha256"]:
                raise ValueError("Alert source changed.")
            sources[item["path"]] = item["sha256"]
            yield from read_snapshots(path)

    index = IncidentIndex(alerts(), max_age_seconds=300)
    print(json.dumps({"stage": "INCIDENT_PLAN", "incidents": len(plans), "cutoffs": sum(map(len, by_date.values()))}), flush=True)
    snapshots_by_time, raw_predictions, carry = {}, {}, {}
    first = date.fromisoformat(POLICY["test_dates"][0]) - timedelta(days=1)
    final = date.fromisoformat(POLICY["test_dates"][1])
    while first <= final:
        day = first.isoformat()
        item = days[day]["outputs"]["snapshots"]
        path = ROOT / item["path"]
        if sha(path) != item["sha256"]:
            raise ValueError("Snapshot source changed.")
        sources[item["path"]] = item["sha256"]
        cutoffs = sorted(by_date.get(day, []))
        new_item = supplemental_days[day]["outputs"]["snapshots"]
        new_path = ROOT / new_item["path"]
        if sha(new_path) != new_item["sha256"]:
            raise ValueError("New-leg snapshot source changed.")
        sources[new_item["path"]] = new_item["sha256"]
        original_records = (s for s in read_snapshots(path) if s["feed_id"] in {"ace", "subway-alerts"})
        replacement_records = (s for s in read_snapshots(new_path) if s["feed_id"] in {"numbered", "bdfm"})
        records = (project_snapshot(s, POLICY["routes"]) for s in chain(original_records, replacement_records))
        selected, carry = latest_at_cutoffs(records, cutoffs, carry)
        snapshots_by_time.update(selected)
        for cutoff in cutoffs:
            raw_predictions[cutoff] = predict(selected[cutoff], cutoff, index)
        print(json.dumps({"stage": "INPUT_DAY", "day": day, "cutoffs": len(cutoffs),
                          "elapsed_seconds": round(time.monotonic() - started, 1)}), flush=True)
        first += timedelta(days=1)
    anchors, candidates, failures = [], [], Counter()
    for plan in plans:
        anchor = choose_anchor(plan, raw_predictions, POLICY)
        anchors.append({"incident_id": plan["incident_id"], "plan": plan, "anchor": anchor})
        for cutoff in plan["decision_times"]:
            case, reason = select_delayed(plan, anchor, raw_predictions[cutoff], cutoff, POLICY)
            if case is not None:
                candidates.append(case)
            else:
                failures[reason] += 1
    estimator = ProfileEstimator(ROOT / "data/artifacts/october-2026-profiles-train.json.gz")
    for position, case in enumerate(candidates):
        cutoff = case["decision_at"]
        case["predictions"] = {mode: raw_predictions[cutoff] if mode == "mta" else
                               predict(snapshots_by_time[cutoff], cutoff, index, estimator, mode) for mode in MODES}
        if (case["anchor"]["prediction"]["cutoff"] != case["anchor"]["decision_at"]
                or any(p["cutoff"] != cutoff for p in case["predictions"].values())):
            raise ValueError("Prediction cutoff differs from its predeclared checkpoint.")
        case["walking_sensitivity"] = []
        for route_id in [r["id"] for r in POLICY["routes"]]:
            template = next(r for r in POLICY["routes"] if r["id"] == route_id)
            components = [("access_walk_seconds", None), ("egress_walk_seconds", None)]
            components.extend(("transfer_walk_seconds", i) for i in range(len(template["transfer_walk_seconds"])))
            for component, transfer_index in components:
                for delta in POLICY["walking_sensitivity_seconds"]:
                    routes = deepcopy(POLICY["routes"])
                    target = next(r for r in routes if r["id"] == route_id)
                    if transfer_index is None:
                        target[component] += delta
                    else:
                        target[component][transfer_index] += delta
                    anchor_time = case["anchor"]["decision_at"]
                    before = predict(snapshots_by_time[anchor_time], anchor_time, index, routes=routes)
                    known = [r for r in before["routes"] if r.get("timing_eligible")]
                    winner = min(known, key=lambda r: (r["total_duration_seconds"], r["id"])) if known else None
                    after = predict(snapshots_by_time[cutoff], cutoff, index, estimator, "incident_profile", routes)
                    decision = decide(after, case["reference_route_id"], switch_margin_seconds=300, require_severe=False)
                    complete = len(known) == len(routes) and all(r.get("comparison_eligible") for r in known)
                    case["walking_sensitivity"].append({"route_id": route_id, "component": component, "transfer_index": transfer_index, "delta_seconds": delta,
                        "anchor_complete": complete,
                        "anchor_winner": winner["id"] if winner else None,
                        "same_baseline_winner": complete and winner is not None and winner["id"] == case["reference_route_id"],
                        "strict_decision": decision["strict_decision"], "conditional_timing_decision": decision["conditional_timing_decision"]})
        if (position + 1) % 20 == 0:
            print(json.dumps({"stage": "INPUT_SENSITIVITY", "completed": position + 1, "candidates": len(candidates)}), flush=True)
    if code_provenance() != provenance:
        raise ValueError("Code changed during input preparation.")
    prepared = {"provenance": provenance, "input_sources": sources, "plans_and_anchors": anchors,
                "selection_rejection_counts": dict(failures), "cases": candidates,
                "no_outcome_labels_opened": True}
    output = LOCAL / "prepared-inputs.json.gz"
    dump(output, prepared)
    review_rows = []
    for case in candidates:
        current = next(r for r in case["asof_mta_prediction"]["routes"] if r["id"] == case["reference_route_id"])
        notices = [a for leg in current["selected_legs"] for a in leg["incident_context"]["alerts"]
                   if a["incident_id"] in case["incident_ids"]]
        review_rows.append({"case_id": case["id"], "incident_ids": case["incident_ids"], "decision_at": case["decision_at"],
            "local_time": case["local_time"], "reference_route_id": case["reference_route_id"],
            "anchor_time": case["anchor"]["local_time"], "anchor_winner_lead_seconds": case["anchor"]["winner_lead_seconds"],
            "duration_deterioration_seconds": case["duration_deterioration_seconds"],
            "selected_legs": [{k: leg.get(k) for k in ("route_id", "platform_direction", "from_stop_id", "to_stop_id", "segment_stop_ids")} for leg in current["selected_legs"]],
            "notices": notices, "status": "PENDING"})
    proposal = {"policy": POLICY, "input_artifact": artifact(output), "candidate_count": len(candidates),
                "candidate_incidents": len({i for c in candidates for i in c["incident_ids"]}),
                "anchor_counts": dict(Counter(a["anchor"]["status"] for a in anchors)),
                "selection_rejection_counts": dict(failures), "cases": review_rows}
    dump(report_path("-candidate-selection.json"), proposal)
    print(json.dumps({"stage": "INPUT_ONLY_PREPARED", "cases": len(candidates), "incidents": proposal["candidate_incidents"], "anchors": proposal["anchor_counts"]}), flush=True)


def freeze():
    prepared_path = LOCAL / "prepared-inputs.json.gz"
    prepared = load(prepared_path)
    if code_provenance() != prepared["provenance"]:
        raise ValueError("Prepared prediction code differs.")
    for name, expected in prepared["input_sources"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Prepared input changed: " + name)
    review_path = report_path("-text-review.json")
    review = load(review_path)
    if review["input_artifact"] != artifact(prepared_path):
        raise ValueError("Text review input differs.")
    selected = {row["case_id"]: row for row in review["cases"]}
    if (len(selected) != len(review["cases"]) or len(selected) != len(prepared["cases"])
            or set(selected) != {c["id"] for c in prepared["cases"]}):
        raise ValueError("Text review is incomplete.")
    label_manifest = load(ROOT / "data/manifests/preincident-inputs.json")
    value = {"schema_version": "preincident-freeze-v1", "study_status": "POST_HOC_TEST_CASE_SEARCH",
             "selection_uses_outcomes": False, "prepared_inputs": artifact(prepared_path),
             "text_review": artifact(review_path), "provenance": prepared["provenance"],
             "supplemental_label_manifest": artifact(ROOT / "data/manifests/preincident-inputs.json"),
             "confirmed_case_ids": sorted(key for key, row in selected.items() if row["status"] == "CONFIRMED"),
             "excluded_case_ids": sorted(key for key, row in selected.items() if row["status"] != "CONFIRMED")}
    target = report_path("-selection-frozen.json")
    if target.exists() and load(target) != value:
        raise ValueError("Existing freeze differs; do not overwrite it.")
    dump(target, value)
    print(json.dumps({"stage": "FROZEN", "confirmed": len(value["confirmed_case_ids"]), "excluded": len(value["excluded_case_ids"])}), flush=True)


def minutes(value):
    return "unknown" if value is None else "{:.1f}".format(value / 60)


def score():
    frozen = load(report_path("-selection-frozen.json"))
    if code_provenance() != frozen["provenance"]:
        raise ValueError("Frozen prediction code differs.")
    for key in ("prepared_inputs", "text_review", "supplemental_label_manifest"):
        item = frozen[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Frozen artifact changed: " + key)
    prepared = load(ROOT / frozen["prepared_inputs"]["path"])
    review = {row["case_id"]: row for row in load(ROOT / frozen["text_review"]["path"])["cases"]}
    cases = [c for c in prepared["cases"] if c["id"] in frozen["confirmed_case_ids"]]
    labels = {}
    source = load(ROOT / "data/manifests/october.json")
    label_sources = {}
    days = sorted({local_time(c["decision_at"])[:10] for c in cases})
    for day in days:
        for label_day in ((date.fromisoformat(day) - timedelta(days=1)).isoformat(), day):
            item = source["daily_labels"][label_day]
            if item["path"] in label_sources:
                continue
            path = ROOT / item["path"]
            if sha(path) != item["sha256"]:
                raise ValueError("Original label source changed.")
            label_sources[item["path"]] = item["sha256"]
            for identity, endpoints in read_labels(path).items():
                if identity in labels and labels[identity] != endpoints:
                    raise ValueError("Conflicting original labels.")
                labels[identity] = endpoints
    supplemental_path = ROOT / "data/processed/preincident-inputs/d16-labels.json.gz"
    # The supplemental manifest is frozen above; its recorded output hash is checked
    # recursively without assuming a particular manifest nesting convention.
    supplemental_manifest = load(ROOT / frozen["supplemental_label_manifest"]["path"])
    def entries(value):
        if isinstance(value, dict):
            if value.get("path") == str(supplemental_path.relative_to(ROOT)) and "sha256" in value:
                yield value["sha256"]
            for child in value.values():
                yield from entries(child)
        elif isinstance(value, list):
            for child in value:
                yield from entries(child)
    hashes = set(entries(supplemental_manifest))
    if hashes != {sha(supplemental_path)}:
        raise ValueError("Supplemental label hash is unverified.")
    label_sources[str(supplemental_path.relative_to(ROOT))] = sha(supplemental_path)
    for identity, endpoints in read_labels(supplemental_path).items():
        for stop, endpoint in endpoints.items():
            if stop != "D16S":
                raise ValueError("Unexpected supplemental endpoint.")
            current = labels.setdefault(identity, {})
            if stop in current:
                raise ValueError("Supplemental labels cannot overwrite an original endpoint.")
            current[stop] = endpoint
    evaluated = []
    config = load(ROOT / "data/config/october.json")
    for case in cases:
        case["official_text_review"] = review[case["id"]]
        result = score_modes(case, case["predictions"], labels, POLICY)
        result.update(local_context(case["decision_at"], config))
        result["reference"] = next(r for r in case["asof_mta_prediction"]["routes"] if r["id"] == case["reference_route_id"])
        result["reference_service_context"] = reference_service_context(result["reference"])
        evaluated.append(result)
    details = LOCAL / "scored-cases.json.gz"
    dump(details, evaluated)
    summary = summarize(evaluated)
    def correct_policy(value):
        if isinstance(value, dict):
            if "reference_service_context" in value:
                value["reference_service_context"]["policy"] = POLICY["reference_policy"]
            for child in value.values():
                correct_policy(child)
        elif isinstance(value, list):
            for child in value:
                correct_policy(child)
    correct_policy(summary)
    summary["unique_checkpoints"] = len({c["decision_at"] for c in evaluated})
    summary["predicted_alternative_counterfactual"] = {}
    for mode in MODES:
        values = [c["modes"][mode] for c in evaluated]
        alternatives = [v["alternative_counterfactual"] for v in values]
        gains = [a["inferred_savings_seconds"] for a in alternatives if a["outcomes_comparable"]]
        summary["predicted_alternative_counterfactual"][mode] = {
            "cases": len(values), "comparable": len(gains), "unknown": len(values) - len(gains),
            "meaningful_gains": sum(g > 180 for g in gains), "practical_ties": sum(abs(g) <= 180 for g in gains),
            "meaningful_losses": sum(g < -180 for g in gains),
            "meaningful_predicted_alternative_missed_by_strict_stay": sum(
                v["strict_decision"]["action"] == "STAY" and v["alternative_counterfactual"]["inferred_savings_seconds"] is not None
                and v["alternative_counterfactual"]["inferred_savings_seconds"] > 180 for v in values),
            "definition": "Compare the forecast-best alternative with fixed Stay even when the decision is STAY; no outcome-based alternative selection.",
        }
    firsts = {}
    observables = {}
    for case in sorted(evaluated, key=lambda c: (c["decision_at"], c["id"])):
        identity = case["incident_ids"][0]
        firsts.setdefault(identity, case["id"])
        value = case["modes"]["incident_profile"]
        if value["alternative_counterfactual"]["outcomes_comparable"]:
            observables.setdefault(identity, case["id"])
    report = {"stage": "COMPLETE_POST_HOC_TEST", "policy": POLICY, "summary": summary,
              "selection_freeze": artifact(report_path("-selection-frozen.json")),
              "source_label_sha256": label_sources, "detail_artifact": artifact(details),
              "first_input_selected_example_ids": list(firsts.values()),
              "outcome_selected_illustration_ids": list(observables.values()),
              "examples": [c for c in evaluated if c["id"] in set(firsts.values()) | set(observables.values())]}
    dump(report_path("-test.json"), report)
    lines = ["# Pre-incident fastest-route delay replay", "",
        "This is an exploratory, post-hoc search within October 25–31. The original predictor and development profiles are unchanged. The new Stay route is selected before the first problem, using only then-available feeds. It is fastest among the supplied alternatives, not a historical Google route or an exhaustive citywide optimum.", "",
        "Origin: {}. Destination: {}. Both comparisons start anew from the same origin; the person has not boarded. The interval between planning and reassessment is not added to the new journey duration.".format(POLICY["origin"], POLICY["destination"]), "",
        "Authored walking per candidate (seconds): `{}`. These are research assumptions, including station access; all one-component +/-120-second sensitivities are retained, including whether the original fastest route remains fastest.".format(json.dumps({r["id"]: {k:r[k] for k in ("access_walk_seconds", "egress_walk_seconds", "transfer_walk_seconds")} for r in POLICY["routes"]}, sort_keys=True)), "",
        "An anchor must precede the earlier of the first incident receipt and its initially declared active start, and its fastest route must have fresh NORMAL evidence. All supplied alternatives need complete timing and verified service evidence. Fixed lookbacks are 1/5/10/15/30 minutes. A baseline lead of three minutes or less is flagged as a near tie.", "",
        "At reassessment the same route must carry an applicable official delay notice and its remaining MTA duration must increase by at least five minutes. Waiting and riding changes are separate. This does not prove causation: headways and train selection also change. Ordinary disruption is sufficient in this request, so the existing comparator uses require_severe=False; its five-minute Switch margin and three-minute outcome tie remain unchanged. A maintenance-related delay whose planning status is unspecified is not asserted to be unplanned.", "",
        "Confirmed cases: **{}**; distinct incident families: **{}**.".format(summary["case_count"], summary["incident_count"]), "",
        "| Mode | Scope | Switch | Scorable | Unknown | Gains >3 min | Ties | Losses >3 min |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        for scope in ("strict_decision", "conditional_timing_decision"):
            row = summary["modes"][mode][scope]
            classes = row["outcome_classes"]
            lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(mode, scope, row["switches"], row["switches_with_comparable_outcomes"], row["switches_without_comparable_outcomes"], classes.get("MEANINGFUL_GAIN", 0), classes.get("PRACTICAL_TIE", 0), classes.get("MEANINGFUL_LOSS", 0)))
    lines += ["", "Forecast-best alternative compared with Stay regardless of the issued decision:", "",
              "| Mode | Comparable | Gain >3 min | Tie | Loss >3 min | Unknown | Gain missed by strict STAY |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for mode, row in summary["predicted_alternative_counterfactual"].items():
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(mode, row["comparable"], row["meaningful_gains"], row["practical_ties"], row["meaningful_losses"], row["unknown"], row["meaningful_predicted_alternative_missed_by_strict_stay"]))
    lines += ["", "Cases within an incident are correlated. Unknowns and missed selected trains are not successes. Scored arrival times are screened final MTA prediction proxies plus authored walks, not independently observed passenger arrivals.", "", "## Case illustrations", "",
        "The report retains the first input-qualified case per incident, plus the earliest comparable incident-profile Stay versus forecast-best alternative per incident, regardless of action or winner. The latter are explicitly outcome-selected illustrations and do not define the evaluation population.", ""]
    for case in report["examples"]:
        anchor = case["anchor"]
        lines += ["### " + case["local_time"] + " — " + case["reference_route_id"], "",
            "Selection: {}. Incident: {}.".format("INPUT_FIRST" if case["id"] in firsts.values() else "OUTCOME_SELECTED_ILLUSTRATION", case["incident_ids"][0]), "",
            "Pre-problem anchor: {}. Problem boundary: {}. First problem receipt: {}. Winner lead: {} min; near tie: {}. Planning interval: {} min.".format(anchor["local_time"], local_time(case["problem_anchor_boundary"]), local_time(case["first_problem_receipt"]), minutes(anchor["winner_lead_seconds"]), anchor["baseline_near_tie"], minutes(case["planning_interval_seconds"])), "",
            "| Route | Before-problem MTA min | Delay-time MTA min |", "|---|---:|---:|"]
        for before in anchor["prediction"]["routes"]:
            after = next(r for r in case["asof_mta_prediction"]["routes"] if r["id"] == before["id"])
            lines.append("| {} | {} | {} |".format(before["id"], minutes(before["total_duration_seconds"]), minutes(after["total_duration_seconds"])))
        lines += ["", "Stay duration deterioration: {} min; component changes (seconds): `{}`.".format(minutes(case["duration_deterioration_seconds"]), json.dumps(case["component_deterioration_seconds"], sort_keys=True)), "",
            "| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |", "|---|---|---|---|---|---|---:|"]
        for mode in MODES:
            value = case["modes"][mode]
            decision = value["strict_decision"]
            counterfactual = value["alternative_counterfactual"]
            chosen_id = counterfactual["predicted_alternative_route_id"]
            current = next(r for r in value["routes"] if r["id"] == case["reference_route_id"])
            chosen = next((r for r in value["routes"] if r["id"] == chosen_id), {})
            a = value["outcomes"].get(case["reference_route_id"], {})
            b = value["outcomes"].get(chosen_id, {})
            lines.append("| {} | {} | {} | {} | {} / {} | {} / {} | {} |".format(mode, decision["action"], decision.get("recommended_itinerary_id") or "none", chosen_id or "none", minutes(current.get("total_duration_seconds")), minutes(chosen.get("total_duration_seconds")), minutes(a.get("total_duration_seconds")), minutes(b.get("total_duration_seconds")), minutes(counterfactual["inferred_savings_seconds"])))
        sensitivity = case["walking_sensitivity"]
        lines += ["", "Walking stress tests: original winner remains fastest in {}/{} variations; formal incident-profile Switch occurs in {}/{}.".format(sum(r["same_baseline_winner"] for r in sensitivity), len(sensitivity), sum(r["strict_decision"]["action"] == "SWITCH" for r in sensitivity), len(sensitivity)), ""]
    lines += ["## Coverage and limitations", "",
        "The case table compares Stay with the forecast-best alternative even when the algorithm says STAY. This is a counterfactual diagnostic, not a recommendation to switch. JSON separately records the best alternative known from later outcomes and missed-opportunity counts; hindsight never selects a recommendation or the evaluation cohort.", "",
        "Input selection rejections and every pre-problem anchor attempt are preserved in the prepared artifact and candidate-selection report. Official route/direction qualification is separate from the original classifier; planned work, opposite directions and narrow notices beyond the traversed segment are excluded.", "",
        "New segments outside the frozen training groups explicitly fall back; existing component segments retain development-only profiles. Supplemental endpoint outcomes, when needed, use unchanged original quality rules. No new regressor is trained.", "",
        "Full cases: `{}` (SHA256 `{}`).".format(report["detail_artifact"]["path"], report["detail_artifact"]["sha256"]), ""]
    report_path("-test.md").write_text("\n".join(lines))
    print(json.dumps({"stage": report["stage"], "cases": len(evaluated), "incidents": summary["incident_count"], "modes": {mode: summary["modes"][mode]["strict_decision"] for mode in MODES}}), flush=True)


def main():
    global POLICY, LOCAL, PREFIX
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--od", choices=("courtsq-times-square", "grandcentral-borough-hall"), default="courtsq-times-square")
    parser.add_argument("--prepare-inputs", action="store_true")
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if args.od == "grandcentral-borough-hall":
        POLICY, PREFIX = BROOKLYN_POLICY, "preincident-brooklyn"
        LOCAL = ROOT / "algo/local/october-preincident-brooklyn"
    if args.prepare_inputs:
        prepare()
    elif args.freeze_only:
        freeze()
    else:
        score()


if __name__ == "__main__":
    main()
