"""Map two additional current Google corridors without changing their defaults."""

from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json

from data.scripts.build_google_corridor_templates import map_stop
from stayorswitch.mta import ROUTE_FEEDS
from stayorswitch.severe import validate_templates


PAIRS = {
    ("2", "Times Sq-42 St", "Borough Hall"): ("127S", "232S"),
    ("3", "Times Sq-42 St", "Borough Hall"): ("127S", "232S"),
    ("A", "42 St-Port Authority Bus Terminal", "Jay St-MetroTech"): ("A27S", "A41S"),
    ("C", "42 St-Port Authority Bus Terminal", "Jay St-MetroTech"): ("A27S", "A41S"),
    ("F", "42 St-Bryant Pk", "Jay St-MetroTech"): ("D16S", "A41S"),
    ("R", "Times Sq-42 St", "Jay St - MetroTech"): ("R16S", "R29S"),
}
ALLOWED_CORRIDORS = {"timesquare_boroughhall", "portauthority_tandon"}


def station_evidence(stop, stop_id, line, stations):
    value = {"name": stop["name"], "coordinates": stop["location"]["latLng"]}
    alias = value["name"] == "Jay St - MetroTech" and stop_id == "R29S" and line == "R"
    if alias:
        value["name"] = "Jay St-MetroTech"
    result = map_stop(value, stop_id, line, stations)
    result["provider_name"] = stop["name"]
    result["explicit_station_name_alias"] = alias
    return result


def route_template(corridor, route, stations, access_supplement=None):
    steps = route["steps"]
    indices = [i for i, step in enumerate(steps) if step["travel_mode"] == "TRANSIT"]
    if len(indices) != 1 or any(step["travel_mode"] not in {"WALK", "TRANSIT"} for step in steps):
        raise ValueError("This audited capture contains direct subway paths only.")
    index = indices[0]
    transit = steps[index]
    if transit["vehicle_type"] != "SUBWAY":
        raise ValueError("A subway path is required.")
    line = transit["line"]
    pair = PAIRS[(line, transit["departure_stop"]["name"], transit["arrival_stop"]["name"])]
    access = sum(step["static_duration_seconds"] for step in steps[:index])
    egress = sum(step["static_duration_seconds"] for step in steps[index + 1:])
    if not steps[index + 1:]:
        raise ValueError("Missing egress walk cannot be silently replaced.")
    repair = None
    if index == 0:
        if (corridor["id"] != "portauthority_tandon" or line not in {"A", "C"}
                or not access_supplement or access_supplement.get("status") != "AVAILABLE"
                or access_supplement.get("seconds") is None
                or access_supplement.get("stop_id") != pair[0]
                or access_supplement.get("corridor_id") != corridor["id"]):
            raise ValueError("Missing access requires separately captured, matching walking evidence.")
        access = access_supplement["seconds"] + access_supplement.get("authored_platform_access_seconds", 0)
        repair = deepcopy(access_supplement)
    elif route["normalization_status"] == "REJECTED":
        raise ValueError("An unrelated provider normalization rejection cannot be repaired.")
    identity = route.get("normalized_itinerary_id")
    if identity is None:
        key = [corridor["id"], line, pair, access, egress]
        identity = "google-derived-" + hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24]
    arrival = datetime.fromisoformat(transit["arrival_time"].replace("Z", "+00:00")) + timedelta(seconds=egress)
    return {"id": identity, "family": "GOOGLE_" + line,
        "name": line + ": " + transit["departure_stop"]["name"] + " to " + transit["arrival_stop"]["name"],
        "access_walk_seconds": access, "egress_walk_seconds": egress, "transfer_walk_seconds": [],
        "legs": [{"route_id": line, "route_ids": [line], "feed_id": ROUTE_FEEDS[line],
                  "from_stop_id": pair[0], "to_stop_id": pair[1]}],
        "candidate_provenance": "CURRENT_GOOGLE_ROUTE_WITH_EXPLICIT_ACCESS_SUPPLEMENT" if repair else "CURRENT_GOOGLE_ROUTE",
        "walking_provenance": {"access": repair or {"kind": "SUM_OF_EXPLICIT_GOOGLE_WALK_STEPS"},
            "egress": {"kind": "SUM_OF_EXPLICIT_GOOGLE_WALK_STEPS"},
            "historical_assumption": "CURRENT_WALKS_HELD_FIXED; NOT_OBSERVED_HISTORICAL_PLATFORM_ACCESS"},
        "google": {"representative_route_index": route["route_index"],
            "source_route_indices": [route["route_index"]],
            "original_normalization_status": route["normalization_status"],
            "current_provider_eta": arrival.isoformat().replace("+00:00", "Z"),
            "explicit_access_supplement": repair},
        "station_mapping_evidence": [{"route_id": line, "headsign": transit["headsign"],
            "boarding": station_evidence(transit["departure_stop"], pair[0], line, stations),
            "alighting": station_evidence(transit["arrival_stop"], pair[1], line, stations)}]}


def build_corridor(captured, summary, stations, access_supplement=None):
    corridor = captured["corridor"]
    if corridor["id"] not in ALLOWED_CORRIDORS:
        raise ValueError("Only the two preselected additional corridors are allowed.")
    defaults = [r for r in summary["routes"] if "DEFAULT_ROUTE" in r["route_labels"]]
    if len(defaults) != 1 or summary["stay_selection"]["method"] != "GOOGLE_DEFAULT_ROUTE":
        raise ValueError("A unique explicit Google default is required.")
    templates, index_to_id, paths = [], {}, {}
    for route in sorted(summary["routes"], key=lambda row: (row is not defaults[0], row["route_index"])):
        if route["normalization_status"] == "REJECTED":
            codes = {issue["code"] for issue in summary["normalization"]["issues"]
                     if issue["route_index"] == route["route_index"]}
            if codes != {"MISSING_ACCESS_WALK"}:
                raise ValueError("Only the documented missing-access rejection can be supplemented.")
        value = route_template(corridor, route, stations, access_supplement)
        key = (value["legs"][0]["route_id"], value["legs"][0]["from_stop_id"],
               value["legs"][0]["to_stop_id"], value["access_walk_seconds"], value["egress_walk_seconds"])
        if key in paths:
            prior = paths[key]
            prior["google"]["source_route_indices"].append(route["route_index"])
            index_to_id[route["route_index"]] = prior["id"]
        else:
            paths[key] = value
            templates.append(value)
            index_to_id[route["route_index"]] = value["id"]
    validate_templates(templates)
    default = defaults[0]
    return dict(corridor, reference_route_id=index_to_id[default["route_index"]], routes=templates,
        unavailable_candidates=[], google={"capture": captured["provider_capture"],
            "derived_summary": captured["derived_summary"], "requested_at": captured["requested_at"],
            "received_at": captured["received_at"], "selection": summary["stay_selection"],
            "default_route_id": index_to_id[default["route_index"]], "default_route_index": default["route_index"],
            "default_route_labels": default["route_labels"], "current_duration_seconds": default["provider_duration_seconds"],
            "current_duration_used_as_historical_outcome": False,
            "all_provider_routes": [{key: row[key] for key in ("route_index", "route_labels",
                "provider_duration_seconds", "selected_as_stay", "normalization_status", "normalized_itinerary_id")}
                for row in summary["routes"]], "derived_template_by_raw_index": index_to_id})
