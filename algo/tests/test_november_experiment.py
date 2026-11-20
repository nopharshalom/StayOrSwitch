"""Regression checks for scoring boundaries and the published two-corridor replay."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from algo.scripts import evaluate_all_forecast_boarding as experiment


class NovemberReplayTests(unittest.TestCase):
    def test_outcome_boundaries(self):
        examples = [
            ("SWITCH", [99, 99], "gain"),
            ("SWITCH", [100, 100], "tie"),
            ("SWITCH", [110, 110], "tie"),
            ("SWITCH", [111, 111], "loss"),
            ("STAY", [101, 101], "gain"),
            ("STAY", [90, 90], "tie"),
            ("STAY", [89, 89], "loss"),
            ("STAY", [99, 101], "ambiguous"),
            ("SWITCH", None, None),
        ]
        for action, alternative, expected in examples:
            with self.subTest(action=action, alternative=alternative):
                row = dict(action=action, bounds=[[100, 100], alternative])
                self.assertEqual(experiment.any_saving_category(row), expected)

    def test_frozen_evidence_reproduces_both_published_files(self):
        published = experiment.REPORT
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / published.name
            with patch.object(experiment, "REPORT", target):
                experiment.main()
            for path in (target, target.with_name("november-all-forecast-boarding-any-saving.md")):
                self.assertEqual(path.read_bytes(), published.with_name(path.name).read_bytes())
