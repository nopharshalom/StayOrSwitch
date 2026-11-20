#!/usr/bin/env python3
"""Freeze and score a post-hoc affected-route-as-Stay October supplement."""

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from stayorswitch.affected_replay import SCOPES, apply_text_review, example_view, re_reference, selection_view, select_affected, summarize_affected
from stayorswitch.october_evaluation import MODES


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def records(path):
    with gzip.open(path, "rt") as handle:
        for line in handle:
            yield json.loads(line)


def provenance():
    original = json.loads((ROOT / "algo/reports/october-evaluation-frozen.json").read_text())
    for relative, expected in original["code_sha256"].items():
        if sha(ROOT / relative) != expected:
            raise ValueError("Frozen implementation changed: " + relative)
    if sha(ROOT / "data/config/october.json") != original["config_sha256"]:
        raise ValueError("Frozen configuration changed.")
    inputs = {}
    for split in ("validation", "test"):
        report_path = ROOT / ("algo/reports/october-" + split + ".json")
        report = json.loads(report_path.read_text())
        artifact = report["detail_artifact"]
        if sha(ROOT / artifact["path"]) != artifact["sha256"]:
            raise ValueError("Archived case artifact changed: " + split)
        inputs[split] = {"path": artifact["path"], "sha256": artifact["sha256"],
                         "report_path": str(report_path.relative_to(ROOT)), "report_sha256": sha(report_path)}
    bundle = ROOT / "data/artifacts/october-2026-profiles-train.json.gz"
    profile = json.loads(gzip.decompress(bundle.read_bytes()))
    metadata = json.loads((ROOT / "data/artifacts/october-2026-profiles-train.manifest.json").read_text())
    if sha(bundle) != metadata["sha256"] or profile["seal"] != metadata["profile_seal"] or profile["fit_split"] != "train":
        raise ValueError("Frozen training bundle no longer matches.")
    return {"inputs": inputs, "original_evaluation_freeze_sha256": sha(ROOT / "algo/reports/october-evaluation-frozen.json"),
            "config_sha256": original["config_sha256"], "original_code_sha256": original["code_sha256"],
            "supplement_code_sha256": {name: sha(ROOT / name) for name in (
                "algo/stayorswitch/affected_replay.py", "algo/scripts/evaluate_affected_stay.py")},
            "training_profile_sha256": sha(bundle), "training_profile_seal": profile["seal"]}


def build_freeze():
    sources = provenance()
    review_path = ROOT / "algo/reports/october-affected-stay-text-review.json"
    review = json.loads(review_path.read_text())
    for path, expected in review["source_artifact_sha256"].items():
        if sha(ROOT / path) != expected:
            raise ValueError("Official text audit source differs.")
    sources["official_text_review"] = {"path": str(review_path.relative_to(ROOT)), "sha256": sha(review_path)}
    selections = {}
    for split, source in sources["inputs"].items():
        broad = select_affected(selection_view(record) for record in records(ROOT / source["path"]))
        selections[split] = apply_text_review(broad, review["pairs"], split)
    return {"schema_version": "affected-stay-freeze-v1", "study_status": "POST_HOC_SUPPLEMENTAL_REFERENCE_DESIGN",
            "original_results_already_observed": True, "prediction_or_training_changes": False,
            "selection_uses_outcomes": False, "switch_margin_seconds": 300, "tie_margin_seconds": 180,
            "provenance": sources, "selections": selections,
            "limits": ["Restricted to the previously declared incident checkpoints, not an exhaustive search of every October minute.",
                       "Definite applicable official severe exposure does not establish a measured individual passenger delay.",
                       "Unavailable selected journeys cannot establish cached exact-segment exposure; reported separately.",
                       "Repeated checkpoints and multiple routes in one incident are correlated."]}


def minutes(value):
    return "unknown" if value is None else "{:.1f}".format(value / 60)


def markdown(report):
    summary = report["summary"]
    lines = ["# Affected-route-as-Stay replay: " + report["split"], "",
        "This is a **post-hoc supplemental case study**, requested after the original results. It changes the Stay reference only; the algorithm, selected trains, historical profiles, thresholds and outcomes remain unchanged. It does not replace the original fastest-MTA benchmark or establish general performance.", "",
        "Selection uses contemporaneous official severe exposure, never outcomes or recommended savings. A separate input-only text audit verifies that severe wording applies to the selected leg's actual line and direction. Every confirmed route at every original primary checkpoint is retained, including stale alert evidence that must withhold formal advice. All 11 candidate variants remain in each comparison.", "",
        "Selected: **{} affected route/checkpoint pairs**, **{} unique checkpoints**, **{} affecting incident families**.".format(summary["case_count"], summary["unique_primary_checkpoints"], summary["incident_count"]), "",
        "The frozen classifier initially supplied {} candidate pairs; {} were excluded from the confirmed cohort because severe wording concerned another line or direction. The broader classifier summary remains in JSON. This input-only case qualification does not fix or change the frozen predictor.".format(report["classifier_summary"]["case_count"], report["excluded_classifier_pairs"]), "",
        "| Mode | Scope | Switches | Scorable | Unknown | Gain >3 min | Tie | Loss >3 min |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        for scope in SCOPES:
            row = summary["modes"][mode][scope]
            cls = row["outcome_classes"]
            lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(mode, scope, row["switches"], row["switches_with_comparable_outcomes"], row["switches_without_comparable_outcomes"], cls.get("MEANINGFUL_GAIN", 0), cls.get("PRACTICAL_TIE", 0), cls.get("MEANINGFUL_LOSS", 0)))
    lines += ["", "A Switch requires at least five minutes of predicted savings. Outcome differences within +/-three minutes are ties. Strict and conditional results overlap; they must not be added. Counts are route/checkpoint pairs, not independent passengers or incidents.", "",
        "Outcome evidence follows exactly the originally forecast-selected trains. Missing or unusable endpoint labels and missed selected departures/transfers leave the complete journey ETA unknown; a later train is never substituted using hindsight. A missed departure is a known catchability failure, not absence of all evidence. Outcomes are screened final MTA prediction proxies with authored walking assumptions, not independently observed journeys.", "",
        "## Why some Switches cannot be scored", ""]
    for scope in SCOPES:
        row = summary["unknown_switch_reasons"]["incident_profile"][scope]
        lines += ["`incident_profile / {}`: {} unknown Switch pairs.".format(scope, row["unknown_switch_count"]), ""]
        for reason, count in sorted(row["side_reason_counts"].items()):
            lines.append("- `{}`: {}".format(reason, count))
        lines += ["", "Known catchability failures (complete journey ETA still unknown):", ""]
        for reason, count in sorted(row["known_catchability_failures"].items()):
            lines.append("- `{}`: {}".format(reason, count))
        lines += ["", "Endpoint quality flags (overlapping):", ""]
        for reason, count in sorted(row["endpoint_flag_counts"].items()):
            lines.append("- `{}`: {}".format(reason, count))
        lines.append("")
    lines += ["## Input-selected examples", "", "Examples are the earliest chronological route per affecting incident and route family; route ID breaks ties. Selection does not require an outcome or a successful Switch. Every selected pair remains in the full results.", ""]
    for case in report["examples"]:
        lines += ["### {} — Stay `{}`".format(case["local_time"], case["reference_route_id"]), "",
                  "Incident(s): {}. Alert evidence: **{}**.".format(", ".join(case["incident_ids"]), case["reference_service_context"]["evidence_status"]), ""]
        for alert in case["affecting_alerts"]:
            lines.append("Official as-of notice: " + " ".join(((alert.get("header") or "") + " " + (alert.get("description") or "")).split()))
            lines.append("")
        lines += ["| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |",
                  "|---|---|---|---:|---:|---:|---:|---|"]
        for mode in MODES:
            value = case["modes"][mode]
            strict = value["strict_decision"]["decision"]
            timing = value["conditional_timing_decision"]
            decision = timing["decision"]
            lines.append("| {} | {} / {} | {} / {} | {} | {} | {} | {} | {} |".format(mode, strict["action"], strict.get("recommended_itinerary_id") or "none", decision["action"], decision.get("recommended_itinerary_id") or "none", minutes(value["stay_predicted_seconds"]), minutes(timing["recommended_predicted_seconds"]), minutes(decision.get("estimated_savings_seconds")), minutes(timing["score"]["inferred_switch_savings_seconds"]), timing["score"]["classification"]))
        lines.append("")
    lines += ["## Scope and artifacts", "", report["selection_scope_limit"], "",
              "Severe-specific training support is unchanged and sparse; an incident-profile result may use time-profile fallback. The MTA mode shows how much switching is already supported by current feeds without historical correction. Different line names do not prove independent disruption exposure.", "",
              "Full deterministic cases: `{}` (SHA256 `{}`).".format(report["detail_artifact"]["path"], report["detail_artifact"]["sha256"]), "",
              "Selection and code/input hashes were saved before supplemental scoring in `algo/reports/affected-stay-selection-frozen.json`. Original evaluation artifacts are unchanged.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    frozen_path = ROOT / "algo/reports/affected-stay-selection-frozen.json"
    expected = build_freeze()
    if args.freeze_only:
        if frozen_path.exists() and json.loads(frozen_path.read_text()) != expected:
            raise ValueError("Existing supplemental freeze differs; do not overwrite it.")
        write_json(frozen_path, expected)
        print(json.dumps({split: {"pairs": len(value["cases"]), "examples": len(value["example_ids"])} for split, value in expected["selections"].items()}))
        return
    if not frozen_path.exists() or json.loads(frozen_path.read_text()) != expected:
        raise ValueError("Create and review an unchanged supplemental freeze before scoring.")
    config = json.loads((ROOT / "data/config/october.json").read_text())
    if config["switch_margin_seconds"] != 300 or config["tie_margin_seconds"] != 180:
        raise ValueError("Decision thresholds changed.")
    for split, selection in expected["selections"].items():
        source = expected["provenance"]["inputs"][split]
        originals = {record["case"]["id"]: record["case"] for record in records(ROOT / source["path"]) if record["kind"] == "BASELINE_REPLAY"}
        selected_by_id = {row["id"]: row for row in selection["cases"] + selection["excluded_classifier_candidates"]}
        broad_cases = [re_reference(originals[row["checkpoint_id"]], selected_by_id[row["id"]], config) for row in selection["classifier_candidates"]]
        cases = [case for case in broad_cases if case["official_text_review"]["status"] == "CONFIRMED"]
        local_path = ROOT / ("algo/local/october-affected-stay/" + split + "-cases.jsonl.gz")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with local_path.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as handle:
                for case in broad_cases:
                    handle.write((canonical(case) + "\n").encode())
        report = {"schema_version": "affected-stay-report-v1", "stage": "COMPLETE_POST_HOC_SUPPLEMENT", "split": split,
                  "selection_freeze_sha256": sha(frozen_path), "summary": summarize_affected(cases),
                  "classifier_summary": summarize_affected(broad_cases),
                  "excluded_classifier_pairs": len(broad_cases) - len(cases),
                  "selection_scope_limit": selection["scope_limit"],
                  "examples": [example_view(case) for case in cases if case["id"] in selection["example_ids"]],
                  "detail_artifact": {"path": str(local_path.relative_to(ROOT)), "sha256": sha(local_path)}}
        if build_freeze() != expected:
            raise ValueError("Inputs, code or selection changed during supplemental scoring.")
        target = ROOT / ("algo/reports/affected-stay-" + split)
        write_json(target.with_suffix(".json"), report)
        target.with_suffix(".md").write_text(markdown(report))
        print(json.dumps({"split": split, "pairs": len(cases), "modes": {mode: report["summary"]["modes"][mode]["strict_decision"] for mode in MODES}}, sort_keys=True))


if __name__ == "__main__":
    main()
