#!/usr/bin/env python3
"""Capture current Google paths once; preserve raw responses only in ignored storage."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.google_corridors import summarize_capture
from stayorswitch.network import HttpClient, NetworkError, read_local_settings
from stayorswitch.provider_client import query_routes


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def artifact(path):
    return {"path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not str(output).startswith(str(ROOT / "data/local") + os.sep):
        raise ValueError("Provider response storage must be inside ignored data/local.")
    config = json.loads(args.config.read_text())
    corridors = config["corridors"]
    if not corridors or len({row["id"] for row in corridors}) != len(corridors):
        raise ValueError("Unique nonempty corridor IDs are required.")
    if any((output / (row["id"] + ".provider.json")).exists() for row in corridors):
        raise ValueError("A capture already exists; do not silently repeat billable requests.")
    settings = read_local_settings(ROOT / ".env")
    key = os.environ.get("GOOGLE_ROUTES_API_KEY", settings.get("GOOGLE_ROUTES_API_KEY", ""))
    ipv4 = os.environ.get("GOOGLE_ROUTES_IPV4", settings.get("GOOGLE_ROUTES_IPV4", "true")).lower()
    if ipv4 not in {"true", "false", "1", "0"}:
        raise ValueError("GOOGLE_ROUTES_IPV4 must be true or false.")

    def capture(corridor):
        with HttpClient(ipv4=ipv4 in {"true", "1"}, timeout_seconds=30) as client:
            try:
                provider = query_routes(client, key, corridor["origin"], corridor["destination"])
            except NetworkError as error:
                failure = {"corridor": corridor, "status": "CAPTURE_FAILED",
                           "code": error.code, "http_status": error.status_code,
                           "message": str(error)}
                write(output / (corridor["id"] + ".failure.json"), failure)
                return failure
        raw_path = output / (corridor["id"] + ".provider.json")
        write(raw_path, provider)
        summary = summarize_capture(provider, corridor)
        summary_path = output / (corridor["id"] + ".summary.json")
        write(summary_path, summary)
        return {"corridor": corridor, "status": "CAPTURED", "provider_capture": artifact(raw_path),
                "derived_summary": artifact(summary_path), "requested_at": provider["requested_at"],
                "received_at": provider["received_at"], "stay_selection": summary["stay_selection"],
                "route_count": len(summary["routes"]),
                "routes": [{key: route[key] for key in ("route_index", "route_labels", "provider_duration_seconds",
                           "selected_as_stay", "normalization_status", "normalized_itinerary_id")}
                           for route in summary["routes"]]}

    with ThreadPoolExecutor(max_workers=min(3, len(corridors))) as executor:
        results = list(executor.map(capture, corridors))
    files = [Path(__file__), ROOT / "data/google_corridors.py", ROOT / "algo/stayorswitch/provider_client.py",
             ROOT / "algo/stayorswitch/network.py", ROOT / "algo/stayorswitch/google_routes.py"]
    manifest = {"schema_version": "current-google-corridor-capture-v1",
        "created_at": datetime.now(timezone.utc).isoformat(), "config": artifact(args.config.resolve()),
        "code_sha256": {str(p.relative_to(ROOT)): artifact(p)["sha256"] for p in files},
        "selection_policy": "UNIQUE_GOOGLE_DEFAULT_ROUTE_ELSE_EXPLICIT_FASTEST_DURATION_FALLBACK",
        "query_time_policy": "PROVIDER_CURRENT_DEPARTURE_TIME; HISTORICAL_LABELS_ARE_NOT_READ",
        "use": "SELECT_CURRENT_STAY_PATH_ONLY; REPLAY_TIMES_USE_HISTORICAL_MTA",
        "corridors": results}
    write(args.manifest, manifest)
    for result in results:
        print(json.dumps({"corridor": result["corridor"]["id"], "status": result["status"],
                          "route_count": result.get("route_count"), "stay_selection": result.get("stay_selection"),
                          "error_code": result.get("code")}), flush=True)
    return 0 if all(row["status"] == "CAPTURED" for row in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
