#!/usr/bin/env python3
"""Discover fixed Court Square F/G delay cases without comparing alternatives.

This diagnostic scan uses already processed, held-out November 12-15 shards.
It does not train a model or select cases by alternative-route outcomes. The
subsequent raw replay must verify complete forecasts, labels, and the fastest
uncorrected MTA reference route. Final-ETA labels remain arrival proxies.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import gzip
import hashlib
from itertools import repeat
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ZONE = ZoneInfo("America/New_York")
ROUTES = {
    "G": {"origin": "G22S", "destination": "A42S", "access": 240},
    "F": {"origin": "F09S", "destination": "A41S", "access": 300},
}
DAYS = ("2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15")
SELECTION_RULE = (
    "For G at each cutoff independently choose earliest predicted destination "
    "arrival after fixed access. Keep cases with eligible endpoint labels and "
    ">=300s arrival/departure forecast miss. For F the 30-minute processed "
    "arrival horizon truncates the complete catchable route; discover "
    "supplementary origin-only cases using the earliest catchable F09S "
    "departure with an eligible label and >=300s departure miss. Per route/day "
    "select at most4 distinct trips in chronological order, >=60min apart. "
    "No model output or alternative outcome is inspected. Raw replay rechecks "
    "complete forecasts, labels and the cross-route baseline winner."
)


def sha256_file(path: Path) -> str:
    """Hash the exact source or compressed input bytes used by discovery."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_day(day: str, input_directory: Path) -> tuple[str, dict]:
    """Select route-local candidate moments before any cross-route evaluation."""
    origins = {}
    destinations = {}
    counts = Counter()
    by_time = {}

    for kind in ("segments", "arrivals"):
        with gzip.open(input_directory / f"{day}.{kind}.jsonl.gz", "rt") as stream:
            for line in stream:
                row = json.loads(line)
                features = row["features"]
                route = features["route_id"]
                if route not in ROUTES:
                    continue
                local = datetime.fromtimestamp(row["decision_at"], ZONE)
                if not 6 <= local.hour < 23:
                    continue
                key = (route, row["decision_at"], row["trip_identity"])
                config = ROUTES[route]
                if kind == "segments" and row["from_stop_id"] == config["origin"]:
                    counts[route + "_origin_rows"] += 1
                    if features["origin_prediction_basis"] == "DEPARTURE_PREDICTION":
                        origins[key] = row
                if kind == "arrivals" and row["stop_id"] == config["destination"]:
                    counts[route + "_destination_rows"] += 1
                    destinations[key] = row

    for key, origin in origins.items():
        destination = destinations.get(key)
        if destination is None:
            continue
        route, cutoff, identity = key
        departure = origin["features"]["mta_departure_at"]
        arrival = destination["features"]["mta_arrival_at"]
        if departure < cutoff + ROUTES[route]["access"] or arrival < departure:
            continue
        by_time.setdefault((route, cutoff), []).append(
            (arrival, departure, identity, origin, destination)
        )

    cases = []
    for (route, cutoff), options in sorted(by_time.items()):
        arrival, departure, identity, origin, destination = min(
            options, key=lambda option: option[:3]
        )
        counts[route + "_full_join_cutoffs"] += 1
        # Select the forecast train first; label quality cannot change that choice.
        if not origin["eligible_for_training"] or not destination["eligible_for_training"]:
            counts[route + "_ineligible_selected"] += 1
            continue
        counts[route + "_eligible_cutoffs"] += 1
        departure_label = origin["label"]["departure_at"]
        arrival_label = destination["label"]["arrival_at"]
        if max(departure_label - departure, arrival_label - arrival) < 300:
            continue
        counts[route + "_delay_cutoffs"] += 1
        cases.append({
            "route_id": route,
            "discovery_basis": "FULL_PATH_DESTINATION_OR_DEPARTURE_RESIDUAL",
            "decision_at": cutoff,
            "local_time": datetime.fromtimestamp(cutoff, ZONE).isoformat(),
            "boarding_stop_id": ROUTES[route]["origin"],
            "alighting_stop_id": ROUTES[route]["destination"],
            "access_seconds": ROUTES[route]["access"],
            "trip_identity": identity,
            "raw_trip_id": origin["provenance"]["raw_trip_id"],
            "source_trip_uid": origin["label"]["source_trip_uid"],
            "source_archive_member": origin["provenance"]["archive_member"],
            "predicted_departure_at": departure,
            "predicted_arrival_at": arrival,
            "label_departure_at": departure_label,
            "label_arrival_at": arrival_label,
            "departure_residual_seconds": departure_label - departure,
            "arrival_residual_seconds": arrival_label - arrival,
            "riding_residual_seconds": (
                (arrival_label - departure_label) - (arrival - departure)
            ),
            "predicted_remaining_minutes": round((arrival - cutoff) / 60, 2),
            "label_remaining_minutes": round((arrival_label - cutoff) / 60, 2),
            "boarding_horizon_seconds": departure - cutoff,
            "origin_example_id": origin["example_id"],
            "destination_example_id": destination["example_id"],
            "label_quality_flags": (
                origin["label"]["quality_flags"] + destination["label"]["quality_flags"]
            ),
            "asof_alert_status": destination["features"].get("service_alert_status"),
            "asof_alert_count": destination["features"].get("service_alert_count"),
            "asof_eta_revision_count": destination["features"].get(
                "prediction_revisions_last_10_minutes"
            ),
        })

    # Five-minute access plus the F ride exceeds the processed arrival horizon.
    # Supplement with its earliest catchable origin departure. Raw replay must
    # recover the complete destination forecast and check cross-route ranking.
    f_by_time = {}
    for (route, cutoff, identity), origin in origins.items():
        departure = origin["features"]["mta_departure_at"]
        if route != "F" or departure < cutoff + ROUTES[route]["access"]:
            continue
        existing = f_by_time.get(cutoff)
        if existing is None or (departure, identity) < (
            existing["features"]["mta_departure_at"], existing["trip_identity"]
        ):
            f_by_time[cutoff] = origin

    for cutoff, origin in sorted(f_by_time.items()):
        counts["F_origin_only_cutoffs"] += 1
        if not origin["eligible_for_training"]:
            counts["F_origin_only_ineligible_selected"] += 1
            continue
        counts["F_origin_only_eligible_cutoffs"] += 1
        departure = origin["features"]["mta_departure_at"]
        departure_label = origin["label"]["departure_at"]
        if departure_label - departure < 300:
            continue
        counts["F_origin_only_delay_cutoffs"] += 1
        cases.append({
            "route_id": "F",
            "discovery_basis": "ORIGIN_DEPARTURE_RESIDUAL_30_MINUTE_DESTINATION_TRUNCATION",
            "decision_at": cutoff,
            "local_time": datetime.fromtimestamp(cutoff, ZONE).isoformat(),
            "boarding_stop_id": ROUTES["F"]["origin"],
            "alighting_stop_id": ROUTES["F"]["destination"],
            "access_seconds": ROUTES["F"]["access"],
            "trip_identity": origin["trip_identity"],
            "raw_trip_id": origin["provenance"]["raw_trip_id"],
            "source_trip_uid": origin["label"]["source_trip_uid"],
            "source_archive_member": origin["provenance"]["archive_member"],
            "predicted_departure_at": departure,
            "predicted_arrival_at": None,
            "label_departure_at": departure_label,
            "label_arrival_at": None,
            "departure_residual_seconds": departure_label - departure,
            "arrival_residual_seconds": None,
            "boarding_horizon_seconds": departure - cutoff,
            "origin_example_id": origin["example_id"],
            "label_quality_flags": origin["label"]["quality_flags"],
            "asof_alert_status": origin["features"].get("service_alert_status"),
            "asof_alert_count": origin["features"].get("service_alert_count"),
        })

    picked = []
    for route in ROUTES:
        chosen = []
        seen = set()
        route_cases = sorted(
            (row for row in cases if row["route_id"] == route),
            key=lambda row: (row["decision_at"], row["trip_identity"]),
        )
        for row in route_cases:
            if row["trip_identity"] in seen or any(
                abs(row["decision_at"] - other["decision_at"]) < 3600
                for other in chosen
            ):
                continue
            row = dict(
                row,
                case_id=day + "-" + route + "-" + row["local_time"][11:16].replace(":", ""),
                requires_outlier_review=max(
                    row["arrival_residual_seconds"] or 0,
                    row["departure_residual_seconds"],
                ) > 1800,
            )
            chosen.append(row)
            seen.add(row["trip_identity"])
            if len(chosen) == 4:
                break
        picked.extend(chosen)
    return day, {
        "counts": dict(counts),
        "all_delay_candidates": cases,
        "selected_cases": picked,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir", type=Path,
        default=REPOSITORY_ROOT / "data/processed/history-pilot",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=REPOSITORY_ROOT / "data/processed/corridor-replay",
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")

    start = time.monotonic()
    source = Path(__file__).resolve()
    inputs = [
        args.input_dir / f"{day}.{kind}.jsonl.gz"
        for day in DAYS for kind in ("segments", "arrivals")
    ]
    provenance = {
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "input_shards": [
            {"path": str(path.resolve()), "sha256": sha256_file(path)}
            for path in inputs
        ],
    }
    result = {
        "route_templates": ROUTES,
        "selection_rule": SELECTION_RULE,
        "days": {},
        "provenance": provenance,
    }
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for day, data in executor.map(process_day, DAYS, repeat(args.input_dir)):
            result["days"][day] = data
            print(json.dumps({
                "day": day,
                "counts": data["counts"],
                "selected_cases": len(data["selected_cases"]),
                "elapsed_seconds": round(time.monotonic() - start, 1),
            }), flush=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "scout-primary.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    pool = {
        "route_templates": ROUTES,
        "selection_rule": result["selection_rule"],
        "cases": sorted(
            [row for data in result["days"].values() for row in data["selected_cases"]],
            key=lambda row: row["decision_at"],
        ),
        "summary": {day: data["counts"] for day, data in result["days"].items()},
        "provenance": provenance,
    }
    (args.output_dir / "scout-primary-pool.json").write_text(
        json.dumps(pool, indent=2) + "\n"
    )
    print("Selected cases:", len(pool["cases"]))
    for row in pool["cases"]:
        print(
            row["case_id"], row["local_time"],
            "arrival residual:", row["arrival_residual_seconds"],
            "departure residual:", row["departure_residual_seconds"],
        )


if __name__ == "__main__":
    main()
