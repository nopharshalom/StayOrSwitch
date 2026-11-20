"""Synthetic as-of, transfer, and severe-incident decision regressions."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from data.delay_profiles import IncidentIndex
from stayorswitch.matching import match_request
from stayorswitch.severe import decide, predict_routes


NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc).timestamp()
FEEDS = {"F": "bdfm", "FX": "bdfm", "G": "g", "R": "nqrw"}


def stamp(offset=0):
    return datetime.fromtimestamp(NOW + offset, timezone.utc).isoformat().replace("+00:00", "Z")


def train(identifier="first", line="F", departure=120, arrival=600,
          start="P1S", end="P2S"):
    feed = FEEDS[line]
    return {"id": "MTA:" + feed + ":20261012:" + line + ":" + identifier,
            "trip_id": identifier, "route_id": line, "feed_id": feed,
            "start_date": "20261012", "start_time": "08:00:00",
            "direction_id": 1, "timestamp": NOW - 10,
            "schedule_relationship": "SCHEDULED", "reason_codes": [],
            "stop_updates": [
                {"stop_id": start, "stop_sequence": 1,
                 "arrival_time": NOW + departure, "departure_time": NOW + departure,
                 "schedule_relationship": "SCHEDULED"},
                {"stop_id": end, "stop_sequence": 2,
                 "arrival_time": NOW + arrival, "departure_time": NOW + arrival,
                 "schedule_relationship": "SCHEDULED"}]}


def snapshot(trains=(), feed="bdfm", *, fetched=-5, source=-10, status="AVAILABLE"):
    return {"feed_id": feed, "kind": "alerts" if feed == "subway-alerts" else "train",
            "status": status, "fetched_at": stamp(fetched),
            "requested_at": stamp(fetched - 1), "source_updated_at": stamp(source),
            "captured_at": NOW + fetched, "trips": list(trains), "alerts": [],
            "reason_codes": []}


def leg(line="F", start="P1S", end="P2S"):
    return {"route_id": line, "feed_id": FEEDS[line],
            "from_stop_id": start, "to_stop_id": end}


def route(identifier="current", line="F", *, access=60, egress=60,
          legs=None, transfers=()):
    return {"id": identifier, "name": "Synthetic " + identifier, "family": line,
            "access_walk_seconds": access, "egress_walk_seconds": egress,
            "legs": legs if legs is not None else [leg(line)],
            "transfer_walk_seconds": list(transfers)}


def context(state="NORMAL", ids=(), evidence="FRESH"):
    return {"state": state, "cause": "SIGNAL_PROBLEM" if state == "SEVERE" else "NONE",
            "incident_ids": list(ids), "evidence_status": evidence,
            "first_observed_at": NOW - 300 if ids else None,
            "age_seconds": 300 if ids else None, "alerts": []}


class IncidentFake:
    def __init__(self, contexts=None):
        self.contexts = contexts or {}
        self.calls = []

    def context_at(self, cutoff, route_id, stop_ids=None):
        self.calls.append((cutoff, route_id, tuple(stop_ids or ())))
        return deepcopy(self.contexts.get(route_id, context()))


class ProfileFake:
    def __init__(self, corrections=None):
        self.corrections = corrections or {}
        self.calls = []

    def estimate(self, target, route_id, from_stop_id, to_stop_id, cutoff,
                 horizon_seconds, context):
        self.calls.append({"target": target, "route_id": route_id,
                           "from_stop_id": from_stop_id, "to_stop_id": to_stop_id,
                           "cutoff": cutoff, "horizon_seconds": horizon_seconds,
                           "context": deepcopy(context)})
        correction = self.corrections.get((route_id, target), 0)
        return {"correction_seconds": correction, "supported": True,
                "level": "SYNTHETIC", "event_count": 50, "incident_count": 4,
                "statistics": {}, "reason": None}


def prediction(templates=None, snapshots=None, *, mode="mta", profiles=None,
               incidents=None):
    templates = templates if templates is not None else [route()]
    snapshots = list(snapshots) if snapshots is not None else [snapshot([train()])]
    if not any(item["feed_id"] == "subway-alerts" for item in snapshots):
        snapshots.append(snapshot(feed="subway-alerts"))
    return predict_routes(snapshots, templates, NOW, mode=mode,
                          estimator=profiles, incident_index=incidents or IncidentFake())


def paired_prediction(*, saving=360, contexts=None, mode="incident_profile"):
    return prediction([route(), route("alternative", "G")],
        [snapshot([train(arrival=1200)]),
         snapshot([train("alternative", "G", arrival=1200 - saving)], feed="g")],
        mode=mode, profiles=ProfileFake(),
        incidents=IncidentFake(contexts or {"F": context("SEVERE", ["incident-f"])}))


class SeverePredictionTests(unittest.TestCase):
    def test_complete_journey_components_equal_destination_duration(self):
        result = prediction()["routes"][0]
        self.assertEqual(result["total_duration_seconds"], 660)
        self.assertEqual(result["components"],
            {"walking_seconds": 120, "waiting_seconds": 60, "riding_seconds": 480})
        self.assertEqual(result["selected_legs"][0]["departure_at"], NOW + 120)

    def test_overtaking_selects_earliest_arrival_not_first_departure(self):
        result = prediction(snapshots=[snapshot([
            train("local", departure=120, arrival=900),
            train("express", departure=180, arrival=600)])])["routes"][0]
        self.assertTrue(result["selected_legs"][0]["trip_id"].endswith(":express"))
        self.assertEqual(result["total_duration_seconds"], 660)

    def test_endpoint_corrections_are_not_added_twice(self):
        profiles = ProfileFake({("F", "departure"): 30, ("F", "arrival"): 120})
        result = prediction(mode="time_profile", profiles=profiles)["routes"][0]
        self.assertEqual(result["total_duration_seconds"], 780)
        self.assertEqual(result["components"],
            {"walking_seconds": 120, "waiting_seconds": 90, "riding_seconds": 570})
        self.assertEqual(result["selected_legs"][0]["arrival_at"], NOW + 720)

    def test_corrected_first_leg_reselects_catchable_transfer(self):
        template = route(legs=[leg(), leg("G", "P2S", "P3S")], transfers=[60])
        feeds = [snapshot([train(arrival=300)]),
                 snapshot([train("early", "G", 390, 600, "P2S", "P3S"),
                           train("later", "G", 500, 800, "P2S", "P3S")], feed="g")]
        profiles = ProfileFake({("F", "arrival"): 120})
        result = prediction([template], feeds, mode="time_profile", profiles=profiles)["routes"][0]
        self.assertTrue(result["selected_legs"][1]["trip_id"].endswith(":later"))
        self.assertEqual(result["selected_legs"][1]["platform_ready_at"], NOW + 480)
        self.assertEqual(result["total_duration_seconds"], 860)
        self.assertTrue(all(call["cutoff"] == NOW for call in profiles.calls))

    def test_future_feed_does_not_replace_available_asof_forecast(self):
        old = snapshot([train("asof", arrival=600)])
        future = snapshot([train("future", arrival=200)], fetched=1, source=0)
        result = prediction(snapshots=[old, future])["routes"][0]
        self.assertTrue(result["selected_legs"][0]["trip_id"].endswith(":asof"))

    def test_failed_latest_capture_does_not_revive_older_feed(self):
        old = snapshot([train()], fetched=-30, source=-35)
        failure = snapshot([], fetched=-5, source=-10, status="MISSING")
        result = prediction(snapshots=[old, failure])["routes"][0]
        self.assertFalse(result["timing_eligible"])
        self.assertIsNone(result["total_duration_seconds"])

    def test_stale_train_feed_is_not_comparison_ready(self):
        result = prediction(snapshots=[snapshot([train()], fetched=-181, source=-185)])["routes"][0]
        self.assertFalse(result["timing_eligible"])

    def test_future_trip_timestamp_is_rejected(self):
        item = train()
        item["timestamp"] = NOW + 1
        result = prediction(snapshots=[snapshot([item])])["routes"][0]
        self.assertFalse(result["timing_eligible"])

    def test_future_incident_evidence_cannot_enter_a_current_prediction(self):
        future = context("SEVERE", ["future-incident"])
        future["first_observed_at"] = NOW + 1
        with self.assertRaises(ValueError):
            prediction(incidents=IncidentFake({"F": future}))

    def test_supplied_express_alias_preserves_actual_profile_line(self):
        template = route()
        template["legs"][0]["route_ids"] = ["F", "FX"]
        profiles = ProfileFake()
        result = prediction([template], [snapshot([train("express", "FX")])],
                            profiles=profiles, mode="time_profile")["routes"][0]
        self.assertTrue(result["timing_eligible"])
        self.assertEqual(result["selected_legs"][0]["route_id"], "FX")
        self.assertTrue(all(call["route_id"] == "FX" for call in profiles.calls))

    def test_route_alias_string_is_rejected_instead_of_split_into_characters(self):
        template = route()
        template["legs"][0]["route_ids"] = "FX"
        with self.assertRaises(ValueError):
            prediction([template])

    def test_missing_true_departure_cannot_use_arrival_as_boarding(self):
        item = train()
        item["stop_updates"][0]["departure_time"] = None
        result = prediction(snapshots=[snapshot([item])])["routes"][0]
        self.assertFalse(result["timing_eligible"])

    def test_expired_prediction_cannot_be_resurrected_by_correction(self):
        profiles = ProfileFake({("F", "departure"): 300})
        result = prediction(snapshots=[snapshot([train(departure=-30)])],
                            mode="time_profile", profiles=profiles)["routes"][0]
        self.assertFalse(result["timing_eligible"])

    def test_incoherent_corrected_endpoints_are_not_a_negative_ride(self):
        profiles = ProfileFake({("F", "arrival"): -550})
        result = prediction(mode="time_profile", profiles=profiles)["routes"][0]
        self.assertFalse(result["timing_eligible"])

    def test_duplicate_train_identity_is_unusable(self):
        first = train()
        second = deepcopy(first)
        second["stop_updates"][1]["arrival_time"] += 60
        result = prediction(snapshots=[snapshot([first, second])])["routes"][0]
        self.assertFalse(result["timing_eligible"])

    def test_simultaneous_start_time_aliases_reject_both_normalized_trips(self):
        first = train("060000_F..S")
        first["id"] += ":08:00:00"
        second = deepcopy(first)
        second["id"] = second["id"].replace("08:00:00", "08:00:30")
        second["start_time"] = "08:00:30"
        result = prediction(snapshots=[snapshot([first, second])])["routes"][0]
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertFalse(result["timing_eligible"])
        self.assertEqual({item["trip_id"] for item in result["rejected"]},
                         {first["id"], second["id"]})
        self.assertEqual([item["reason"] for item in result["rejected"]],
                         ["SIMULTANEOUS_CANONICAL_TRIP_ALIASES"] * 2)

    def test_start_time_jitter_across_snapshots_preserves_latest_normalized_id(self):
        first = train("060000_F..S", arrival=400)
        first["id"] += ":08:00:00"
        first["timestamp"] = NOW - 35
        second = train("060000_F..S", arrival=700)
        second["id"] += ":08:00:30"
        second["start_time"] = "08:00:30"
        result = prediction(snapshots=[snapshot([second]),
                            snapshot([first], fetched=-30, source=-35)])["routes"][0]
        self.assertTrue(result["timing_eligible"])
        self.assertEqual(result["selected_legs"][0]["trip_id"], second["id"])
        self.assertEqual(result["selected_legs"][0]["start_time"], "08:00:30")
        self.assertEqual(result["total_duration_seconds"], 760)

    def test_same_encoded_run_on_distinct_actual_routes_is_not_merged(self):
        first = train("060000_F..S", "F", arrival=600)
        second = train("060000_F..S", "FX", arrival=500)
        template = route()
        template["legs"][0]["route_ids"] = ["F", "FX"]
        result = prediction([template], [snapshot([first, second])])["routes"][0]
        self.assertTrue(result["timing_eligible"])
        self.assertEqual(result["leg_candidate_counts"], [2])
        self.assertEqual(result["selected_legs"][0]["trip_id"], second["id"])
        self.assertEqual(result["selected_legs"][0]["route_id"], "FX")

    def test_same_encoded_run_on_distinct_service_dates_is_not_merged(self):
        first = train("060000_F..S", arrival=600)
        second = train("060000_F..S", arrival=500)
        second["start_date"] = "20261011"
        second["id"] = second["id"].replace("20261012", "20261011")
        result = prediction(snapshots=[snapshot([first, second])])["routes"][0]
        self.assertTrue(result["timing_eligible"])
        self.assertEqual(result["leg_candidate_counts"], [2])
        self.assertEqual(result["selected_legs"][0]["trip_id"], second["id"])
        self.assertEqual(result["selected_legs"][0]["service_date"], "20261011")

    def test_canceled_train_is_not_scored_as_available(self):
        item = train()
        item["schedule_relationship"] = "CANCELED"
        result = prediction(snapshots=[snapshot([item])])["routes"][0]
        self.assertFalse(result["timing_eligible"])

    def test_known_fresh_no_service_conflict_rejects_apparently_timed_train(self):
        alerts = snapshot(feed="subway-alerts")
        alerts["alerts"] = [{"id": "closure", "effect": "NO_SERVICE",
            "cause": "TECHNICAL_PROBLEM", "header": "Synthetic suspension",
            "description": "No F service in the affected segment.",
            "active_periods": [{"start": NOW - 60, "end": NOW + 3600}],
            "informed_entities": [{"route_id": "F"}]}]
        result = prediction(snapshots=[snapshot([train()]), alerts])["routes"][0]
        self.assertFalse(result["timing_eligible"])

    def test_ambiguous_repeated_boarding_stop_does_not_choose_arbitrary_visit(self):
        item = train()
        repeated = deepcopy(item["stop_updates"][0])
        repeated["stop_sequence"] = 2
        repeated["departure_time"] += 60
        item["stop_updates"][1]["stop_sequence"] = 3
        item["stop_updates"].insert(1, repeated)
        result = prediction(snapshots=[snapshot([item])])["routes"][0]
        self.assertFalse(result["timing_eligible"])

    def test_later_outcome_fields_do_not_change_prediction(self):
        base = [snapshot([train()])]
        poisoned = deepcopy(base)
        poisoned[0]["trips"][0]["later_outcome"] = {"arrival_at": NOW + 99999}
        first = prediction(snapshots=base)["routes"][0]
        second = prediction(snapshots=poisoned)["routes"][0]
        self.assertEqual(first["total_duration_seconds"], second["total_duration_seconds"])
        self.assertEqual(first["selected_legs"], second["selected_legs"])

    def test_all_eleven_configured_variants_remain_visible_when_missing(self):
        root = Path(__file__).resolve().parents[2]
        templates = json.loads((root / "data/config/october.json").read_text())["routes"]
        result = prediction(templates, [])
        self.assertEqual(len(result["routes"]), 11)
        self.assertEqual(len({item["family"] for item in result["routes"]}), 7)
        self.assertTrue(all(not item["timing_eligible"] for item in result["routes"]))


class SevereDecisionTests(unittest.TestCase):
    def test_fresh_severe_problem_and_meaningful_independent_alternative_switch(self):
        result = decide(paired_prediction(), "current")
        self.assertEqual(result["strict_decision"]["action"], "SWITCH")
        self.assertEqual(result["strict_decision"]["recommended_itinerary_id"], "alternative")
        self.assertEqual(result["strict_decision"]["estimated_savings_seconds"], 360)

    def test_below_margin_is_stay_and_exact_margin_is_switch(self):
        below = decide(paired_prediction(saving=299), "current")
        exact = decide(paired_prediction(saving=300), "current")
        self.assertEqual(below["strict_decision"]["action"], "STAY")
        self.assertEqual(exact["strict_decision"]["action"], "SWITCH")

    def test_missing_current_reference_does_not_invent_stay_or_switch(self):
        result = decide(paired_prediction(), None)
        self.assertEqual(result["strict_decision"]["action"], "NOT_APPLICABLE")

    def test_ordinary_service_does_not_trigger_severe_switch_policy(self):
        report = paired_prediction(contexts={"F": context(), "G": context()})
        result = decide(report, "current")
        self.assertNotEqual(result["strict_decision"]["action"], "SWITCH")

    def test_shared_incident_switch_discloses_that_it_is_not_an_independent_escape(self):
        shared = context("SEVERE", ["shared-incident"])
        report = paired_prediction(contexts={"F": shared, "G": shared})
        result = decide(report, "current")
        self.assertEqual(result["strict_decision"]["action"], "SWITCH")
        self.assertIn("alternative", result["strict_decision"]["shared_incident_alternatives"])
        self.assertIn("SHARED_SEVERE_INCIDENT_EXPOSURE", result["strict_decision"]["reason_codes"])

    def test_stale_severe_evidence_keeps_conditional_ranking_separate(self):
        report = paired_prediction(contexts={"F": context("SEVERE", ["incident-f"], "LAST_OBSERVED")})
        result = decide(report, "current")
        self.assertEqual(result["conditional_timing_decision"]["action"], "SWITCH")
        self.assertEqual(result["strict_decision"]["action"], "UNDETERMINED")

    def test_missing_alternative_does_not_become_successful_stay(self):
        report = prediction([route(), route("alternative", "G")],
                            incidents=IncidentFake({"F": context("SEVERE", ["incident-f"])}))
        result = decide(report, "current")
        self.assertEqual(result["strict_decision"]["action"], "UNDETERMINED")

    def test_known_faster_route_can_switch_with_other_alternatives_unknown(self):
        templates = [route(), route("alternative", "G"), route("unknown", "R")]
        report = prediction(templates,
            [snapshot([train(arrival=1200)]), snapshot([train("alt", "G", arrival=600)], feed="g")],
            incidents=IncidentFake({"F": context("SEVERE", ["incident-f"])}))
        result = decide(report, "current")
        self.assertEqual(result["strict_decision"]["action"], "SWITCH")
        self.assertFalse(result["strict_decision"]["comparison_complete"])

    def test_explicit_non_severe_comparison_can_compare_mta(self):
        report = paired_prediction(contexts={"F": context(), "G": context()}, mode="mta")
        result = decide(report, "current", require_severe=False)
        self.assertEqual(result["strict_decision"]["action"], "SWITCH")


class IncidentIndexIntegrationTests(unittest.TestCase):
    def test_route_wide_text_suspension_rejects_train_without_structured_effect(self):
        alerts = snapshot(feed="subway-alerts")
        alerts["alerts"] = [{"id": "g-suspension", "effect": None,
            "cause": None, "header": "G trains are not running.", "description": "",
            "active_periods": [{"start": NOW - 60, "end": NOW + 3600}],
            "informed_entities": [{"route_id": "G"}]}]
        report = prediction([route(line="G")],
            [snapshot([train("g-train", "G")], feed="g"), alerts],
            incidents=IncidentIndex([alerts]))
        result = report["routes"][0]
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertFalse(result["timing_eligible"])
        self.assertIn("NO_SERVICE_ALERT_CONFLICT",
                      [item["reason"] for item in result["rejected"]])

    def test_unresolved_text_segment_suspension_withholds_formal_switch(self):
        alerts = snapshot(feed="subway-alerts")
        alerts["alerts"] = [
            {"id": "f-delay", "effect": None, "cause": None,
             "header": "F trains have severe delays.", "description": "",
             "active_periods": [{"start": NOW - 60, "end": NOW + 3600}],
             "informed_entities": [{"route_id": "F"}]},
            {"id": "g-segment", "effect": None, "cause": None,
             "header": "No G trains between X and Y.", "description": "",
             "active_periods": [{"start": NOW - 60, "end": NOW + 3600}],
             "informed_entities": [{"route_id": "G"}]}]
        report = prediction([route(), route("alternative", "G")],
            [snapshot([train(arrival=1200)]),
             snapshot([train("alternative", "G", arrival=600)], feed="g"), alerts],
            incidents=IncidentIndex([alerts]))
        alternative = report["routes"][1]
        self.assertTrue(alternative["timing_eligible"])
        self.assertFalse(alternative["comparison_eligible"])
        result = decide(report, "current")
        self.assertEqual(result["conditional_timing_decision"]["action"], "SWITCH")
        self.assertEqual(result["strict_decision"]["action"], "UNDETERMINED")

    def test_base_route_severe_notice_applies_to_express_with_actual_profile_lookup(self):
        template = route()
        template["legs"][0]["route_ids"] = ["F", "FX"]
        alerts = snapshot(feed="subway-alerts")
        alerts["alerts"] = [{"id": "f-delay", "effect": None, "cause": None,
            "header": "F trains have severe delays because of a signal problem.",
            "description": "", "active_periods": [{"start": NOW - 60, "end": NOW + 3600}],
            "informed_entities": [{"route_id": "F"}]}]
        profiles = ProfileFake()
        report = prediction([template], [snapshot([train("express", "FX")]), alerts],
            incidents=IncidentIndex([alerts]), mode="incident_profile", profiles=profiles)
        result = report["routes"][0]
        self.assertTrue(result["comparison_eligible"])
        self.assertEqual(result["context"]["state"], "SEVERE")
        self.assertEqual(result["severe_incident_ids"], ["f-delay"])
        self.assertEqual(result["selected_legs"][0]["route_id"], "FX")
        self.assertEqual(len(profiles.calls), 2)
        self.assertTrue(all(call["route_id"] == "FX" for call in profiles.calls))
        self.assertTrue(all(call["context"]["state"] == "SEVERE" for call in profiles.calls))

    def test_base_route_no_service_notice_rejects_express_train(self):
        template = route()
        template["legs"][0]["route_ids"] = ["F", "FX"]
        alerts = snapshot(feed="subway-alerts")
        alerts["alerts"] = [{"id": "f-suspension", "effect": "NO_SERVICE",
            "cause": "TECHNICAL_PROBLEM", "header": "F service suspended",
            "description": "F service is suspended because of a signal problem.",
            "active_periods": [{"start": NOW - 60, "end": NOW + 3600}],
            "informed_entities": [{"route_id": "F"}]}]
        report = prediction([template], [snapshot([train("express", "FX")]), alerts],
                            incidents=IncidentIndex([alerts]))
        result = report["routes"][0]
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertFalse(result["timing_eligible"])
        self.assertIsNone(result["total_duration_seconds"])
        self.assertIn("NO_SERVICE_ALERT_CONFLICT",
                      [item["reason"] for item in result["rejected"]])

    def test_fresh_empty_alert_capture_keeps_ordinary_route_comparison_eligible(self):
        alerts = snapshot(feed="subway-alerts")
        incidents = IncidentIndex([alerts])
        service = incidents.context_at(NOW, "F", ["P1S", "P2S"])
        self.assertEqual(service["state"], "NORMAL")
        self.assertFalse(service["applicable"])
        report = prediction([route(), route("alternative", "G")],
            [snapshot([train()]),
             snapshot([train("alternative", "G", arrival=900)], feed="g"), alerts],
            incidents=incidents, mode="incident_profile", profiles=ProfileFake())
        self.assertTrue(all(item["comparison_eligible"] for item in report["routes"]))
        result = decide(report, "current")["strict_decision"]
        self.assertEqual(result["action"], "STAY")
        self.assertIn("NO_APPLICABLE_SEVERE_INCIDENT", result["reason_codes"])

    def test_route_scoped_severe_alert_allows_switch_to_normal_alternative(self):
        alerts = snapshot(feed="subway-alerts")
        alerts["alerts"] = [{"id": "incident-f", "effect": "SIGNIFICANT_DELAYS",
            "cause": "TECHNICAL_PROBLEM", "header": "F severe delays",
            "description": "F trains have severe delays because of a signal problem.",
            "active_periods": [{"start": NOW - 60, "end": NOW + 3600}],
            "informed_entities": [{"route_id": "F"}]}]
        incidents = IncidentIndex([alerts])
        alternative_service = incidents.context_at(NOW, "G", ["P1S", "P2S"])
        self.assertEqual(alternative_service["state"], "NORMAL")
        self.assertFalse(alternative_service["applicable"])
        report = prediction([route(), route("alternative", "G")],
            [snapshot([train(arrival=1200)]),
             snapshot([train("alternative", "G", arrival=600)], feed="g"), alerts],
            incidents=incidents, mode="incident_profile", profiles=ProfileFake())
        self.assertTrue(all(item["comparison_eligible"] for item in report["routes"]))
        result = decide(report, "current")["strict_decision"]
        self.assertEqual(result["action"], "SWITCH")
        self.assertEqual(result["recommended_itinerary_id"], "alternative")
        self.assertEqual(result["estimated_savings_seconds"], 600)
        self.assertEqual(result["shared_incident_alternatives"], [])


class MatchedRequestHandoffTests(unittest.TestCase):
    def test_matched_provider_request_preserves_walks_platforms_and_current_route(self):
        def location(number):
            return {"id": "location-" + str(number), "name": "Station " + str(number),
                    "coordinates": None, "provider_place_id": None,
                    "mta_stop_id": "P" + str(number)}

        def walk(identifier, station, seconds):
            return {"id": identifier, "mode": "WALK", "from": location(station),
                    "to": location(station), "provider_duration_seconds": seconds,
                    "provider_departure_at": None, "provider_arrival_at": None, "transit": None}

        def subway(identifier, line, start, end, departure, arrival):
            return {"id": identifier, "mode": "SUBWAY", "from": location(start),
                    "to": location(end), "provider_duration_seconds": arrival - departure,
                    "provider_departure_at": stamp(departure), "provider_arrival_at": stamp(arrival),
                    "transit": {"agency": "MTA New York City Transit", "route_short_name": line,
                                "provider_route_id": None, "headsign": None, "direction_id": None,
                                "provider_trip_id": None}}

        stops = {}
        for number in (1, 2, 3):
            for suffix in ("", "N", "S"):
                identifier = "P" + str(number) + suffix
                stops[identifier] = {"id": identifier, "name": "Station " + str(number),
                    "latitude": None, "longitude": None,
                    "parent_station": "P" + str(number) if suffix else "",
                    "location_type": 0 if suffix else 1}
        static = {"stops": stops, "routes": {line: {"short_name": line} for line in ("F", "G")},
                  "route_stops": {"F": [key for key in stops if key.startswith(("P1", "P2"))],
                                  "G": [key for key in stops if key.startswith(("P2", "P3"))]}}
        request = {"schema_version": "1.0", "request_id": "matched-handoff", "data_mode": "simulated",
            "decision_time": stamp(), "user_state": "NOT_BOARDED", "origin": location(1),
            "destination": location(3), "current_itinerary_id": "selected", "itineraries": [{
                "id": "selected", "provider": {"name": "synthetic", "itinerary_id": None,
                                                  "queried_at": stamp(-10)},
                "provider_eta": stamp(620), "legs": [walk("access", 1, 60),
                    subway("first", "F", 1, 2, 100, 300), walk("transfer", 2, 45),
                    subway("second", "G", 2, 3, 330, 600), walk("egress", 3, 20)]}]}
        feeds = [snapshot([train("first", departure=100, arrival=300)]),
                 snapshot([train("missed", "G", 330, 600, "P2S", "P3S"),
                           train("catchable", "G", 360, 700, "P2S", "P3S")], feed="g"),
                 snapshot(feed="subway-alerts")]
        matching = match_request(request, static, feeds)
        matched = matching["itineraries"][0]
        self.assertEqual(matching["current_itinerary_id"], "selected")
        self.assertEqual(matched["status"], "MATCHED")

        supplied = request["itineraries"][0]
        template_legs = []
        for supplied_leg, matched_leg in zip(supplied["legs"], matched["legs"]):
            if supplied_leg["mode"] != "SUBWAY":
                continue
            endpoints = {(candidate["boarding_stop_id"], candidate["alighting_stop_id"])
                         for candidate in matched_leg["candidates"]}
            self.assertEqual(len(endpoints), 1)
            self.assertEqual(len(matched_leg["required_feed_ids"]), 1)
            boarding, alighting = endpoints.pop()
            template_legs.append({"route_id": supplied_leg["transit"]["route_short_name"],
                "feed_id": matched_leg["required_feed_ids"][0],
                "from_stop_id": boarding, "to_stop_id": alighting})
        template = {"id": supplied["id"], "name": "Matched provider itinerary", "family": "F_G",
            "access_walk_seconds": supplied["legs"][0]["provider_duration_seconds"],
            "transfer_walk_seconds": [supplied["legs"][2]["provider_duration_seconds"]],
            "egress_walk_seconds": supplied["legs"][4]["provider_duration_seconds"],
            "legs": template_legs}
        report = predict_routes(feeds, [template], NOW, incident_index=IncidentIndex(feeds))
        result = report["routes"][0]
        self.assertEqual(result["id"], "selected")
        self.assertEqual(decide(report, matching["current_itinerary_id"])["current_route_id"], "selected")
        self.assertEqual((result["access_walk_seconds"], result["transfer_walk_seconds"],
                          result["egress_walk_seconds"]), (60, [45], 20))
        self.assertEqual([(item["boarding_stop_id"], item["alighting_stop_id"])
                          for item in result["selected_legs"]], [("P1S", "P2S"), ("P2S", "P3S")])
        self.assertEqual([item["feed_id"] for item in result["selected_legs"]], ["bdfm", "g"])
        self.assertEqual([item["raw_trip_id"] for item in result["selected_legs"]], ["first", "catchable"])
        self.assertEqual([item["platform_ready_at"] for item in result["selected_legs"]],
                         [NOW + 60, NOW + 345])
        self.assertTrue(result["comparison_eligible"])
        self.assertEqual(result["eta"], NOW + 720)
        self.assertEqual(result["total_duration_seconds"], 720)
        self.assertEqual(result["components"],
                         {"walking_seconds": 125, "waiting_seconds": 55, "riding_seconds": 540})


if __name__ == "__main__":
    unittest.main()
