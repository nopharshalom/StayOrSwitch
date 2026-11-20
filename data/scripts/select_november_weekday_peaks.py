#!/usr/bin/env python3
"""Freeze the user-requested weekday view before opening November outcomes."""

from collections import Counter
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.delay_profiles.common import file_sha256, read_json, write_json


POLICY = ROOT / "data/manifests/november-weekday-reporting.json"
BASE_FREEZE = ROOT / "data/manifests/november-peak-inputs-frozen.json"
OUTPUT = ROOT / "data/manifests/november-weekday-peak-selection.json"


def artifact(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path)}


def select():
    if OUTPUT.exists():
        raise ValueError("The pre-outcome weekday selection already exists; preserve it.")
    policy = read_json(POLICY)
    dates = policy["analysis_dates"]
    if len(dates) != 13 or any(date.fromisoformat(day).weekday() >= 5 for day in dates):
        raise ValueError("The approved view requires exactly thirteen local weekdays.")
    freeze = read_json(BASE_FREEZE)
    item = freeze["prepared_inputs"]
    prepared_path = ROOT / item["path"]
    if artifact(prepared_path) != item:
        raise ValueError("The original frozen peak inputs changed.")
    prepared = read_json(prepared_path)
    rows = [row for row in prepared["rows"] if row["date"] in dates]
    if len(rows) != policy["peak_scheduled_checkpoints"] or any("outcome" in row for row in rows):
        raise ValueError("Weekday membership must contain 2,860 input-only predictions.")
    counts = Counter((row["corridor_id"], row["date"]) for row in rows)
    if len(counts) != 65 or set(counts.values()) != {44}:
        raise ValueError("Every corridor/weekday must retain all 44 scheduled checkpoints.")
    result = {"schema_version": "november-weekday-peak-selection-v1",
              "stage": "FROZEN_BEFORE_OUTCOME_SCORING",
              "user_reporting_policy": artifact(POLICY), "base_input_freeze": artifact(BASE_FREEZE),
              "prepared_inputs": item, "producer": artifact(Path(__file__)),
              "dates": dates, "selected_case_ids": [row["id"] for row in rows],
              "selected_checkpoint_count": len(rows),
              "inherited_event_representative_count": sum(row["event_representative"] for row in rows),
              "selection_uses_outcomes": False, "prediction_values_changed": False,
              "calendar_filter_only": True, "excluded_weekend_checkpoint_count": len(prepared["rows"]) - len(rows)}
    write_json(OUTPUT, result)
    print({"stage": result["stage"], "selected_checkpoints": len(rows),
           "manifest": str(OUTPUT.relative_to(ROOT)), "sha256": file_sha256(OUTPUT)})


if __name__ == "__main__":
    select()
