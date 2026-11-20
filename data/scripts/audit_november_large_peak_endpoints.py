#!/usr/bin/env python3
"""Independently audit the raw journals behind three large weekday peak cells."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path
import statistics
import sys
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]
from data.delay_profiles.common import file_sha256, read_json, write_json
from data.october.sources import iter_csv_rows

CELLS = (("pilot_hayden_tandon", "2026-11-12", "MIDDAY"),
         ("portauthority_tandon", "2026-11-02", "MIDDAY"),
         ("pilot_hayden_tandon", "2026-11-13", "EVENING_PEAK"))
SCORED = ROOT / "data/processed/november-peak-analysis/scored-weekday-checkpoints.json.gz"
SOURCE = ROOT / "data/manifests/november-2026.json"
REPORT = ROOT / "data/reports/november-weekday-large-peak-raw-audit.json"


def main():
    checks = Counter()
    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        checks[name] += 1
    source = read_json(SOURCE)
    days = {row["date"]: row for row in source["days"]}
    rows = [row for row in read_json(SCORED)["rows"]
            if (row["corridor_id"], row["date"], row["period"]) in CELLS and row["outcome"]["status"] == "INFERRED"]
    check(len(rows) == 22, "expected_22_usable_journeys")
    sources = {str(SCORED.relative_to(ROOT)): file_sha256(SCORED), str(SOURCE.relative_to(ROOT)): file_sha256(SOURCE)}
    cases = []
    for day in sorted({row["date"] for row in rows}):
        day_rows = [row for row in rows if row["date"] == day]
        inputs = {"labels": source["daily_labels"][day], "receipts": days[day]["outputs"]["receipts"]}
        loaded = {}
        for name, item in inputs.items():
            check(file_sha256(ROOT / item["path"]) == item["sha256"], name + "_hash")
            sources[item["path"]] = item["sha256"]
            loaded[name] = read_json(ROOT / item["path"])
        labels, receipts = loaded["labels"], loaded["receipts"]
        wanted = {labels[row["forecast"]["selected_legs"][0]["trip_id"]][row["forecast"]["selected_legs"][0]["from_stop_id"]]["source_trip_uid"] for row in day_rows}
        raw_path = ROOT / ("data/raw/november-2026/subwaydatanyc_" + day + "_csv.tar.xz")
        raw_item = next(item for item in source["archives"] if item["archive_date"] == day and item["kind"] == "csv")
        check(file_sha256(raw_path) == raw_item["sha256"], "raw_csv_archive_hash")
        sources[str(raw_path.relative_to(ROOT))] = raw_item["sha256"]
        trips, stops = defaultdict(list), defaultdict(list)
        for value in iter_csv_rows(raw_path, "trips"):
            if value["trip_uid"] in wanted:
                trips[value["trip_uid"]].append(value)
        for value in iter_csv_rows(raw_path, "stop_times"):
            if value["trip_uid"] in wanted:
                stops[(value["trip_uid"], value["stop_id"])].append(value)
        for row in day_rows:
            forecast, outcome = row["forecast"], row["outcome"]
            check(len(forecast["selected_legs"]) == len(outcome["selected_legs"]) == 1, "single_exact_selected_leg")
            leg, actual = forecast["selected_legs"][0], outcome["selected_legs"][0]
            check(leg["trip_id"] == actual["trip_id"], "selected_train_unchanged")
            check(leg["boarding_time_source"] == "DEPARTURE", "forecast_boarding_uses_departure")
            check(leg["baseline_arrival_at"] == leg["arrival_at"], "zero_arrival_correction")
            check(leg["baseline_departure_at"] == leg["departure_at"], "zero_departure_correction")
            check(leg["nyct_direction"] == "SOUTH", "selected_southbound_direction")
            parts = [unquote(part) for part in leg["trip_id"].split(":")]
            identity = [leg["feed_id"], leg["service_date"], leg["route_id"], leg["raw_trip_id"]]
            check(parts[:5] == ["MTA", *identity], "encoded_selected_identity")
            origin = int(datetime.strptime(leg["service_date"], "%Y%m%d").replace(tzinfo=timezone.utc).timestamp())
            uid = str(origin + int(leg["raw_trip_id"][:6]) * 6 // 10) + leg["raw_trip_id"][6:]
            canonical = "MTA_EVENT:" + ":".join(quote(value, safe="") for value in identity)
            check(row["physical_sequence"] == [[canonical, leg["from_stop_id"], leg["to_stop_id"]]], "physical_identity")
            endpoints = []
            for role, stop, endpoint in (("boarding", leg["from_stop_id"], "departure"), ("alighting", leg["to_stop_id"], "arrival")):
                label = labels[leg["trip_id"]][stop]
                check(label["source_trip_uid"] == uid, "independent_csv_uid_reconstruction")
                check(label["canonical_event_trip_id"] == canonical, "canonical_label_identity")
                for key in ("raw_trip_id", "route_id", "feed_id", "service_date"):
                    check(label[key] == leg[key], "label_" + key + "_matches")
                check(label["stop_id"] == stop, "label_stop_matches")
                check(len(trips[uid]) == len(stops[(uid, stop)]) == 1, "unique_raw_rows")
                raw_trip, raw_stop = trips[uid][0], stops[(uid, stop)][0]
                check(raw_trip["route_id"] == leg["route_id"] and raw_trip["trip_id"] == leg["raw_trip_id"], "raw_trip_route_identity")
                check(raw_trip["direction_id"] == "1", "raw_trip_southbound")
                check(raw_trip["num_schedule_changes"] == raw_trip["num_schedule_rewrites"] == "0", "raw_schedule_unchanged")
                for raw_field, label_field in (("arrival_time", "arrival_at"), ("departure_time", "departure_at"), ("last_observed", "stop_last_observed_at"), ("marked_past", "available_at")):
                    value = None if raw_stop[raw_field] == "" else float(raw_stop[raw_field])
                    check(label[label_field] == value, "raw_" + raw_field + "_equals_label")
                check(label[endpoint + "_usable"] is True and not label["quality_flags"] and not label[endpoint + "_quality_flags"], "usable_flag_free_required_endpoint")
                check(label["confirmation_status"] == "CONFIRMED" and math.isfinite(label["confirmed_at"]), "finite_confirmed_receipt")
                confirmation = min((r for r in receipts[leg["feed_id"]] if r.get("status", "AVAILABLE") in ("AVAILABLE", "FRESH")
                    and label["available_at"] < r["source_updated_at"] <= r["captured_at"]), key=lambda r: r["captured_at"])
                check(confirmation["captured_at"] == label["confirmed_at"], "first_later_raw_receipt_confirms")
                age = abs(label["stop_last_observed_at"] - label[endpoint + "_at"])
                gap = label["available_at"] - label["stop_last_observed_at"]
                check(age <= 180 and 0 <= gap <= 180, "near_event_and_short_removal_gap")
                check(actual[endpoint + "_at"] == label[endpoint + "_at"], "scored_endpoint_equals_raw")
                endpoints.append({"role": role, "stop_id": stop, "endpoint": endpoint, "proxy_at": label[endpoint + "_at"],
                    "arrival_at": label["arrival_at"], "departure_at": label["departure_at"],
                    "arrival_departure_difference_seconds": label["departure_at"] - label["arrival_at"],
                    "absolute_observation_age_seconds": age, "removal_gap_seconds": gap, "confirmed_at": label["confirmed_at"],
                    "normalized_alias_count": label["normalized_alias_count"], "raw_stop_row": raw_stop, "raw_trip_row": raw_trip})
            slack = actual["departure_at"] - row["decision_at"] - forecast["access_walk_seconds"]
            check(slack >= 0 and actual["arrival_at"] >= actual["departure_at"], "feasible_inferred_journey")
            error = actual["arrival_at"] - leg["baseline_arrival_at"]
            check(error == row["eta_error_seconds"] == outcome["total_duration_seconds"] - forecast["total_duration_seconds"], "paired_error_recomputed")
            cases.append({"case_id": row["id"], "corridor_id": row["corridor_id"], "date": day, "period": row["period"],
                "local_time": row["local_time"], "physical_train_id": canonical, "normalized_train_id": leg["trip_id"],
                "source_trip_uid": uid, "forecast_departure_at": leg["baseline_departure_at"], "forecast_arrival_at": leg["baseline_arrival_at"],
                "proxy_departure_at": actual["departure_at"], "proxy_arrival_at": actual["arrival_at"], "eta_error_seconds": error,
                "inferred_boarding_slack_seconds": slack, "endpoints": endpoints})
        print({"stage": "RAW_CSV_DAY_AUDITED", "date": day, "journeys": len(day_rows)}, flush=True)
    cells = []
    published = read_json(ROOT / "data/reports/november-weekday-peak-delays.json")
    for corridor, day, period in CELLS:
        cell = [r for r in cases if (r["corridor_id"], r["date"], r["period"]) == (corridor, day, period)]
        report = next(r for r in published["groups"]["daily"] if (r["corridor_id"], r["date"], r["period"]) == (corridor, day, period))
        errors = [r["eta_error_seconds"] for r in cell]
        signed, positive = statistics.mean(errors), statistics.mean(max(e, 0) for e in errors)
        check(signed == report["grid_weighted"]["mean_signed_seconds"] and positive == report["grid_weighted"]["mean_positive_seconds"], "published_means_recomputed")
        check(len({r["physical_train_id"] for r in cell}) == len(cell), "distinct_trains_within_cell")
        cells.append({"corridor_id": corridor, "date": day, "period": period, "usable_journeys": len(cell),
            "scheduled_checkpoints": report["scheduled_checkpoints"], "mean_signed_seconds": signed,
            "mean_positive_seconds": positive, "sorted_errors_seconds": sorted(errors), "distinct_trains": len(cell)})
    forecast_audit = ROOT / "data/reports/november-weekday-large-peak-forecast-audit.json"
    result = {"schema_version": "november-weekday-large-peak-raw-audit-v1", "status": "PASSED",
        "selection": "All 22 usable journeys in three outcome-selected large daily cells; audit only, no result changes.",
        "checks": dict(checks), "assertions": sum(checks.values()), "source_sha256": sources, "cells": cells, "cases": cases,
        "max_required_endpoint_age_seconds": max(e["absolute_observation_age_seconds"] for r in cases for e in r["endpoints"]),
        "max_removal_gap_seconds": max(e["removal_gap_seconds"] for r in cases for e in r["endpoints"]),
        "limitations": ["Final MTA predictions are outcome proxies, not independent physical arrivals.",
            "No incident cause is established by this audit.", "Exact selected trains are retained; an adaptive passenger might use an earlier same-line train.",
            "Outcome-selected quality audit; no cohort, settings, outcomes or means changed."],
        "forecast_field_spotcheck": {"path": str(forecast_audit.relative_to(ROOT)), "sha256": file_sha256(forecast_audit)},
        "producer": {"path": str(Path(__file__).relative_to(ROOT)), "sha256": file_sha256(Path(__file__))}}
    write_json(REPORT, result)
    print({"stage": "RAW_ENDPOINT_AUDIT_PASSED", "assertions": result["assertions"], "sha256": file_sha256(REPORT)}, flush=True)


if __name__ == "__main__":
    main()
