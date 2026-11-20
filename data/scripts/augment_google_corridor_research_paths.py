#!/usr/bin/env python3
"""Add declared research paths using current provider walks for the actual OD."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.google_corridors import duration_seconds
from stayorswitch.network import HttpClient, NetworkError, read_local_settings
from stayorswitch.provider_client import GOOGLE_ROUTES_URL
from stayorswitch.preincident_replay import BROOKLYN_POLICY
from stayorswitch.severe import validate_templates

SOURCE = ROOT / "data/config/google-corridors-provider.json"
OUTPUT = ROOT / "data/config/google-corridors.json"
DIRECTORY = ROOT / "data/local/google-corridors/2026-11-20-current/research-walks"
WALK_MANIFEST = ROOT / "data/manifests/google-corridor-research-walks.json"


def load(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def artifact(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def path_identity(route):
    return tuple((leg["route_id"], leg["from_stop_id"], leg["to_stop_id"]) for leg in route["legs"])


def main():
    source = load(SOURCE)
    result = deepcopy(source)
    station_path = ROOT / source["station_metadata"]["path"]
    stations = {row["gtfs_stop_id"]: row for row in load(station_path)}
    originals = load(ROOT / "data/config/october.json")["routes"]
    libraries = {"pilot_hayden_tandon": originals, "grandcentral_boroughhall": BROOKLYN_POLICY["routes"],
                 "courtsquare_timessquare": []}
    walking, jobs, additions, deduplicated = {}, {}, {}, {}

    for corridor in result["corridors"]:
        cid = corridor["id"]
        walking[cid] = {}
        for route in corridor["routes"]:
            for component, stop, seconds in (
                ("access", route["legs"][0]["from_stop_id"], route["access_walk_seconds"]),
                ("egress", route["legs"][-1]["to_stop_id"], route["egress_walk_seconds"])):
                walking[cid].setdefault((component, stop), {"seconds": seconds,
                    "kind": "CURRENT_PROVIDER_EXPLICIT_WALK_SAME_OD_AND_STATION",
                    "source_route_id": route["id"], "component": component, "stop_id": stop})
        existing = {path_identity(route): route for route in corridor["routes"]}
        additions[cid], deduplicated[cid] = [], []
        for original in libraries[cid]:
            research = deepcopy(original)
            if cid == "grandcentral_boroughhall" and original["id"] == "lexington_direct":
                deduplicated[cid].append({"research_route_id": original["id"],
                    "reason": "EXACT_GOOGLE_4_AND_5_ROUTES_ALREADY_PRESERVED_SEPARATELY"})
                continue
            if path_identity(research) in existing:
                provider = existing[path_identity(research)]
                deduplicated[cid].append({"research_route_id": original["id"], "provider_route_id": provider["id"],
                    "reason": "PREFER_CURRENT_GOOGLE_PATH_AND_WALKS; KEEP_EXACT_GOOGLE_LINE_SCOPE",
                    "original_research_route_ids": [leg.get("route_ids", [leg["route_id"]]) for leg in original["legs"]]})
                continue
            if cid == "grandcentral_boroughhall" and original["id"] == "broadway_via_7":
                # The Google 7->3 path supplies the same transfer geometry; add
                # the library's 2 service without duplicating the 3 candidate.
                same = next(route for route in corridor["routes"]
                    if [leg["route_id"] for leg in route["legs"]] == ["7", "3"])
                research["legs"][0]["route_ids"] = ["7"]
                research["legs"][1]["route_ids"] = ["2"]
                research["name"] = "7 to 2 via Times Square (research library service variant)"
                research["transfer_walk_seconds"] = deepcopy(same["transfer_walk_seconds"])
                research["transfer_walking_provenance"] = [{"kind": "CURRENT_PROVIDER_EXPLICIT_WALK_SAME_STATION_PAIR",
                    "source_route_id": same["id"], "transfer_index": 0}]
                research["authored_transfer_indices"] = []
            else:
                research["transfer_walking_provenance"] = [{"kind": "AUTHORED_TRANSFER_FROM_PRIOR_RESEARCH_LIBRARY",
                    "transfer_index": index, "seconds": seconds}
                    for index, seconds in enumerate(research["transfer_walk_seconds"])]
                research["authored_transfer_indices"] = list(range(len(research["transfer_walk_seconds"])))
            research["id"] = "research_" + original["id"]
            research["candidate_provenance"] = "EXISTING_RESEARCH_ROUTE_LIBRARY_WITH_RECONCILED_CURRENT_OD_WALKS"
            research["research_library_id"] = original["id"]
            research["service_alias_policy"] = "PRESERVE_DECLARED_RESEARCH_ALIASES_EXCEPT_GOOGLE_COVERED_3_SERVICE; NEVER_POOL_GOOGLE_STAY"
            additions[cid].append(research)
            for component, stop in (("access", research["legs"][0]["from_stop_id"]),
                                    ("egress", research["legs"][-1]["to_stop_id"])):
                if (component, stop) in walking[cid]:
                    continue
                official = stations[stop[:-1]]
                point = {"location": {"latLng": {"latitude": float(official["gtfs_latitude"]),
                                                  "longitude": float(official["gtfs_longitude"])}}}
                address = {"address": corridor["origin"] if component == "access" else corridor["destination"]}
                payload = {"origin": address if component == "access" else point,
                           "destination": point if component == "access" else address,
                           "travelMode": "WALK", "languageCode": "en-US"}
                identifier = cid + "_" + component + "_" + stop
                jobs.setdefault(identifier, {"id": identifier, "corridor_id": cid, "component": component,
                    "stop_id": stop, "station_name": official["stop_name"], "request": payload})

    settings = read_local_settings(ROOT / ".env")
    key = os.environ.get("GOOGLE_ROUTES_API_KEY", settings.get("GOOGLE_ROUTES_API_KEY", ""))
    ipv4 = os.environ.get("GOOGLE_ROUTES_IPV4", settings.get("GOOGLE_ROUTES_IPV4", "true")).lower()
    if not key or ipv4 not in {"true", "false", "1", "0"}:
        raise ValueError("A valid local provider key and IPv4 setting are required.")
    mask = "routes.duration,routes.routeLabels,routes.legs.startLocation,routes.legs.endLocation,routes.legs.steps.travelMode,routes.legs.steps.staticDuration"

    def collect(job):
        output = DIRECTORY / (job["id"] + ".json")
        if output.exists():
            capture = load(output)
            if capture["job"] != job:
                raise ValueError("Existing walking capture belongs to a different request.")
        else:
            try:
                with HttpClient(ipv4=ipv4 in {"true", "1"}) as client:
                    response = client.post_json(GOOGLE_ROUTES_URL, job["request"],
                        {"Content-Type": "application/json", "X-Goog-Api-Key": key, "X-Goog-FieldMask": mask})
                capture = {"job": job, "requested_at": response.requested_at, "received_at": response.fetched_at,
                           "http_status": response.status_code, "response": json.loads(response.body)}
            except NetworkError as error:
                capture = {"job": job, "status": "UNAVAILABLE", "code": error.code,
                           "http_status": error.status_code, "message": str(error)}
            write(output, capture)
        routes = capture.get("response", {}).get("routes", [])
        valid = len(routes) == 1 and duration_seconds(routes[0].get("duration")) is not None
        if valid:
            modes = [step.get("travelMode") for leg in routes[0].get("legs", []) for step in leg.get("steps", [])]
            valid = bool(modes) and all(mode == "WALK" for mode in modes)
        return {"job": job, "capture": artifact(output), "status": "AVAILABLE" if valid else "UNAVAILABLE",
                "seconds": duration_seconds(routes[0]["duration"]) if valid else None,
                "requested_at": capture.get("requested_at"), "received_at": capture.get("received_at"),
                "kind": "GOOGLE_WALK_TO_STATION_COORDINATE_PLATFORM_ACCESS_UNVERIFIED",
                "reason": None if valid else capture.get("code", "NO_UNAMBIGUOUS_WALK_ROUTE")}

    with ThreadPoolExecutor(max_workers=3) as executor:
        collected = list(executor.map(collect, jobs.values()))
    for row in collected:
        job = row["job"]
        walking[job["corridor_id"]][(job["component"], job["stop_id"])] = row
    walk_manifest = {"schema_version": "google-research-walking-capture-v1", "source_provider_config": artifact(SOURCE),
                     "builder": artifact(Path(__file__)), "walks": collected,
                     "duration_source": "SINGLE_GOOGLE_WALK_ROUTE_DURATION",
                     "historical_assumption": "CURRENT_WALKING_DURATIONS_HELD_FIXED_AT_HISTORICAL_CUTOFFS"}
    write(WALK_MANIFEST, walk_manifest)
    for corridor in result["corridors"]:
        cid = corridor["id"]
        for research in additions[cid]:
            references = {component: walking[cid][(component, stop)] for component, stop in (
                ("access", research["legs"][0]["from_stop_id"]),
                ("egress", research["legs"][-1]["to_stop_id"]))}
            if any(row.get("seconds") is None for row in references.values()):
                corridor["unavailable_candidates"].append({"id": research["id"], "name": research["name"],
                    "candidate_provenance": research["candidate_provenance"],
                    "reason_codes": ["RESEARCH_ACCESS_OR_EGRESS_WALK_UNAVAILABLE"],
                    "walking_provenance": references})
                continue
            research["access_walk_seconds"] = references["access"]["seconds"]
            research["egress_walk_seconds"] = references["egress"]["seconds"]
            research["walking_provenance"] = references
            corridor["routes"].append(research)
        validate_templates(corridor["routes"])
        corridor["research_library_deduplication"] = deduplicated[cid]
    result.update(schema_version="google-corridor-experiment-config-v1",
        provider_only_config=artifact(SOURCE), research_walk_manifest=artifact(WALK_MANIFEST),
        research_candidates_included=True, augmentation_builder=artifact(Path(__file__)),
        research_library_sources=[artifact(ROOT / "data/config/october.json"),
                                  artifact(ROOT / "algo/stayorswitch/preincident_replay.py")],
        supplemental_sources=[
            {"manifest": "data/manifests/preincident-inputs.json", "replace_feeds": ["bdfm", "numbered"]},
            {"manifest": "data/manifests/google-corridor-inputs.json", "replace_feeds": ["numbered", "nqrw"]}],
        extra_label_sources=[{"manifest": "data/manifests/preincident-inputs.json", "key": "labels"},
                             {"manifest": "data/manifests/google-corridor-inputs.json", "key": "labels"}],
        historical_walking_limit="Current Google provider walks or station-coordinate walks are fixed assumptions. Platform access and authored transfer durations are not independently measured.")
    write(OUTPUT, result)
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "walking_requests": len(collected),
        "walking_requests_available": sum(row["status"] == "AVAILABLE" for row in collected),
        "candidate_counts": {row["id"]: len(row["routes"]) for row in result["corridors"]}}))


if __name__ == "__main__":
    main()
