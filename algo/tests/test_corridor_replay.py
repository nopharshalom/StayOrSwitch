"""Synthetic causal replay, outcome identity, and walking-boundary checks."""

from copy import deepcopy
from datetime import datetime, timezone
import unittest

from stayorswitch.corridor_replay import (
    decide, evaluate_case, outcome_for, predict_routes, summarize_cases,
    validate_templates, walking_sensitivity,
)


NOW = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc).timestamp()


def stamp(offset=0):
    return datetime.fromtimestamp(NOW + offset, timezone.utc).isoformat().replace("+00:00", "Z")


def templates():
    return [
        {"id": "g_path", "name": "Synthetic G path", "feed_id": "g", "route_id": "G",
         "boarding_stop_id": "G22S", "alighting_stop_id": "A42S",
         "access_walk_seconds": 60, "egress_walk_seconds": 30},
        {"id": "f_path", "name": "Synthetic F path", "feed_id": "bdfm", "route_id": "F",
         "boarding_stop_id": "B04S", "alighting_stop_id": "A41S",
         "access_walk_seconds": 90, "egress_walk_seconds": 45},
    ]


def trip(name="g1", line="G", departure=100, arrival=300, intermediate=None):
    feed, origin, destination = ("g", "G22S", "A42S") if line == "G" else ("bdfm", "B04S", "A41S")
    stops = [{"stop_id": origin, "arrival_time": NOW + departure - 5,
              "departure_time": NOW + departure, "schedule_relationship": "SCHEDULED"}]
    if intermediate is not None:
        stops.append({"stop_id": "G30S", "arrival_time": NOW + intermediate[0],
                      "departure_time": NOW + intermediate[1], "schedule_relationship": "SCHEDULED"})
    stops.append({"stop_id": destination, "arrival_time": NOW + arrival,
                  "departure_time": NOW + arrival + 10, "schedule_relationship": "SCHEDULED"})
    for index, stop in enumerate(stops):
        stop["stop_sequence"] = index + 1
    return {"id": "MTA:" + feed + ":20261115:" + line + ":" + name + ":",
            "trip_id": name, "feed_id": feed, "route_id": line, "start_date": "20261115",
            "start_time": "10:00:00", "direction_id": 1, "nyct_direction": "SOUTH",
            "timestamp": NOW - 10, "is_assigned": True, "schedule_relationship": "SCHEDULED",
            "stop_updates": stops, "reason_codes": []}


def snapshot(trips=(), feed="g", source=-10, fetched=-5, alerts=()):
    return {"feed_id": feed, "kind": "alerts" if feed == "subway-alerts" else "train",
            "status": "AVAILABLE", "source_updated_at": stamp(source),
            "fetched_at": stamp(fetched), "requested_at": stamp(fetched - 1),
            "trips": list(trips), "alerts": list(alerts), "reason_codes": []}


def case(g_trips=None, f_trips=None, with_alerts=True):
    values = [snapshot([trip()] if g_trips is None else g_trips),
              snapshot([trip("f1", "F", 110, 400)] if f_trips is None else f_trips, feed="bdfm")]
    if with_alerts:
        values.append(snapshot(feed="subway-alerts"))
    return {"id": "synthetic-replay", "decision_at": stamp(), "snapshots": values,
            "selection_reason": "SYNTHETIC_TEST_NOT_OBSERVED_DELAY"}


def labels_for(trains, overrides=None):
    result = {}
    overrides = overrides or {}
    for train in trains:
        records = {}
        for stop in train["stop_updates"]:
            arrival, departure = stop["arrival_time"], stop["departure_time"]
            if (train["trip_id"], stop["stop_id"]) in overrides:
                delta_arrival, delta_departure = overrides[(train["trip_id"], stop["stop_id"])]
                arrival, departure = NOW + delta_arrival, NOW + delta_departure
            records[stop["stop_id"]] = {
                "arrival_at": arrival, "departure_at": departure,
                "arrival_usable": True, "departure_usable": True,
                "arrival_quality_flags": [], "departure_quality_flags": [],
                "quality_flags": [], "usable_proxy": True,
            }
        result[train["id"]] = records
    return result


class FixedPredictor:
    """A deterministic synthetic model whose inputs remain inspectable."""

    def __init__(self, corrections=None, default=0):
        self.corrections = corrections or {}
        self.default = default
        self.calls = []

    def predict_case(self, value):
        self.calls.append(deepcopy(value))
        features = value["features"]
        key = (value["trip_identity"], features.get("from_stop_id", features.get("stop_id")),
               features.get("to_stop_id"))
        delta = self.corrections.get(key, self.default)
        return {"target": value["target"], "method": "EXPERIMENTAL_COMPONENT_MODEL",
                "correction_seconds": delta, "seconds": value["baseline_seconds"] + delta,
                "uncertainty": None, "live_enabled": False}


class ReplayPredictionTests(unittest.TestCase):
    def test_later_departure_can_arrive_earlier(self):
        slow = trip("slow", departure=100, arrival=500)
        fast = trip("fast", departure=150, arrival=350)
        result = predict_routes(case([slow, fast]), templates())
        route = result["routes"][0]
        self.assertEqual(route["selected_train"]["trip_id"], fast["id"])
        self.assertEqual(route["total_duration_seconds"], 380)
        self.assertEqual(sum(route["components"].values()), 380)

    def test_future_snapshot_cannot_replace_as_of_observation(self):
        value = case([trip("known", arrival=500)])
        value["snapshots"].append(snapshot([trip("future", arrival=200)], fetched=1))
        result = predict_routes(value, templates())
        self.assertTrue(result["routes"][0]["selected_train"]["trip_id"].endswith(":known:"))

    def test_stale_train_feed_is_unavailable_not_zero(self):
        value = case()
        value["snapshots"][0]["source_updated_at"] = stamp(-181)
        result = predict_routes(value, templates())["routes"][0]
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIsNone(result["eta"])
        self.assertIsNone(result["total_duration_seconds"])

    def test_fresh_alerts_allow_strict_switch(self):
        prediction = predict_routes(case([trip(arrival=500)]), templates())
        decisions = decide(prediction, "g_path")
        self.assertEqual(decisions["strict_decision"]["action"], "SWITCH")
        self.assertEqual(decisions["strict_decision"]["recommended_itinerary_id"], "f_path")
        self.assertEqual(decisions["conditional_timing_decision"], decisions["strict_decision"])

    def test_unknown_alerts_preserve_only_conditional_switch(self):
        prediction = predict_routes(case([trip(arrival=500)], with_alerts=False), templates())
        decisions = decide(prediction, "g_path")
        self.assertEqual(decisions["strict_decision"]["action"], "UNDETERMINED")
        self.assertEqual(decisions["conditional_timing_decision"]["action"], "SWITCH")
        self.assertTrue(prediction["routes"][0]["timing_eligible"])
        self.assertFalse(prediction["routes"][0]["comparison_eligible"])

    def test_old_alert_source_can_be_freshly_received(self):
        value = case([trip(arrival=500)])
        value["snapshots"][-1]["source_updated_at"] = stamp(-86400)
        prediction = predict_routes(value, templates())
        self.assertTrue(prediction["alerts_fresh"])
        self.assertEqual(decide(prediction, "g_path")["strict_decision"]["action"], "SWITCH")

    def test_active_no_service_alert_excludes_matching_train(self):
        value = case()
        value["snapshots"][-1]["alerts"] = [{
            "id": "closed", "effect": "NO_SERVICE", "cause": "MAINTENANCE",
            "active_periods": [{"start": NOW, "end": NOW + 600}],
            "informed_entities": [{"route_id": "G"}],
        }]
        result = predict_routes(value, templates())["routes"][0]
        self.assertIsNone(result["selected_train"])
        self.assertIn("NO_SERVICE_ALERT_CONFLICT", [item["reason"] for item in result["rejected"]])

    def test_label_mutation_cannot_change_predictions_or_reference(self):
        g, f = trip(), trip("f1", "F", 110, 400)
        value = case([g], [f])
        labels = labels_for([g, f])
        first = evaluate_case(value, templates(), labels)
        changed = deepcopy(labels)
        changed[g["id"]]["A42S"]["arrival_at"] += 10000
        changed[f["id"]]["A41S"]["arrival_at"] += 20000
        second = evaluate_case(value, templates(), changed)
        self.assertEqual(first["reference_route_id"], second["reference_route_id"])
        for mode in first["modes"]:
            for key in ("routes", "strict_decision", "conditional_timing_decision"):
                self.assertEqual(first["modes"][mode][key], second["modes"][mode][key])
        self.assertNotEqual(first["reference_delay_seconds"], second["reference_delay_seconds"])

    def test_no_available_reference_does_not_invent_stay(self):
        result = evaluate_case(case([], []), templates(), {})
        self.assertIsNone(result["reference_route_id"])
        self.assertIsNone(result["reference_outcome"])
        for mode in result["modes"].values():
            self.assertEqual(mode["strict_decision"]["action"], "NOT_APPLICABLE")
            self.assertIsNone(mode["inferred_switch_savings_seconds"])


class ReplayCompositionTests(unittest.TestCase):
    def test_chained_segment_corrections_preserve_intermediate_dwell(self):
        g = trip(intermediate=(180, 200))
        predictor = FixedPredictor({(g["id"], "G22S", "G30S"): 30,
                                    (g["id"], "G30S", "A42S"): 20})
        result = predict_routes(case([g]), templates(), "segment_model",
                                predictors={"segment": predictor}, anchor_ids=["G30S"])
        route = result["routes"][0]
        self.assertEqual(route["selected_train"]["timing"]["arrival_at"], NOW + 350)
        self.assertEqual(route["components"]["riding_seconds"], 250)
        self.assertEqual(route["total_duration_seconds"], 380)
        self.assertEqual(route["selected_train"]["corrections"]["applied_segment_count"], 2)
        self.assertTrue(all(call["decision_at"] == NOW for call in predictor.calls))

    def test_departure_correction_is_applied_once_and_arrival_model_is_unused(self):
        g = trip(intermediate=(180, 200))
        segment = FixedPredictor({(g["id"], "G22S", "G30S"): 30,
                                  (g["id"], "G30S", "A42S"): 20})
        departure, arrival = FixedPredictor(default=10), FixedPredictor(default=900)
        result = predict_routes(case([g]), templates(), "departure_segment_research",
                                predictors={"segment": segment, "departure": departure, "arrival": arrival},
                                anchor_ids=["G30S"])
        route = result["routes"][0]
        self.assertEqual(route["selected_train"]["timing"]["departure_at"], NOW + 110)
        self.assertEqual(route["selected_train"]["timing"]["arrival_at"], NOW + 360)
        self.assertEqual(route["total_duration_seconds"], 390)
        self.assertEqual(arrival.calls, [])

    def test_out_of_horizon_preserves_baseline_and_counts_fallback(self):
        predictor = FixedPredictor(default=900)
        result = predict_routes(case([trip(arrival=2000)]), templates(), "segment_model",
                                predictors={"segment": predictor})
        route = result["routes"][0]
        self.assertEqual(route["total_duration_seconds"], 2030)
        self.assertEqual(route["selected_train"]["corrections"]["applied_segment_count"], 0)
        self.assertEqual(route["selected_train"]["corrections"]["fallback_segment_count"], 1)
        self.assertFalse(any(call["trip_identity"].endswith(":g1:") for call in predictor.calls))

    def test_nonmonotonic_anchor_dwell_falls_back_whole_leg(self):
        predictor = FixedPredictor(default=100)
        result = predict_routes(case([trip(intermediate=(200, 180))]), templates(), "segment_model",
                                predictors={"segment": predictor}, anchor_ids=["G30S"])
        route = result["routes"][0]
        self.assertEqual(route["total_duration_seconds"], 330)
        self.assertEqual(route["selected_train"]["corrections"]["fallback_segment_count"], 2)
        self.assertFalse(any(call["trip_identity"].endswith(":g1:") for call in predictor.calls))

    def test_corrected_departure_rechecks_platform_readiness(self):
        predictor = FixedPredictor(default=-50)
        result = predict_routes(case(), templates(), "departure_segment_research",
                                predictors={"departure": predictor})
        self.assertIsNone(result["routes"][0]["selected_train"])
        self.assertIn("NOT_CATCHABLE_AT_READY_TIME", [item["reason"] for item in result["routes"][0]["rejected"]])


class ReplayOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.g, self.f = trip(), trip("f1", "F", 110, 400)
        self.route = predict_routes(case([self.g], [self.f]), templates())["routes"][0]
        self.labels = labels_for([self.g, self.f])

    def test_outcome_follows_selected_train_not_hindsight_fastest(self):
        another = trip("another", departure=150, arrival=500)
        value = case([self.g, another], [self.f])
        route = predict_routes(value, templates())["routes"][0]
        labels = labels_for([self.g, another], {
            ("g1", "A42S"): (700, 710), ("another", "A42S"): (200, 210)})
        outcome = outcome_for(route, labels, stamp())
        self.assertEqual(outcome["trip_id"], self.g["id"])
        self.assertEqual(outcome["total_duration_seconds"], 730)

    def test_inferred_missed_train_is_not_reassigned(self):
        self.labels[self.g["id"]]["G22S"]["departure_at"] = NOW + 50
        outcome = outcome_for(self.route, self.labels, stamp())
        self.assertEqual(outcome["status"], "MISSED_SELECTED_TRAIN")
        self.assertEqual(outcome["trip_id"], self.g["id"])
        self.assertNotIn("total_duration_seconds", outcome)

    def test_departure_and_arrival_usability_are_endpoint_specific(self):
        start = self.labels[self.g["id"]]["G22S"]
        end = self.labels[self.g["id"]]["A42S"]
        start.update(arrival_usable=False, arrival_quality_flags=["UNUSABLE_ORIGIN_ARRIVAL"])
        end.update(departure_usable=False, departure_quality_flags=["UNUSABLE_DESTINATION_DEPARTURE"])
        self.assertEqual(outcome_for(self.route, self.labels, stamp())["status"], "INFERRED")

    def test_required_field_usability_and_quality_are_fail_closed(self):
        mutations = (
            ("G22S", "departure_usable", False),
            ("G22S", "departure_usable", None),
            ("G22S", "departure_quality_flags", ["UNVERIFIED_DEPARTURE"]),
            ("A42S", "arrival_usable", False),
            ("A42S", "arrival_quality_flags", ["UNVERIFIED_ARRIVAL"]),
            ("G22S", "quality_flags", ["CSV_SCHEDULE_CHANGED"]),
        )
        for stop, field, value in mutations:
            labels = deepcopy(self.labels)
            labels[self.g["id"]][stop][field] = value
            with self.subTest(stop=stop, field=field):
                self.assertEqual(outcome_for(self.route, labels, stamp())["status"], "UNAVAILABLE")

    def test_missing_selected_label_does_not_use_another_trip_label(self):
        labels = {"unrelated": self.labels[self.g["id"]]}
        outcome = outcome_for(self.route, labels, stamp())
        self.assertEqual(outcome["reason"], "MISSING_OR_UNUSABLE_ENDPOINT_LABEL")

    def test_within_mode_switch_savings_differs_from_original_strategy_gain(self):
        first, second = trip(), trip("g2", departure=120, arrival=340)
        f = self.f
        labels = labels_for([first, second, f], {
            ("g1", "A42S"): (900, 910), ("g2", "A42S"): (500, 510),
            ("f1", "A41S"): (600, 610),
        })
        predictor = FixedPredictor({(first["id"], "G22S", "A42S"): 300,
                                    (second["id"], "G22S", "A42S"): 180,
                                    (f["id"], "B04S", "A41S"): -50})
        result = evaluate_case(case([first, second], [f]), templates(), labels,
                               predictors={"segment": predictor}, modes=("mta", "segment_model"))
        model = result["modes"]["segment_model"]
        self.assertEqual(result["reference_route_id"], "g_path")
        self.assertEqual(model["conditional_timing_decision"]["action"], "SWITCH")
        self.assertEqual(model["conditional_timing_decision"]["recommended_itinerary_id"], "f_path")
        self.assertEqual(model["outcomes"]["g_path"]["trip_id"], second["id"])
        self.assertEqual(model["inferred_switch_savings_seconds"], -115)
        self.assertEqual(model["inferred_savings_vs_original_reference_seconds"], 285)
        self.assertEqual(model["inferred_regret_within_forecast_selected_candidate_trains_seconds"], 115)
        summary = summarize_cases([result])
        self.assertEqual(summary["modes"]["segment_model"]["conditional_switches_with_nonpositive_inferred_savings"], 1)
        self.assertEqual(summary["modes"]["segment_model"]["conditional_switches_with_positive_inferred_savings"], 0)

    def test_unknown_outcome_keeps_savings_unavailable(self):
        result = evaluate_case(case([self.g], [self.f]), templates(), {})
        for mode in result["modes"].values():
            self.assertIsNone(mode["inferred_switch_savings_seconds"])
            self.assertIsNone(mode["inferred_savings_vs_original_reference_seconds"])
            self.assertFalse(mode["comparable_outcomes_complete"])


class ReplaySummaryTests(unittest.TestCase):
    def test_delay_filter_retains_success_failure_unknown_and_missed_opportunity(self):
        g, f = trip(), trip("f1", "F", 110, 400)
        value = case([g], [f])
        predictor = FixedPredictor({(g["id"], "G22S", "A42S"): 300})

        def replay(g_arrival, f_arrival, *, switch=True):
            labels = labels_for([g, f], {
                ("g1", "A42S"): (g_arrival, g_arrival + 10),
                ("f1", "A41S"): (f_arrival or 400, (f_arrival or 400) + 10),
            })
            if f_arrival is None:
                del labels[f["id"]]
            return evaluate_case(value, templates(), labels,
                                 predictors={"segment": predictor} if switch else None,
                                 modes=("mta", "segment_model"))

        # Qualification is based on the original MTA reference delay, even if
        # the model loses, cannot be scored, or fails to suggest a useful switch.
        delayed_success = replay(900, 400)
        delayed_failure_at_threshold = replay(600, 700)
        delayed_unknown_alternative = replay(900, None)
        delayed_stay_with_faster_alternative = replay(900, 400, switch=False)
        not_delayed_success = replay(500, 400)
        missing_reference = evaluate_case(value, templates(), {})
        missed_labels = labels_for([g, f])
        missed_labels[g["id"]]["G22S"]["departure_at"] = NOW + 50
        missed_reference = evaluate_case(value, templates(), missed_labels)
        no_reference = evaluate_case(case([], []), templates(), {})

        result = summarize_cases([
            delayed_success, delayed_failure_at_threshold, delayed_unknown_alternative,
            delayed_stay_with_faster_alternative, not_delayed_success,
            missing_reference, missed_reference, no_reference,
        ])
        self.assertEqual(result["candidate_case_count"], 8)
        self.assertEqual(result["qualifying_reference_delay_cases"], 4)
        self.assertFalse(result["selection_uses_model_switch_success"])
        self.assertEqual(result["reference_outcome_status_counts"], {
            "INFERRED": 5, "UNAVAILABLE": 1, "MISSED_SELECTED_TRAIN": 1, "NO_REFERENCE": 1,
        })
        summary = result["modes"]["segment_model"]
        self.assertEqual(summary["conditional_timing_actions"], {"SWITCH": 3, "STAY": 1})
        self.assertEqual(summary["conditional_switches_with_comparable_outcomes"], 2)
        self.assertEqual(summary["conditional_switches_with_positive_inferred_savings"], 1)
        self.assertEqual(summary["conditional_switches_with_nonpositive_inferred_savings"], 1)
        self.assertEqual(summary["conditional_switches_without_comparable_outcomes"], 1)
        self.assertEqual(summary["conditional_stays_with_faster_inferred_alternative"], 1)


class ReplayWalkingTests(unittest.TestCase):
    def test_cached_walking_changes_match_uncached_choice_and_actual_catchability(self):
        first = trip("first", departure=80, arrival=300)
        second = trip("second", departure=120, arrival=500)
        f = trip("f1", "F", 130, 400)
        value = case([first, second], [f])
        labels = labels_for([first, second, f], {
            ("first", "G22S"): (65, 70),
        })
        predictors = {"segment": FixedPredictor(default=20),
                      "departure": FixedPredictor(default=10)}
        original = templates()
        egress_only = deepcopy(original)
        egress_only[0]["egress_walk_seconds"] = 200
        access_with_inferred_miss = deepcopy(original)
        access_with_inferred_miss[0]["access_walk_seconds"] = 75
        access_selecting_later_train = deepcopy(original)
        access_selecting_later_train[0]["access_walk_seconds"] = 90
        access_and_egress = deepcopy(access_selecting_later_train)
        access_and_egress[0]["egress_walk_seconds"] = 0
        access_and_egress[1]["egress_walk_seconds"] = 200
        cache = {}
        results = []
        for route_templates in (original, egress_only, access_with_inferred_miss,
                                access_selecting_later_train, access_and_egress, original):
            cached = evaluate_case(value, route_templates, labels, predictors=predictors,
                                   prediction_cache=cache)
            uncached = evaluate_case(value, route_templates, labels, predictors=predictors)
            with self.subTest(walks=[(item["access_walk_seconds"], item["egress_walk_seconds"])
                                    for item in route_templates]):
                self.assertEqual(cached, uncached)
            results.append(cached)

        # Egress can change the fastest reference without changing the train.
        self.assertEqual([item["reference_route_id"] for item in results],
                         ["g_path", "f_path", "g_path", "f_path", "g_path", "g_path"])
        self.assertEqual([item["modes"]["mta"]["routes"][0]["selected_train"]["trip_id"]
                          for item in results],
                         [first["id"], first["id"], first["id"], second["id"], second["id"], first["id"]])
        self.assertEqual([item["modes"]["mta"]["outcomes"]["g_path"]["status"] for item in results],
                         ["INFERRED", "INFERRED", "MISSED_SELECTED_TRAIN",
                          "INFERRED", "INFERRED", "INFERRED"])
        self.assertEqual(results[1]["modes"]["mta"]["outcomes"]["g_path"]["total_duration_seconds"], 500)
        # Returning to the original walks must not inherit a cached ETA shift.
        self.assertEqual(results[0], results[-1])

    def test_walking_sensitivity_varies_each_access_and_egress_independently(self):
        first = trip("first", departure=60, arrival=300)
        second = trip("second", departure=100, arrival=350)
        f = trip("f1", "F", 130, 400)
        result = walking_sensitivity(case([first, second], [f]), templates(),
                                     labels_for([first, second, f]), deltas=(-20, 0, 20))
        self.assertEqual(result["scenario_count"], 81)
        scenarios = result["scenarios"]
        selected = {item["modes"]["mta"]["selected_train_ids"]["g_path"] for item in scenarios}
        self.assertEqual(selected, {first["id"], second["id"]})
        walks = {(item["walks"]["g_path"]["access_walk_seconds"],
                  item["walks"]["g_path"]["egress_walk_seconds"],
                  item["walks"]["f_path"]["access_walk_seconds"],
                  item["walks"]["f_path"]["egress_walk_seconds"]) for item in scenarios}
        self.assertEqual(len(walks), 81)
        self.assertIn((80, 10, 70, 65), walks)

    def test_negative_or_boolean_walking_time_is_invalid(self):
        for value in (-1, True, float("nan")):
            routes = templates()
            routes[0]["access_walk_seconds"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_templates(routes)


if __name__ == "__main__":
    unittest.main()
