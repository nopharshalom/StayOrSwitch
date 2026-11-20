import unittest

from stayorswitch.commuter_advice import commuter_advice


def forecast(values, mode="incident_profile"):
    return {
        "cutoff": 100,
        "mode": mode,
        "routes": [
            {
                "id": name,
                "total_duration_seconds": duration,
                "timing_eligible": duration is not None,
                "comparison_eligible": verified,
            }
            for name, duration, verified in values
        ],
    }


def choose(model_values, raw_values=None):
    return commuter_advice(
        forecast(model_values), forecast(raw_values or model_values, "mta"), "stay"
    )


class CommuterAdviceTest(unittest.TestCase):
    def test_unassessed_route_does_not_veto_available_comparison(self):
        result = choose(
            [("stay", 1000, True), ("similar", 920, True), ("blocked", None, False)]
        )
        self.assertEqual(
            ("STAY", "COMPARED_AVAILABLE", 1),
            (result["action"], result["basis"], result["timed_alternatives"]),
        )

    def test_switch_at_ten_percent_with_unverified_alert_scope(self):
        result = choose([("stay", 1000, False), ("faster", 900, False)])
        self.assertEqual(
            ("SWITCH", "faster", "MODEL_AND_RAW_TIMING"),
            (result["action"], result["route_id"], result["basis"]),
        )

    def test_switch_requires_second_forecast_for_same_route(self):
        model = [("stay", 1000, False), ("first", 800, False), ("second", 950, False)]
        raw = [("stay", 1000, False), ("first", 950, False), ("second", 800, False)]
        self.assertEqual("SWITCH_NOT_CORROBORATED", choose(model, raw)["basis"])

    def test_one_timed_route_is_not_a_comparison(self):
        d = choose([("stay", 1000, True), ("blocked", None, False)])
        self.assertEqual(("MONITOR", "ONLY_STAY_TIMED"), (d["action"], d["basis"]))

    def test_missing_reference_is_explicit(self):
        self.assertEqual(
            "UNDETERMINED",
            choose([("stay", None, False), ("alt", 900, True)])["action"],
        )

    def test_raw_reference_fallback_is_labeled(self):
        model = [("stay", None, False), ("alt", 950, False)]
        raw = [("stay", 1000, False), ("alt", 950, False)]
        result = choose(model, raw)
        self.assertEqual(("STAY", "raw"), (result["action"], result["forecast_source"]))

    def test_preserves_original_supported_decision(self):
        model = [("stay", 1000, True), ("alt", 850, True)]
        raw = [("stay", 1000, True), ("alt", 1050, True)]
        result = choose(model, raw)
        self.assertEqual(("SWITCH", "STRICT"), (result["action"], result["basis"]))

    def test_cannot_compare_different_cutoffs(self):
        data = [("stay", 1000, True)]
        raw = forecast(data, "mta")
        raw["cutoff"] += 1
        with self.assertRaises(ValueError):
            commuter_advice(forecast(data), raw, "stay")
