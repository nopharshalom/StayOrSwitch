"""Synthetic boundary checks for Step 2 station and service matching."""

from copy import deepcopy
from datetime import datetime, timezone
import unittest

from stayorswitch.matching import map_station, match_request


NOW = datetime(2026, 11, 19, 20, 0, tzinfo=timezone.utc).timestamp()


def stamp(offset=0):
    return datetime.fromtimestamp(NOW + offset, timezone.utc).isoformat().replace("+00:00", "Z")


def station(number):
    return {"id": "provider-" + number, "name": "Station " + number,
            "coordinates": {"latitude": 40.75 + int(number) / 100, "longitude": -73.94},
            "provider_place_id": None, "mta_stop_id": None}


def static_data():
    stops = {}
    for number in ("1", "2", "3"):
        for suffix in ("", "N", "S"):
            identifier = "P" + number + suffix
            stops[identifier] = {"id": identifier, "name": "Station " + number,
                                 "latitude": 40.75 + int(number) / 100, "longitude": -73.94,
                                 "parent_station": "P" + number if suffix else "",
                                 "location_type": 0 if suffix else 1}
    return {"stops": stops, "routes": {"F": {"short_name": "F"}, "G": {"short_name": "G"}},
            "route_stops": {"F": list(stops), "G": [key for key in stops if key.startswith(("P2", "P3"))]}}


def walk(identifier, start, end, duration):
    return {"id": identifier, "mode": "WALK", "from": start, "to": end,
            "provider_duration_seconds": duration, "provider_departure_at": None,
            "provider_arrival_at": None, "transit": None}


def subway(identifier="ride", start=None, end=None, line="F"):
    return {"id": identifier, "mode": "SUBWAY", "from": start or station("1"), "to": end or station("2"),
            "provider_duration_seconds": 200, "provider_departure_at": stamp(100), "provider_arrival_at": stamp(300),
            "transit": {"agency": "MTA New York City Transit", "route_short_name": line, "provider_route_id": None,
                        "headsign": "Untrusted provider headsign", "direction_id": None, "provider_trip_id": None}}


def request(legs=None):
    origin, destination = station("1"), station("2")
    return {"schema_version": "1.0", "request_id": "synthetic-matching-check", "data_mode": "simulated",
            "decision_time": stamp(), "user_state": "NOT_BOARDED", "origin": origin, "destination": destination,
            "current_itinerary_id": "selected", "itineraries": [{"id": "selected",
                "provider": {"name": "synthetic", "itinerary_id": None, "queried_at": stamp(-10)},
                "provider_eta": stamp(400), "legs": legs or [walk("access", origin, origin, 60), subway(),
                                                             walk("egress", destination, destination, 90)]}]}


def trip(identifier="train", line="F", feed="bdfm", departure=100, arrival=300,
         start="P1N", end="P2N", relationship="SCHEDULED"):
    return {"id": "MTA/" + feed + "/20261119/" + line + "/" + identifier, "feed_id": feed,
            "route_id": line, "trip_id": identifier, "start_date": "20261119", "start_time": "14:00:00",
            "direction_id": 0, "schedule_relationship": relationship, "reason_codes": [],
            "stop_updates": [{"stop_id": start, "stop_sequence": 1, "arrival_time": NOW + departure,
                              "departure_time": NOW + departure, "schedule_relationship": "SCHEDULED"},
                             {"stop_id": end, "stop_sequence": 2, "arrival_time": NOW + arrival,
                              "departure_time": NOW + arrival, "schedule_relationship": "SCHEDULED"}]}


def snapshot(trips=None, feed="bdfm", fetched=-5, source=-10, kind="train", alerts=None):
    return {"feed_id": feed, "kind": kind, "status": "AVAILABLE", "requested_at": stamp(fetched - 1),
            "fetched_at": stamp(fetched), "source_updated_at": stamp(source), "reason_codes": [],
            "trips": trips if trips is not None else [trip()], "alerts": alerts or []}


def first_subway(report):
    return next(leg for leg in report["itineraries"][0]["legs"] if leg["mode"] == "SUBWAY")


class MatchingTests(unittest.TestCase):
    def test_preserves_reference_and_provider_eta_without_emitting_decision(self):
        original = request()
        untouched = deepcopy(original)
        result = match_request(original, static_data(), [snapshot()])
        self.assertEqual(result["current_itinerary_id"], "selected")
        self.assertEqual(result["itineraries"][0]["provider_eta"], stamp(400))
        self.assertEqual(result["itineraries"][0]["status"], "MATCHED")
        self.assertNotIn("decision", result)
        self.assertNotIn("eta", result["itineraries"][0])
        self.assertEqual(original, untouched)
        leg = first_subway(result)
        self.assertEqual(leg["platform_ready_at"], stamp(60))
        self.assertEqual(leg["candidates"][0]["platform_direction"], "N")
        self.assertIn("20261119", leg["candidates"][0]["trip_id"])

    def test_excludes_departure_before_access_walk_finishes(self):
        trains = [trip("missed", departure=59), trip("catchable", departure=60)]
        leg = first_subway(match_request(request(), static_data(), [snapshot(trains)]))
        self.assertEqual([x["raw_trip_id"] for x in leg["candidates"]], ["catchable"])
        self.assertIn("DEPARTS_BEFORE_READY", [x["reason_code"] for x in leg["rejected_candidates"]])

    def test_does_not_match_reverse_stop_order_or_conflicting_platforms(self):
        reverse = trip("reverse", start="P2S", end="P1S")
        conflict = trip("conflict", start="P1N", end="P2S")
        leg = first_subway(match_request(request(), static_data(), [snapshot([reverse, conflict])]))
        self.assertEqual(leg["status"], "UNMATCHED")
        self.assertEqual({x["reason_code"] for x in leg["rejected_candidates"]},
                         {"STOPS_IN_REVERSE_ORDER", "PLATFORM_DIRECTION_CONFLICT"})

    def test_nearby_equal_name_stations_remain_ambiguous(self):
        data = static_data()
        for suffix in ("", "N", "S"):
            new = deepcopy(data["stops"]["P1" + suffix])
            new["id"], new["parent_station"] = "OTHER" + suffix, "OTHER" if suffix else ""
            data["stops"][new["id"]] = new
            data["route_stops"]["F"].append(new["id"])
        result = map_station(station("1"), {"F"}, data)
        self.assertEqual(result["status"], "AMBIGUOUS")
        self.assertIsNone(result["station_id"])

    def test_unrelated_line_does_not_win_station_match_by_distance(self):
        mapped = map_station(station("1"), {"G"}, static_data())
        self.assertEqual(mapped["status"], "UNMATCHED")

    def test_live_reroute_stops_augment_static_line_membership(self):
        req = request()
        req["itineraries"][0]["legs"][1]["transit"]["route_short_name"] = "G"
        result = match_request(req, static_data(), [snapshot([trip(line="G", feed="g")], feed="g")])
        self.assertEqual(first_subway(result)["status"], "MATCHED")

    def test_explicit_platform_id_is_not_changed_to_another_direction(self):
        req = request()
        req["itineraries"][0]["legs"][1]["from"]["mta_stop_id"] = "P1S"
        leg = first_subway(match_request(req, static_data(), [snapshot()]))
        self.assertEqual(leg["boarding_station"]["platform_stop_ids"], ["P1S"])
        self.assertEqual(leg["candidates"], [])

    def test_transfer_walk_is_added_before_selecting_second_service(self):
        one, two, three = station("1"), station("2"), station("3")
        req = request([walk("access", one, one, 60), subway(), walk("transfer", two, two, 45),
                       subway("second", two, three, "G"), walk("exit", three, three, 20)])
        feeds = [snapshot(), snapshot([trip("too-early", "G", "g", 330, 600, "P2S", "P3S"),
                                       trip("next", "G", "g", 400, 700, "P2S", "P3S")], feed="g")]
        result = match_request(req, static_data(), feeds)
        second = result["itineraries"][0]["legs"][3]
        self.assertEqual(second["platform_ready_at"], stamp(345))
        self.assertEqual([x["raw_trip_id"] for x in second["candidates"]], ["next"])
        self.assertEqual(second["status"], "MATCHED")

    def test_missing_transfer_walk_does_not_invent_zero_seconds(self):
        req = request([subway(), subway("second", station("2"), station("3"), "G")])
        feeds = [snapshot(), snapshot([trip("next", "G", "g", 400, 700, "P2S", "P3S")], feed="g")]
        second = match_request(req, static_data(), feeds)["itineraries"][0]["legs"][1]
        self.assertIn("MISSING_TRANSFER_WALK", second["reason_codes"])
        self.assertIsNone(second["platform_ready_at"])
        self.assertIsNone(second["candidates"][0]["catchable"])

    def test_unresolved_first_leg_prevents_downstream_reachability_claim(self):
        req = request([subway(), walk("transfer", station("2"), station("2"), 45),
                       subway("second", station("2"), station("3"), "G")])
        feeds = [snapshot([], feed="bdfm"), snapshot([trip("next", "G", "g", 400, 700, "P2S", "P3S")], feed="g")]
        second = match_request(req, static_data(), feeds)["itineraries"][0]["legs"][2]
        self.assertEqual(second["status"], "UNMATCHED")
        self.assertIsNone(second["platform_ready_at"])
        self.assertIn("UPSTREAM_REACHABILITY_UNKNOWN", second["reason_codes"])

    def test_stale_missing_and_future_feeds_cannot_supply_candidates(self):
        stale = snapshot(source=-181)
        missing = snapshot()
        missing["status"] = "MISSING"
        future = snapshot(fetched=1, source=0)
        future_source = snapshot(source=1)
        for feed in (stale, missing, future, future_source):
            with self.subTest(feed=feed):
                result = match_request(request(), static_data(), [feed])
                self.assertEqual(first_subway(result)["candidates"], [])
                self.assertEqual(result["itineraries"][0]["status"], "UNMATCHED")

    def test_asof_selection_ignores_newer_future_observation(self):
        available = snapshot([trip("asof")])
        future = snapshot([trip("future")], fetched=1, source=0)
        leg = first_subway(match_request(request(), static_data(), [available, future]))
        self.assertEqual(leg["candidates"][0]["raw_trip_id"], "asof")

    def test_latest_failure_does_not_resurrect_previous_feed_entities(self):
        earlier = snapshot(fetched=-10, source=-15)
        failure = snapshot(fetched=-1, source=-2)
        failure["status"] = "MISSING"
        result = match_request(request(), static_data(), [earlier, failure])
        self.assertEqual(first_subway(result)["candidates"], [])

    def test_tied_conflicting_snapshots_fail_closed_in_either_order(self):
        success = snapshot()
        failure = snapshot()
        failure["status"] = "MISSING"
        changed = snapshot([trip("different")])
        for observations in ([success, failure], [failure, success], [success, changed], [changed, success]):
            result = match_request(request(), static_data(), observations)
            self.assertEqual(first_subway(result)["candidates"], [])
            state = next(feed for feed in result["feed_status"] if feed["feed_id"] == "bdfm")
            self.assertEqual(state["status"], "MISSING")

    def test_trip_observation_time_is_distinct_from_future_predictions(self):
        fresh = trip("fresh")
        fresh["timestamp"] = NOW - 15
        stale = trip("stale")
        stale["timestamp"] = NOW - 181
        future = trip("future")
        future["timestamp"] = NOW + 1
        after_fetch = trip("after-fetch")
        after_fetch["timestamp"] = NOW - 1
        leg = first_subway(match_request(request(), static_data(), [snapshot([fresh, stale, future, after_fetch])]))
        self.assertEqual([x["raw_trip_id"] for x in leg["candidates"]], ["fresh"])
        self.assertEqual({x["reason_code"] for x in leg["rejected_candidates"]},
                         {"STALE_TRIP_OBSERVATION", "FUTURE_TRIP_OBSERVATION"})

    def test_canceled_skipped_and_missing_times_remain_explicit(self):
        canceled = trip("canceled", relationship="CANCELED")
        skipped = trip("skipped")
        skipped["stop_updates"][1]["schedule_relationship"] = "SKIPPED"
        missing = trip("missing")
        missing["stop_updates"][1]["arrival_time"] = None
        nodata = trip("no-data")
        nodata["stop_updates"][0]["schedule_relationship"] = "NO_DATA"
        leg = first_subway(match_request(request(), static_data(), [snapshot([canceled, skipped, missing, nodata])]))
        self.assertEqual(leg["candidates"], [])
        self.assertEqual({x["reason_code"] for x in leg["rejected_candidates"]},
                         {"TRIP_CANCELED", "STOP_SKIPPED", "MISSING_STOP_TIME", "STOP_PREDICTION_UNAVAILABLE"})

    def test_arrival_proxy_is_marked_when_boarding_departure_absent(self):
        train = trip()
        train["stop_updates"][0]["departure_time"] = None
        candidate = first_subway(match_request(request(), static_data(), [snapshot([train])]))["candidates"][0]
        self.assertEqual(candidate["boarding_time_source"], "ARRIVAL_PROXY")
        self.assertIn("BOARDING_TIME_USES_ARRIVAL_PROXY", candidate["reason_codes"])

    def test_service_date_is_required_for_trip_identity(self):
        train = trip()
        train["start_date"] = None
        leg = first_subway(match_request(request(), static_data(), [snapshot([train])]))
        self.assertEqual(leg["candidates"], [])
        self.assertEqual(leg["rejected_candidates"][0]["reason_code"], "MISSING_SERVICE_DATE_IDENTITY")

    def test_stale_or_future_provider_data_is_not_freshened(self):
        for offset, reason in ((-301, "STALE_PROVIDER_DATA"), (1, "PROVIDER_DATA_AFTER_DECISION")):
            req = request()
            req["itineraries"][0]["provider"]["queried_at"] = stamp(offset)
            result = match_request(req, static_data(), [snapshot()])
            self.assertEqual(result["itineraries"][0]["status"], "UNMATCHED")
            self.assertIn(reason, result["itineraries"][0]["reason_codes"])
            self.assertIsNone(first_subway(result)["platform_ready_at"])

    def test_alerts_use_active_period_and_selectors_not_header_age(self):
        def alert(identifier, selectors, periods):
            return {"id": identifier, "effect": "MODIFIED_SERVICE", "cause": "OTHER_CAUSE",
                    "header": "Synthetic service notice", "description": "Synthetic details",
                    "informed_entities": selectors, "active_periods": periods}
        alerts = [alert("network", [], []),
                  alert("route", [{"route_id": "F"}], [{"start": NOW - 60, "end": NOW + 60}]),
                  alert("wrong-route", [{"route_id": "G"}], []),
                  alert("expired", [{"route_id": "F"}], [{"end": NOW}]),
                  alert("during-ride", [{"route_id": "F"}], [{"start": NOW + 150, "end": NOW + 250}]),
                  alert("later", [{"route_id": "F"}], [{"start": NOW + 1000}]),
                  alert("wrong-direction", [{"route_id": "F", "direction_id": 1}], [])]
        result = match_request(request(), static_data(), [snapshot(),
            snapshot([], feed="subway-alerts", source=-86400, kind="alerts", alerts=alerts)])
        leg = first_subway(result)
        self.assertEqual({a["id"] for a in leg["alerts"]}, {"network", "route", "during-ride"})
        self.assertIn("ACTIVE_SERVICE_ALERT", leg["reason_codes"])
        self.assertNotIn("ALERTS_FEED_STALE", leg["reason_codes"])

    def test_stale_alert_fetch_is_not_used_as_current_service_info(self):
        alert = {"id": "old", "active_periods": [], "informed_entities": []}
        result = match_request(request(), static_data(), [snapshot(),
            snapshot([], feed="subway-alerts", source=-500, fetched=-400, kind="alerts", alerts=[alert])])
        leg = first_subway(result)
        self.assertEqual(leg["alerts"], [])
        self.assertIn("ALERTS_FEED_STALE", leg["reason_codes"])

    def test_mapping_tolerance_does_not_limit_walking_duration(self):
        req = request()
        req["itineraries"][0]["legs"][0]["provider_duration_seconds"] = 3600
        train = trip(departure=3700, arrival=4000)
        result = match_request(req, static_data(), [snapshot([train])])
        self.assertEqual(first_subway(result)["status"], "MATCHED")
        self.assertEqual(first_subway(result)["platform_ready_at"], stamp(3600))

    def test_express_variant_uses_actual_stop_pair(self):
        data = static_data()
        data["routes"]["FX"] = {"short_name": "FX"}
        data["route_stops"]["FX"] = list(data["stops"])
        result = match_request(request(), data, [snapshot([trip(line="FX")])])
        self.assertEqual(first_subway(result)["candidates"][0]["route_id"], "FX")

    def test_unknown_route_feed_is_explicitly_unsupported(self):
        req = request()
        req["itineraries"][0]["legs"][1]["transit"]["route_short_name"] = "UNKNOWN"
        leg = first_subway(match_request(req, static_data(), [snapshot()]))
        self.assertIn("UNSUPPORTED_ROUTE_FEED", leg["reason_codes"])
        self.assertEqual(leg["status"], "UNMATCHED")

    def test_other_operator_cannot_be_matched_by_shared_line_name(self):
        req = request()
        req["itineraries"][0]["legs"][1]["transit"]["agency"] = "Another rail operator"
        leg = first_subway(match_request(req, static_data(), [snapshot()]))
        self.assertEqual(leg["candidates"], [])
        self.assertIn("UNSUPPORTED_TRANSIT_AGENCY", leg["reason_codes"])

    def test_intermediate_stop_and_waiting_period_alerts_are_relevant(self):
        train = trip()
        train["stop_updates"][1]["stop_sequence"] = 3
        train["stop_updates"].insert(1, {"stop_id": "P3N", "stop_sequence": 2,
            "arrival_time": NOW + 200, "departure_time": NOW + 210, "schedule_relationship": "SCHEDULED"})
        alerts = [{"id": "intermediate", "active_periods": [], "informed_entities": [{"stop_id": "P3"}]},
                  {"id": "while-waiting", "active_periods": [{"start": NOW + 65, "end": NOW + 90}],
                   "informed_entities": [{"route_id": "F"}]}]
        result = match_request(request(), static_data(), [snapshot([train]),
            snapshot([], feed="subway-alerts", kind="alerts", alerts=alerts)])
        leg = first_subway(result)
        self.assertEqual({alert["id"] for alert in leg["alerts"]}, {"intermediate", "while-waiting"})
        self.assertIn("P3N", leg["candidates"][0]["segment_stop_ids"])

    def test_alert_trip_and_time_constraints_must_match_same_candidate(self):
        early, later = trip("early", arrival=120), trip("later", departure=200, arrival=360)
        alert = {"id": "early-only-later-period", "active_periods": [{"start": NOW + 300, "end": NOW + 360}],
                 "informed_entities": [{"trip": {"trip_id": "early"}}]}
        result = match_request(request(), static_data(), [snapshot([early, later]),
            snapshot([], feed="subway-alerts", kind="alerts", alerts=[alert])])
        self.assertEqual(first_subway(result)["alerts"], [])

    def test_alert_trip_and_stop_constraints_must_match_same_candidate(self):
        direct, stopping = trip("direct"), trip("stopping")
        stopping["stop_updates"][1]["stop_sequence"] = 3
        stopping["stop_updates"].insert(1, {"stop_id": "P3N", "stop_sequence": 2,
            "arrival_time": NOW + 200, "departure_time": NOW + 210, "schedule_relationship": "SCHEDULED"})
        alerts = [{"id": "not-direct-stop", "active_periods": [],
                   "informed_entities": [{"stop_id": "P3", "trip": {"trip_id": "direct"}}]},
                  {"id": "unbounded", "active_periods": [], "informed_entities": [{"route_id": "F"}]}]
        result = match_request(request(), static_data(), [snapshot([direct, stopping]),
            snapshot([], feed="subway-alerts", kind="alerts", alerts=alerts)])
        selected = first_subway(result)["alerts"]
        self.assertEqual([a["id"] for a in selected], ["unbounded"])
        self.assertTrue(selected[0]["overlaps_candidate_interval"])


if __name__ == "__main__":
    unittest.main()
