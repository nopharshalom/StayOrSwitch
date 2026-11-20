"""Safeguards for preserving two exact provider defaults and walking provenance."""

from copy import deepcopy
import unittest

from data.incremental_extra_corridors import build_corridor, route_template


def station(name, line, latitude, longitude):
    return {"stop_name": name, "daytime_routes": line, "gtfs_latitude": latitude,
            "gtfs_longitude": longitude, "south_direction_label": "Downtown"}


STATIONS = {
    "A27": station("42 St-Port Authority Bus Terminal", "A C E", 40.7573, -73.9897),
    "A41": station("Jay St-MetroTech", "A C F", 40.6923, -73.9873),
}


def route(index=0, line="A", access=False):
    def stop(name, latitude, longitude):
        return {"name": name, "location": {"latLng": {"latitude": latitude, "longitude": longitude}}}
    steps = [{"travel_mode": "TRANSIT", "vehicle_type": "SUBWAY", "line": line,
        "departure_stop": stop("42 St-Port Authority Bus Terminal", 40.7573, -73.9897),
        "arrival_stop": stop("Jay St-MetroTech", 40.6923, -73.9873),
        "arrival_time": "2026-11-20T17:00:00Z", "headsign": "Brooklyn"},
        {"travel_mode": "WALK", "static_duration_seconds": 90}]
    if access:
        steps.insert(0, {"travel_mode": "WALK", "static_duration_seconds": 60})
    return {"route_index": index, "route_labels": ["DEFAULT_ROUTE"] if index == 0 else [],
        "steps": steps, "normalized_itinerary_id": "provider-path" if access else None,
        "normalization_status": "NORMALIZED" if access else "REJECTED",
        "provider_duration_seconds": 1200, "selected_as_stay": index == 0}


ACCESS = {"corridor_id": "portauthority_tandon", "stop_id": "A27S", "status": "AVAILABLE",
          "seconds": 0, "authored_platform_access_seconds": 120, "kind": "CAPTURED_WALK"}
CAPTURE = {"corridor": {"id": "portauthority_tandon", "origin": "Street origin", "destination": "Destination"},
           "provider_capture": {}, "derived_summary": {}, "requested_at": "2026-11-20T16:00:00Z",
           "received_at": "2026-11-20T16:00:01Z"}


def summary(rows):
    return {"routes": rows, "stay_selection": {"method": "GOOGLE_DEFAULT_ROUTE", "route_index": 0},
            "normalization": {"issues": [{"route_index": r["route_index"], "code": "MISSING_ACCESS_WALK"}
                                         for r in rows if r["normalization_status"] == "REJECTED"]}}


class ExtraCorridorTests(unittest.TestCase):
    def test_missing_access_is_not_silently_zero(self):
        with self.assertRaises(ValueError):
            route_template(CAPTURE["corridor"], route(), STATIONS)

    def test_captured_zero_and_authored_allowance_remain_separate(self):
        result = route_template(CAPTURE["corridor"], route(), STATIONS, ACCESS)
        self.assertEqual(result["access_walk_seconds"], 120)
        self.assertEqual(result["google"]["explicit_access_supplement"]["seconds"], 0)
        self.assertEqual(result["google"]["original_normalization_status"], "REJECTED")
        self.assertEqual(result["legs"][0]["route_ids"], ["A"])

    def test_same_allowance_for_a_and_c(self):
        values = [route_template(CAPTURE["corridor"], route(line=line), STATIONS, ACCESS) for line in ("A", "C")]
        self.assertEqual([r["access_walk_seconds"] for r in values], [120, 120])
        self.assertNotEqual(values[0]["id"], values[1]["id"])

    def test_default_preserved_and_all_duplicates_retained(self):
        rows = [route(), route(1), route(2, "C")]
        result = build_corridor(CAPTURE, summary(rows), STATIONS, ACCESS)
        self.assertEqual(len(result["routes"]), 2)
        self.assertEqual(result["reference_route_id"], result["routes"][0]["id"])
        self.assertEqual(result["routes"][0]["google"]["source_route_indices"], [0, 1])
        self.assertEqual(len(result["google"]["all_provider_routes"]), 3)

    def test_unrelated_rejection_not_repaired(self):
        value = summary([route()])
        value["normalization"]["issues"].append({"route_index": 0, "code": "BROKEN_BOUNDARY"})
        with self.assertRaises(ValueError):
            build_corridor(CAPTURE, value, STATIONS, ACCESS)

    def test_unique_default_required(self):
        rows = [route(), route(1)]
        rows[1]["route_labels"] = ["DEFAULT_ROUTE"]
        with self.assertRaises(ValueError):
            build_corridor(CAPTURE, summary(rows), STATIONS, ACCESS)

    def test_no_third_additional_corridor(self):
        captured = deepcopy(CAPTURE)
        captured["corridor"]["id"] = "unauthorized_sixth_corridor"
        with self.assertRaises(ValueError):
            build_corridor(captured, summary([route()]), STATIONS, ACCESS)

    def test_station_distance_checked(self):
        row = route()
        row["steps"][0]["departure_stop"]["location"]["latLng"]["latitude"] += 0.1
        with self.assertRaises(ValueError):
            route_template(CAPTURE["corridor"], row, STATIONS, ACCESS)


if __name__ == "__main__":
    unittest.main()
