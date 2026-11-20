"""Boundary and policy safeguards for the new November corridor evaluation."""

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from algo.scripts import evaluate_november
from algo.tests import test_google_corridor_replay as google_fixtures

from stayorswitch.november_replay import (
    POLICY, asof_problem_notices, cohort_summary, compare_modes, date_subset, plan_incidents,
    score_annotations, select_applicable_windows, select_encounter,
)
from stayorswitch.preincident_replay import local_time


def timestamp(text):
    return datetime.fromisoformat(text).timestamp()


def corridor(identity="corridor"):
    return {"id": identity, "reference_route_id": "stay", "routes": [
        {"id": "stay", "legs": [{"route_id": "5", "from_stop_id": "631S", "to_stop_id": "423S"}]}]}


def version(at, state="DISRUPTION", route="5", direction="S"):
    return {"first_observed_at": at, "state": state,
            "alert": {"informed_entities": [{"route_id": route}],
                      "description": direction + " trains are delayed"}}


def family(first, versions, identity="incident", routes=None):
    return {"incident_id": identity, "route_ids": routes or ["5"],
            "first_observed_at": first, "versions": versions}


def confirmed_case(at, identity="case", corridor_id="corridor", incident="incident"):
    return {"id": identity, "corridor_id": corridor_id, "incident_ids": [incident],
            "decision_at": at, "evaluation_anchor": at - 100,
            "official_text_review": {"status": "CONFIRMED", "confirmed_impact": "DISRUPTION"}}


def inferred(seconds):
    return {"status": "INFERRED", "total_duration_seconds": seconds}


def mode(action, selected, outcomes, classification="UNKNOWN", complete=False):
    return {"strict_decision": {"action": action, "recommended_itinerary_id": selected},
            "outcomes": outcomes, "scores": {"strict_decision": {
                "classification": classification,
                "all_forecast_selected_candidate_outcomes_available": complete}}}


def scored_case(identity="case", corridor_id="corridor", incident="incident", *,
                model_action="SWITCH", model_outcome=None, classification="MEANINGFUL_GAIN"):
    model_outcome = inferred(1200) if model_outcome is None else model_outcome
    chosen = "alternative" if model_action == "SWITCH" else "stay" if model_action == "STAY" else None
    return score_annotations({"id": identity, "corridor_id": corridor_id,
        "incident_ids": [incident], "incident_origin": "FIRST_OBSERVED_DURING_NOVEMBER",
        "official_text_review": {"confirmed_impact": "DISRUPTION"},
        "modes": {
            "mta": mode("STAY", "stay", {"stay": inferred(1800), "alternative": inferred(1700)},
                        "ACCEPTABLE_STAY", True),
            "time_profile": mode("STAY", "stay", {"stay": inferred(1600)}, "UNKNOWN"),
            "incident_profile": mode(model_action, chosen,
                {} if chosen is None else {chosen: model_outcome}, classification)}})


class IncidentPlanningTests(unittest.TestCase):
    def test_every_relevant_version_receipt_starts_a_candidate_grid(self):
        first = timestamp("2026-11-03T08:00:00-05:00")
        later = first + 3 * 3600 + 17.25
        inventory = {"incidents": [family(first, [version(first), version(later)])]}
        plans, excluded = plan_incidents(inventory, corridor())
        self.assertEqual(excluded, {})
        self.assertEqual(plans[0]["candidate_receipt_anchors"], [first, later])
        for anchor in (first, later):
            for lag in range(0, 7201, 300):
                self.assertIn(anchor + lag, plans[0]["decision_times"])
        self.assertEqual(len(plans[0]["decision_times"]), 50)

    def test_later_qualified_direction_receipt_gets_its_own_full_window(self):
        first = timestamp("2026-11-03T08:00:00-05:00")
        southbound = first + 3 * 3600
        later_receipt = southbound + 67
        plans, _ = plan_incidents({"incidents": [family(first, [
            version(first, direction="N"), version(southbound), version(later_receipt)])]}, corridor())
        # The earlier northbound version never enters the confirmed input set.
        times = [southbound, southbound + 300, later_receipt,
                 later_receipt + 300, southbound + 7200, southbound + 7500]
        cases = [confirmed_case(at, "case-" + str(i)) for i, at in enumerate(times)]
        original = deepcopy(cases)
        selected, excluded, anchors = select_applicable_windows(cases, {"corridor": plans})
        self.assertEqual(anchors[0]["first_applicable_receipt"], southbound)
        self.assertEqual([c["decision_at"] for c in selected],
                         [southbound, later_receipt, southbound + 300, southbound + 7200])
        self.assertEqual(len(excluded), 2)
        self.assertTrue(all(c["evaluation_anchor"] == southbound for c in selected))
        self.assertEqual(selected[-1]["lag_from_first_applicable_seconds"], 7200)
        self.assertEqual(cases, original)

    def test_carried_october_family_is_clipped_to_november_boundary(self):
        earlier = timestamp("2026-10-31T22:30:00-04:00")
        start = timestamp("2026-11-01T00:00:00-04:00")
        plans, _ = plan_incidents({"incidents": [family(earlier, [version(earlier)])]}, corridor())
        plan = plans[0]
        self.assertEqual(plan["incident_origin"], "CARRIED_IN_FROM_OCTOBER")
        self.assertEqual(plan["first_problem_receipt"], earlier)
        self.assertEqual(plan["candidate_receipt_anchors"], [start])
        self.assertEqual(plan["decision_times"][0], start)
        selected, _, anchors = select_applicable_windows(
            [confirmed_case(start)], {"corridor": plans})
        self.assertEqual(anchors[0]["first_applicable_receipt"], start)
        self.assertEqual(len(selected), 1)

    def test_first_boundary_minutes_have_unresolved_origin(self):
        start = timestamp("2026-11-01T00:00:00-04:00")
        inventory = {"incidents": [
            family(start + 299, [version(start + 299)], "uncertain"),
            family(start + 300, [version(start + 300)], "later")]}
        plans, _ = plan_incidents(inventory, corridor())
        self.assertEqual([p["incident_origin"] for p in plans],
                         ["LEFT_BOUNDARY_ORIGIN_UNRESOLVED", "FIRST_OBSERVED_DURING_NOVEMBER"])

    def test_dst_repeated_clock_times_remain_distinct_instants(self):
        early = timestamp("2026-11-01T01:30:00-04:00")
        late = timestamp("2026-11-01T01:30:00-05:00")
        plans, _ = plan_incidents({"incidents": [family(early, [version(early), version(late)])]}, corridor())
        self.assertEqual(late - early, 3600)
        self.assertEqual(local_time(early)[:19], local_time(late)[:19])
        self.assertNotEqual(local_time(early), local_time(late))
        self.assertIn(early, plans[0]["decision_times"])
        self.assertIn(late, plans[0]["decision_times"])
        self.assertEqual(len(plans[0]["decision_times"]), len(set(plans[0]["decision_times"])))
        self.assertTrue(all(local_time(at)[:10] == "2026-11-01" for at in plans[0]["decision_times"]))

    def test_end_boundary_uses_new_york_calendar_date(self):
        final = timestamp("2026-11-18T23:59:00-05:00")
        beyond = timestamp("2026-11-19T00:00:00-05:00")
        plans, excluded = plan_incidents({"incidents": [
            family(final, [version(final)], "last"),
            family(beyond, [version(beyond)], "outside")]}, corridor())
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["decision_times"], [final])
        self.assertEqual(excluded, {"PROBLEM_AFTER_EVALUATION_END": 1})

    def test_november_19_is_outcome_boundary_not_a_decision_date(self):
        boundary = timestamp("2026-11-19T12:00:00-05:00")
        plans, excluded = plan_incidents({"incidents": [
            family(boundary, [version(boundary)], "boundary-only")]}, corridor())
        self.assertEqual(POLICY["outcome_boundary_date"], "2026-11-19")
        self.assertEqual(plans, [])
        self.assertEqual(excluded, {"PROBLEM_AFTER_EVALUATION_END": 1})
        self.assertFalse(date_subset({"decision_at": boundary}))

    def test_missing_confirmed_receipt_is_explicitly_excluded(self):
        first = timestamp("2026-11-03T08:00:00-05:00")
        plans, _ = plan_incidents({"incidents": [family(first, [version(first)])]}, corridor())
        selected, excluded, anchors = select_applicable_windows(
            [confirmed_case(first + 300)], {"corridor": plans})
        self.assertEqual(selected, [])
        self.assertEqual(anchors, [])
        self.assertEqual(excluded, [{"id": "case", "reason": "NO_TEXT_CONFIRMED_APPLICABLE_RECEIPT"}])

    def test_planned_and_other_line_versions_do_not_start_grid(self):
        first = timestamp("2026-11-03T08:00:00-05:00")
        inventory = {"incidents": [family(first, [version(first, "PLANNED"),
            version(first + 100, route="4")])]}
        plans, excluded = plan_incidents(inventory, corridor())
        self.assertEqual(plans, [])
        self.assertEqual(excluded, {"NO_UNPLANNED_CLASSIFIED_SERVICE_PROBLEM": 1})


class PolicyOutcomeTests(unittest.TestCase):
    def test_compares_actual_policy_trains_not_unconditional_fastest(self):
        case = {"modes": {
            "mta": mode("STAY", "stay", {"stay": inferred(1800), "fastest": inferred(800)}),
            "incident_profile": mode("SWITCH", "alternative", {
                "stay": inferred(3100), "alternative": inferred(1200)})}}
        result = compare_modes(case, "mta", "incident_profile")
        self.assertEqual(result["gain_seconds"], 600)
        self.assertEqual(result["baseline_route_id"], "stay")
        self.assertEqual(result["classification"], "MEANINGFUL_GAIN")

    def test_three_minute_tie_boundaries_are_inclusive(self):
        for gain, expected in ((180, "PRACTICAL_TIE"), (-180, "PRACTICAL_TIE"),
                               (181, "MEANINGFUL_GAIN"), (-181, "MEANINGFUL_LOSS")):
            with self.subTest(gain=gain):
                case = {"modes": {"mta": mode("STAY", "stay", {"stay": inferred(1800)}),
                    "time_profile": mode("SWITCH", "alternative", {"alternative": inferred(1800 - gain)})}}
                self.assertEqual(compare_modes(case, "mta", "time_profile")["classification"], expected)

    def test_missed_or_missing_selected_journey_never_counts_as_success(self):
        for outcome in ({"status": "MISSED_SELECTED_TRAIN"}, {"status": "UNAVAILABLE"}, {}):
            with self.subTest(outcome=outcome):
                case = {"modes": {"mta": mode("STAY", "stay", {"stay": inferred(1800)}),
                    "incident_profile": mode("SWITCH", "alternative", {"alternative": outcome})}}
                result = compare_modes(case, "mta", "incident_profile")
                self.assertTrue(result["eligible_actions"])
                self.assertFalse(result["comparable"])
                self.assertIsNone(result["gain_seconds"])
                self.assertEqual(result["classification"], "UNKNOWN")

    def test_abstention_is_not_an_eligible_policy_pair(self):
        case = {"modes": {"mta": mode("UNDETERMINED", None, {}),
            "incident_profile": mode("SWITCH", "alternative", {"alternative": inferred(1200)})}}
        result = compare_modes(case, "mta", "incident_profile")
        self.assertFalse(result["eligible_actions"])
        self.assertFalse(result["comparable"])

    def test_summary_keeps_repeated_incidents_and_unknowns_separate(self):
        cases = [scored_case("gain"),
                 scored_case("miss", model_outcome={"status": "MISSED_SELECTED_TRAIN"}, classification="UNKNOWN"),
                 scored_case("other-corridor", corridor_id="second", model_action="STAY",
                             model_outcome=inferred(1800), classification="UNKNOWN"),
                 scored_case("abstention", incident="second-incident", model_action="UNDETERMINED",
                             classification="NOT_A_DECISION")]
        result = cohort_summary(cases)
        self.assertEqual(result["cases"], 4)
        self.assertEqual(result["corridor_incidents"], 3)
        self.assertEqual(result["unique_incident_count"], 2)
        self.assertEqual(result["model_switch_vs_model_stay"], {
            "recommendations": 2, "classes": {"MEANINGFUL_GAIN": 1, "UNKNOWN": 1}})
        model = result["by_mode"]["incident_profile"]
        self.assertEqual(model["known_missed_selected_journeys"], 1)
        self.assertEqual(model["stay_outcomes"], {"UNKNOWN": 1})
        self.assertEqual(model["selected_journey_statuses"]["NO_SELECTED_JOURNEY"], 1)
        paired = result["paired_policies"]["incident_vs_mta"]
        self.assertEqual(paired["eligible_actions"], 3)
        self.assertEqual(paired["comparable"], 2)
        self.assertEqual(paired["classes"], {"MEANINGFUL_GAIN": 1, "UNKNOWN": 1, "PRACTICAL_TIE": 1})
        self.assertEqual(result["mta_stay_model_switch"]["cases"], 2)

    def test_new_date_subset_is_local_date_not_utc_date(self):
        self.assertFalse(date_subset({"decision_at": timestamp("2026-11-16T04:59:59+00:00")}))
        self.assertTrue(date_subset({"decision_at": timestamp("2026-11-16T05:00:00+00:00")}))
        self.assertTrue(date_subset({"decision_at": timestamp("2026-11-19T04:59:59+00:00")}))
        self.assertFalse(date_subset({"decision_at": timestamp("2026-11-19T05:00:00+00:00")}))

    def test_annotations_do_not_mutate_input_case(self):
        original = {"modes": {
            "mta": mode("STAY", "stay", {"stay": inferred(1800)}),
            "time_profile": mode("STAY", "stay", {"stay": inferred(1700)}),
            "incident_profile": mode("SWITCH", "alternative", {"alternative": inferred(1200)})}}
        before = deepcopy(original)
        annotated = score_annotations(original)
        self.assertEqual(original, before)
        self.assertEqual(set(annotated["paired_policies"]), {"time_vs_mta", "incident_vs_mta", "incident_vs_time"})
        self.assertEqual(annotated["policy_comparison"]["gain_seconds"], 600)


class SharedSnapshotStorageTests(unittest.TestCase):
    def test_shared_records_round_trip_once_and_requested_cutoffs_are_filtered(self):
        first = timestamp("2026-11-03T08:00:00-05:00")
        train = {"feed_id": "numbered", "captured_at": first - 10,
                 "trips": [{"trip_id": "train-1", "stops": ["631S", "423S"]}]}
        alerts = {"feed_id": "alerts", "captured_at": first - 15, "alerts": [{"id": "notice"}]}
        later_train = {"feed_id": "numbered", "captured_at": first + 45,
                       "trips": [{"trip_id": "train-2", "stops": ["631S", "423S"]}]}
        selected = {first: [train, alerts], first + 30: [train, alerts], first + 60: [later_train, alerts]}
        packed = evaluate_november.pack_snapshots(selected, [first + 60, first, first + 30, first + 30])
        self.assertEqual(len(packed["records"]), 3)
        self.assertEqual([r["cutoff"] for r in packed["cutoffs"]], [first, first + 30, first + 60])
        self.assertEqual(packed["cutoffs"][0]["snapshot_indices"], packed["cutoffs"][1]["snapshot_indices"])
        with TemporaryDirectory() as folder:
            root = Path(folder)
            evaluate_november.dump(root / "day.json.gz", packed)
            evaluate_november.dump(root / "index.json", {"days": [
                {"date": "2026-11-03", "path": "day.json.gz"},
                {"date": "2026-11-04", "path": "unrequested-day-does-not-exist.json.gz"}]})
            prepared = {"selected_input_snapshots": {"path": "index.json"}}
            with patch.object(evaluate_november, "ROOT", root):
                full = list(evaluate_november.selected_snapshots(prepared, selected))
                filtered = list(evaluate_november.selected_snapshots(prepared, [first + 30]))
            self.assertEqual(full, [{"cutoff": at, "snapshots": snapshots} for at, snapshots in selected.items()])
            self.assertIs(full[0]["snapshots"][0], full[1]["snapshots"][0])
            self.assertIs(full[0]["snapshots"][1], full[2]["snapshots"][1])
            self.assertEqual(filtered, [{"cutoff": first + 30, "snapshots": selected[first + 30]}])

    def test_conflicting_records_at_same_capture_are_not_merged_by_hash(self):
        cutoff = timestamp("2026-11-03T08:00:00-05:00")
        original = {"feed_id": "numbered", "captured_at": cutoff - 5,
                    "sha256": "same-source-hash", "status": "VALID", "trips": [{"trip_id": "train-1"}]}
        conflict = dict(deepcopy(original), status="MISSING", trips=[],
                        reason_codes=["CONFLICTING_EQUAL_CAPTURE_OBSERVATIONS"])
        selected = {cutoff: [original], cutoff + 10: [conflict]}
        packed = evaluate_november.pack_snapshots(selected, selected)
        self.assertEqual(len(packed["records"]), 2)
        self.assertNotEqual(packed["cutoffs"][0]["snapshot_indices"], packed["cutoffs"][1]["snapshot_indices"])
        decoded = {r["cutoff"]: [packed["records"][i] for i in r["snapshot_indices"]]
                   for r in packed["cutoffs"]}
        self.assertEqual(decoded, selected)
        self.assertEqual(decoded[cutoff][0]["status"], "VALID")
        self.assertEqual(decoded[cutoff + 10][0]["status"], "MISSING")


class CohortRouteAliasTests(unittest.TestCase):
    def fixture(self, observed, selector):
        index = google_fixtures.Index()
        index.versions["notice-v1"]["alert"].update(
            header="Downtown [{}] trains are delayed.".format(selector),
            informed_entities=[{"route_id": selector}])
        candidate = google_fixtures.corridor()
        template = candidate["routes"][0]["legs"][0]
        base = POLICY["cohort_route_aliases"].get(observed, observed)
        # These are already supplied route variants, not new provider pooling.
        template.update(route_id=base, route_ids=[base] + ([observed] if observed != base else []))
        prediction = google_fixtures.prediction()
        prediction["routes"][0]["selected_legs"][0]["route_id"] = observed
        plan = {"decision_times": [google_fixtures.BASE], "incident_id": google_fixtures.INCIDENT,
                "first_family_receipt": google_fixtures.BASE, "first_problem_receipt": google_fixtures.BASE}
        return index, candidate, prediction, plan

    def notices(self, index, observed):
        return asof_problem_notices(index, google_fixtures.BASE, observed,
                                    ["631S", "423S"], google_fixtures.INCIDENT)

    def test_observed_variants_match_base_selectors_and_preserve_actual_line(self):
        for observed, base in (("7X", "7"), ("FX", "F")):
            with self.subTest(observed=observed):
                index, candidate, prediction, plan = self.fixture(observed, base)
                originals = deepcopy((index.versions, candidate, prediction))
                notices = self.notices(index, observed)
                self.assertEqual(len(notices), 1)
                self.assertEqual(notices[0]["cohort_base_route_alias"],
                                 {"observed_route_id": observed, "selector_route_id": base})
                self.assertEqual(notices[0]["informed_entities"], [{"route_id": base}])
                selected, reason = select_encounter(plan, candidate, prediction, index)
                self.assertIsNone(reason)
                self.assertEqual(selected["exposure"][0]["route_id"], observed)
                self.assertEqual(selected["asof_mta_prediction"]["routes"][0]["selected_legs"][0]["route_id"], observed)
                self.assertEqual((index.versions, candidate, prediction), originals)
                self.assertEqual(candidate["routes"][0]["legs"][0]["route_ids"], [base, observed])

    def test_base_service_does_not_inherit_variant_only_selector(self):
        for observed, selector in (("7", "7X"), ("F", "FX")):
            with self.subTest(observed=observed, selector=selector):
                index, candidate, prediction, plan = self.fixture(observed, selector)
                self.assertEqual(self.notices(index, observed), [])
                selected, reason = select_encounter(plan, candidate, prediction, index)
                self.assertIsNone(selected)
                self.assertEqual(reason, "NO_ASOF_RECORDED_PROBLEM_FOR_FIXED_STAY")
                self.assertEqual(candidate["routes"][0]["legs"][0]["route_ids"], [observed])

    def test_same_platform_five_and_four_remain_distinct_notice_scopes(self):
        for observed, selector in (("5", "4"), ("4", "5")):
            with self.subTest(observed=observed, selector=selector):
                index, candidate, prediction, plan = self.fixture(observed, selector)
                self.assertEqual(self.notices(index, observed), [])
                self.assertIsNone(select_encounter(plan, candidate, prediction, index)[0])

    def test_notice_matching_exact_variant_and_base_is_returned_once(self):
        for observed, base in (("7X", "7"), ("FX", "F")):
            with self.subTest(observed=observed):
                index, _, _, _ = self.fixture(observed, observed)
                index.versions["notice-v1"]["alert"]["informed_entities"] = [
                    {"route_id": observed}, {"route_id": base}]
                notices = self.notices(index, observed)
                self.assertEqual(len(notices), 1)
                self.assertNotIn("cohort_base_route_alias", notices[0])
                self.assertEqual(notices[0]["version_id"], "notice-v1")


class StayScopePredictionTests(unittest.TestCase):
    def test_scope_prediction_uses_only_fixed_stay_without_mutating_config(self):
        candidate = google_fixtures.corridor()
        candidate["routes"].reverse()
        candidate["unavailable_candidates"] = [{"id": "unresolved-provider-path"}]
        original = deepcopy(candidate)
        snapshots = [{"feed_id": "numbered", "captured_at": google_fixtures.BASE}]
        index = google_fixtures.Index()
        expected = {"cutoff": google_fixtures.BASE, "routes": [{"id": "google-stay"}]}
        with patch.object(evaluate_november, "predict", return_value=expected) as mock_predict:
            actual = evaluate_november.predict_stay_scope(snapshots, candidate, google_fixtures.BASE, index)
        self.assertIs(actual, expected)
        mock_predict.assert_called_once()
        called_snapshots, scoped, cutoff, called_index = mock_predict.call_args.args
        self.assertIs(called_snapshots, snapshots)
        self.assertIs(called_index, index)
        self.assertEqual(cutoff, google_fixtures.BASE)
        self.assertEqual(scoped["routes"], [next(r for r in candidate["routes"] if r["id"] == "google-stay")])
        self.assertEqual(scoped["unavailable_candidates"], [])
        self.assertEqual(candidate, original)

    def predictions(self):
        stay = {"id": "stay", "eta": 1800, "total_duration_seconds": 1200,
                "selected_legs": [{"trip_id": "selected-train", "route_id": "5"}],
                "context": {"state": "DISRUPTION", "evidence_status": "FRESH"}}
        scoped = {"cutoff": 600, "routes": [stay],
                  "feed_evidence": {"numbered": {"captured_at": 590, "sha256": "original-source"}}}
        full = deepcopy(scoped)
        full["routes"].insert(0, {"id": "alternative", "eta": 1700})
        return full, scoped

    def test_same_stay_and_feed_evidence_pass_with_additional_alternatives(self):
        full, scoped = self.predictions()
        self.assertIsNone(evaluate_november.assert_stay_parity(full, scoped, "stay"))

    def test_changed_stay_eta_train_context_or_feed_metadata_fails_parity(self):
        for defect in ("eta", "train", "context", "feed"):
            with self.subTest(defect=defect):
                full, scoped = self.predictions()
                stay = next(r for r in full["routes"] if r["id"] == "stay")
                if defect == "eta":
                    stay["eta"] += 1
                elif defect == "train":
                    stay["selected_legs"][0]["trip_id"] = "different-train"
                elif defect == "context":
                    stay["context"]["state"] = "SEVERE"
                else:
                    full["feed_evidence"]["numbered"]["captured_at"] += 1
                with self.assertRaises(ValueError):
                    evaluate_november.assert_stay_parity(full, scoped, "stay")


if __name__ == "__main__":
    unittest.main()
