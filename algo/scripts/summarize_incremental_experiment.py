#!/usr/bin/env python3
"""Combine the disjoint three- and two-corridor exploratory result cohorts."""

from collections import Counter
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "algo/reports"
SOURCES = ("incremental-switch-test.json", "extra-corridor-switch-test.json")
CLASSES = ("MEANINGFUL_GAIN", "PRACTICAL_TIE", "MEANINGFUL_LOSS", "UNKNOWN")


def distribution(values):
    counts = Counter(values)
    assert set(counts) <= set(CLASSES)
    return {"cases": sum(counts.values()),
            "comparable": sum(counts.values()) - counts["UNKNOWN"],
            "classes": {key: counts[key] for key in CLASSES}}


def summarize(rows):
    comparisons = [row["policy_comparison"] for row in rows]
    switches = [row for row in rows
                if row["modes"]["incident_profile"]["strict_decision"]["action"] == "SWITCH"]
    missed = []
    for row in switches:
        mode = row["modes"]["incident_profile"]
        chosen_id = mode["strict_decision"]["recommended_itinerary_id"]
        chosen = next(route for route in mode["selected_routes"] if route["id"] == chosen_id)
        if chosen["outcome"]["status"] == "MISSED_SELECTED_TRAIN":
            missed.append(row["id"])
    return {
        "checkpoints": len(rows),
        "corridor_incident_pairs": len({(row["corridor_id"], tuple(row["incident_ids"])) for row in rows}),
        "unique_incident_ids": len({item for row in rows for item in row["incident_ids"]}),
        "action_pairs": dict(sorted(Counter(value["raw_mta_action"] + "->" + value["model_action"]
                                             for value in comparisons).items())),
        "qualified_impact_counts": dict(Counter(row["official_text_review"]["confirmed_impact"] for row in rows)),
        "model_switch_vs_own_stay": distribution(
            row["modes"]["incident_profile"]["scores"]["classification"] for row in switches),
        "model_switch_known_missed_journey_ids": missed,
        "mta_stay_model_switch": distribution(value["classification"] for value in comparisons
                                               if value["mta_stay_model_switch"]),
        "all_concrete_policy_pairs": distribution(value["classification"] for value in comparisons
                                                  if value["eligible_actions"]),
    }


def selected_route(row, mode):
    value = row["modes"][mode]
    chosen = value["strict_decision"]["recommended_itinerary_id"]
    return next(route for route in value["selected_routes"] if route["id"] == chosen)


def main():
    rows, corridors, sources = [], [], []
    for name in SOURCES:
        path = REPORTS / name
        payload = path.read_bytes()
        report = json.loads(payload)
        sources.append({"path": str(path.relative_to(ROOT)),
                        "sha256": hashlib.sha256(payload).hexdigest()})
        rows.extend(report["cases"])
        corridors.extend(report["corridors"])
    assert len(corridors) == len({row["id"] for row in corridors}) == 5
    assert len(rows) == len({row["id"] for row in rows})
    assert {row["corridor_id"] for row in rows} <= {row["id"] for row in corridors}
    rows.sort(key=lambda row: (row["decision_at"], row["corridor_id"], row["id"]))
    discrepancies = []
    for row in rows:
        comparison = row["policy_comparison"]
        if comparison["comparable"]:
            before = comparison["raw_mta_selected_outcome"]["total_duration_seconds"]
            after = comparison["model_selected_outcome"]["total_duration_seconds"]
            gain = before - after
            assert abs(gain - comparison["gain_seconds"]) < 1e-6
            expected = "MEANINGFUL_GAIN" if gain > 180 else "MEANINGFUL_LOSS" if gain < -180 else "PRACTICAL_TIE"
            assert expected == comparison["classification"]
        if comparison["mta_stay_model_switch"]:
            discrepancies.append({key: row[key] for key in
                ("id", "corridor_id", "incident_ids", "local_time", "primary", "official_text_review", "exposure")} | {
                    "raw_mta_stay": selected_route(row, "mta"),
                    "model_switch": selected_route(row, "incident_profile"),
                    "raw_mta_decision": row["modes"]["mta"]["strict_decision"],
                    "model_decision": row["modes"]["incident_profile"]["strict_decision"],
                    "comparison": comparison})
    positives = [row for row in discrepancies if row["comparison"]["classification"] == "MEANINGFUL_GAIN"]
    incident_train_pairs = {(row["corridor_id"], tuple(row["incident_ids"]),
                             tuple(row["raw_mta_stay"]["selected_train_ids"]),
                             tuple(row["model_switch"]["selected_train_ids"])) for row in positives}
    train_pairs = {(row["corridor_id"], tuple(row["raw_mta_stay"]["selected_train_ids"]),
                    tuple(row["model_switch"]["selected_train_ids"])) for row in positives}
    result = {
        "schema_version": "five-corridor-incremental-summary-v1",
        "sources": sources,
        "scope": "Disjoint baseline cohorts only; earlier 322-case study and walking variants are not added again.",
        "interpretation": "Frozen fixed-selected-train proxy results. Read the findings and independent audits for quality and adaptive-Stay qualifications.",
        "corridors": [{key: row[key] for key in ("id", "origin", "destination", "reference_route_id")} for row in corridors],
        "all_checkpoints": summarize(rows),
        "primary_representatives": summarize([row for row in rows if row["primary"]]),
        "per_corridor": {corridor["id"]: summarize([row for row in rows if row["corridor_id"] == corridor["id"]]) for corridor in corridors},
        "positive_disagreement_corridor_incidents": len({(row["corridor_id"], tuple(row["incident_ids"])) for row in positives}),
        "positive_disagreement_unique_incident_ids": len({item for row in positives for item in row["incident_ids"]}),
        "positive_disagreement_distinct_incident_train_pairs": len(incident_train_pairs),
        "positive_disagreement_distinct_train_pairs": len(train_pairs),
        "all_disagreement_cases": discrepancies,
    }
    output = REPORTS / "five-corridor-incremental-summary.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"report": str(output.relative_to(ROOT)), "all_checkpoints": result["all_checkpoints"],
                      "positive_disagreement_distinct_train_pairs": len(train_pairs)}, indent=2))


if __name__ == "__main__":
    main()
