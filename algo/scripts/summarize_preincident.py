#!/usr/bin/env python3
"""Describe predeclared clear-default and near-tie groups after frozen scoring."""

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from stayorswitch.october_evaluation import summarize
from stayorswitch.preincident_replay import local_time
from stayorswitch.severe import MODES


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def minutes(value):
    return "unknown" if value is None else "{:.2f}".format(value / 60)


def summary(cases):
    result = summarize(cases, grouped=False)
    result["reference_service_context"]["policy"] = "PRE_PROBLEM_FASTEST_FIXED_ROUTE"
    result["counterfactual"] = {}
    for mode in MODES:
        rows = [case["modes"][mode] for case in cases]
        values = [r["alternative_counterfactual"]["inferred_savings_seconds"] for r in rows]
        known = [v for v in values if v is not None]
        missing = Counter()
        for case, row in zip(cases, rows):
            cf = row["alternative_counterfactual"]
            if cf["outcomes_comparable"]:
                continue
            for side, outcome in (("stay", row["outcomes"][case["reference_route_id"]]),
                                  ("alternative", cf["alternative_outcome"])):
                if outcome.get("status") != "INFERRED":
                    missing[side + ":" + outcome.get("reason", "NO_ALTERNATIVE")] += 1
        result["counterfactual"][mode] = {
            "comparable": len(known), "unknown": len(values) - len(known),
            "meaningful_gains": sum(v > 180 for v in known),
            "practical_ties": sum(abs(v) <= 180 for v in known),
            "meaningful_losses": sum(v < -180 for v in known),
            "unknown_reasons_overlapping": dict(missing),
            "strict_stay_missed_meaningful_gain": sum(r["strict_decision"]["action"] == "STAY" and
                r["alternative_counterfactual"]["inferred_savings_seconds"] is not None and
                r["alternative_counterfactual"]["inferred_savings_seconds"] > 180 for r in rows),
        }
    return result


def detail(case):
    output = {key: case[key] for key in ("id", "local_time", "decision_at", "incident_ids", "reference_route_id",
                                       "problem_anchor_boundary", "first_problem_receipt", "planning_interval_seconds",
                                       "duration_deterioration_seconds", "component_deterioration_seconds")}
    output["anchor"] = case["anchor"]
    output["modes"] = {}
    for mode in MODES:
        value = case["modes"][mode]
        cf = value["alternative_counterfactual"]
        ids = [case["reference_route_id"], cf["predicted_alternative_route_id"]]
        output["modes"][mode] = {"decision": value["strict_decision"], "counterfactual": cf,
            "routes": [r for r in value["routes"] if r["id"] in ids],
            "outcomes": {key: value["outcomes"].get(key) for key in ids}}
    output["walking_sensitivity"] = case["walking_sensitivity"]
    output["official_text_review"] = case["official_text_review"]
    return output


def main():
    source = ROOT / "algo/local/october-preincident-brooklyn/scored-cases.json.gz"
    report_path = ROOT / "algo/reports/preincident-brooklyn-test.json"
    report = json.loads(report_path.read_text())
    headway_audit_path = ROOT / "algo/reports/preincident-brooklyn-headway-audit.json"
    if digest(source) != report["detail_artifact"]["sha256"]:
        raise ValueError("Frozen scored artifact differs.")
    cases = json.loads(gzip.decompress(source.read_bytes()))
    groups = {"clear_default": [c for c in cases if not c["anchor"]["baseline_near_tie"]],
              "near_tie": [c for c in cases if c["anchor"]["baseline_near_tie"]]}
    chosen = {}
    for case in sorted(groups["clear_default"], key=lambda c: (c["decision_at"], c["id"])):
        if case["modes"]["incident_profile"]["alternative_counterfactual"]["outcomes_comparable"]:
            chosen.setdefault(case["incident_ids"][0], case)
    duplicates = Counter()
    for case in groups["clear_default"]:
        value = case["modes"]["incident_profile"]
        cf = value["alternative_counterfactual"]
        if cf["inferred_savings_seconds"] is not None and cf["inferred_savings_seconds"] > 180:
            route_ids = [case["reference_route_id"], cf["predicted_alternative_route_id"]]
            signature = tuple(tuple(leg["trip_id"] for leg in next(r for r in value["routes"] if r["id"] == identity)["selected_legs"])
                              for identity in route_ids)
            duplicates[signature] += 1
    artifact = {"path": str(source.relative_to(ROOT)), "sha256": digest(source)}
    result = {"schema_version": "preincident-clear-default-description-v1",
              "source_artifact": artifact, "source_report_sha256": digest(report_path),
              "headway_audit": {"path": str(headway_audit_path.relative_to(ROOT)), "sha256": digest(headway_audit_path)},
              "producer_sha256": digest(Path(__file__)),
              "grouping_rule": "Use the baseline_near_tie flag declared before outcomes: winner lead <=180s is near tie.",
              "no_cohort_or_prediction_changes": True,
              "illustration_selection": "Earliest comparable incident-profile Stay versus forecast-best alternative per clear-default incident, without filtering gains, losses or decisions. These are outcome-selected illustrations.",
              "groups": {name: summary(rows) for name, rows in groups.items()},
              "clear_default_meaningful_gain_train_pair_multiplicity": [
                  {"stay_train_ids": list(key[0]), "alternative_train_ids": list(key[1]), "checkpoint_count": value}
                  for key, value in sorted(duplicates.items())],
              "illustrations": [detail(case) for case in chosen.values()]}
    target = ROOT / "algo/reports/preincident-brooklyn-clear-default"
    target.with_suffix(".json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    lines = ["# Clear-default route before delay: observed comparison", "",
        "This is a descriptive appendix to the frozen exploratory test, not a new cohort or a retuned algorithm. The predeclared baseline near-tie boundary is three minutes. All 31 cases remain in the original report; this appendix separates the 24 clearly fastest Lexington-route cases from seven F cases whose initial lead was only 17 seconds.", "",
        "The October 26 positive comparison below is a later-departure counterfactual, not proof that the original fastest train became delayed. A separate raw-input audit shows that the originally selected 4 train `017800_4..S13X061` became uncatchable as planning time advanced under the three-minute access assumption. The later selected train `019800_4..S13X061` was already present at T0, and both its departure and arrival forecasts improved by 53 seconds by T1. The apparent 11.84-minute route deterioration mixes a missed earlier train and headway; a separate same-physical-train revision experiment is needed for the stronger delay claim. Evidence: `algo/reports/preincident-brooklyn-headway-audit.json`.", "",
        "Origin: Grand Central at East 42nd Street / Lexington Avenue. Destination: Borough Hall at Court Street / Joralemon Street. Supplied candidates are direct 4-or-5; 7 then 2-or-3; walk to Times Square then 2-or-3; and walk to Bryant Park, F to Jay Street, then walk. Same-platform 4/5 choices are one route, not a manufactured Switch opportunity.", "",
        "Walking times are authored research assumptions: direct 4/5 has three minutes of access and two minutes of egress; the F option has ten minutes of access and eight minutes of egress. Catchability, including whether the earlier direct train can still be boarded, depends on these assumptions.", "",
        "The state is unboarded at each cutoff. Reassessment starts a new journey from the same origin; elapsed planning time is not added to either route. These are ordinary official delay notices, not all severe events. Outcome durations use screened final MTA predictions plus authored walking, not independent passenger observations.", "",
        "## Decision results by predeclared baseline group", "",
        "| Group | Cases | Incidents | Mode | Strict Switch | Scorable Switch | Gains | Ties | Losses | Unknown Switch |", "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|"]
    for name, group in result["groups"].items():
        for mode in MODES:
            row = group["modes"][mode]["strict_decision"]
            cls = row["outcome_classes"]
            lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(name, group["case_count"], group["incident_count"], mode, row["switches"], row["switches_with_comparable_outcomes"], cls.get("MEANINGFUL_GAIN", 0), cls.get("PRACTICAL_TIE", 0), cls.get("MEANINGFUL_LOSS", 0), row["switches_without_comparable_outcomes"]))
    lines += ["", "## Would the forecast-best alternative actually help?", "",
        "This comparison is made even when the algorithm says STAY. The alternative is selected by its forecast, never by its later outcome. A separate hindsight best-known alternative is retained only as a diagnostic in JSON.", "",
        "| Group | Mode | Comparable | Gains >3 min | Ties | Losses >3 min | Unknown | Meaningful gains missed by strict STAY |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for name, group in result["groups"].items():
        for mode, row in group["counterfactual"].items():
            lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(name, mode, row["comparable"], row["meaningful_gains"], row["practical_ties"], row["meaningful_losses"], row["unknown"], row["strict_stay_missed_meaningful_gain"]))
    lines += ["", "The two clear-default incident-profile gains come from one incident and the same selected 4/F train pair at two checkpoints. They are one repeated opportunity, not two independent successes. The algorithm said STAY at both, so they are missed opportunities rather than validated successful recommendations.", "",
        "## Observable illustrations", "",
        result["illustration_selection"], ""]
    for case in result["illustrations"]:
        anchor = case["anchor"]
        lines += ["### " + case["local_time"], "",
            "Incident {}. Anchor {}. First recorded problem boundary {}; first problem receipt {}. Planning interval {} minutes. Initial winner lead {} minutes.".format(case["incident_ids"][0], anchor["local_time"], local_time(case["problem_anchor_boundary"]), local_time(case["first_problem_receipt"]), minutes(case["planning_interval_seconds"]), minutes(anchor["winner_lead_seconds"])), "",
            "| Route | Before-problem MTA duration, min |", "|---|---:|"]
        for route in anchor["prediction"]["routes"]:
            lines.append("| {} | {} |".format(route["id"], minutes(route["total_duration_seconds"])))
        lines += ["", "Stay's unmodified remaining duration deteriorated by {} minutes. Components (seconds): `{}`.".format(minutes(case["duration_deterioration_seconds"]), json.dumps(case["component_deterioration_seconds"], sort_keys=True)), "",
                  "| Mode | Strict decision | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |", "|---|---|---|---|---|---:|"]
        for mode in MODES:
            value = case["modes"][mode]
            alt_id = value["counterfactual"]["predicted_alternative_route_id"]
            current = next(r for r in value["routes"] if r["id"] == case["reference_route_id"])
            alternative = next(r for r in value["routes"] if r["id"] == alt_id)
            a, b = value["outcomes"][case["reference_route_id"]], value["outcomes"][alt_id]
            lines.append("| {} | {} / {} | {} | {} / {} | {} / {} | {} |".format(mode, value["decision"]["action"], value["decision"].get("recommended_itinerary_id"), alt_id, minutes(current["total_duration_seconds"]), minutes(alternative["total_duration_seconds"]), minutes(a.get("total_duration_seconds")), minutes(b.get("total_duration_seconds")), minutes(value["counterfactual"]["inferred_savings_seconds"])))
        baseline_stay = next(r for r in anchor["prediction"]["routes"] if r["id"] == case["reference_route_id"])
        current_stay = next(r for r in case["modes"]["mta"]["routes"] if r["id"] == case["reference_route_id"])
        baseline_ids = [leg["trip_id"] for leg in baseline_stay["selected_legs"]]
        current_ids = [leg["trip_id"] for leg in current_stay["selected_legs"]]
        if baseline_ids != current_ids:
            lines += ["", "The baseline and reassessment select different MTA trains: `{}` becomes `{}`. The duration increase therefore includes a changed catchable train/headway; it is not the same vehicle becoming that many minutes late, and the contemporaneous official delay does not establish that it caused the full increase.".format("; ".join(baseline_ids), "; ".join(current_ids))]
        value = case["modes"]["incident_profile"]
        notices = {a["id"]: a for route in value["routes"] if route["id"] == case["reference_route_id"]
                   for leg in route["selected_legs"] for a in leg["incident_context"]["alerts"] if a["incident_id"] in case["incident_ids"]}
        for notice in notices.values():
            lines += ["", "Official as-of notice: " + " ".join(((notice.get("header") or "") + " " + (notice.get("description") or "")).split())]
        lines += ["", "Exact incident-profile proxy train evidence:", ""]
        for identity, outcome in value["outcomes"].items():
            for leg in outcome.get("selected_legs", []):
                lines.append("- `{}` / `{}`: platform-ready {}, inferred departure {}, inferred station arrival {}.".format(identity, leg["trip_id"], local_time(leg["platform_ready_at"]), local_time(leg["departure_at"]), local_time(leg["arrival_at"])))
        sensitivity = case["walking_sensitivity"]
        lines += ["", "Original winner remains fastest in {}/{} single-walk perturbations; this tests +/-two minutes of an access, transfer, or egress component. Exact trips and outcome quality remain in the linked JSON.".format(sum(v["same_baseline_winner"] for v in sensitivity), len(sensitivity)), ""]
    lines += ["## Limits", "", "Missing or missed-train outcomes remain unknown. The small correlated sample does not establish a general success rate. These results show one observable later-departure switching opportunity the incident-profile algorithm missed, not proof that the original train became delayed or that this model reliably selects better switches. No model fitting, threshold changes or outcome-driven case replacement occurred.", "",
              "Full frozen cases: `{}` (SHA256 `{}`).".format(artifact["path"], artifact["sha256"]), ""]
    target.with_suffix(".md").write_text("\n".join(lines))
    print(json.dumps({name: {"cases": value["case_count"], "counterfactual": value["counterfactual"]["incident_profile"], "strict": value["modes"]["incident_profile"]["strict_decision"]} for name, value in result["groups"].items()}, sort_keys=True))


if __name__ == "__main__":
    main()
