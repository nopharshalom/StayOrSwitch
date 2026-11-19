"""Synthetic tests for provider normalization; no network or private data."""

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ALGO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ALGO))
from stayorswitch.google_routes import normalize_google_response


SPEC = importlib.util.spec_from_file_location("contract_validator", ALGO / "scripts" / "validate_contract.py")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
SCHEMA = json.loads((ALGO / "contracts" / "evaluate.schema.json").read_text())


def point(latitude, longitude):
    return {"latLng": {"latitude": latitude, "longitude": longitude}}


ORIGIN_POINT = point(40.7, -74.0)
BOARD_POINT = point(40.701, -74.0)
ALIGHT_POINT = point(40.72, -74.0)
DESTINATION_POINT = point(40.721, -74.0)


def endpoint(name, coordinates):
    return {"id": name, "name": name, "coordinates": coordinates["latLng"],
            "provider_place_id": None, "mta_stop_id": None}


def walk(start, end, seconds=60):
    return {"travelMode": "WALK", "staticDuration": "{}s".format(seconds),
            "startLocation": copy.deepcopy(start), "endLocation": copy.deepcopy(end)}


def subway(start=BOARD_POINT, end=ALIGHT_POINT, line="F", departure="2026-11-19T12:05:00Z",
           arrival="2026-11-19T12:20:00Z", headsign="Synthetic terminal"):
    return {"travelMode": "TRANSIT", "staticDuration": "900s", "startLocation": copy.deepcopy(start),
            "endLocation": copy.deepcopy(end), "transitDetails": {
                "headsign": headsign, "stopDetails": {
                    "departureStop": {"name": "Synthetic boarding", "location": copy.deepcopy(start)},
                    "arrivalStop": {"name": "Synthetic alighting", "location": copy.deepcopy(end)},
                    "departureTime": departure, "arrivalTime": arrival},
                "transitLine": {"nameShort": line, "vehicle": {"type": "SUBWAY"},
                                "agencies": [{"name": "MTA New York City Transit"}]}}}


def route():
    return {"duration": "1020s", "legs": [{"steps": [walk(ORIGIN_POINT, BOARD_POINT),
                                                                 subway(), walk(ALIGHT_POINT, DESTINATION_POINT)]}]}


def normalize(routes=None, **kwargs):
    args = {"queried_at": "2026-11-19T12:00:00Z", "received_at": "2026-11-19T12:00:01Z",
            "decision_time": "2026-11-19T12:00:02Z", "origin": endpoint("Synthetic origin", ORIGIN_POINT),
            "destination": endpoint("Synthetic destination", DESTINATION_POINT)}
    args.update(kwargs)
    return normalize_google_response({"routes": [route()] if routes is None else routes}, **args)


class GoogleRoutesTests(unittest.TestCase):
    def assert_valid(self, result):
        self.assertIsNotNone(result["request"], result["issues"])
        VALIDATOR.schema_validate(result["request"], "Request", SCHEMA)
        VALIDATOR.request_invariants(result["request"])
        return result["request"]

    def test_destination_eta_uses_train_clock_and_egress(self):
        result = normalize()
        request = self.assert_valid(result)
        itinerary = request["itineraries"][0]
        self.assertEqual(itinerary["provider_eta"], "2026-11-19T12:21:00Z")
        self.assertEqual(result["provenance"][0]["original_duration_seconds"], 1020)
        self.assertEqual(result["provenance"][0]["duration_vs_clock_difference_seconds"], 240)
        self.assertIsNone(request["current_itinerary_id"])
        self.assertIsNone(itinerary["provider"]["itinerary_id"])
        self.assertEqual(itinerary["provider"]["queried_at"], "2026-11-19T12:00:00Z")
        self.assertIsNone(itinerary["legs"][1]["transit"]["direction_id"])
        self.assertIsNone(itinerary["legs"][1]["transit"]["provider_trip_id"])
        self.assertIsNone(itinerary["legs"][1]["from"]["mta_stop_id"])

    def test_deduplicates_headsigns_and_keeps_earliest_arrival(self):
        late, early = route(), route()
        late["legs"][0]["steps"][1]["transitDetails"]["stopDetails"].update(
            departureTime="2026-11-19T12:10:00Z", arrivalTime="2026-11-19T12:25:00Z")
        early["legs"][0]["steps"][1]["transitDetails"]["headsign"] = "Another terminal beyond our stop"
        result = normalize([late, early])
        request = self.assert_valid(result)
        self.assertEqual(len(request["itineraries"]), 1)
        self.assertEqual(request["itineraries"][0]["provider_eta"], "2026-11-19T12:21:00Z")
        self.assertEqual(result["provenance"][0]["status"], "DUPLICATE")
        self.assertEqual(result["provenance"][1]["status"], "NORMALIZED")
        self.assertEqual(result["provenance"][1]["source_route_indices"], [0, 1])
        self.assertEqual(normalize([late])["request"]["itineraries"][0]["id"], request["itineraries"][0]["id"])

    def test_refresh_preserves_current_even_when_provider_order_changes(self):
        first, alternative = route(), route()
        alternative["legs"][0]["steps"][1]["transitDetails"]["transitLine"]["nameShort"] = "C"
        current = normalize([first])["request"]["itineraries"][0]["id"]
        result = normalize([alternative, first], current_itinerary_id=current)
        request = self.assert_valid(result)
        self.assertEqual(request["current_itinerary_id"], current)
        self.assertNotEqual(request["itineraries"][0]["id"], current)

    def test_missing_selected_route_does_not_reset_reference(self):
        result = normalize(current_itinerary_id="previous-selection")
        self.assertIsNone(result["request"])
        self.assertIn("CURRENT_ITINERARY_MISSING", [item["code"] for item in result["issues"]])

    def test_grouped_walking_is_continuous_and_has_only_supplied_time(self):
        item = route()
        middle = point(40.7005, -74.0)
        item["legs"][0]["steps"][:1] = [walk(ORIGIN_POINT, middle, 30), walk(middle, BOARD_POINT, 45)]
        result = normalize([item])
        request = self.assert_valid(result)
        legs = request["itineraries"][0]["legs"]
        self.assertEqual(len(legs), 3)
        self.assertEqual(legs[0]["provider_duration_seconds"], 75)
        self.assertEqual(legs[0]["to"], legs[1]["from"])
        self.assertIsNone(legs[0]["provider_departure_at"])

    def test_small_provider_geometry_snap_is_disclosed(self):
        item = route()
        item["legs"][0]["steps"][0]["endLocation"] = point(40.70101, -74.0)
        result = normalize([item])
        self.assert_valid(result)
        self.assertGreater(result["provenance"][0]["boundary_reconciliations"][0]["distance_metres"], 0)

    def test_explicit_station_access_with_150_metre_offset_is_flagged(self):
        item = route()
        item["legs"][0]["steps"][0]["endLocation"] = point(40.69965, -74.0)
        result = normalize([item])
        legs = self.assert_valid(result)["itineraries"][0]["legs"]
        self.assertEqual(legs[0]["provider_duration_seconds"], 60)
        self.assertEqual(legs[0]["to"], legs[1]["from"])
        self.assertEqual(result["issues"][0]["code"], "PROVIDER_PLATFORM_ACCESS_UNVERIFIED")
        record = result["provenance"][0]["boundary_reconciliations"][0]
        self.assertGreater(record["distance_metres"], 149)
        self.assertEqual(record["walking_duration_adjustment_seconds"], 0)
        self.assertNotEqual(record["walking_endpoint_coordinates"], record["station_point_coordinates"])
        stricter = normalize([item], station_boundary_tolerance_metres=100)
        self.assertIsNone(stricter["request"])

    def test_station_boundary_over_250_metres_is_rejected(self):
        item = route()
        item["legs"][0]["steps"][0]["endLocation"] = point(40.698, -74.0)
        result = normalize([item])
        self.assertIsNone(result["request"])
        self.assertEqual(result["issues"][0]["code"], "DISCONNECTED_PROVIDER_GEOMETRY")

    def test_walking_to_walking_gap_keeps_strict_tolerance(self):
        item = route()
        item["legs"][0]["steps"][:1] = [walk(ORIGIN_POINT, point(40.7004, -74)),
                                          walk(point(40.701, -74), BOARD_POINT)]
        result = normalize([item])
        self.assertIsNone(result["request"])
        self.assertEqual(result["issues"][0]["code"], "DISCONNECTED_PROVIDER_GEOMETRY")

    def test_disconnected_walk_is_rejected(self):
        item = route()
        item["legs"][0]["steps"][0]["endLocation"] = point(40.71, -74.0)
        result = normalize([item])
        self.assertIsNone(result["request"])
        self.assertEqual(result["issues"][0]["code"], "DISCONNECTED_PROVIDER_GEOMETRY")

    def test_missing_walking_duration_is_rejected(self):
        item = route()
        del item["legs"][0]["steps"][0]["staticDuration"]
        result = normalize([item])
        self.assertIsNone(result["request"])
        self.assertEqual(result["issues"][0]["code"], "MISSING_OR_INVALID_DURATION")

    def test_missing_transit_timing_is_rejected(self):
        item = route()
        del item["legs"][0]["steps"][1]["transitDetails"]["stopDetails"]["arrivalTime"]
        result = normalize([item])
        self.assertIsNone(result["request"])
        self.assertEqual(result["issues"][0]["code"], "MISSING_TRANSIT_TIMING")

    def test_static_train_duration_discrepancy_is_preserved(self):
        item = route()
        item["legs"][0]["steps"][1]["staticDuration"] = "850s"
        result = normalize([item])
        request = self.assert_valid(result)
        self.assertEqual(request["itineraries"][0]["legs"][1]["provider_duration_seconds"], 900)
        self.assertEqual(result["provenance"][0]["subway_durations"][0]["static_duration_seconds"], 850)

    def test_unsupported_mode_and_agency_are_not_silently_subway(self):
        for change, expected in (("BUS", "UNSUPPORTED_TRANSIT_MODE"), ("agency", "UNSUPPORTED_AGENCY"), ("DRIVE", "UNSUPPORTED_MODE")):
            with self.subTest(change=change):
                item = route()
                step = item["legs"][0]["steps"][1]
                if change == "agency":
                    step["transitDetails"]["transitLine"]["agencies"] = [{"name": "Synthetic other operator"}]
                elif change == "DRIVE":
                    step["travelMode"] = change
                else:
                    step["transitDetails"]["transitLine"]["vehicle"]["type"] = change
                result = normalize([item, route()])
                self.assertEqual(len(self.assert_valid(result)["itineraries"]), 1)
                self.assertEqual(result["issues"][0]["code"], expected)
                self.assertEqual(result["provenance"][0]["status"], "REJECTED")

    def test_consecutive_subways_do_not_turn_wait_gap_into_walking(self):
        item = route()
        second = subway(ALIGHT_POINT, ALIGHT_POINT, "C", "2026-11-19T12:25:00Z", "2026-11-19T12:30:00Z")
        item["legs"][0]["steps"].insert(2, second)
        result = normalize([item])
        self.assertIsNone(result["request"])
        self.assertEqual(result["issues"][0]["code"], "MISSING_TRANSFER_WALK")

    def test_explicit_transfer_walk_is_kept(self):
        item = route()
        transfer = point(40.7202, -74.0)
        second = subway(transfer, ALIGHT_POINT, "C", "2026-11-19T12:25:00Z", "2026-11-19T12:30:00Z")
        item["legs"][0]["steps"][2:2] = [walk(ALIGHT_POINT, transfer, 20), second]
        result = normalize([item])
        legs = self.assert_valid(result)["itineraries"][0]["legs"]
        self.assertEqual([leg["mode"] for leg in legs], ["WALK", "SUBWAY", "WALK", "SUBWAY", "WALK"])
        self.assertEqual(legs[2]["provider_duration_seconds"], 20)

    def test_impossible_provider_transfer_cannot_win_deduplication(self):
        item = route()
        transfer = point(40.7202, -74.0)
        second = subway(transfer, ALIGHT_POINT, "C", "2026-11-19T12:05:00Z", "2026-11-19T12:10:00Z")
        item["legs"][0]["steps"][2:2] = [walk(ALIGHT_POINT, transfer, 20), second]
        result = normalize([item, route()])
        self.assertEqual(len(self.assert_valid(result)["itineraries"]), 1)
        self.assertEqual(result["issues"][0]["code"], "UNREACHABLE_PROVIDER_TRANSFER")

    def test_current_identity_ignores_endpoint_display_label(self):
        current = normalize()["request"]["itineraries"][0]["id"]
        origin = endpoint("Synthetic origin", ORIGIN_POINT)
        origin["name"] = "Updated display label for the same origin"
        request = self.assert_valid(normalize(origin=origin, current_itinerary_id=current))
        self.assertEqual(request["current_itinerary_id"], current)

    def test_observations_after_cutoff_are_rejected(self):
        result = normalize(received_at="2026-11-19T12:00:03Z")
        self.assertIsNone(result["request"])
        self.assertEqual(result["issues"][0]["code"], "INVALID_SNAPSHOT_TIMING")

    def test_unverified_endpoint_coordinates_remain_null(self):
        origin = endpoint("Synthetic origin", ORIGIN_POINT)
        origin["coordinates"] = None
        result = normalize(origin=origin)
        self.assertIsNone(self.assert_valid(result)["origin"]["coordinates"])
        self.assertEqual(result["provenance"][0]["unverified_endpoint_coordinates"], ["origin"])

    def test_pure_walking_candidate_has_a_complete_provider_eta(self):
        item = {"duration": "120s", "legs": [{"steps": [walk(ORIGIN_POINT, DESTINATION_POINT, 120)]}]}
        result = normalize([item])
        self.assertEqual(self.assert_valid(result)["itineraries"][0]["provider_eta"], "2026-11-19T12:02:00Z")
        self.assertEqual(result["provenance"][0]["eta_basis"], "WALKING_FROM_QUERY")

    def test_bad_timestamps_and_nonfinite_coordinates_are_rejected(self):
        for bad in ("2026-11-19T12:00:00", "2026-02-31T12:00:00Z", "2026-11-19T12:00:00+01:99"):
            with self.subTest(timestamp=bad):
                self.assertEqual(normalize(queried_at=bad)["issues"][0]["code"], "INVALID_TIMESTAMP")
        for bad in (float("nan"), float("inf"), 10 ** 500, True):
            with self.subTest(coordinate=bad):
                item = route()
                item["legs"][0]["steps"][0]["startLocation"]["latLng"]["latitude"] = bad
                self.assertIsNone(normalize([item])["request"])

    def test_changed_boarding_stop_is_a_different_itinerary(self):
        item = route()
        item["legs"][0]["steps"][1]["transitDetails"]["stopDetails"]["departureStop"]["name"] = "Synthetic other boarding"
        result = normalize([route(), item])
        self.assertEqual(len(self.assert_valid(result)["itineraries"]), 2)

    def test_conflicting_location_ids_cannot_escape_as_a_valid_request(self):
        initial = self.assert_valid(normalize())
        origin = endpoint("Synthetic origin", ORIGIN_POINT)
        origin["id"] = initial["itineraries"][0]["legs"][1]["from"]["id"]
        result = normalize(origin=origin)
        self.assertIsNone(result["request"])
        self.assertEqual(result["issues"][0]["code"], "CONFLICTING_LOCATION_ID")

    def test_missing_access_or_egress_walk_is_not_replaced_by_zero(self):
        for removed in (0, -1):
            with self.subTest(removed=removed):
                item = route()
                del item["legs"][0]["steps"][removed]
                origin = endpoint("Synthetic origin", ORIGIN_POINT)
                destination = endpoint("Synthetic destination", DESTINATION_POINT)
                origin["coordinates"] = destination["coordinates"] = None
                result = normalize([item], origin=origin, destination=destination)
                self.assertIsNone(result["request"])
                self.assertIn(result["issues"][0]["code"], ("MISSING_ACCESS_WALK", "MISSING_EGRESS_WALK"))

    def test_no_routes_and_malformed_payloads_are_explicit(self):
        self.assertEqual(normalize([])["issues"][0]["code"], "NO_ROUTES")
        for item in (None, {}, {"duration": "1020s", "legs": [{"steps": [None]}]}):
            with self.subTest(item=item):
                self.assertIsNone(normalize([item])["request"])

    def test_inputs_are_not_mutated(self):
        item = route()
        before = copy.deepcopy(item)
        normalize([item])
        self.assertEqual(item, before)


if __name__ == "__main__":
    unittest.main()
