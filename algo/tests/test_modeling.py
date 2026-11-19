"""Regression checks for chronological model fitting and component inference."""

import gzip
import json
from pathlib import Path
import tempfile
import unittest

from data.modeling.features import FEATURE_VERSION, build_features, support_key, support_keys
from stayorswitch.model_training.artifacts import (load_rows, seal, sha256, verify_frozen,
                                                  write_json)
from stayorswitch.model_training.models import (ComponentPredictor, feature_names, fit_historical,
                                               fit_support, historical_residual, supported)
from stayorswitch.model_training.pipeline import promotion


def example(target="arrival", split="train"):
    date = {"train": "2026-11-02", "validation": "2026-11-09", "test": "2026-11-12"}[split]
    source = {"route_id": "G", "feed_id": "g", "day_type": "WEEKDAY", "stop_id": "G22S",
              "from_stop_id": "G22S", "to_stop_id": "G23S", "seconds_since_local_midnight": 30000,
              "feed_age_seconds": 30, "trip_update_age_seconds": 20, "is_assigned": True,
              "prediction_horizon_seconds": 300, "departure_horizon_seconds": 300,
              "arrival_horizon_seconds": 420, "predicted_duration_seconds": 120,
              "remaining_stop_pattern": ["G21S", "G22S", "G23S"],
              "segment_stop_pattern": ["G22S", "G23S"]}
    features = build_features(target, source)
    baseline = 120 if target == "segment" else 300
    return {"schema_version": "model-example-v1", "feature_version": FEATURE_VERSION,
            "target": target, "split": split, "example_id": "example", "event_id": "event",
            "trip_identity": "trip", "decision_date": date, "service_date": date,
            "day_type": "WEEKDAY", "route_id": "G", "horizon_bucket": "05_15_MIN",
            "disruption_group": "UNKNOWN_ALERT_STATE", "features": features,
            "baseline_seconds": baseline, "label_seconds": baseline + 20,
            "target_residual_seconds": 20, "weight": 1.0, "eligible": True,
            "support_key": support_key(target, features, source),
            "support_keys": support_keys(target, features, source), "support_source": source,
            "origin_prediction_basis": "DEPARTURE_PREDICTION"}


class ModelArtifactTests(unittest.TestCase):
    def test_test_view_requires_explicit_gate(self):
        with self.assertRaisesRegex(ValueError, "Final-test"):
            load_rows({}, "arrival", "test")

    def _load(self, row, mutation=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "view.jsonl.gz"
            with gzip.open(path, "wt") as handle:
                handle.write(json.dumps(row) + "\n")
            manifest = {"outputs": [{"target": row["target"], "split": row["split"],
                                     "path": "view.jsonl.gz", "sha256": sha256(path), "rows": 1}]}
            if mutation:
                mutation(path)
            return load_rows(manifest, row["target"], row["split"], root=root)

    def test_valid_view_has_explicit_component_target(self):
        self.assertEqual(self._load(example("segment"))[0]["target_residual_seconds"], 20)

    def test_view_rejects_label_leakage_feature(self):
        row = example()
        row["features"]["actual_arrival"] = 999
        with self.assertRaisesRegex(ValueError, "allowlist"):
            self._load(row)

    def test_view_rejects_ineligible_and_wrong_split_rows(self):
        for mutation in (lambda row: row.update(eligible=False),
                         lambda row: row.update(service_date="2026-11-12"),
                         lambda row: row.update(decision_date="2026-11-12"),
                         lambda row: row.update(target_residual_seconds=300)):
            row = example()
            mutation(row)
            with self.assertRaises(ValueError):
                self._load(row)

    def test_view_checksum_is_enforced(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            self._load(example(), lambda path: path.write_bytes(b"changed"))

    def test_frozen_source_hashes_are_enforced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code = root / "source.py"
            code.write_text("old")
            path = root / "frozen.json"
            write_json(path, seal({"test_labels_opened": False, "hashes": {"source.py": sha256(code)}}))
            verify_frozen(path, root=root)
            code.write_text("changed")
            with self.assertRaisesRegex(ValueError, "dependency changed"):
                verify_frozen(path, root=root)

    def test_frozen_payload_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = seal({"test_labels_opened": False, "hashes": {}})
            value["payload"]["test_labels_opened"] = True
            path = root / "frozen.json"
            write_json(path, value)
            with self.assertRaisesRegex(ValueError, "seal"):
                verify_frozen(path, root=root)


class HistoricalBaselineTests(unittest.TestCase):
    def test_historical_mean_uses_event_weights(self):
        first, second, third = example(), example(), example()
        first.update(weight=0.5, target_residual_seconds=100)
        second.update(weight=0.5, target_residual_seconds=100)
        third.update(event_id="another", target_residual_seconds=0)
        model = fit_historical([first, second, third], 2)
        self.assertEqual(historical_residual(model, first), 50)

    def test_validation_labels_never_fit_history_or_support(self):
        for function in (fit_historical, fit_support):
            with self.assertRaisesRegex(ValueError, "training"):
                function([example(split="validation")], 1)

    def test_history_backoff_is_train_only_global_mean(self):
        row = example()
        model = fit_historical([row], 20)
        unknown = example()
        unknown.update(route_id="UNSEEN", support_key="unseen", horizon_bucket="00_05_MIN")
        self.assertEqual(historical_residual(model, unknown), 20)

    def test_support_counts_events_once_and_allows_observed_progress(self):
        row = example()
        support = fit_support([row, row], 1)
        self.assertTrue(all(count == 1 for count in support["event_counts"].values()))
        progress = dict(row, support_key=row["support_keys"][-1])
        self.assertTrue(supported(support, progress))
        self.assertFalse(supported(support, dict(row, support_key="unseen-detour")))

    def test_stale_or_invalid_source_cannot_receive_model_correction(self):
        row = example()
        support = fit_support([row], 1)
        for age in (181, -1, True, float("nan")):
            changed = dict(row, features=dict(row["features"], feed_age_seconds=age))
            self.assertFalse(supported(support, changed))

    def test_ablation_has_fixed_explicit_feature_set(self):
        names = feature_names("arrival", "without_clock")
        self.assertNotIn("time_sin", names)
        self.assertNotIn("time_cos", names)
        self.assertIn("day_type", names)


class ComponentPredictorTests(unittest.TestCase):
    def predictor(self, row):
        class ConstantModel:
            def predict(self, values):
                return [10.0] * len(values)
        model = ComponentPredictor.__new__(ComponentPredictor)
        model.target = row["target"]
        model.required_features = list(row["features"])
        model.names = feature_names(row["target"], "core")
        model.support = fit_support([row], 1)
        model.model = ConstantModel()
        model.config = {"max_horizon_seconds": 1800, "prediction_floor_seconds": 0}
        model.frozen = {"experiment_version": "test"}
        return model

    def test_component_prediction_has_no_label_dependency(self):
        row = example()
        model = self.predictor(row)
        for key in ("label_seconds", "target_residual_seconds", "weight", "eligible"):
            del row[key]
        result = model.predict_case(row)
        self.assertEqual(result["seconds"], 310)
        self.assertFalse(result["live_enabled"])

    def test_inconsistent_component_units_are_rejected(self):
        for target in ("arrival", "departure", "segment"):
            row = example(target)
            model = self.predictor(row)
            row["baseline_seconds"] += 1
            with self.assertRaisesRegex(ValueError, "disagree"):
                model.predict_case(row)

    def test_arrival_proxy_cannot_predict_actual_departure(self):
        row = example("departure")
        model = self.predictor(row)
        row["origin_prediction_basis"] = "ARRIVAL_AS_DEPARTURE_PROXY"
        result = model.predict_case(row)
        self.assertEqual(result["method"], "MTA_FALLBACK")
        self.assertEqual(result["seconds"], 300)

    def test_missing_pattern_cannot_claim_operating_support(self):
        row = example()
        model = self.predictor(row)
        del row["support_source"]
        with self.assertRaisesRegex(ValueError, "support key"):
            model.predict_case(row)

    def test_segment_duration_must_match_its_endpoints(self):
        row = example("segment")
        model = self.predictor(row)
        row["features"]["arrival_horizon_seconds"] += 10
        with self.assertRaisesRegex(ValueError, "endpoint horizons"):
            model.predict_case(row)

    def test_supported_but_stale_case_falls_back(self):
        row = example()
        model = self.predictor(row)
        row["features"]["feed_age_seconds"] = 181
        self.assertEqual(model.predict_case(row)["method"], "MTA_FALLBACK")


class PromotionTests(unittest.TestCase):
    def test_improvement_requires_both_references_and_key_groups(self):
        methods = {name: {"rmse_seconds": value} for name, value in (("mta", 10), ("history", 9), ("model", 8))}
        metrics = {"overall": {"methods": methods}, "by_day_type": {
            "WEEKDAY": {"event_count": 100, "methods": methods}}}
        config = {"promotion": {"required_overall_rmse_improvement_seconds": 0,
                  "key_group_axes": ["by_day_type"], "key_group_min_events": 50,
                  "allowed_key_group_rmse_increase_seconds": 0}}
        self.assertEqual(promotion(metrics, config)["status"], "PROVISIONAL_COMPONENT_IMPROVEMENT")
        metrics["by_day_type"]["SATURDAY"] = {"event_count": 100, "methods": {
            "mta": {"rmse_seconds": 3}, "history": {"rmse_seconds": 4}, "model": {"rmse_seconds": 5}}}
        self.assertEqual(promotion(metrics, config)["status"], "RETAIN_BASELINE")


if __name__ == "__main__":
    unittest.main()
