#!/usr/bin/env python3
"""Derive the two additional provider paths and explicitly supplement missing access."""

import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.incremental_extra_corridors import build_corridor
from data.google_corridors import duration_seconds
from stayorswitch.network import HttpClient, read_local_settings
from stayorswitch.provider_client import GOOGLE_ROUTES_URL

DIRECTORY = ROOT / "data/local/google-corridors/2026-11-20-extra"
CAPTURE = ROOT / "data/manifests/incremental-extra-corridors-2026-11-20.json"
STATIONS = ROOT / "data/local/google-corridors/2026-11-20-current/official-stations.json"
OUTPUT = ROOT / "data/config/incremental-extra-corridors.json"
WALK_MANIFEST = ROOT / "data/manifests/incremental-extra-walks.json"


def load(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def artifact(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def capture_access(corridor, station):
    payload = {"origin": {"address": corridor["origin"]},
        "destination": {"location": {"latLng": {"latitude": float(station["gtfs_latitude"]),
            "longitude": float(station["gtfs_longitude"])}}}, "travelMode": "WALK", "languageCode": "en-US"}
    output = DIRECTORY / "portauthority_tandon_access_A27S.json"
    if output.exists():
        captured = load(output)
        if captured["request"] != payload:
            raise ValueError("Saved walk belongs to a different request.")
    else:
        settings = read_local_settings(ROOT / ".env")
        key = os.environ.get("GOOGLE_ROUTES_API_KEY", settings.get("GOOGLE_ROUTES_API_KEY", ""))
        ipv4 = os.environ.get("GOOGLE_ROUTES_IPV4", settings.get("GOOGLE_ROUTES_IPV4", "true")).lower()
        if not key or ipv4 not in {"true", "false", "1", "0"}:
            raise ValueError("Valid local provider settings are required.")
        mask = "routes.duration,routes.routeLabels,routes.legs.startLocation,routes.legs.endLocation,routes.legs.steps.travelMode,routes.legs.steps.staticDuration"
        with HttpClient(ipv4=ipv4 in {"true", "1"}) as client:
            response = client.post_json(GOOGLE_ROUTES_URL, payload, {"Content-Type": "application/json",
                "X-Goog-Api-Key": key, "X-Goog-FieldMask": mask})
        captured = {"request": payload, "requested_at": response.requested_at, "received_at": response.fetched_at,
            "http_status": response.status_code, "response": json.loads(response.body)}
        write(output, captured)
    routes = captured["response"].get("routes", [])
    if len(routes) != 1 or duration_seconds(routes[0].get("duration")) is None:
        raise ValueError("An unambiguous walking duration is required.")
    modes = [s.get("travelMode") for leg in routes[0].get("legs", []) for s in leg.get("steps", [])]
    if not modes or any(mode != "WALK" for mode in modes):
        raise ValueError("Supplement contains non-walking steps.")
    return {"corridor_id": corridor["id"], "stop_id": "A27S", "status": "AVAILABLE",
        "seconds": duration_seconds(routes[0]["duration"]), "capture": artifact(output),
        "requested_at": captured["requested_at"], "received_at": captured["received_at"],
        "kind": "GOOGLE_WALK_TO_STATION_COORDINATE_PLATFORM_ACCESS_UNVERIFIED",
        "authored_platform_access_seconds": 120,
        "authored_allowance_policy": "ADD_120_SECONDS_TO_BOTH_A_AND_C_BEFORE_INPUT_FREEZE; NOT_A_TRANSFER_PENALTY_OR_PROVIDER_ESTIMATE",
        "repair_reason": "RAW_GOOGLE_TRANSIT_RESPONSE_OMITS_ACCESS_WALK; RAW_REJECTION_PRESERVED"}


def main():
    capture = load(CAPTURE)
    if {row["corridor"]["id"] for row in capture["corridors"]} != {"timesquare_boroughhall", "portauthority_tandon"}:
        raise ValueError("Exactly the two preselected additional corridors are required.")
    stations = {row["gtfs_stop_id"]: row for row in load(STATIONS)}
    port = next(row for row in capture["corridors"] if row["corridor"]["id"] == "portauthority_tandon")
    access = capture_access(port["corridor"], stations["A27"])
    write(WALK_MANIFEST, {"schema_version": "additional-corridor-access-capture-v1", "walks": [access],
        "builder": artifact(Path(__file__)), "source_capture": artifact(CAPTURE)})
    corridors = []
    for row in capture["corridors"]:
        summary_path = ROOT / row["derived_summary"]["path"]
        if artifact(summary_path)["sha256"] != row["derived_summary"]["sha256"]:
            raise ValueError("Provider summary changed after capture.")
        corridors.append(build_corridor(row, load(summary_path), stations, access))
    existing = load(ROOT / "data/config/google-corridors.json")
    result = {"schema_version": "google-corridor-experiment-config-v1", "corridors": corridors,
        "capture_manifest": artifact(CAPTURE),
        "station_metadata": artifact(STATIONS), "walking_manifest": artifact(WALK_MANIFEST),
        "builder": artifact(Path(__file__)), "mapper": artifact(ROOT / "data/incremental_extra_corridors.py"),
        "maximum_total_corridors": 5, "existing_corridor_count": 3,
        "selection_uses_outcome_labels": False,
        "portauthority_access_policy": {"provider_street_walk_seconds": access["seconds"],
            "authored_platform_access_seconds": 120,
            "applies_to_lines": ["A", "C"],
            "predeclared_coupled_sensitivity_platform_seconds": [0, 240],
            "meaning": "Same origin-to-platform allowance for both services; not an additional Switch transfer cost."},
        "supplemental_sources": existing["supplemental_sources"] + [
            {"manifest": "data/manifests/incremental-extra-inputs.json", "replace_feeds": ["nqrw"]}],
        "extra_label_sources": existing["extra_label_sources"] + [
            {"manifest": "data/manifests/incremental-extra-inputs.json", "key": "labels"}],
        "provider_line_policy": "EXACT_CAPTURED_LINE_WITHOUT_COMPATIBLE_SERVICE_POOLING",
        "historical_walking_limit": "Current walking durations held fixed; station-coordinate walks do not independently establish platform access."}
    write(OUTPUT, result)
    print(json.dumps({"config": str(OUTPUT.relative_to(ROOT)), "access_supplement_seconds": access["seconds"],
        "corridors": [{"id": row["id"], "reference_route_id": row["reference_route_id"],
            "paths": len(row["routes"])} for row in corridors]}))


if __name__ == "__main__":
    main()
