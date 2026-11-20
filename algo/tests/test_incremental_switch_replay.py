"""Meaningful safeguards for the separate dense-checkpoint policy comparison."""

import copy
import unittest

from stayorswitch.incremental_switch_replay import approved_scopes, classify, dense_plans, policy_comparison, qualify, scope_signature


def exposure():
    return [{"leg_index": 0, "route_id": "5", "from_stop_id": "631S", "to_stop_id": "423S",
             "platform_direction": "S", "segment_stop_ids": ["631S", "640S", "423S"],
             "exposure_source": "ASOF_SELECTED_TRAIN_SEGMENT", "notices": [{"version_id": "v1"}]}]


def mode(action, chosen, outcomes):
    return {"strict_decision": {"action": action, "recommended_itinerary_id": chosen}, "outcomes": outcomes}


class ScopeTests(unittest.TestCase):
    def test_review_does_not_authorize_new_segment_direction_or_version(self):
        original = exposure()
        expected = scope_signature("c", ["i"], original)
        for field, value in [("route_id", "4"), ("platform_direction", "N"),
                             ("segment_stop_ids", ["631S", "635S", "423S"]),
                             ("exposure_source", "FIXED_GOOGLE_PATH_ENDPOINTS_ONLY")]:
            changed = copy.deepcopy(original)
            changed[0][field] = value
            self.assertNotEqual(expected, scope_signature("c", ["i"], changed))
        original[0]["notices"][0]["version_id"] = "future-v2"
        self.assertNotEqual(expected, scope_signature("c", ["i"], original))

    def test_age_and_model_context_do_not_change_manual_scope(self):
        original = exposure()
        changed = copy.deepcopy(original)
        changed[0]["notices"][0]["captured_at"] = 123
        changed[0]["applicable"] = False
        self.assertEqual(scope_signature("c", ["i"], original), scope_signature("c", ["i"], changed))

    def test_only_confirmed_prior_scope_can_be_reused(self):
        group = {"status": "CONFIRMED", "corridor_ids": ["c"], "incident_ids": ["i"],
                 "confirmed_impact": "DISRUPTION", "exposure": exposure(), "case_ids": ["old"]}
        case = {"corridor_id": "c", "incident_ids": ["i"], "exposure": exposure()}
        self.assertIsNotNone(qualify(case, approved_scopes({"groups": [group]})))
        group["status"] = "UNRESOLVED"
        self.assertIsNone(qualify(case, approved_scopes({"groups": [group]})))

    def test_grid_retains_receipts_and_family_boundary(self):
        first = 1793044800.125
        base = {"c": [{"incident_id": "i", "first_problem_receipt": first,
                        "decision_times": [first, first + 72.5]},
                       {"incident_id": "unapproved", "first_problem_receipt": first, "decision_times": [first]}]}
        result = dense_plans(base, {("c", "i")})["c"]
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["decision_times"]), 26)
        self.assertIn(first + 72.5, result[0]["decision_times"])
        self.assertEqual(result[0]["decision_times"][-1], first + 7200)


class PolicyComparisonTests(unittest.TestCase):
    def test_uses_raw_strict_stay_not_raw_fastest_or_model_stay(self):
        case = {"modes": {"mta": mode("STAY", "stay", {
            "stay": {"status": "INFERRED", "total_duration_seconds": 1800},
            "other": {"status": "INFERRED", "total_duration_seconds": 900}}),
            "incident_profile": mode("SWITCH", "other", {
                "stay": {"status": "INFERRED", "total_duration_seconds": 3000},
                "other": {"status": "INFERRED", "total_duration_seconds": 1200}})}}
        actual = policy_comparison(case)
        self.assertEqual(actual["gain_seconds"], 600)
        self.assertTrue(actual["mta_stay_model_switch"])

    def test_missed_train_remains_unknown(self):
        case = {"modes": {"mta": mode("STAY", "stay", {"stay": {"status": "INFERRED", "total_duration_seconds": 1800}}),
            "incident_profile": mode("SWITCH", "other", {"other": {"status": "MISSED_SELECTED_TRAIN"}})}}
        result = policy_comparison(case)
        self.assertIsNone(result["gain_seconds"])
        self.assertEqual(result["classification"], "UNKNOWN")

    def test_undetermined_is_not_an_observed_strategy(self):
        case = {"modes": {"mta": mode("UNDETERMINED", None, {}),
            "incident_profile": mode("SWITCH", "other", {"other": {"status": "INFERRED", "total_duration_seconds": 1000}})}}
        self.assertFalse(policy_comparison(case)["eligible_actions"])

    def test_tie_boundaries(self):
        self.assertEqual(classify(180), "PRACTICAL_TIE")
        self.assertEqual(classify(-180), "PRACTICAL_TIE")
        self.assertEqual(classify(181), "MEANINGFUL_GAIN")
        self.assertEqual(classify(-181), "MEANINGFUL_LOSS")


if __name__ == "__main__":
    unittest.main()
