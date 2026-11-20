"""Google Stay identity, chronological event selection, and review safeguards."""

from copy import deepcopy
from datetime import datetime
import unittest

from stayorswitch.google_corridor_replay import (
    POLICY, apply_review, asof_problem_notices, plan_incidents, representatives, review_groups,
    select_encounter, validate_corridors,
)


BASE = datetime.fromisoformat("2026-10-28T09:00:00-04:00").timestamp()
INCIDENT = "lmm:alert:example"


def corridor():
    return {"id": "example", "origin": "origin", "destination": "destination",
            "google": {"capture_id": "current"}, "reference_route_id": "google-stay",
            "routes": [{"id": name, "access_walk_seconds": 120, "egress_walk_seconds": 120,
                        "transfer_walk_seconds": [], "legs": [{"route_id": line, "route_ids": [line],
                        "feed_id": "numbered", "from_stop_id": "631S", "to_stop_id": "423S"}]}
                       for name, line in (("google-stay", "5"), ("alternative", "4"))]}


def version(at=BASE, line="5", state="DISRUPTION"):
    return {"first_observed_at": at, "state": state,
            "alert": {"informed_entities": [{"route_id": line}]}}


def family(first=BASE, versions=None):
    return {"incident_id": INCIDENT, "first_observed_at": first, "route_ids": ["4", "5"],
            "versions": versions or [version(at=first)]}


def plan():
    return plan_incidents({"incidents": [family()]}, corridor())[0][0]


class Index:
    def __init__(self, present=True, freshness="FRESH"):
        self.present, self.freshness = present, freshness
        self.times = [BASE]
        self.entries = [{"captured_at": BASE, "valid": True,
                         "version_ids": ["notice-v1"] if present else []}]
        self.versions = {"notice-v1": {"incident_id": INCIDENT, "state": "DISRUPTION", "cause": "UNKNOWN",
            "classification_rule": "EXPLICIT_SERVICE_IMPACT", "no_service_scope": None,
            "no_service": False, "no_service_route_ids": [], "alert": {
            "id": INCIDENT, "header": "Downtown [5] trains are delayed.",
            "informed_entities": [{"route_id": "5"}], "active_periods": [{"start": BASE, "end": None}]}}}
        self.families = {INCIDENT: {"first_observed_at": BASE}}

    def context_at(self, at, line, stop_ids):
        return {"state": "DISRUPTION", "evidence_status": self.freshness,
                "applicable": True, "ambiguous_scope": False,
                "alerts": [{"incident_id": INCIDENT, "version_id": "notice-v1", "state": "DISRUPTION",
                            "header": "Downtown [5] trains are delayed.", "captured_at": at,
                            "age_seconds": at - BASE}] if self.present else []}


def prediction(at=BASE, timing=True, freshness="FRESH"):
    index = Index(freshness=freshness)
    stay = {"id": "google-stay", "timing_eligible": timing, "comparison_eligible": timing,
            "total_duration_seconds": 1800 if timing else None,
            "selected_legs": [{"leg_index": 0, "route_id": "5", "from_stop_id": "631S",
                "to_stop_id": "423S", "platform_direction": "S", "segment_stop_ids": ["631S", "423S"],
                "incident_context": index.context_at(at, "5", [])}] if timing else []}
    return {"cutoff": at, "routes": [stay, {"id": "alternative", "timing_eligible": True,
                                           "total_duration_seconds": 600}]}


def case(at=BASE, timing=True):
    return select_encounter(plan(), corridor(), prediction(at, timing), Index())[0]


def review(cases):
    result = {"groups": review_groups(cases)}
    for group in result["groups"]:
        group.update(status="CONFIRMED", confirmed_impact="DISRUPTION",
                     planning_status="UNPLANNED", reason="The exact notice names the southbound Stay line.")
    return result


class PlanningTests(unittest.TestCase):
    def test_current_google_stay_identity_is_required(self):
        c = corridor()
        self.assertEqual(validate_corridors({"corridors": [c]})[0]["reference_route_id"], "google-stay")
        c["reference_route_id"] = "invented"
        with self.assertRaises(ValueError):
            validate_corridors({"corridors": [c]})

    def test_first_problem_names_exact_google_line_not_family_union(self):
        f = family(versions=[version(BASE, "4"), version(BASE + 900, "5")])
        selected, _ = plan_incidents({"incidents": [f]}, corridor())
        self.assertEqual(selected[0]["first_problem_receipt"], BASE + 900)

    def test_first_problem_and_later_version_receipts_do_not_backdate_severity(self):
        f = family(versions=[version(), version(BASE + 6100, state="SEVERE")])
        selected, _ = plan_incidents({"incidents": [f]}, corridor())
        self.assertEqual(selected[0]["first_problem_receipt"], BASE)
        self.assertIn(BASE + 6100, selected[0]["decision_times"])
        self.assertIn(BASE + 7200, selected[0]["decision_times"])

    def test_version_receipts_after_two_hours_are_outside_scope(self):
        f = family(versions=[version(), version(BASE + 7201, state="SEVERE")])
        selected, _ = plan_incidents({"incidents": [f]}, corridor())
        self.assertNotIn(BASE + 7201, selected[0]["decision_times"])

    def test_planned_only_and_cross_split_families_are_excluded(self):
        earlier = datetime.fromisoformat("2026-10-24T23:00:00-04:00").timestamp()
        selected, counts = plan_incidents({"incidents": [family(versions=[version(state="PLANNED")]),
            family(first=earlier, versions=[version()])]}, corridor())
        self.assertEqual(selected, [])
        self.assertEqual(sum(counts.values()), 2)

    def test_cutoffs_cannot_escape_the_test_week(self):
        late = datetime.fromisoformat("2026-10-31T23:45:00-04:00").timestamp()
        selected, _ = plan_incidents({"incidents": [family(first=late)]}, corridor())
        self.assertTrue(all(t < late + 900 for t in selected[0]["decision_times"]))


class EncounterTests(unittest.TestCase):
    def test_google_stay_does_not_change_when_historical_alternative_is_faster(self):
        selected = case()
        self.assertEqual(selected["reference_route_id"], "google-stay")
        self.assertFalse(selected["selection_uses_outcomes"])

    def test_missing_stay_timing_is_retained_with_path_endpoint_exposure(self):
        selected = case(timing=False)
        self.assertEqual(selected["exposure"][0]["exposure_source"], "FIXED_GOOGLE_PATH_ENDPOINTS_ONLY")
        self.assertFalse(selected["asof_mta_prediction"]["routes"][0]["timing_eligible"])

    def test_last_observed_notice_is_retained_but_freshness_is_disclosed(self):
        selected, _ = select_encounter(plan(), corridor(), prediction(freshness="LAST_OBSERVED"), Index())
        self.assertEqual(selected["exposure"][0]["evidence_status"], "LAST_OBSERVED")

    def test_no_relevant_asof_notice_does_not_create_an_incident(self):
        pred = prediction()
        pred["routes"][0]["selected_legs"][0]["incident_context"]["alerts"] = []
        selected, reason = select_encounter(plan(), corridor(), pred, Index(present=False))
        self.assertIsNone(selected)
        self.assertEqual(reason, "NO_ASOF_RECORDED_PROBLEM_FOR_FIXED_STAY")

    def test_unplanned_extra_checkpoint_is_rejected(self):
        self.assertEqual(select_encounter(plan(), corridor(), prediction(BASE + 1), Index())[1],
                         "OUTSIDE_PREDECLARED_CHECKPOINTS")

    def test_outcomes_and_recommendations_cannot_change_selection(self):
        original = case()
        pred = prediction()
        pred.update(outcomes={"google-stay": "slow"}, recommendation="alternative")
        changed, _ = select_encounter(plan(), corridor(), pred, Index())
        self.assertEqual(original["id"], changed["id"])
        self.assertEqual(original["exposure_sha256"], changed["exposure_sha256"])


class RawAsOfNoticeTests(unittest.TestCase):
    def notices(self, index, cutoff=BASE, line="5"):
        return asof_problem_notices(index, cutoff, line, ["631S", "423S"], INCIDENT)

    def test_newer_empty_capture_replaces_an_earlier_active_notice(self):
        index = Index()
        index.times.append(BASE + 300)
        index.entries.append({"captured_at": BASE + 300, "valid": True, "version_ids": []})
        self.assertEqual(len(self.notices(index, BASE + 299)), 1)
        self.assertEqual(self.notices(index, BASE + 300), [])

    def test_newer_invalid_capture_does_not_fall_back_to_an_older_success(self):
        index = Index()
        index.times.append(BASE + 300)
        index.entries.append({"captured_at": BASE + 300, "valid": False,
                              "version_ids": ["notice-v1"]})
        self.assertEqual(len(self.notices(index, BASE + 299)), 1)
        self.assertEqual(self.notices(index, BASE + 300), [])

    def test_later_severe_version_is_not_visible_before_its_receipt(self):
        index = Index()
        severe = deepcopy(index.versions["notice-v1"])
        severe.update(state="SEVERE", classification_rule="EXPLICIT_SEVERE_IMPACT")
        severe["alert"]["header"] = "Downtown [5] trains are severely delayed."
        index.versions["notice-v2"] = severe
        index.times.append(BASE + 300)
        index.entries.append({"captured_at": BASE + 300, "valid": True,
                              "version_ids": ["notice-v2"]})
        earlier = self.notices(index, BASE + 299)
        self.assertEqual([(r["version_id"], r["state"]) for r in earlier],
                         [("notice-v1", "DISRUPTION")])
        later = self.notices(index, BASE + 300)
        self.assertEqual([(r["version_id"], r["state"]) for r in later],
                         [("notice-v2", "SEVERE")])
        self.assertEqual(later[0]["captured_at"], BASE + 300)

    def test_no_notice_is_visible_before_the_first_received_capture(self):
        self.assertEqual(self.notices(Index(), BASE - 1), [])

    def test_both_directions_text_is_retained_for_review_when_frozen_scope_rejects_it(self):
        index = Index()
        index.versions["notice-v1"]["alert"]["header"] = (
            "[5] trains are delayed in both directions after an uptown train had a brake issue.")
        original = deepcopy(index.versions)
        rows = self.notices(index)
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["model_scope_matches"], False)
        self.assertEqual(rows[0]["model_scope"], "UNRELATED")
        self.assertTrue(rows[0]["frozen_classifier_and_scope_are_unchanged"])
        self.assertIn("both directions", rows[0]["header"])
        self.assertEqual(index.versions, original)

    def test_expired_active_period_is_excluded_at_its_end_boundary(self):
        index = Index()
        index.versions["notice-v1"]["alert"]["active_periods"] = [
            {"start": BASE, "end": BASE + 300}]
        self.assertEqual(len(self.notices(index, BASE + 299)), 1)
        self.assertEqual(self.notices(index, BASE + 300), [])

    def test_future_active_period_is_not_yet_a_service_problem(self):
        index = Index()
        index.versions["notice-v1"]["alert"]["active_periods"] = [
            {"start": BASE + 300, "end": None}]
        self.assertEqual(self.notices(index, BASE + 299), [])
        self.assertEqual(len(self.notices(index, BASE + 300)), 1)

    def test_family_route_union_cannot_override_the_actual_stay_line(self):
        index = Index()
        index.families[INCIDENT]["route_ids"] = ["4", "5"]
        index.versions["notice-v1"]["alert"].update(
            header="Downtown [4] trains are delayed.", informed_entities=[{"route_id": "4"}])
        self.assertEqual(self.notices(index, line="5"), [])
        self.assertEqual(len(self.notices(index, line="4")), 1)
        # Even a cached prediction context naming the family cannot create raw
        # evidence that this current notice affects the selected 5 train.
        selected, reason = select_encounter(plan(), corridor(), prediction(), index)
        self.assertIsNone(selected)
        self.assertEqual(reason, "NO_ASOF_RECORDED_PROBLEM_FOR_FIXED_STAY")


class ReviewAndRepresentativeTests(unittest.TestCase):
    def test_receipt_ages_do_not_create_redundant_review_groups(self):
        values = [case(), case(BASE + 300)]
        self.assertEqual(len(review_groups(values)), 1)
        confirmed, excluded = apply_review(values, review(values))
        self.assertEqual(len(confirmed), 2)
        self.assertEqual(excluded, [])

    def test_edited_text_or_case_membership_fails_review_validation(self):
        values = [case()]
        for defect in ("text", "case"):
            r = review(values)
            if defect == "text":
                r["groups"][0]["exposure"][0]["notices"][0]["header"] = "Different notice"
            else:
                r["groups"][0]["case_ids"].append("not-a-case")
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                apply_review(values, r)

    def test_pending_duplicate_or_missing_groups_cannot_freeze(self):
        values = [case()]
        pending = {"groups": review_groups(values)}
        duplicate = review(values)
        duplicate["groups"] += deepcopy(duplicate["groups"])
        for r in (pending, duplicate, {"groups": []}):
            with self.assertRaises(ValueError):
                apply_review(values, r)

    def test_planned_confirmations_are_not_admitted(self):
        values = [case()]
        r = review(values)
        r["groups"][0]["planning_status"] = "PLANNED"
        with self.assertRaises(ValueError):
            apply_review(values, r)

    def test_first_timed_checkpoint_is_selected_without_outcome_filtering(self):
        early, timed, late = case(timing=False), case(BASE + 300), case(BASE + 600)
        timed["outcomes"] = {"status": "UNAVAILABLE"}
        late["outcomes"] = {"saving_seconds": 1000}
        self.assertEqual(representatives([late, early, timed])[0]["id"], timed["id"])

    def test_all_unavailable_incident_retains_earliest_unknown_representative(self):
        early, later = case(timing=False), case(BASE + 300, timing=False)
        self.assertEqual(representatives([later, early])[0]["id"], early["id"])


if __name__ == "__main__":
    unittest.main()
