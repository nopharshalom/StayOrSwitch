#!/usr/bin/env python3
"""Replay prespecified October incidents with frozen train-only ETA profiles."""

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import gzip
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.delay_profiles.estimator import ProfileEstimator
from data.delay_profiles.incidents import IncidentIndex
from data.october.sources import dates_between, read_labels, read_snapshots, sha256, write_json
from stayorswitch.october_evaluation import (
    MODES, decision_margin_case, evaluate_case, latest_at_cutoffs, project_snapshot, select_incident_checkpoints,
    selection_digest, sensitivity_selection, summarize, summary_case, walking_variations,
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def verify_artifact(item):
    path = ROOT / item["path"]
    if not path.is_file() or sha256(path) != item["sha256"]:
        raise ValueError("Prepared artifact differs from its manifest: " + str(path))
    return path


def verify_frozen_profile(config_path, manifest_path):
    frozen = json.loads(manifest_path.read_text())
    if not frozen.get("complete_month_inputs"):
        raise ValueError("Full October input coverage is required for evaluation.")
    if frozen["config_sha256"] != sha256(config_path):
        raise ValueError("Configuration differs from the train-profile freeze.")
    for path, expected in frozen["code_sha256"].items():
        if sha256(ROOT / path) != expected:
            raise ValueError("Profile code differs from its pre-outcome freeze: " + path)
    profile_path = verify_artifact(frozen["train_profile"])
    estimator = ProfileEstimator(profile_path)
    if estimator.fit_split != "train" or not estimator.profile.get("complete_month_inputs"):
        raise ValueError("Replay requires complete train-only profiles, never month-descriptive profiles.")
    if estimator.seal != frozen["profile_seal"]:
        raise ValueError("Profile content seal differs from the freeze manifest.")
    if estimator.profile.get("protocol_freeze_sha256") != frozen.get("protocol_freeze_sha256"):
        raise ValueError("Profile protocol seal differs from the freeze manifest.")
    if estimator.profile.get("source_hashes") != frozen.get("source_sha256"):
        raise ValueError("Profile source provenance differs from its freeze manifest.")
    for path, expected in frozen["source_sha256"].items():
        if sha256(ROOT / path) != expected:
            raise ValueError("Frozen training or input-inventory source changed: " + path)
    return estimator


def source_artifacts(manifest):
    result = {}
    for day in manifest["days"]:
        for item in day["outputs"].values():
            result[item["path"]] = item["sha256"]
        metadata = (ROOT / day["outputs"]["snapshots"]["path"]).parent / (day["date"] + ".source.json")
        result[str(metadata.relative_to(ROOT))] = sha256(metadata)
    for item in manifest["daily_labels"].values():
        result[item["path"]] = item["sha256"]
    return result


def protocol_fingerprint(config_path):
    paths = []
    for directory in ("algo/stayorswitch", "data/delay_profiles", "data/october"):
        paths.extend((ROOT / directory).glob("*.py"))
    paths.extend(ROOT / path for path in ("algo/scripts/evaluate_october.py", "data/scripts/build_delay_profiles.py",
                                         "data/scripts/prepare_october.py", "data/scripts/rebuild_october_labels.py"))
    return {"schema_version": "october-protocol-freeze-v1", "config_sha256": sha256(config_path),
            "code_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in sorted(paths)}}


def evaluation_fingerprint(config_path, source_path, profile_path, source, selection):
    protocol = protocol_fingerprint(config_path)
    return {"schema_version": "october-evaluation-freeze-v1",
            "config_sha256": protocol["config_sha256"], "source_manifest_sha256": sha256(source_path),
            "profile_frozen_manifest_sha256": sha256(profile_path),
            "code_sha256": protocol["code_sha256"],
            "input_sha256": source_artifacts(source), "selection_sha256": selection_digest(selection),
            "selection_uses_outcomes": False,
            "final_test_policy": "REQUIRE_EXISTING_UNCHANGED_FREEZE_AND_EXPLICIT_FINAL_TEST_FLAG"}


def verify_evaluation_freeze(path, fingerprint, *, create=False):
    if path.is_file():
        frozen = json.loads(path.read_text())
        if frozen != fingerprint:
            raise ValueError("Evaluation inputs, code, profiles, or selection changed after freezing.")
    elif create:
        write_json(path, fingerprint)
    else:
        raise ValueError("Create and review the evaluation freeze before outcome scoring.")


def markdown(report):
    summary = report["summary"]
    exposure = summary["reference_service_context"]
    categories = exposure["checkpoints_by_category"]
    lines = ["# October severe-incident replay", "", "Stage: **" + report["stage"] + "**.", "",
             "This report uses " + str(summary["case_count"]) + " predeclared checkpoints from " +
             str(summary["incident_count"]) + " incident families. Checkpoints within an incident are correlated.", "",
             "The Stay reference is the fastest unmodified MTA candidate at the same cutoff, across all 11 variants and 7 families. "
             "Each correction mode selects its own trains for that fixed route. Switch gain compares that mode's Stay and Switch trains; "
             "strategy gain against the original MTA train is a separate measure.", "",
             "The selected MTA Stay reference had definite applicable severe context at " +
             str(categories.get("DEFINITE_APPLICABLE_SEVERE", 0)) + " checkpoints (" +
             str(exposure["definite_severe_comparison_eligible_checkpoints"]) + " with fully verified comparison evidence), " +
             "fresh normal context at " + str(categories.get("UNAFFECTED_FRESH_NORMAL", 0)) +
             ", other known non-severe context at " + str(categories.get("OTHER_KNOWN_NON_SEVERE", 0)) +
             ", unknown or ambiguous context at " + str(categories.get("UNKNOWN_OR_AMBIGUOUS", 0)) +
             ", and was unavailable at " + str(categories.get("REFERENCE_UNAVAILABLE", 0)) + ". "
             "The same-cutoff fastest MTA route may already avoid the incident; total selected incident checkpoints are therefore not all severe-affected Stay opportunities.", "",
             "| Mode | Evidence scope | Switches | Scorable | Unknown | Gains >3 min | Ties | Losses >3 min | Incident-weighted gain rate |", 
             "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        for scope in ("strict_decision", "conditional_timing_decision"):
            row = summary["modes"][mode][scope]
            classes = row["outcome_classes"]
            rate = row["incident_weighted_meaningful_switch_gain_rate"]
            lines.append("| " + " | ".join(str(value) for value in (
                mode, scope, row["switches"], row["switches_with_comparable_outcomes"],
                row["switches_without_comparable_outcomes"], classes.get("MEANINGFUL_GAIN", 0),
                classes.get("PRACTICAL_TIE", 0), classes.get("MEANINGFUL_LOSS", 0),
                "N/A" if rate is None else "{:.1%} ({} incidents)".format(rate, row["incidents_with_comparable_switch_outcomes"]))) + " |")
    lines.extend(["", "Strict advice requires fresh train and alert evidence with applicable severe context. "
                  "Conditional timing results are diagnostics when strict evidence is unavailable, never formal advice success.", "",
                  "| Route family | Candidate observations | Timing available | Timing unavailable | Outcome inferred | Outcome missing | Missed selected train |",
                  "|---|---:|---:|---:|---:|---:|---:|"])
    for family, values in summary["route_families"].items():
        lines.append("| " + " | ".join(str(value) for value in (family,
            values.get("candidate_variant_observations", 0), values.get("timing_estimated", 0),
            values.get("timing_unavailable", 0), values.get("outcome_INFERRED", 0),
            values.get("outcome_UNAVAILABLE", 0), values.get("outcome_MISSED_SELECTED_TRAIN", 0))) + " |")
    lines.extend(["", "Unknown outcomes remain in coverage counts. A missed selected train or transfer is unknown; "
                  "the evaluator never substitutes a later train using hindsight. Outcomes are screened final MTA prediction proxies, "
                  "not independently observed physical arrivals.", "",
                  "Walking durations are authored research assumptions. Sensitivity uses the first checkpoint of the first three "
                  "chronological incident families per split, regardless of outcomes, changing one candidate's one walking component "
                  "by +/-120 seconds and recomputing all train choices and the MTA reference.", "",
                  "Sensitivity checkpoints evaluated: " + str(report["sensitivity"]["checkpoint_count"]) +
                  "; variations: " + str(report["sensitivity"]["variation_count"]) + ".", "",
                  "Per-period, weekday/Saturday/Sunday, split, incident, missed-opportunity, and candidate-outcome counts are in "
                  "the JSON summary. Full selected-train evidence and every sensitivity variation are in deterministic compressed JSONL.", "",
                  "Full local case artifact: `" + report["detail_artifact"]["path"] + "` (SHA256 `" + report["detail_artifact"]["sha256"] + "`).", "",
                  "No general severe-service success claim is warranted where incident or outcome coverage is insufficient."])
    return "\n".join(lines) + "\n"


def run(args):
    started = time.monotonic()
    config = json.loads(args.config.read_text())
    source_path = ROOT / "data/manifests/october.json"
    source = json.loads(source_path.read_text())
    if source.get("stage") != "PREPARED" or not source.get("full_month_processed"):
        raise ValueError("Full October source preparation must finish before formal replay.")
    if source["config"]["sha256"] != sha256(args.config):
        raise ValueError("Source configuration differs from evaluation configuration.")
    for path, expected in source["code_sha256"].items():
        if sha256(ROOT / path) != expected:
            raise ValueError("Source preparation code changed after normalization: " + path)
    if args.split == "test" and not args.allow_final_test and not args.freeze_only and not args.select_only:
        raise ValueError("Final-test scoring requires an explicit approved --allow-final-test run.")
    days = {item["date"]: item for item in source["days"]}
    def alert_observations():
        for day in sorted(days):
            yield from read_snapshots(verify_artifact(days[day]["outputs"]["alerts"]))
    incident_index = IncidentIndex(alert_observations(), max_age_seconds=config["alerts_max_age_seconds"])
    selection = select_incident_checkpoints(incident_index, config)
    selection["walking_sensitivity"] = sensitivity_selection(selection["cases"], config)
    selection_path = args.output / "october-selection.json"
    args.output.mkdir(parents=True, exist_ok=True)
    # The freeze run creates this shared artifact. Parallel validation/test
    # readers verify and reuse it rather than racing on the same temporary file.
    verify_evaluation_freeze(selection_path, selection, create=True)
    counts = Counter(case["split"] for case in selection["cases"])
    print(json.dumps({"stage": "INPUT_ONLY_CASES_SELECTED", "checkpoints_by_split": dict(counts),
                      "incident_candidates": selection["incident_candidates"],
                      "purged_incidents": len(selection["purged_cross_split_incident_ids"]),
                      "elapsed_seconds": round(time.monotonic() - started, 1)}), flush=True)
    if args.select_only:
        return
    profile_path = ROOT / "data/manifests/profiles-frozen.json"
    protocol_path = args.output / "october-protocol-frozen.json"
    verify_evaluation_freeze(protocol_path, protocol_fingerprint(args.config))
    frozen_profile = json.loads(profile_path.read_text())
    if frozen_profile.get("protocol_freeze_sha256") != sha256(protocol_path):
        raise ValueError("Train profile did not seal the approved all-code protocol before outcome access.")
    current_sources = source_artifacts(source)
    if any(current_sources.get(path) != expected for path, expected in frozen_profile["source_sha256"].items()):
        raise ValueError("Train profile sources differ from the prepared replay source manifest.")
    estimator = verify_frozen_profile(args.config, profile_path)
    fingerprint = evaluation_fingerprint(args.config, source_path, profile_path, source, selection)
    freeze_path = args.output / "october-evaluation-frozen.json"
    verify_evaluation_freeze(freeze_path, fingerprint, create=args.freeze_only)
    if args.freeze_only:
        print(json.dumps({"stage": "EVALUATION_FROZEN", "path": str(freeze_path)}), flush=True)
        return
    selected = [case for case in selection["cases"] if case["split"] == args.split]
    by_date = defaultdict(list)
    for case in selected:
        by_date[case["date"]].append(case)
    sensitivity_ids = {row["case_id"] for row in selection["walking_sensitivity"] if row["split"] == args.split}
    summaries, sensitivity_summaries = [], []
    margin_summaries = {value: [] for value in (120, 180, 300)} if args.split == "validation" else {}
    sensitivity_checkpoints, variations = 0, 0
    args.details_output.mkdir(parents=True, exist_ok=True)
    detail_path = args.details_output / ("october-" + args.split + "-cases.jsonl.gz")
    temporary = detail_path.with_suffix(detail_path.suffix + ".part")
    carry, previous_labels = {}, {}
    first_day, last_day = config["splits"][args.split]
    seed_day = (date.fromisoformat(first_day) - timedelta(days=1)).isoformat()
    with temporary.open("wb") as binary, gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0, compresslevel=6) as stream:
        for day in dates_between(seed_day, last_day):
            cases = by_date.get(day, [])
            records = read_snapshots(verify_artifact(days[day]["outputs"]["snapshots"]))
            snapshots, carry = latest_at_cutoffs((project_snapshot(item, config["routes"]) for item in records),
                                                  [case["decision_at"] for case in cases], carry)
            # A prior-day selected train may remain in the first current-day capture.
            # All labels are opened only after freeze verification above.
            labels = read_labels(verify_artifact(source["daily_labels"][day]))
            combined = dict(previous_labels)
            for identity, outcomes in labels.items():
                if identity in combined and combined[identity] != outcomes:
                    raise ValueError("Conflicting daily outcome labels for " + identity)
                combined[identity] = outcomes
            for position, case in enumerate(cases):
                replay = dict(case, snapshots=snapshots[case["decision_at"]])
                result = evaluate_case(replay, config["routes"], combined, config,
                                       estimator=estimator, incident_index=incident_index)
                stream.write(canonical({"kind": "BASELINE_REPLAY", "case": result}) + b"\n")
                summaries.append(summary_case(result))
                for margin in margin_summaries:
                    rescored = decision_margin_case(result, config, margin)
                    margin_summaries[margin].append(summary_case(rescored))
                    stream.write(canonical({"kind": "VALIDATION_DECISION_MARGIN", "case_id": case["id"],
                        "predicted_switch_margin_seconds": margin,
                        "modes": {mode: {key: value[key] for key in ("strict_decision", "conditional_timing_decision", "scores")}
                                  for mode, value in rescored["modes"].items()}}) + b"\n")
                if case["id"] in sensitivity_ids:
                    sensitivity_checkpoints += 1
                    for variation, templates in walking_variations(config["routes"], config):
                        changed = evaluate_case(replay, templates, combined, config,
                                                estimator=estimator, incident_index=incident_index)
                        stream.write(canonical({"kind": "WALKING_SENSITIVITY", "variation": variation, "case": changed}) + b"\n")
                        sensitivity_summaries.append(summary_case(changed))
                        variations += 1
                if (position + 1) % 50 == 0:
                    print(json.dumps({"stage": "REPLAY_PROGRESS", "date": day, "completed_checkpoints": len(summaries),
                                      "elapsed_seconds": round(time.monotonic() - started, 1)}), flush=True)
            previous_labels = labels
            print(json.dumps({"stage": "REPLAY_DAY", "date": day, "checkpoints": len(cases),
                              "elapsed_seconds": round(time.monotonic() - started, 1)}), flush=True)
    if fingerprint != evaluation_fingerprint(args.config, source_path, profile_path, source, selection):
        raise ValueError("Evaluation code or provenance changed during replay; output remains unfinalized.")
    temporary.replace(detail_path)
    report = {"schema_version": "october-evaluation-report-v1", "stage": "COMPLETE_" + args.split.upper(),
              "split": args.split, "summary": summarize(summaries),
              "validation_decision_margin_sensitivity": {str(margin): summarize(cases) for margin, cases in margin_summaries.items()},
              "primary_predicted_switch_margin_seconds": config["switch_margin_seconds"],
              "outcome_tie_margin_seconds": config["tie_margin_seconds"],
              "sensitivity": {"selection": [row for row in selection["walking_sensitivity"] if row["split"] == args.split],
                              "checkpoint_count": sensitivity_checkpoints, "variation_count": variations,
                              "summary": summarize(sensitivity_summaries)},
              "selection": {key: value for key, value in selection.items() if key != "cases"},
              "provenance": fingerprint,
              "detail_artifact": {"path": str(detail_path.relative_to(ROOT)), "sha256": sha256(detail_path)},
              "elapsed_seconds": round(time.monotonic() - started, 1),
              "limitations": ["Final-prediction proxy outcomes are not verified physical arrivals.",
                  "Content-deduplicated alert captures cannot establish continuously fresh unchanged alerts.",
                  "Authored route and walking assumptions are not historical Google API responses.",
                  "Incident classifier rules have not been independently labeled for accuracy.",
                  "Correlated checkpoints are not independent event successes."]}
    path = args.output / ("october-" + args.split + ".json")
    write_json(path, report)
    path.with_suffix(".md").write_text(markdown(report))
    print(json.dumps({"stage": report["stage"], "checkpoints": len(summaries),
                      "elapsed_seconds": report["elapsed_seconds"], "report": str(path)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "data/config/october.json")
    parser.add_argument("--output", type=Path, default=ROOT / "algo/reports")
    parser.add_argument("--details-output", type=Path, default=ROOT / "algo/local/october",
                        help="Local full-case evidence directory; compact reports retain its path and SHA256.")
    parser.add_argument("--split", choices=("validation", "test"), default="validation")
    parser.add_argument("--select-only", action="store_true", help="Read alert inputs and save case selection without outcomes.")
    parser.add_argument("--freeze-only", action="store_true", help="Seal profiles, code, inputs, and selection without outcome scoring.")
    parser.add_argument("--freeze-protocol-only", action="store_true", help="Seal all implementation code before profile fitting or descriptive outcomes.")
    parser.add_argument("--allow-final-test", action="store_true", help="Use only after explicit final-test freeze review.")
    args = parser.parse_args()
    if args.freeze_protocol_only:
        path = args.output / "october-protocol-frozen.json"
        verify_evaluation_freeze(path, protocol_fingerprint(args.config), create=True)
        print(json.dumps({"stage": "PROTOCOL_FROZEN", "path": str(path)}), flush=True)
    else:
        run(args)


if __name__ == "__main__":
    main()
