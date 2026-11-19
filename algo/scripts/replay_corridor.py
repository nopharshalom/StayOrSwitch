#!/usr/bin/env python3
"""Replay fixed supplied corridor paths using unchanged frozen component models."""

import argparse
import gzip
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "algo"))

from stayorswitch.corridor_replay import MODES, evaluate_case, summarize_cases, walking_sensitivity
from stayorswitch.model_training.artifacts import sha256, verify_frozen, write_json
from stayorswitch.model_training.models import ComponentPredictor


MODE_NAMES = {"mta": "Unmodified MTA", "segment_model": "Passed segment model only",
              "departure_segment_research": "Departure + segment (research only)"}


class CachedPredictor:
    """Memoize deterministic frozen inference; the key includes all model input."""

    def __init__(self, predictor):
        self.predictor = predictor
        self.cache = {}

    def predict_case(self, case):
        key = json.dumps(case, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if key not in self.cache:
            self.cache[key] = self.predictor.predict_case(case)
        return dict(self.cache[key])


def read_bundle(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        return json.load(handle)


def report_base(path):
    return path.with_suffix("").with_suffix("") if path.suffix == ".gz" else path.with_suffix("")


def write_report(path, report):
    if path.suffix != ".gz":
        write_json(path, report)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with temporary.open("wb") as handle, gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as compressed:
        compressed.write(payload)
    with gzip.open(temporary, "rb") as handle:
        if handle.read() != payload:
            raise ValueError("Compressed report failed its round-trip verification.")
    temporary.replace(path)


def minutes(value):
    return "unknown" if value is None else f"{value / 60:.1f}"


def local_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).strftime("%m-%d %a %H:%M:%S")


def coverage(route):
    train = route.get("selected_train")
    if train is None:
        return "unavailable"
    details = train["corrections"]
    departure = details["departure_model"]
    applied = departure is not None and departure["method"] == "EXPERIMENTAL_COMPONENT_MODEL"
    return f"segments {details['applied_segment_count']} applied / {details['fallback_segment_count']} fallback; departure {'applied' if applied else 'unchanged'}"


def markdown(report):
    config, summary = report["configuration"], report["summary"]
    segment, research = (summary["modes"][mode] for mode in ("segment_model", "departure_segment_research"))
    lines = ["# Historical corridor replay", "",
        f"The replay screened {summary['candidate_case_count']} discovered cutoffs and found {summary['qualifying_reference_delay_cases']} "
        f"qualifying delayed moments involving {summary['qualifying_distinct_baseline_train_count']} distinct baseline trains. "
        f"These correlated moments are not independent incidents. {len(report['detailed_case_ids'])} "
        "distinct baseline-train examples, spaced at least one hour apart, were selected chronologically before model scoring. "
        f"The passed segment model's conditional timing actions were {segment['conditional_timing_actions']}; "
        f"its conditional Switch outcomes were {segment['conditional_switches_with_positive_inferred_savings']} faster, "
        f"{segment['conditional_switches_with_nonpositive_inferred_savings']} not faster, and "
        f"{segment['conditional_switches_without_comparable_outcomes']} unknown. "
        f"Departure-plus-segment research actions were {research['conditional_timing_actions']}.", "",
        "This is an exploratory diagnostic on already-inspected November 12–15, 2026 data. "
        "It does not retrain or activate any model, and it is not an unbiased success-rate estimate or a new untouched test.", "",
        "The Stay route is the fastest **uncorrected MTA** estimate at the same decision time among the two supplied paths. "
        "Every mode then selects its train using only that cutoff's available predictions. The MTA mode therefore stays by construction when both paths are assessable.", "",
        "Outcomes are quality-screened final-prediction proxies, not observed passenger journeys or verified physical train arrivals. "
        "Outcome scoring follows exactly the train chosen by each forecast and verifies its inferred departure against platform readiness; a missed train is unknown, with no hindsight replacement.", "",
        "## Supplied paths and walking assumptions", "",
        "| Path | Access to platform | Exit to destination |", "|---|---:|---:|"]
    for route in config["routes"]:
        lines.append(f"| {route['name']} | {minutes(route['access_walk_seconds'])} min | {minutes(route['egress_walk_seconds'])} min |")
    lines += ["", config["candidate_scope"], "", config["walking_policy"], "",
        "## Case selection and result counts", "",
        f"The source pool contains {summary['candidate_case_count']} moments selected without checking model Switch success. "
        f"{summary['qualifying_reference_delay_cases']} have a baseline-fastest train whose inferred outcome is at least "
        f"{minutes(summary['minimum_reference_delay_seconds'])} minutes later than its as-of prediction. "
        "Missing or uncatchable baseline outcomes cannot qualify. All pool cases remain in the JSON artifact.", "",
        "| Mode | Strict actions | Conditional timing actions | Switch outcome: faster / not faster / unknown |",
        "|---|---|---|---|"]
    for mode in MODES:
        row = summary["modes"][mode]
        lines.append(f"| {MODE_NAMES[mode]} | {row['strict_actions']} | {row['conditional_timing_actions']} | "
                     f"{row['conditional_switches_with_positive_inferred_savings']} / "
                     f"{row['conditional_switches_with_nonpositive_inferred_savings']} / "
                     f"{row['conditional_switches_without_comparable_outcomes']} |")
    lines += ["", "Strict eligibility retains the existing fresh-alert requirement. Archived alerts are content-deduplicated; "
        "an old capture does not establish fresh receipt. A conditional timing Switch assumes no unobserved service constraints "
        "and is not a recommendation the current app is entitled to emit. Fresh known NO_SERVICE conflicts are still rejected.", "",
        f"The research mode's strict-eligible Switches break down into {research['strict_switches_with_positive_inferred_savings']} "
        f"faster, {research['strict_switches_with_nonpositive_inferred_savings']} not faster, and "
        f"{research['strict_switches_without_comparable_outcomes']} unknown outcomes. "
        "Do not combine the number of strict Switches with the conditional-only positive outcomes as a success rate.", "",
        "The segment model passed its component gate provisionally. Departure failed that gate, so the departure-plus-segment "
        "column is research only. Arrival residuals are never added to these routes. Supported disjoint trained segments are "
        "corrected at the original cutoff; unsupported or beyond-30-minute segments retain MTA timing, and intermediate dwells are retained once.", "",
        f"Missed timing opportunities among assessable same-selected-train outcomes: the passed segment model stayed despite a faster "
        f"inferred alternative in {segment['conditional_stays_with_faster_inferred_alternative']} qualifying moments; "
        f"the research mode did so in {research['conditional_stays_with_faster_inferred_alternative']}.", "",
        "| Day type | Discovered cutoffs | Qualifying moments | Segment timing actions | Research timing actions |",
        "|---|---:|---:|---|---|"]
    for day, row in summary["by_day_type"].items():
        lines.append(f"| {day} | {row['candidate_case_count']} | {row['qualifying_reference_delay_cases']} | "
                     f"{row['modes']['segment_model']['conditional_timing_actions']} | {row['modes']['departure_segment_research']['conditional_timing_actions']} |")
    detailed_day_types = sorted({case["day_type"] for case in report["cases"] if case["case_id"] in report["detailed_case_ids"]})
    lines += ["", f"The chronological detailed examples cover {', '.join(detailed_day_types)} only; "
        "they do not establish weekend behavior. The day-type counts above retain the full discovered pool.", "",
        "## All qualifying moments", "",
        "| New York time | Original route | Original ETA duration | Inferred original duration | Original error | Segment action | Research action | Continuity review |",
        "|---|---|---:|---:|---:|---|---|---|"]
    threshold = summary["minimum_reference_delay_seconds"]
    for case in report["cases"]:
        if case["reference_delay_seconds"] is None or case["reference_delay_seconds"] < threshold:
            continue
        lines.append(f"| {local_time(case['decision_at'])} | {case['reference']['name']} | "
            f"{minutes(case['reference']['total_duration_seconds'])} | {minutes(case['reference_outcome']['total_duration_seconds'])} | "
            f"{minutes(case['reference_delay_seconds'])} | {case['modes']['segment_model']['conditional_timing_decision']['action']} | "
            f"{case['modes']['departure_segment_research']['conditional_timing_decision']['action']} | "
            f"{'required' if case.get('reference_continuity_review_required') or case.get('discovery_metadata', {}).get('requires_outlier_review') else 'not flagged'} |")
    lines += ["", "All durations below are door-to-door minutes. Positive Switch outcome savings means the alternative's "
        "forecast-selected train arrived earlier than the same mode's selected train on the Stay route. Strategy gain compares "
        "the recommendation against the original uncorrected MTA train instead; these are separate quantities.", "",
        "## Detailed cases", "", "Detailed cases are the earliest qualifying distinct source-pool moments in chronological order, "
        "up to the declared limit. They are not chosen for a favorable recommendation."]
    for case in report["cases"]:
        if case["case_id"] not in report["detailed_case_ids"]:
            continue
        lines += ["", f"### {case['case_id']} — {local_time(case['decision_at'])}", "",
            f"Original route: **{case['reference']['name']}**. As-of duration {minutes(case['reference']['total_duration_seconds'])} min; "
            f"inferred duration {minutes(case['reference_outcome']['total_duration_seconds'])} min; "
            f"forecast error +{minutes(case['reference_delay_seconds'])} min.", "",
            "| Mode and path | Predicted duration | Inferred selected-train duration | Model coverage |",
            "|---|---:|---:|---|"]
        if case.get("reference_continuity_review_required") or case.get("discovery_metadata", {}).get("requires_outlier_review"):
            lines[-2:-2] = ["This discovery event has an unresolved long-trip continuity warning. "
                "Screened endpoint labels do not independently establish that the entire unusual delay is physical; interpret its proxy savings conditionally.", ""]
        for mode in MODES:
            value = case["modes"][mode]
            for route in value["routes"]:
                outcome = value["outcomes"][route["id"]]
                observed = minutes(outcome.get("total_duration_seconds")) if outcome["status"] == "INFERRED" else outcome["status"]
                lines.append(f"| {MODE_NAMES[mode]}: {route['name']} | {minutes(route['total_duration_seconds'])} | {observed} | {coverage(route)} |")
        lines += ["", "| Mode | Strict decision | Conditional timing decision | Predicted Switch savings | Inferred Switch savings | Strategy gain vs original MTA train |",
                  "|---|---|---|---:|---:|---:|"]
        for mode in MODES:
            value = case["modes"][mode]
            conditional = value["conditional_timing_decision"]
            lines.append(f"| {MODE_NAMES[mode]} | {value['strict_decision']['action']} | {conditional['action']} | "
                f"{minutes(conditional['estimated_savings_seconds'])} | {minutes(value['inferred_switch_savings_seconds'])} | "
                f"{minutes(value['inferred_savings_vs_original_reference_seconds'])} |")
        sensitivity = case.get("walking_sensitivity")
        if sensitivity:
            lines += ["", f"Walking sensitivity: {sensitivity['scenario_count']} independent access/egress scenarios, "
                      "each varied by −2, 0, or +2 minutes. Trains and the original route are reselected in each scenario. "
                      f"Reference counts: {sensitivity['reference_route_counts']}. "
                      f"Segment actions: {sensitivity['mode_action_counts']['segment_model']}; "
                      f"research actions: {sensitivity['mode_action_counts']['departure_segment_research']}."]
    lines += ["", "## Reproduction and limits", "",
        f"Frozen experiment seal: `{report['model_provenance']['frozen_seal']}`. Dependencies were verified before and after replay; "
        "the seal is unchanged. No arrival/departure adoption decision has changed.", "",
        "The JSON artifact contains every supplied path, chosen service-qualified train identity, model application/fallback, "
        "forecast/outcome timing, alert freshness, rejected candidates, unknown outcomes, and walking-sensitivity scenario. "
        "Only the supplied direct F and G paths are compared; transfers, other lines, street disruptions, entrance access, "
        "physical walking observations, and routes absent from the as-of train horizon are outside this diagnostic.", "",
        f"Source bundle: `{report['inputs']['bundle_path']}`. Configuration: `{report['inputs']['config_path']}`.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "data/config/corridor-replay.json")
    parser.add_argument("--frozen", type=Path, default=ROOT / "algo/models/pilot-v1/frozen.json")
    parser.add_argument("--output", type=Path, default=ROOT / "algo/reports/corridor-replay.json.gz")
    parser.add_argument("--detailed-cases", type=int, default=6)
    parser.add_argument("--skip-sensitivity", action="store_true")
    args = parser.parse_args()
    if args.detailed_cases < 0:
        parser.error("Detailed case count must be nonnegative.")
    config = json.loads(args.config.read_text())
    bundle = read_bundle(args.bundle)
    input_hashes = {str(args.bundle): sha256(args.bundle), str(args.config): sha256(args.config),
                    str(ROOT / "algo/docs/corridor-replay.md"): sha256(ROOT / "algo/docs/corridor-replay.md")}
    data_manifest_path = ROOT / "data/manifests/corridor-replay.json"
    if data_manifest_path.exists():
        data_manifest = json.loads(data_manifest_path.read_text())
        if (ROOT / data_manifest["bundle"]["path"]).resolve() == args.bundle.resolve():
            if data_manifest["bundle"]["sha256"] != input_hashes[str(args.bundle)]:
                raise ValueError("Replay bundle differs from the prepared data manifest.")
            input_hashes[str(data_manifest_path)] = sha256(data_manifest_path)
    frozen = verify_frozen(args.frozen)
    replay_sources = ["algo/scripts/replay_corridor.py", "algo/stayorswitch/corridor_replay.py"]
    source_hashes = {path: sha256(ROOT / path) for path in replay_sources}
    anchors = json.loads((ROOT / "data/config/pilot-history.json").read_text())["stop_ids"]
    ordered = sorted(bundle["cases"], key=lambda item: item["decision_at"])
    discovery = bundle.get("case_selection", {}).get("by_case", {})
    screened = [evaluate_case(case, config["routes"], bundle["labels"], anchor_ids=anchors, modes=("mta",)) for case in ordered]
    threshold = config["delay_case_rule"]["minimum_reference_proxy_error_seconds"]
    qualifying = [case for case in screened if case["reference_delay_seconds"] is not None
                  and case["reference_delay_seconds"] >= threshold]
    detailed_ids, used_trains, last_cutoff = [], set(), None
    for case in qualifying:
        identity = case["reference"]["selected_train"]["trip_id"]
        cutoff = datetime.fromisoformat(case["decision_at"].replace("Z", "+00:00")).timestamp()
        if identity in used_trains or (last_cutoff is not None and cutoff - last_cutoff < 3600):
            continue
        if len(detailed_ids) >= args.detailed_cases:
            break
        detailed_ids.append(case["case_id"])
        used_trains.add(identity)
        last_cutoff = cutoff
    base = report_base(args.output)
    selection_path = base.with_name(base.name + "-case-selection.json")
    write_json(selection_path, {"phase": "BASELINE_ONLY_BEFORE_FROZEN_MODEL_SCORING",
        "selection_uses_model_predictions": False, "minimum_reference_delay_seconds": threshold,
        "detailed_case_policy": "CHRONOLOGICAL_DISTINCT_BASELINE_TRAINS_AT_LEAST_60_MINUTES_APART",
        "detailed_case_limit": args.detailed_cases, "detailed_case_ids": detailed_ids,
        "bundle_sha256": sha256(args.bundle), "configuration_sha256": sha256(args.config),
        "qualifying_case_ids": [case["case_id"] for case in qualifying],
        "screening": [{"case_id": case["case_id"], "decision_at": case["decision_at"],
                       "reference_route_id": case["reference_route_id"],
                       "reference_trip_id": case["reference"]["selected_train"]["trip_id"] if case["reference"] else None,
                       "reference_outcome": case["reference_outcome"],
                       "requires_outlier_review": discovery.get(case["case_id"], {}).get("requires_outlier_review", False),
                       "reference_continuity_review_required": case["reference_continuity_review_required"],
                       "reference_delay_seconds": case["reference_delay_seconds"]} for case in screened]})
    print(f"Saved baseline-only selection: {len(qualifying)} qualifying moments; {len(detailed_ids)} detailed episodes.", flush=True)
    predictors = {target: CachedPredictor(ComponentPredictor(args.frozen, target)) for target in ("departure", "segment")}
    cases = []
    for index, case in enumerate(ordered, 1):
        result = evaluate_case(case, config["routes"], bundle["labels"], predictors=predictors, anchor_ids=anchors)
        result["discovery_metadata"] = discovery.get(case["id"], {})
        cases.append(result)
        print(f"Predicted and scored historical case {index}/{len(bundle['cases'])}.", flush=True)
    detailed = [case for case in cases if case["case_id"] in detailed_ids]
    source_cases = {case["id"]: case for case in bundle["cases"]}
    if not args.skip_sensitivity:
        for index, result in enumerate(detailed, 1):
            result["walking_sensitivity"] = walking_sensitivity(source_cases[result["case_id"]], config["routes"], bundle["labels"],
                predictors=predictors, anchor_ids=anchors, deltas=config["walking_sensitivity_seconds"])
            print(f"Checked walking sensitivity {index}/{len(detailed)}.", flush=True)
    verified_after = verify_frozen(args.frozen)
    if verified_after != frozen:
        raise ValueError("Frozen experiment changed during replay.")
    if source_hashes != {path: sha256(ROOT / path) for path in replay_sources}:
        raise ValueError("Replay code changed during evaluation.")
    if input_hashes != {path: sha256(path) for path in input_hashes}:
        raise ValueError("Replay inputs changed during evaluation.")
    report = {"schema_version": "corridor-replay-report-v1", "configuration": config,
              "code_sha256": source_hashes,
              "input_sha256": input_hashes,
              "source_case_selection": bundle.get("case_selection"),
              "inputs": {"bundle_path": str(args.bundle), "bundle_sha256": sha256(args.bundle),
                         "config_path": str(args.config), "config_sha256": sha256(args.config),
                         "protocol_path": "algo/docs/corridor-replay.md", "protocol_sha256": sha256(ROOT / "algo/docs/corridor-replay.md"),
                         "case_selection_path": str(selection_path), "case_selection_sha256": sha256(selection_path)},
              "model_provenance": {"frozen_seal": frozen["sha256"], "dependencies_verified_before_and_after": True,
                                   "live_model_activation": False, "retraining": False},
              "summary": summarize_cases(cases, minimum_delay_seconds=threshold),
              "detailed_case_ids": [case["case_id"] for case in detailed], "cases": cases}
    write_report(args.output, report)
    base.with_suffix(".md").write_text(markdown(report))
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved {args.output} and {base.with_suffix('.md')}.")


if __name__ == "__main__":
    main()
