"""Synthetic journey arithmetic and coverage checks, not observed accuracy claims."""

from copy import deepcopy
from datetime import datetime, timezone
import unittest

from stayorswitch.baseline import evaluate_baseline, evaluate_integration
from stayorswitch.matching import match_request


NOW = datetime(2026, 11, 19, 20, 0, tzinfo=timezone.utc).timestamp()


def stamp(offset=0):
    return datetime.fromtimestamp(NOW + offset, timezone.utc).isoformat().replace("+00:00", "Z")


def location(number):
    return {"id": "location-" + str(number), "name": "Synthetic station " + str(number),
            "coordinates": None, "provider_place_id": None, "mta_stop_id": "P" + str(number)}


def static_data():
    stops = {}
    for number in range(1, 4):
        for suffix in ("", "N", "S"):
            stop_id = "P" + str(number) + suffix
            stops[stop_id] = {"id": stop_id, "name": "Synthetic station " + str(number),
                              "latitude": None, "longitude": None,
                              "parent_station": "P" + str(number) if suffix else "",
                              "location_type": 0 if suffix else 1}
    return {"stops": stops, "routes": {line: {"short_name": line} for line in ("F", "G")},
            "route_stops": {line: list(stops) for line in ("F", "G")}}


def walk(identifier, start, end, seconds):
    return {"id": identifier, "mode": "WALK", "from": location(start), "to": location(end),
            "provider_duration_seconds": seconds, "provider_departure_at": None,
            "provider_arrival_at": None, "transit": None}


def subway(identifier="ride", line="F", start=1, end=2, departure=100, arrival=300):
    return {"id": identifier, "mode": "SUBWAY", "from": location(start), "to": location(end),
            "provider_duration_seconds": arrival - departure, "provider_departure_at": stamp(departure),
            "provider_arrival_at": stamp(arrival),
            "transit": {"agency": "MTA New York City Transit", "route_short_name": line,
                        "provider_route_id": None, "headsign": None, "direction_id": None,
                        "provider_trip_id": None}}


def route(identifier="current", line="F", access=60, exit_seconds=90, legs=None, queried=-10):
    return {"id": identifier, "provider": {"name": "synthetic", "itinerary_id": None,
                                           "queried_at": stamp(queried)},
            "provider_eta": stamp(300 + exit_seconds),
            "legs": legs or [walk("access", 1, 1, access), subway(line=line), walk("exit", 2, 2, exit_seconds)]}


def request(routes=None, current="current", destination=2):
    return {"schema_version": "1.0", "request_id": "synthetic-baseline", "data_mode": "simulated",
            "decision_time": stamp(), "user_state": "NOT_BOARDED", "origin": location(1),
            "destination": location(destination), "current_itinerary_id": current,
            "itineraries": routes or [route()]}


def trip(identifier="train", line="F", departure=100, arrival=300, start=1, end=2, relationship="SCHEDULED"):
    feed = "bdfm" if line == "F" else "g"
    return {"id": "MTA/" + feed + "/20261119/" + line + "/" + identifier,
            "feed_id": feed, "trip_id": identifier, "route_id": line, "start_date": "20261119",
            "start_time": "14:00:00", "direction_id": 0, "schedule_relationship": relationship,
            "reason_codes": [], "stop_updates": [
                {"stop_id": "P" + str(start) + "N", "stop_sequence": 1, "arrival_time": NOW + departure,
                 "departure_time": NOW + departure, "schedule_relationship": "SCHEDULED"},
                {"stop_id": "P" + str(end) + "N", "stop_sequence": 2, "arrival_time": NOW + arrival,
                 "departure_time": NOW + arrival, "schedule_relationship": "SCHEDULED"}]}


def snapshot(trips=None, feed="bdfm", source=-10, fetched=-5, alerts=None):
    return {"feed_id": feed, "kind": "alerts" if feed == "subway-alerts" else "train",
            "status": "AVAILABLE", "source_updated_at": stamp(source), "fetched_at": stamp(fetched),
            "requested_at": stamp(fetched - 1), "reason_codes": [],
            "trips": trips or [], "alerts": alerts or []}


def alert(identifier="notice", effect="NO_SERVICE", start=0, end=900, trip_id=None, line="F"):
    selector = {"route_id": line}
    if trip_id:
        selector["trip"] = {"trip_id": trip_id}
    return {"id": identifier, "effect": effect, "cause": "MAINTENANCE", "header": "Synthetic notice",
            "description": "Synthetic service information.", "active_periods": [{"start": NOW + start, "end": NOW + end}],
            "informed_entities": [selector]}


def evaluate(req=None, feeds=None, *, with_alerts=True, **options):
    req = req or request()
    feeds = list(feeds) if feeds is not None else [snapshot([trip()])]
    if with_alerts and not any(feed.get("kind") == "alerts" for feed in feeds):
        feeds.append(snapshot(feed="subway-alerts"))
    return evaluate_baseline(req, match_request(req, static_data(), feeds), evaluated_at=stamp(1), **options)


class BaselineTests(unittest.TestCase):
    def test_full_destination_eta_accounts_for_every_component(self):
        response = evaluate()["response"]
        result = response["itineraries"][0]
        self.assertEqual(result["eta"], stamp(390))
        self.assertEqual(result["total_duration_seconds"], 390)
        self.assertEqual(result["components"], {"walking_seconds": 150, "waiting_seconds": 40, "riding_seconds": 200})
        self.assertTrue(result["comparison_eligible"])
        self.assertEqual(result["method"], "MTA_REALTIME")
        self.assertIsNone(response["model_version"])
        self.assertIsNone(result["uncertainty"])

    def test_later_departure_can_arrive_earlier(self):
        report = evaluate(feeds=[snapshot([trip("local", departure=100, arrival=600),
                                           trip("express", departure=180, arrival=450)])])
        result = report["response"]["itineraries"][0]
        self.assertEqual(result["eta"], stamp(540))
        self.assertTrue(result["legs"][1]["matched_mta_trip_id"].endswith("/express"))

    def test_transfer_walk_and_wait_are_sequential(self):
        legs = [walk("access", 1, 1, 60), subway(), walk("transfer", 2, 2, 45),
                subway("second", "G", 2, 3, 330, 600), walk("exit", 3, 3, 20)]
        req = request([route(legs=legs)], destination=3)
        feeds = [snapshot([trip()]), snapshot([trip("missed", "G", 330, 600, 2, 3),
                                               trip("catchable", "G", 360, 700, 2, 3)], feed="g")]
        result = evaluate(req, feeds)["response"]["itineraries"][0]
        self.assertEqual(result["total_duration_seconds"], 720)
        self.assertEqual(result["components"], {"walking_seconds": 125, "waiting_seconds": 55, "riding_seconds": 540})
        self.assertTrue(result["legs"][3]["matched_mta_trip_id"].endswith("/catchable"))

    def test_provider_fallback_upstream_rechecks_live_transfer(self):
        legs = [walk("access", 1, 1, 60), subway(), walk("transfer", 2, 2, 45),
                subway("second", "G", 2, 3, 330, 600), walk("exit", 3, 3, 20)]
        req = request([route(legs=legs)], destination=3)
        feeds = [snapshot([trip("missed", "G", 330, 600, 2, 3),
                           trip("catchable", "G", 360, 700, 2, 3)], feed="g")]
        result = evaluate(req, feeds)["response"]["itineraries"][0]
        self.assertEqual(result["method"], "MIXED")
        self.assertFalse(result["comparison_eligible"])
        self.assertEqual(result["eta"], stamp(720))
        self.assertEqual(result["legs"][1]["source"], "PROVIDER")
        self.assertTrue(result["legs"][3]["matched_mta_trip_id"].endswith("/catchable"))

    def test_no_current_does_not_invent_a_stay_reference(self):
        response = evaluate(request(current=None))["response"]
        self.assertEqual(response["decision"]["action"], "NOT_APPLICABLE")
        self.assertEqual(response["decision"]["recommended_itinerary_id"], "current")
        self.assertIsNone(response["decision"]["estimated_savings_seconds"])
        self.assertFalse(response["decision"]["comparison_complete"])

    def test_single_current_is_not_proof_staying_is_best(self):
        response = evaluate()["response"]
        self.assertEqual(response["decision"]["action"], "UNDETERMINED")
        self.assertEqual(response["decision"]["reason_codes"], ["NO_ALTERNATIVES"])

    def test_faster_alternative_yields_switch_and_exact_savings(self):
        req = request([route(), route("alternative", "G")])
        feeds = [snapshot([trip(arrival=600)]), snapshot([trip("second", "G", arrival=300)], feed="g")]
        decision = evaluate(req, feeds)["response"]["decision"]
        self.assertEqual(decision["action"], "SWITCH")
        self.assertEqual(decision["estimated_savings_seconds"], 300)
        self.assertTrue(decision["comparison_complete"])

    def test_exact_tie_favors_current_even_when_listed_last(self):
        req = request([route("alternative", "G"), route()])
        feeds = [snapshot([trip()]), snapshot([trip("second", "G")], feed="g")]
        decision = evaluate(req, feeds)["response"]["decision"]
        self.assertEqual(decision["action"], "STAY")
        self.assertEqual(decision["recommended_itinerary_id"], "current")
        self.assertEqual(decision["estimated_savings_seconds"], 0)

    def test_alternative_tie_uses_request_order(self):
        req = request([route(), route("first", "G"), route("second", "G")])
        feeds = [snapshot([trip(arrival=600)]), snapshot([trip("alternative", "G")], feed="g")]
        self.assertEqual(evaluate(req, feeds)["response"]["decision"]["recommended_itinerary_id"], "first")

    def test_fractional_savings_are_not_rounded_before_selection(self):
        req = request([route(), route("alternative", "G")])
        feeds = [snapshot([trip(arrival=300.2)]), snapshot([trip("second", "G", arrival=300.1)], feed="g")]
        decision = evaluate(req, feeds)["response"]["decision"]
        self.assertEqual(decision["action"], "SWITCH")
        self.assertAlmostEqual(decision["estimated_savings_seconds"], 0.1)

    def test_unknown_alternative_prevents_stay(self):
        req = request([route(), route("unknown", "G")])
        response = evaluate(req, allow_provider_fallback=False)["response"]
        self.assertEqual(response["decision"]["action"], "UNDETERMINED")
        self.assertEqual(response["decision"]["reason_codes"], ["UNASSESSED_ALTERNATIVES"])
        self.assertEqual(response["itineraries"][1]["status"], "UNAVAILABLE")

    def test_unknown_alternative_does_not_hide_known_faster_route(self):
        req = request([route(), route("fast", "G"), route("unknown", "G", access=1000)])
        feeds = [snapshot([trip(arrival=600)]), snapshot([trip("second", "G")], feed="g")]
        response = evaluate(req, feeds, allow_provider_fallback=False)["response"]
        self.assertEqual(response["decision"]["action"], "SWITCH")
        self.assertFalse(response["decision"]["comparison_complete"])
        self.assertIn("PARTIAL_COVERAGE", response["warnings"])

    def test_missing_current_estimate_does_not_make_switch_claim(self):
        req = request([route(), route("alternative", "G")])
        response = evaluate(req, [snapshot([trip("second", "G")], feed="g")])["response"]
        self.assertEqual(response["itineraries"][0]["method"], "PROVIDER_FALLBACK")
        self.assertEqual(response["decision"]["reason_codes"], ["CURRENT_UNAVAILABLE"])
        self.assertIsNone(response["decision"]["recommended_itinerary_id"])

    def test_missing_alerts_preserves_eta_but_withholds_comparison(self):
        response = evaluate(with_alerts=False)["response"]
        result = response["itineraries"][0]
        self.assertEqual(result["status"], "ESTIMATED")
        self.assertFalse(result["comparison_eligible"])
        self.assertIn("ALERTS_UNAVAILABLE", result["reason_codes"])
        self.assertEqual(response["data_status"]["alerts_feed"]["status"], "MISSING")

    def test_stale_alerts_are_not_silently_accepted(self):
        feeds = [snapshot([trip()]), snapshot(feed="subway-alerts", fetched=-400, source=-500)]
        response = evaluate(feeds=feeds)["response"]
        self.assertFalse(response["itineraries"][0]["comparison_eligible"])
        self.assertEqual(response["data_status"]["alerts_feed"]["status"], "STALE")

    def test_old_alert_source_is_acceptable_when_recently_fetched(self):
        feeds = [snapshot([trip()]), snapshot(feed="subway-alerts", source=-86400)]
        self.assertTrue(evaluate(feeds=feeds)["response"]["itineraries"][0]["comparison_eligible"])

    def test_provider_fallback_is_display_only_and_cannot_use_missed_departure(self):
        first = evaluate(feeds=[])["response"]["itineraries"][0]
        self.assertEqual(first["method"], "PROVIDER_FALLBACK")
        self.assertFalse(first["comparison_eligible"])
        second = evaluate(request([route(access=120)]), feeds=[])["response"]["itineraries"][0]
        self.assertEqual(second["status"], "UNAVAILABLE")
        self.assertIsNone(second["total_duration_seconds"])

    def test_stale_provider_walks_are_not_reused_even_with_fresh_trains(self):
        result = evaluate(request([route(queried=-301)]))["response"]["itineraries"][0]
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_stale_train_feed_is_labeled_and_uses_no_live_trip(self):
        response = evaluate(feeds=[snapshot([trip()], source=-181)])["response"]
        result = response["itineraries"][0]
        self.assertEqual(result["method"], "PROVIDER_FALLBACK")
        self.assertIsNone(result["legs"][1]["matched_mta_trip_id"])
        self.assertIn("STALE_TRAIN_FEED", result["reason_codes"])
        self.assertEqual(response["data_status"]["train_feed"]["status"], "STALE")

    def test_future_feed_cannot_supply_a_current_estimate(self):
        result = evaluate(feeds=[snapshot([trip()], source=1, fetched=2)],
                          allow_provider_fallback=False)["response"]["itineraries"][0]
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_unrelated_missing_feed_does_not_poison_summary(self):
        feeds = [snapshot([trip()]), {"feed_id": "ace", "status": "MISSING", "fetched_at": stamp(-1)}]
        response = evaluate(feeds=feeds)["response"]
        self.assertTrue(response["itineraries"][0]["comparison_eligible"])
        self.assertEqual(response["data_status"]["train_feed"]["status"], "FRESH")

    def test_missing_required_feed_summary_does_not_disable_unaffected_route(self):
        req = request([route(), route("unknown", "G")])
        response = evaluate(req)["response"]
        self.assertEqual(response["data_status"]["train_feed"],
                         {"status": "MISSING", "source_updated_at": None, "fetched_at": None})
        self.assertTrue(response["itineraries"][0]["comparison_eligible"])

    def test_cancelled_or_skipped_train_does_not_prove_route_infeasibility(self):
        canceled = trip(relationship="CANCELED")
        skipped = trip()
        skipped["stop_updates"][1]["schedule_relationship"] = "SKIPPED"
        for train in (canceled, skipped):
            with self.subTest(train=train["schedule_relationship"]):
                result = evaluate(feeds=[snapshot([train])], allow_provider_fallback=False)["response"]["itineraries"][0]
                self.assertEqual(result["status"], "UNAVAILABLE")
                self.assertIsNone(result["components"])

    def test_no_service_conflict_does_not_resurrect_provider_route(self):
        feeds = [snapshot([trip()]), snapshot(feed="subway-alerts", alerts=[alert()])]
        report = evaluate(feeds=feeds)
        self.assertEqual(report["response"]["itineraries"][0]["status"], "UNAVAILABLE")
        self.assertIn("NO_SERVICE_ALERT_CONFLICT", [item["reason_code"] for item in
                      report["diagnostics"]["itineraries"][0]["legs"][1]["rejected_candidates"]])

    def test_no_service_alert_without_live_trains_also_blocks_provider_fallback(self):
        feeds = [snapshot([]), snapshot(feed="subway-alerts", alerts=[alert()])]
        report = evaluate(feeds=feeds)
        self.assertEqual(report["response"]["itineraries"][0]["status"], "UNAVAILABLE")
        self.assertIn("PROVIDER_SERVICE_ALERT_CONFLICT_UNRESOLVED",
                      report["diagnostics"]["itineraries"][0]["legs"][1]["reason_codes"])

    def test_known_future_no_service_blocks_provider_fallback_without_live_candidates(self):
        feeds = [snapshot([]), snapshot(feed="subway-alerts", alerts=[alert(start=60, end=900)])]
        result = evaluate(feeds=feeds)["response"]["itineraries"][0]
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_future_no_service_after_provider_arrival_does_not_block_display(self):
        feeds = [snapshot([]), snapshot(feed="subway-alerts", alerts=[alert(start=600, end=900)])]
        result = evaluate(feeds=feeds)["response"]["itineraries"][0]
        self.assertEqual(result["method"], "PROVIDER_FALLBACK")
        self.assertFalse(result["comparison_eligible"])

    def test_later_upstream_choice_cannot_fallback_into_known_future_closure(self):
        legs = [walk("access", 1, 1, 60), subway(), walk("transfer", 2, 2, 45),
                subway("second", "G", 2, 3, 700, 900), walk("exit", 3, 3, 20)]
        req = request([route(legs=legs)], destination=3)
        feeds = [snapshot([trip("early", departure=100, arrival=300), trip("late", departure=400, arrival=600)]),
                 snapshot([trip("missed", "G", 400, 500, 2, 3)], feed="g"),
                 snapshot(feed="subway-alerts", alerts=[alert("first", start=100, end=350),
                                                        alert("second", start=650, end=1000, line="G")])]
        report = evaluate(req, feeds)
        self.assertEqual(report["response"]["itineraries"][0]["status"], "UNAVAILABLE")
        self.assertIn("PROVIDER_SERVICE_ALERT_CONFLICT_UNRESOLVED",
                      report["diagnostics"]["itineraries"][0]["legs"][3]["reason_codes"])

    def test_alert_for_later_rejected_train_does_not_block_selected_train(self):
        feeds = [snapshot([trip("early"), trip("late",  departure=500, arrival=800)]),
                 snapshot(feed="subway-alerts", alerts=[alert(trip_id="late")])]
        result = evaluate(feeds=feeds)["response"]["itineraries"][0]
        self.assertTrue(result["comparison_eligible"])
        self.assertTrue(result["legs"][1]["matched_mta_trip_id"].endswith("/early"))

    def test_alert_ending_before_platform_arrival_does_not_block_train(self):
        feeds = [snapshot([trip()]), snapshot(feed="subway-alerts", alerts=[alert(start=-100, end=50)])]
        self.assertTrue(evaluate(feeds=feeds)["response"]["itineraries"][0]["comparison_eligible"])

    def test_service_resuming_while_waiting_does_not_block_later_train(self):
        feeds = [snapshot([trip(departure=300, arrival=600)]),
                 snapshot(feed="subway-alerts", alerts=[alert(start=-100, end=200)])]
        self.assertTrue(evaluate(feeds=feeds)["response"]["itineraries"][0]["comparison_eligible"])

    def test_valid_current_stop_pattern_can_survive_detour_alert(self):
        feeds = [snapshot([trip()]), snapshot(feed="subway-alerts", alerts=[alert(effect="DETOUR")])]
        report = evaluate(feeds=feeds)
        self.assertTrue(report["response"]["itineraries"][0]["comparison_eligible"])
        self.assertEqual(report["diagnostics"]["itineraries"][0]["legs"][1]["selected_alert_ids"], ["notice"])

    def test_missing_transfer_walk_does_not_become_zero_seconds(self):
        legs = [subway(), subway("second", "G", 2, 3)]
        req = request([route(legs=legs)], destination=3)
        feeds = [snapshot([trip()]), snapshot([trip("second", "G", 400, 700, 2, 3)], feed="g")]
        self.assertEqual(evaluate(req, feeds)["response"]["itineraries"][0]["status"], "UNAVAILABLE")

    def test_walk_only_route_is_displayed_without_claiming_mta_support(self):
        req = request([route(legs=[walk("walk", 1, 2, 900)])])
        result = evaluate(req, feeds=[])["response"]["itineraries"][0]
        self.assertEqual(result["method"], "PROVIDER_FALLBACK")
        self.assertEqual(result["components"], {"walking_seconds": 900, "waiting_seconds": 0, "riding_seconds": 0})
        self.assertTrue(result["comparison_eligible"])

    def test_faster_supplied_walk_can_win_without_any_walking_limit(self):
        req = request([route(), route("walking", legs=[walk("walk", 1, 2, 300)])])
        decision = evaluate(req)["response"]["decision"]
        self.assertEqual(decision["action"], "SWITCH")
        self.assertEqual(decision["recommended_itinerary_id"], "walking")
        self.assertEqual(decision["estimated_savings_seconds"], 90)

    def test_missing_feeds_do_not_block_walk_only_comparison(self):
        req = request([route(legs=[walk("walk", 1, 2, 900)]),
                       route("alternative", legs=[walk("walk", 1, 2, 1000)])])
        response = evaluate(req, feeds=[], with_alerts=False)["response"]
        self.assertEqual(response["decision"]["action"], "STAY")
        self.assertEqual(response["data_status"]["train_feed"]["status"], "MISSING")

    def test_falsely_labeled_fresh_report_does_not_revive_old_observations(self):
        req = request()
        matching = match_request(req, static_data(), [snapshot([trip()])])
        next(feed for feed in matching["feed_status"] if feed["feed_id"] == "bdfm")["source_updated_at"] = stamp(-1000)
        report = evaluate_baseline(req, matching, evaluated_at=stamp(1), allow_provider_fallback=False)
        self.assertEqual(report["response"]["itineraries"][0]["status"], "UNAVAILABLE")

    def test_input_objects_are_not_mutated(self):
        req, feeds = request(), [snapshot([trip()]), snapshot(feed="subway-alerts")]
        matching = match_request(req, static_data(), feeds)
        original = deepcopy((req, matching))
        evaluate_baseline(req, matching, evaluated_at=stamp(1))
        self.assertEqual((req, matching), original)

    def test_matching_from_another_cutoff_is_rejected(self):
        req = request()
        matching = match_request(req, static_data(), [snapshot([trip()])])
        matching["decision_time"] = stamp(-1)
        with self.assertRaisesRegex(ValueError, "does not belong"):
            evaluate_baseline(req, matching, evaluated_at=stamp(1))

    def test_evaluation_time_before_cutoff_is_rejected(self):
        req = request()
        matching = match_request(req, static_data(), [snapshot([trip()])])
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            evaluate_baseline(req, matching, evaluated_at=stamp(-1))

    def test_same_request_ids_do_not_allow_reusing_matches_for_another_line(self):
        req = request()
        matching = match_request(req, static_data(), [snapshot([trip()])])
        req["itineraries"][0]["legs"][1]["transit"]["route_short_name"] = "G"
        with self.assertRaisesRegex(ValueError, "complete supplied request"):
            evaluate_baseline(req, matching, evaluated_at=stamp(1))

    def test_walk_timing_changes_require_rematching(self):
        req = request()
        matching = match_request(req, static_data(), [snapshot([trip()])])
        req["itineraries"][0]["legs"][0]["provider_duration_seconds"] = 200
        with self.assertRaisesRegex(ValueError, "complete supplied request"):
            evaluate_baseline(req, matching, evaluated_at=stamp(1))

    def test_huge_finite_duration_has_a_controlled_input_error(self):
        req = request([route(legs=[walk("walk", 1, 2, 1e100)])])
        with self.assertRaisesRegex(ValueError, "supported timestamp range"):
            evaluate(req, feeds=[])

    def test_integration_wrapper_keeps_provider_diagnostics(self):
        req = request()
        integration = {"request": req, "matching": match_request(req, static_data(), [snapshot([trip()])]),
                       "provider": {"name": "synthetic", "issues": [{"code": "PROVIDER_PLATFORM_ACCESS_UNVERIFIED"}]}}
        report = evaluate_integration(integration, evaluated_at=stamp(1))
        self.assertEqual(report["provider"]["issues"][0]["code"], "PROVIDER_PLATFORM_ACCESS_UNVERIFIED")
        self.assertIn("BUILDING_ENTRANCES_NOT_INDEPENDENTLY_VERIFIED", report["limitations"])


if __name__ == "__main__":
    unittest.main()
