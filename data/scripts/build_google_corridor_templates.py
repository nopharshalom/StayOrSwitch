#!/usr/bin/env python3
"""Map captured provider paths to verified station pairs without generating routes."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from stayorswitch.mta import ROUTE_FEEDS
from stayorswitch.severe import validate_templates

CAPTURE_MANIFEST = ROOT / "data/manifests/google-corridors-2026-11-20.json"
DIRECTORY = ROOT / "data/local/google-corridors/2026-11-20-current"
OUTPUT = ROOT / "data/config/google-corridors-provider.json"

# These southbound platform pairs are checked against the captured Google line,
# station name, coordinates and headsign, official MTA station metadata, and the
# historical source's ordered stop IDs. The replay must still verify actual
# stopping order on each selected historical train.
PAIRS = {
    ("F", "Court Sq-23 St", "Jay St-MetroTech"): ("F09S", "A41S"),
    ("G", "Court Sq", "Hoyt-Schermerhorn Sts"): ("G22S", "A42S"),
    ("5", "Grand Central-42 St", "Borough Hall"): ("631S", "423S"),
    ("4", "Grand Central-42 St", "Borough Hall"): ("631S", "423S"),
    ("7", "Grand Central-42 St", "Times Sq-42 St"): ("723S", "725S"),
    ("3", "Times Sq-42 St", "Borough Hall"): ("127S", "232S"),
    ("7", "Grand Central-42 St", "5 Av"): ("723S", "724S"),
    ("F", "42 St-Bryant Pk", "Jay St-MetroTech"): ("D16S", "A41S"),
    ("6", "Grand Central-42 St", "14 St-Union Sq"): ("631S", "635S"),
    ("R", "14 St-Union Sq", "Court St"): ("R20S", "R28S"),
    ("7", "Court Sq", "Times Sq-42 St"): ("719S", "725S"),
    ("F", "Court Sq-23 St", "42 St-Bryant Pk"): ("F09S", "D16S"),
    ("E", "Court Sq-23 St", "42 St-Port Authority Bus Terminal"): ("F09S", "A27S"),
}


def load(path):
    return json.loads(path.read_text())


def artifact(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def distance(first, second):
    a, b = math.radians(first[0]), math.radians(second[0])
    da, db = b - a, math.radians(second[1] - first[1])
    h = math.sin(da / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(db / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def map_stop(stop, directional_id, line, stations):
    official = stations[directional_id[:-1]]
    if stop["name"] != official["stop_name"] or line not in official["daytime_routes"].split():
        raise ValueError("Provider line/station does not match declared official station mapping.")
    coordinates = stop["coordinates"]
    separation = distance((coordinates["latitude"], coordinates["longitude"]),
                          (float(official["gtfs_latitude"]), float(official["gtfs_longitude"])))
    if separation > 250:
        raise ValueError("Provider station is too far from the declared MTA station.")
    return {"provider_name": stop["name"], "provider_coordinates": coordinates,
            "mta_stop_id": directional_id, "official_station_name": official["stop_name"],
            "official_coordinates": {"latitude": float(official["gtfs_latitude"]),
                                     "longitude": float(official["gtfs_longitude"])},
            "official_daytime_routes": official["daytime_routes"],
            "official_south_direction_label": official["south_direction_label"],
            "distance_metres": round(separation, 3)}


def template(itinerary, record, stations):
    subway = [leg for leg in itinerary["legs"] if leg["mode"] == "SUBWAY"]
    walks, pending, legs, evidence = [], 0, [], []
    for leg in itinerary["legs"]:
        if leg["mode"] == "WALK":
            pending += leg["provider_duration_seconds"]
            continue
        walks.append(pending)
        pending = 0
        line = leg["transit"]["route_short_name"]
        pair = PAIRS[(line, leg["from"]["name"], leg["to"]["name"])]
        evidence.append({"route_id": line, "headsign": leg["transit"]["headsign"],
            "boarding": map_stop(leg["from"], pair[0], line, stations),
            "alighting": map_stop(leg["to"], pair[1], line, stations)})
        legs.append({"route_id": line, "route_ids": [line], "feed_id": ROUTE_FEEDS[line],
                     "from_stop_id": pair[0], "to_stop_id": pair[1]})
    walks.append(pending)
    if len(walks) != len(subway) + 1:
        raise ValueError("A provider route lost a walking boundary.")
    name = " then ".join(leg["transit"]["route_short_name"] for leg in subway)
    return {"id": itinerary["id"], "family": "GOOGLE_" + "_".join(leg["route_id"] for leg in legs),
            "name": name + ": " + subway[0]["from"]["name"] + " to " + subway[-1]["to"]["name"],
            "access_walk_seconds": walks[0], "egress_walk_seconds": walks[-1],
            "transfer_walk_seconds": walks[1:-1], "legs": legs,
            "candidate_provenance": "CURRENT_GOOGLE_ROUTE",
            "walking_provenance": "SUM_OF_EXPLICIT_CURRENT_PROVIDER_WALK_STEPS_HELD_FIXED_FOR_HISTORICAL_REPLAY",
            "google": {"representative_route_index": record["route_index"],
                       "source_route_indices": record["source_route_indices"],
                       "current_provider_eta": itinerary["provider_eta"],
                       "normalization_provenance": deepcopy(record)},
            "station_mapping_evidence": evidence}


def main():
    source = load(CAPTURE_MANIFEST)
    stations_path = DIRECTORY / "official-stations.json"
    stations = {row["gtfs_stop_id"]: row for row in load(stations_path)}
    corridors = []
    for captured in source["corridors"]:
        summary_path = ROOT / captured["derived_summary"]["path"]
        if artifact(summary_path)["sha256"] != captured["derived_summary"]["sha256"]:
            raise ValueError("Captured provider summary changed.")
        summary = load(summary_path)
        normalized = summary["normalization"]
        by_id = {row["itinerary_id"]: row for row in normalized["provenance"] if row["selected"]}
        templates = [template(route, by_id[route["id"]], stations)
                     for route in normalized["request"]["itineraries"]]
        validate_templates(templates)
        default_index = summary["stay_selection"]["route_index"]
        selected = next(row for row in summary["routes"] if row["route_index"] == default_index)
        if selected["normalized_itinerary_id"] not in {row["id"] for row in templates}:
            raise ValueError("The provider default cannot be represented; do not replace it.")
        unavailable = []
        for route in summary["routes"]:
            if route["normalization_status"] != "REJECTED":
                continue
            line_names = [step["line"] for step in route["steps"] if step["travel_mode"] == "TRANSIT"]
            unavailable.append({"id": "google-unavailable-{}-{}".format(captured["corridor"]["id"], route["route_index"]),
                "name": " then ".join(line_names) + " (provider route unavailable)",
                "candidate_provenance": "CURRENT_GOOGLE_ROUTE_REJECTED_NORMALIZATION",
                "google_route_index": route["route_index"],
                "reason_codes": [issue["code"] for issue in normalized["issues"] if issue["route_index"] == route["route_index"]]})
        corridors.append(dict(captured["corridor"], reference_route_id=selected["normalized_itinerary_id"],
            routes=templates, unavailable_candidates=unavailable,
            google={"capture": captured["provider_capture"], "derived_summary": captured["derived_summary"],
                "requested_at": captured["requested_at"], "received_at": captured["received_at"],
                "selection": summary["stay_selection"], "default_route_id": selected["normalized_itinerary_id"],
                "default_route_index": default_index, "default_route_labels": selected["route_labels"],
                "current_duration_seconds": selected["provider_duration_seconds"],
                "current_duration_used_as_historical_outcome": False,
                "all_provider_routes": [{key: row[key] for key in ("route_index", "route_labels",
                    "provider_duration_seconds", "selected_as_stay", "normalization_status", "normalized_itinerary_id")}
                    for row in summary["routes"]]}))
    result = {"schema_version": "google-corridor-provider-templates-v1", "corridors": corridors,
        "capture_manifest": artifact(CAPTURE_MANIFEST), "station_metadata": artifact(stations_path),
        "station_metadata_url": "https://data.ny.gov/resource/39hk-dx4f.json?$limit=5000",
        "builder": artifact(Path(__file__)),
        "provider_line_policy": "EXACT_CAPTURED_LINE_WITHOUT_COMPATIBLE_SERVICE_POOLING",
        "research_candidates_included": False,
        "historical_walking_limit": "Current provider walking values are fixed assumptions, not archived October observations."}
    OUTPUT.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "corridors": len(corridors),
        "supported_paths": {row["id"]: len(row["routes"]) for row in corridors},
        "unavailable_paths": {row["id"]: len(row["unavailable_candidates"]) for row in corridors}}))


if __name__ == "__main__":
    main()
