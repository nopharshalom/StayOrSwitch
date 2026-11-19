"""Independent arithmetic and coverage checks for proxy component metrics."""

from copy import deepcopy
import math
import unittest

from stayorswitch.model_training.metrics import evaluate_predictions, weighted_quantile


def examples():
    return [
        {"target": "arrival", "event_id": "one", "trip_identity": "trip-a", "weight": 0.5,
         "label_seconds": 100, "day_type": "WEEKDAY", "decision_date": "2026-11-12",
         "route_id": "F", "horizon_bucket": "0-5", "disruption_group": "KNOWN_DISRUPTION"},
        {"target": "arrival", "event_id": "one", "trip_identity": "trip-a", "weight": 0.5,
         "label_seconds": 200, "day_type": "WEEKDAY", "decision_date": "2026-11-12",
         "route_id": "F", "horizon_bucket": "5-15", "disruption_group": "KNOWN_DISRUPTION"},
        {"target": "arrival", "event_id": "two", "trip_identity": "trip-b", "weight": 1.0,
         "label_seconds": 300, "day_type": "SATURDAY", "decision_date": "2026-11-14",
         "route_id": "G", "horizon_bucket": "15-30", "disruption_group": "UNKNOWN_ALERT_STATE"},
    ]


class MetricsTests(unittest.TestCase):
    def test_event_balanced_arithmetic_and_sign(self):
        result = evaluate_predictions(examples(), {"mta": [80, 220, 200]})["overall"]
        metrics = result["methods"]["mta"]
        self.assertEqual(result["row_count"], 3)
        self.assertEqual(result["event_count"], 2)
        self.assertEqual(result["trip_count"], 2)
        self.assertEqual(result["date_count"], 2)
        self.assertEqual(result["event_weight_sum"], 2)
        self.assertEqual(metrics["mae_seconds"], 60)
        self.assertAlmostEqual(metrics["rmse_seconds"], math.sqrt(5200))
        self.assertEqual(metrics["bias_seconds"], 50)
        self.assertEqual(metrics["median_absolute_error_seconds"], 20)
        self.assertEqual(metrics["p90_absolute_error_seconds"], 100)

    def test_weighted_quantile_boundary_convention(self):
        self.assertEqual(weighted_quantile([100, 20, 20], [1, 0.5, 0.5], 0.5), 20)
        self.assertEqual(weighted_quantile([100, 20], [1, 1], 0), 20)
        self.assertEqual(weighted_quantile([100, 20], [1, 1], 1), 100)

    def test_decimal_weight_quantile_does_not_cross_exact_boundary(self):
        self.assertEqual(weighted_quantile(list(range(1, 11)), [0.1] * 10, 0.9), 9)
        self.assertEqual(weighted_quantile(list(range(1, 11)), [0.1] * 10, 0.3), 3)
        self.assertEqual(weighted_quantile(list(range(1, 11)), [0.1] * 10, 1), 10)

    def test_exact_zero_and_negative_bias(self):
        result = evaluate_predictions(examples(), {"exact": [100, 200, 300], "late": [200, 300, 400]})
        self.assertEqual(result["overall"]["methods"]["exact"]["rmse_seconds"], 0)
        self.assertEqual(result["overall"]["methods"]["late"]["bias_seconds"], -100)
        self.assertIsNone(result["overall"]["uncertainty"])
        self.assertFalse(result["physical_ground_truth"])

    def test_paired_same_cases_and_fallback_denominators(self):
        result = evaluate_predictions(examples(), {"mta": [80, 220, 200], "history": [90, 210, 250],
                                                  "model": [100, 200, 200]}, [True, True, False])
        overall = result["overall"]
        coverage = overall["model_coverage"]["model"]
        self.assertEqual(coverage["fallback_rows"], 1)
        self.assertEqual(coverage["applied_event_weight_fraction"], 0.5)
        self.assertEqual(overall["methods"]["model"]["mae_seconds"], 50)
        pair = overall["paired_improvements"]["mta"]["model"]
        self.assertEqual(pair["mae_reduction_seconds"], 10)
        self.assertEqual(pair["lower_absolute_error_weight_fraction"], 0.5)
        self.assertEqual(pair["equal_absolute_error_weight_fraction"], 0.5)

    def test_groups_preserve_cases_and_weight(self):
        result = evaluate_predictions(examples(), {"mta": [100, 200, 300]})
        for group_name in ("by_day_type", "by_date", "by_route", "by_horizon", "by_disruption", "by_revision"):
            self.assertEqual(sum(group["row_count"] for group in result[group_name].values()), 3)
            self.assertEqual(sum(group["event_weight_sum"] for group in result[group_name].values()), 2)
        self.assertEqual(result["by_day_type"]["SATURDAY"]["event_count"], 1)
        self.assertEqual(result["by_day_type"]["SATURDAY"]["date_count"], 1)
        self.assertEqual(result["by_day_type"]["WEEKDAY"]["date_count"], 1)
        self.assertEqual(result["by_disruption"]["UNKNOWN_ALERT_STATE"]["row_count"], 1)

    def test_revision_groups_keep_unavailable_history_explicit(self):
        rows = examples()
        rows[0]["revision_group"] = "REPEATED_REVISIONS"
        rows[1]["revision_group"] = "NO_RECENT_REVISIONS"
        result = evaluate_predictions(rows, {"mta": [100, 200, 300]})
        groups = result["by_revision"]
        self.assertEqual(set(groups), {"REPEATED_REVISIONS", "NO_RECENT_REVISIONS", "UNKNOWN"})
        self.assertEqual(groups["REPEATED_REVISIONS"]["row_count"], 1)
        self.assertEqual(groups["NO_RECENT_REVISIONS"]["event_weight_sum"], 0.5)
        self.assertEqual(groups["UNKNOWN"]["event_weight_sum"], 1.0)

    def test_missing_date_is_not_counted_as_an_independent_date(self):
        rows = examples()
        rows[2]["decision_date"] = None
        result = evaluate_predictions(rows, {"mta": [100, 200, 300]})
        self.assertEqual(result["overall"]["date_count"], 1)
        self.assertEqual(result["by_date"]["UNKNOWN"]["date_count"], 0)
        self.assertEqual(result["by_date"]["UNKNOWN"]["row_count"], 1)

    def test_unknown_group_and_named_masks(self):
        rows = examples()
        del rows[0]["day_type"]
        result = evaluate_predictions(rows, {"model": [100, 200, 300]}, {"model": [False, True, True]})
        self.assertEqual(result["by_day_type"]["UNKNOWN"]["row_count"], 1)
        self.assertEqual(result["by_day_type"]["UNKNOWN"]["model_coverage"]["model"]["applied_rows"], 0)

    def test_rejects_different_case_counts(self):
        with self.assertRaises(ValueError):
            evaluate_predictions(examples(), {"mta": [100, 200, 300], "model": [100]})

    def test_rejects_bad_labels_predictions_and_weights(self):
        for bad in (float("nan"), float("inf"), -1, True):
            rows = examples()
            rows[0]["label_seconds"] = bad
            with self.subTest(label=bad), self.assertRaises(ValueError):
                evaluate_predictions(rows, {"mta": [100, 200, 300]})
            with self.subTest(prediction=bad), self.assertRaises(ValueError):
                evaluate_predictions(examples(), {"mta": [bad, 200, 300]})
        for bad in (0, -1, float("nan"), float("inf"), True):
            rows = examples()
            rows[0]["weight"] = bad
            with self.subTest(weight=bad), self.assertRaises(ValueError):
                evaluate_predictions(rows, {"mta": [100, 200, 300]})

    def test_rejects_empty_inputs_and_mixed_targets(self):
        with self.assertRaises(ValueError):
            evaluate_predictions([], {"mta": []})
        with self.assertRaises(ValueError):
            evaluate_predictions(examples(), {})
        rows = examples()
        rows[0]["target"] = "segment"
        with self.assertRaises(ValueError):
            evaluate_predictions(rows, {"mta": [100, 200, 300]})

    def test_rejects_bad_coverage_masks_and_missing_identity(self):
        for mask in ([True], [True, "false", False], [1, True, False], [True, 0, False]):
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                evaluate_predictions(examples(), {"mta": [100, 200, 300]}, mask)
        rows = examples()
        rows[0]["event_id"] = None
        with self.assertRaises(ValueError):
            evaluate_predictions(rows, {"mta": [100, 200, 300]})

    def test_does_not_mutate_rows_or_predictions(self):
        rows = examples()
        expected = deepcopy(rows)
        predictions = {"mta": [100, 200, 300]}
        evaluate_predictions(rows, predictions)
        self.assertEqual(rows, expected)
        self.assertEqual(predictions, {"mta": [100, 200, 300]})

    def test_quantile_rejects_invalid_inputs(self):
        for values, weights, probability in (([], [], 0.5), ([1], [0], 0.5), ([1], [1, 1], 0.5),
                                               ([1], [1], -0.1), ([1], [1], 1.1)):
            with self.subTest(values=values, weights=weights, probability=probability), self.assertRaises(ValueError):
                weighted_quantile(values, weights, probability)


if __name__ == "__main__":
    unittest.main()
