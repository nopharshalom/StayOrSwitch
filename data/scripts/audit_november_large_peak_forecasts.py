#!/usr/bin/env python3
"""Audit raw protobuf fields for the largest errors in three diagnosed peak cells."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import lzma
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from google.transit import gtfs_realtime_pb2 as gtfs
from data.delay_profiles.common import epoch, file_sha256, read_json, write_json
from data.october.sources import read_snapshots, safe_members


SCORED = ROOT / "data/processed/november-peak-analysis/scored-weekday-checkpoints.json.gz"
SOURCE = ROOT / "data/manifests/november-2026.json"
OUTPUT = ROOT / "data/reports/november-weekday-large-peak-forecast-audit.json"
CELLS = [("pilot_hayden_tandon", "2026-11-12", "MIDDAY"),
         ("portauthority_tandon", "2026-11-02", "MIDDAY"),
         ("pilot_hayden_tandon", "2026-11-13", "EVENING_PEAK")]


def artifact(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path)}


def audit_case(case, source):
    checks = []
    def check(name, condition):
        if not condition:
            raise AssertionError(case["id"] + ": " + name)
        checks.append(name)

    chosen = case["forecast"]["selected_legs"][0]
    day = next(row for row in source["days"] if row["date"] == case["date"])
    item = day["outputs"]["snapshots"]
    snapshots_path = ROOT / item["path"]
    check("normalized_source_hash", file_sha256(snapshots_path) == item["sha256"])
    cutoff = case["decision_at"]
    latest, next_capture = None, None
    for snapshot in read_snapshots(snapshots_path):
        if snapshot["feed_id"] != chosen["feed_id"]:
            continue
        captured = snapshot["captured_at"]
        if captured > cutoff:
            next_capture = captured
            break
        if latest is None or captured > latest["captured_at"]:
            latest = snapshot
    check("latest_capture_found", latest is not None)
    check("capture_not_future", latest["captured_at"] <= cutoff)
    check("next_capture_after_cutoff", next_capture is not None and next_capture > cutoff)
    check("capture_age_at_most_180_seconds", cutoff - latest["captured_at"] <= 180)
    check("source_age_at_most_180_seconds", cutoff - epoch(latest["source_updated_at"]) <= 180)
    matches = [trip for trip in latest["trips"] if trip.get("id") == chosen["trip_id"]]
    check("one_normalized_selected_trip", len(matches) == 1)
    trip = matches[0]
    for key, target in (("trip_id", "raw_trip_id"), ("start_date", "service_date"),
                        ("route_id", "route_id"), ("start_time", "start_time")):
        check("normalized_identity_" + key, trip.get(key) == chosen.get(target))
    start = [stop for stop in trip["stop_updates"] if stop["stop_id"] == chosen["from_stop_id"]]
    end = [stop for stop in trip["stop_updates"] if stop["stop_id"] == chosen["to_stop_id"]]
    check("one_boarding_and_alighting_stop", len(start) == len(end) == 1)
    check("normalized_boarding_departure_matches", epoch(start[0]["departure_time"]) == chosen["baseline_departure_at"])
    check("normalized_alighting_arrival_matches", epoch(end[0]["arrival_time"]) == chosen["baseline_arrival_at"])
    check("boarding_is_explicit_departure", chosen["boarding_time_source"] == "DEPARTURE")

    provenance = latest["archive_provenance"]
    raw_item = next(item for item in source["archives"]
                    if item["archive_date"] == case["date"] and item["kind"] == "gtfsrt")
    raw_path = Path(raw_item["path"])
    if not raw_path.is_absolute():
        raw_path = ROOT / raw_path
    check("raw_archive_hash", file_sha256(raw_path) == raw_item["sha256"])
    payload = None
    with lzma.open(raw_path, "rb") as stream, tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in safe_members(archive):
            if member.name == provenance["archive_member"]:
                payload = archive.extractfile(member).read()
                break
    check("raw_archive_member_found", payload is not None)
    raw_sha = hashlib.sha256(payload).hexdigest()
    check("raw_payload_hash_matches_normalized_provenance", raw_sha == provenance["sha256"] == latest["sha256"])
    raw = gtfs.FeedMessage()
    raw.ParseFromString(payload)
    raw_matches = []
    for entity in raw.entity:
        if not entity.HasField("trip_update"):
            continue
        descriptor = entity.trip_update.trip
        if (descriptor.trip_id == chosen["raw_trip_id"] and descriptor.route_id == chosen["route_id"]
                and descriptor.start_date == chosen["service_date"] and descriptor.start_time == chosen["start_time"]):
            raw_matches.append(entity)
    check("one_raw_exact_descriptor", len(raw_matches) == 1)
    entity = raw_matches[0]
    raw_stops = list(entity.trip_update.stop_time_update)
    board = [stop for stop in raw_stops if stop.stop_id == chosen["from_stop_id"]]
    alight = [stop for stop in raw_stops if stop.stop_id == chosen["to_stop_id"]]
    check("one_raw_boarding_and_alighting_stop", len(board) == len(alight) == 1)
    board, alight = board[0], alight[0]
    check("raw_boarding_has_explicit_departure", board.HasField("departure") and board.departure.HasField("time"))
    check("raw_alighting_has_explicit_arrival", alight.HasField("arrival") and alight.arrival.HasField("time"))
    check("raw_departure_equals_frozen_forecast", board.departure.time == chosen["baseline_departure_at"] == chosen["departure_at"])
    check("raw_arrival_equals_frozen_forecast", alight.arrival.time == chosen["baseline_arrival_at"] == chosen["arrival_at"])
    check("raw_stops_have_forward_order", raw_stops.index(board) < raw_stops.index(alight))
    check("raw_header_time_matches_normalized_source", raw.header.timestamp == epoch(latest["source_updated_at"]))
    following = [stop.stop_id for stop in raw_stops[raw_stops.index(alight) + 1:]]
    check("destination_not_last_forecast_stop", bool(following))
    forecast_arrival = float(alight.arrival.time)
    outcome_arrival = case["outcome"]["selected_legs"][0]["arrival_at"]
    check("whole_journey_error_equals_arrival_residual", outcome_arrival - forecast_arrival == case["eta_error_seconds"])
    result = {"case_id": case["id"], "local_time": case["local_time"], "cell": [case["corridor_id"], case["date"], case["period"]],
              "error_seconds": case["eta_error_seconds"], "trip_id": chosen["trip_id"],
              "snapshot": {"path": item["path"], "sha256": item["sha256"], "captured_at": latest["captured_at"],
                           "source_updated_at": latest["source_updated_at"], "next_capture_at": next_capture,
                           "archive_provenance": provenance},
              "raw_archive": {"path": str(raw_path.relative_to(ROOT)), "sha256": raw_item["sha256"]},
              "raw_entity_id": entity.id, "raw_source_timestamp": raw.header.timestamp,
              "raw_boarding": {"stop_id": board.stop_id, "arrival_time": board.arrival.time if board.HasField("arrival") and board.arrival.HasField("time") else None,
                               "departure_time": board.departure.time},
              "raw_alighting": {"stop_id": alight.stop_id, "arrival_time": alight.arrival.time,
                                "departure_time": alight.departure.time if alight.HasField("departure") and alight.departure.HasField("time") else None,
                                "later_forecast_stop_ids": following},
              "outcome_arrival_at": outcome_arrival, "assertion_count": len(checks), "passed_assertions": checks}
    print({"stage": "RAW_FORECAST_AUDITED", "case_id": case["id"], "checks": len(checks)}, flush=True)
    return result


def main():
    scored = read_json(SCORED)
    source = read_json(SOURCE)
    cases = []
    for cell in CELLS:
        candidates = [row for row in scored["rows"]
                      if (row["corridor_id"], row["date"], row["period"]) == cell
                      and row["outcome"]["status"] == "INFERRED"]
        cases.append(max(candidates, key=lambda row: (row["eta_error_seconds"], row["id"])))
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda case: audit_case(case, source), cases))
    write_json(OUTPUT, {"schema_version": "november-large-peak-raw-forecast-audit-v1", "status": "PASS",
        "selection": "POSTHOC_LARGEST_POSITIVE_ERROR_PER_THREE_DIAGNOSED_CELLS", "selection_uses_outcomes": True,
        "purpose": "FIELD_AND_RAW_PROVENANCE_DIAGNOSTIC; NOT_NEW_PERFORMANCE_EVIDENCE",
        "source_manifest": artifact(SOURCE), "scored_rows": artifact(SCORED), "producer": artifact(Path(__file__)),
        "case_count": len(results), "assertion_count": sum(row["assertion_count"] for row in results), "cases": results,
        "conclusion": "All three frozen forecasts use raw boarding departure and raw destination arrival fields; no departure fallback at the destination or terminal-dwell substitution was found.",
        "limitations": ["The selected raw forecasts and later final-prediction proxies are verified feed values, not independent passenger measurements.",
                        "Exact forecast-selected trains remain fixed; an adaptive same-line passenger may board another train."]})
    print({"stage": "COMPLETE", "output": str(OUTPUT.relative_to(ROOT)), "sha256": file_sha256(OUTPUT)})


if __name__ == "__main__":
    main()
