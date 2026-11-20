"""Same-train forecast revision selection without retrospective outcomes."""

from copy import deepcopy
from datetime import datetime
import unittest

from stayorswitch.feed_revision_replay import (
    POLICY, choose_pair, physical_sequence, representatives,
)


BASE = datetime.fromisoformat("2026-10-30T10:00:00-04:00").timestamp()
IDS = [value["id"] for value in POLICY["routes"]]


def route(identifier, line, feed, arrival, departure, cutoff):
    raw = "060000_" + line + "..S"
    return {
        "id": identifier, "family": identifier, "timing_eligible": True,
        "comparison_eligible": True, "eta": arrival + 120,
        "total_duration_seconds": arrival + 120 - cutoff,
        "context": {"state": "NORMAL", "evidence_status": "FRESH", "incident_ids": []},
        "selected_legs": [{
            "feed_id": feed, "service_date": "20261030", "route_id": line,
            "raw_trip_id": raw,
            "trip_id": "MTA:" + feed + ":20261030:" + line + ":" + raw + ":10%3A00%3A00",
            "from_stop_id": "719S" if line == "7" else "F09S",
            "to_stop_id": "725S" if line == "7" else "A27S" if line == "E" else "D16S",
            "departure_at": departure, "arrival_at": arrival,
            "platform_ready_at": cutoff + 120,
        }],
    }


def pair():
    before = {"cutoff": BASE, "routes": [
        route(IDS[0], "7", "numbered", BASE + 1080, BASE + 600, BASE),
        route(IDS[1], "E", "ace", BASE + 1480, BASE + 400, BASE),
        route(IDS[2], "F", "bdfm", BASE + 1680, BASE + 300, BASE),
    ]}
    after = {"cutoff": BASE + 600, "routes": [
        route(IDS[0], "7", "numbered", BASE + 1380, BASE + 900, BASE + 600),
        route(IDS[1], "E", "ace", BASE + 1180, BASE + 780, BASE + 600),
        route(IDS[2], "F", "bdfm", BASE + 1480, BASE + 820, BASE + 600),
    ]}
    return before, after


class PhysicalServiceIdentityTests(unittest.TestCase):
    def test_normalized_start_time_alias_does_not_change_physical_train(self):
        before, after = pair()
        after["routes"][0]["selected_legs"][0]["trip_id"] += "-start-time-revision"
        self.assertEqual(physical_sequence(before["routes"][0]), physical_sequence(after["routes"][0]))
        selected, reason = choose_pair(before, after)
        self.assertIsNone(reason)
        revision = selected["leg_forecast_revisions"][0]
        self.assertNotEqual(revision["baseline_normalized_trip_id"], revision["current_normalized_trip_id"])

    def test_changed_train_service_route_feed_or_endpoint_cannot_count_as_same_train_delay(self):
        replacements = {
            "raw_trip_id": "060100_7..S", "service_date": "20261031",
            "route_id": "7X", "feed_id": "other-feed",
            "from_stop_id": "720S", "to_stop_id": "726S",
        }
        for key, value in replacements.items():
            before, after = pair()
            after["routes"][0]["selected_legs"][0][key] = value
            with self.subTest(key=key):
                self.assertEqual(choose_pair(before, after)[1], "STAY_SELECTED_PHYSICAL_TRAIN_CHANGED")

    def test_train_sequence_order_is_preserved(self):
        before, after = pair()
        two_legs = deepcopy(before["routes"][0])
        two_legs["selected_legs"].append(deepcopy(before["routes"][1]["selected_legs"][0]))
        reversed_legs = deepcopy(two_legs)
        reversed_legs["selected_legs"].reverse()
        self.assertNotEqual(physical_sequence(two_legs), physical_sequence(reversed_legs))

    def test_unresolved_original_identity_is_not_matched_by_a_shared_display_id(self):
        before, after = pair()
        for prediction in (before, after):
            prediction["routes"][0]["selected_legs"][0]["raw_trip_id"] = "unresolved"
        self.assertEqual(choose_pair(before, after)[1], "UNRESOLVED_PHYSICAL_IDENTITY")


class ForecastRevisionSelectionTests(unittest.TestCase):
    def test_absolute_arrival_revision_qualifies_even_when_remaining_duration_falls(self):
        before, after = pair()
        selected, reason = choose_pair(before, after)
        self.assertIsNone(reason)
        self.assertEqual(selected["absolute_arrival_revision_seconds"], 300)
        self.assertEqual(selected["duration_deterioration_seconds"], -300)
        self.assertEqual(selected["reference_route_id"], IDS[0])
        self.assertEqual(selected["planning_interval_seconds"], 600)
        self.assertEqual(selected["leg_forecast_revisions"][0]["departure_shift_seconds"], 300)

    def test_unmoved_arrival_forecast_is_not_delay_merely_because_the_clock_advanced(self):
        before, after = pair()
        after["routes"][0]["selected_legs"][0]["arrival_at"] = BASE + 1080
        # Even an inconsistent downstream ETA must not override the train's endpoint timestamp.
        after["routes"][0]["eta"] = before["routes"][0]["eta"] + 900
        selected, reason = choose_pair(before, after)
        self.assertIsNone(selected)
        self.assertEqual(reason, "ABSOLUTE_ARRIVAL_REVISION_BELOW_FIVE_MINUTES")

    def test_five_minute_revision_threshold_is_inclusive(self):
        before, after = pair()
        self.assertIsNotNone(choose_pair(before, after)[0])
        after["routes"][0]["selected_legs"][0]["arrival_at"] -= 1
        self.assertEqual(choose_pair(before, after)[1], "ABSOLUTE_ARRIVAL_REVISION_BELOW_FIVE_MINUTES")

    def test_only_predeclared_reassessment_lags_are_allowed(self):
        for lag in (0, -300, 299, 601, 1200, 1801):
            before, after = pair()
            after["cutoff"] = BASE + lag
            with self.subTest(lag=lag):
                self.assertEqual(choose_pair(before, after)[1], "OUTSIDE_FIXED_LAGS")

    def test_original_fastest_route_remains_stay_after_another_route_becomes_faster(self):
        before, after = pair()
        selected, _ = choose_pair(before, after)
        self.assertEqual(selected["reference_route_id"], IDS[0])
        self.assertEqual(min(after["routes"], key=lambda r: r["total_duration_seconds"])["id"], IDS[1])
        self.assertEqual(selected["anchor"]["winner_lead_seconds"], 400)

    def test_baseline_requires_all_candidates_and_verified_timing(self):
        for defect in ("missing", "timing_eligible", "comparison_eligible"):
            before, after = pair()
            if defect == "missing":
                before["routes"].pop()
            else:
                before["routes"][-1][defect] = False
            with self.subTest(defect=defect):
                self.assertIsNone(choose_pair(before, after)[0])

    def test_baseline_fastest_must_be_fresh_normal(self):
        for state, freshness in (("DISRUPTION", "FRESH"), ("UNKNOWN", "FRESH"),
                                 ("NORMAL", "LAST_OBSERVED")):
            before, after = pair()
            before["routes"][0]["context"].update(state=state, evidence_status=freshness)
            with self.subTest(state=state, freshness=freshness):
                self.assertEqual(choose_pair(before, after)[1], "BASELINE_WINNER_NOT_FRESH_NORMAL")

    def test_same_train_must_remain_catchable_at_reassessment(self):
        before, after = pair()
        leg = after["routes"][0]["selected_legs"][0]
        leg["departure_at"] = leg["platform_ready_at"] - 1
        self.assertEqual(choose_pair(before, after)[1], "SAME_TRAIN_NOT_CATCHABLE_AT_T1")
        leg["departure_at"] = leg["platform_ready_at"]
        self.assertIsNotNone(choose_pair(before, after)[0])

    def test_route_with_unavailable_timing_is_not_resurrected_by_matching_identity(self):
        before, after = pair()
        after["routes"][0]["timing_eligible"] = False
        self.assertEqual(choose_pair(before, after)[1], "STAY_NO_COMPLETE_CATCHABLE_TIMING_AT_T1")

    def test_no_official_notice_or_successful_switch_is_required_to_select_revision(self):
        before, after = pair()
        for candidate in after["routes"][1:]:
            candidate["total_duration_seconds"] = 2000
        selected, reason = choose_pair(before, after)
        self.assertIsNone(reason)
        self.assertEqual(selected["incident_ids"], [])
        self.assertFalse(selected["selection_uses_outcomes"])

    def test_outcomes_and_prior_recommendations_do_not_affect_pair_selection(self):
        before, after = pair()
        original, original_reason = choose_pair(before, after)
        for prediction in (before, after):
            prediction["outcomes"] = {IDS[0]: {"status": "UNAVAILABLE"}}
            prediction["strict_decision"] = {"action": "STAY", "reason": "future outcome"}
            prediction["scores"] = {"classification": "MEANINGFUL_LOSS"}
        changed, changed_reason = choose_pair(before, after)
        self.assertEqual(original_reason, changed_reason)
        for field in ("id", "physical_sequence_key", "physical_sequence", "reference_route_id",
                      "absolute_arrival_revision_seconds", "duration_deterioration_seconds"):
            self.assertEqual(original[field], changed[field])


class PhysicalTrainDeduplicationTests(unittest.TestCase):
    def test_earliest_reassessment_then_earliest_anchor_is_selected_per_train(self):
        original, _ = choose_pair(*pair())
        later_decision = deepcopy(original)
        later_decision.update(id="later-decision", decision_at=original["decision_at"] + 300,
                              outcomes={"known_winner": True})
        later_anchor = deepcopy(original)
        later_anchor["id"] = "later-anchor"
        later_anchor["anchor"]["decision_at"] += 300
        for candidates in ((later_decision, later_anchor, original),
                           (original, later_anchor, later_decision)):
            selected = representatives(candidates)
            self.assertEqual([row["id"] for row in selected], [original["id"]])

    def test_different_endpoint_pairs_do_not_collapse_into_one_sample(self):
        original, _ = choose_pair(*pair())
        before, after = pair()
        for prediction in (before, after):
            prediction["routes"][0]["selected_legs"][0]["to_stop_id"] = "726S"
        another_endpoint, _ = choose_pair(before, after)
        self.assertNotEqual(original["physical_sequence_key"], another_endpoint["physical_sequence_key"])
        self.assertEqual(len(representatives([original, another_endpoint])), 2)


if __name__ == "__main__":
    unittest.main()
