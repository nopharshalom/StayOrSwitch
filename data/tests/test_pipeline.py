"""Final artifact counts must reflect label checks applied after extraction."""

import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("history_pipeline_cli", ROOT / "data/scripts/build_history.py")
PIPELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PIPELINE)


class NoAlerts:
    def features_for(self, row):
        return {"service_alerts_available": False, "service_alert_count": None}


class ExcludeMissingReceipt:
    def apply(self, row):
        row["eligible_for_training"] = False
        row["label"]["quality_flags"].append("NO_RAW_LABEL_RECEIPT_CONFIRMATION")


class PipelineTests(unittest.TestCase):
    def test_post_join_counts_match_final_ineligible_artifact(self):
        row = {"trip_identity": "trip", "stop_id": "G22S", "eligible_for_training": True,
               "features": {"route_id": "G", "day_type": "WEEKDAY", "decision_local_date": "2026-11-02"},
               "label": {"quality_flags": []}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as output:
                output.write(json.dumps(row) + "\n")
            report = PIPELINE.attach_alerts(path, NoAlerts(), ExcludeMissingReceipt())
            with gzip.open(path, "rt", encoding="utf-8") as source:
                final = json.loads(source.readline())
        self.assertFalse(final["eligible_for_training"])
        self.assertEqual(1, report["counts"]["ineligible_proxy_rows"])
        self.assertEqual(0, report["counts"].get("eligible_proxy_rows", 0))
        self.assertEqual(0, report["unique_eligible_events"])
        self.assertEqual(1, report["label_quality_flags"]["NO_RAW_LABEL_RECEIPT_CONFIRMATION"])

    def test_dates_require_ordered_explicit_window(self):
        self.assertEqual(["2026-11-02", "2026-11-03"], list(PIPELINE.dates_between("2026-11-02", "2026-11-03")))
        with self.assertRaises(ValueError):
            list(PIPELINE.dates_between("2026-11-03", "2026-11-02"))
