"""Small synthetic native-library check of fitting, freezing, and test access."""

import gzip
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from data.modeling.features import CATEGORICAL_FEATURES, FEATURE_NAMES, FEATURE_VERSION
from stayorswitch.model_training.artifacts import ROOT, sha256, write_json
from stayorswitch.model_training.pipeline import _code_paths, evaluate, train
from test_modeling import example


class NativePipelineTests(unittest.TestCase):
    def test_three_targets_freeze_before_test_and_reuse_existing_report(self):
        with tempfile.TemporaryDirectory(prefix="stayorswitch-model-test-") as temporary:
            root = Path(temporary).resolve()
            for source in _code_paths(ROOT):
                path = root / source.relative_to(ROOT)
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, path)
            config = json.loads((ROOT / "algo/config/model-training.json").read_text())
            config.update(iterations=5, early_stopping_rounds=2,
                          min_support_events=1, min_historical_group_events=1)
            config["candidates"] = [{"name": "synthetic", "depth": 2, "feature_set": "core"}]
            config["rolling_research"]["depth"] = 2
            outputs = []
            for target in config["targets"]:
                for split in ("train", "validation", "test"):
                    path = root / ("data/processed/model-pilot/" + target + "/" + split + ".jsonl.gz")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with gzip.open(path, "wt") as stream:
                        for index in range(30):
                            row = example(target, split)
                            identifier = target + "-" + split + "-" + str(index)
                            row.update(example_id=identifier, event_id=identifier,
                                       trip_identity=split + "-" + str(index))
                            row["baseline_seconds"] += index
                            row["target_residual_seconds"] = 20 + index % 5
                            row["label_seconds"] = row["baseline_seconds"] + row["target_residual_seconds"]
                            if target == "segment":
                                row["features"]["predicted_duration_seconds"] += index
                                row["features"]["arrival_horizon_seconds"] += index
                            else:
                                row["features"]["horizon_seconds"] += index
                            row["rolling_features"] = {}
                            stream.write(json.dumps(row) + "\n")
                    outputs.append({"target": target, "split": split, "path": str(path.relative_to(root)),
                                    "sha256": sha256(path), "rows": 30})
            references = {}
            for key, name in (("config", "data/config/model-data.json"),
                              ("source_manifest", "data/manifests/history-pilot.json"),
                              ("report", "data/reports/model-data.json")):
                write_json(root / name, {"synthetic": True})
                references[key] = {"path": name, "sha256": sha256(root / name)}
            manifest = {"stage": "PREPARED", "feature_version": FEATURE_VERSION,
                        "feature_names": {key: list(value) for key, value in FEATURE_NAMES.items()},
                        "categorical_features": {key: list(value) for key, value in CATEGORICAL_FEATURES.items()},
                        "code_sha256": {"data/modeling/features.py": sha256(root / "data/modeling/features.py")},
                        "outputs": outputs, **references}
            write_json(root / config["data_manifest"], manifest)
            config_path = root / "algo/config/model-training.json"
            write_json(config_path, config)
            frozen = train(config_path, root=root)
            self.assertFalse((root / config["test_report"]).exists())
            report = evaluate(frozen, root=root)
            payload = json.loads(report.read_text())
            self.assertEqual(set(payload["targets"]), {"arrival", "departure", "segment"})
            self.assertTrue(payload["test_access_after_freeze"])
            original = report.read_bytes()
            self.assertEqual(evaluate(frozen, root=root), report)
            self.assertEqual(report.read_bytes(), original)
            with self.assertRaisesRegex(ValueError, "already frozen"):
                train(config_path, root=root)


if __name__ == "__main__":
    unittest.main()
