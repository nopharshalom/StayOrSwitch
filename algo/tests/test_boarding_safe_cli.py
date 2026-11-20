"""Exercise the handoff CLI with real temporary route/feed files."""

from contextlib import redirect_stderr, redirect_stdout
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from algo.scripts import run_boarding_safe as cli
from algo.tests.test_severe import NOW, route, snapshot, train


class BoardingSafeCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config_path = self.root / "routes.json"
        self.snapshot_path = self.root / "feeds.snapshots.jsonl.gz"
        self.config = {"routes": [route("stay"), route("alternative", "G")]}
        self.write_config()
        self.write_feeds()

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config))

    def write_feeds(self, departure=300, alternative_arrival=600, extra=()):
        rows = [snapshot([train("stay-train", departure=departure, arrival=1200)]),
                snapshot([train("alternative-train", "G", departure, alternative_arrival)], feed="g"),
                snapshot(feed="subway-alerts"), *extra]
        with gzip.open(self.snapshot_path, "wt") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def args(self, *extra):
        return ["--snapshots", str(self.snapshot_path), "--config", str(self.config_path),
                "--cutoff", str(NOW), "--current-route-id", "stay", "--mode", "mta",
                "--json", *extra]

    def run_cli(self, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = cli.main(self.args(*extra))
        return status, json.loads(stdout.getvalue() or stderr.getvalue())

    def test_script_runs_and_defaults_to_all_service_with_120_second_margin(self):
        output = self.root / "result.json"
        process = subprocess.run(
            [sys.executable, str(Path(cli.__file__).resolve()), *self.args("--output", str(output))],
            check=False, capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report, json.loads(output.read_text()))
        self.assertFalse(report["require_severe"])
        self.assertEqual(report["boarding_margin_seconds"], 120)
        self.assertFalse(report["prediction_uses_outcomes"])
        self.assertFalse(report["actual_travel_time_computed"])
        self.assertIsNone(report["profile"])
        self.assertEqual(report["modes"]["mta"]["strict_decision"]["action"], "SWITCH")

    def test_explicit_severe_only_flag_withholds_normal_service_switch(self):
        status, report = self.run_cli("--severe-only")
        self.assertEqual(status, 0)
        decision = report["modes"]["mta"]["strict_decision"]
        self.assertEqual(decision["action"], "STAY")
        self.assertEqual(decision["reason_codes"], ["NO_APPLICABLE_SEVERE_INCIDENT"])

    def test_margin_override_changes_eligibility_without_inventing_an_eta(self):
        self.write_feeds(departure=150)
        status, strict = self.run_cli()
        self.assertEqual(status, 0)
        self.assertEqual(strict["modes"]["mta"]["strict_decision"]["action"], "UNDETERMINED")
        status, relaxed = self.run_cli("--boarding-margin-seconds", "60")
        self.assertEqual(status, 0)
        self.assertEqual(relaxed["modes"]["mta"]["strict_decision"]["action"], "SWITCH")
        self.assertEqual(relaxed["modes"]["mta"]["routes"][1]["total_duration_seconds"], 660)

    def test_missing_stay_and_invalid_margin_are_explicit_input_errors(self):
        for args in (("--current-route-id", "missing"), ("--boarding-margin-seconds", "-1")):
            with self.subTest(args=args):
                status, error = self.run_cli(*args)
                self.assertEqual(status, 2)
                self.assertEqual(error["status"], "INPUT_ERROR")

    def test_unavailable_provider_candidate_blocks_false_complete_stay(self):
        self.write_feeds(alternative_arrival=1200)
        self.config["unavailable_candidates"] = [{"id": "unresolved", "reason_codes": ["MISSING_TRANSFER_WALK"]}]
        self.write_config()
        status, report = self.run_cli()
        self.assertEqual(status, 0)
        prediction = report["modes"]["mta"]
        self.assertEqual(prediction["strict_decision"]["action"], "UNDETERMINED")
        self.assertIn("UNASSESSED_ALTERNATIVES", prediction["strict_decision"]["reason_codes"])
        self.assertFalse(prediction["routes"][-1]["timing_eligible"])

    def test_future_archive_capture_does_not_change_selected_train(self):
        future = snapshot([train("future-shortcut", "G", 300, 400)], feed="g", fetched=1, source=0)
        self.write_feeds(extra=[future])
        status, report = self.run_cli()
        self.assertEqual(status, 0)
        alternative = report["modes"]["mta"]["routes"][1]
        self.assertTrue(alternative["selected_legs"][0]["trip_id"].endswith(":alternative-train"))
        self.assertEqual(alternative["total_duration_seconds"], 660)

    def test_full_october_profile_is_default_and_cannot_predict_before_its_boundary(self):
        status, error = self.run_cli("--mode", "all")
        self.assertEqual(status, 2)
        self.assertIn("training boundary", error["message"])
        # The fixture feeds are stale at this later date, so the valid result
        # abstains; this checks artifact loading without manufacturing live data.
        status, report = self.run_cli("--mode", "all", "--cutoff", "2026-11-20T12:00:00-05:00")
        self.assertEqual(status, 0)
        self.assertEqual(report["profile"]["path"], str(cli.DEFAULT_PROFILE.resolve()))
        self.assertEqual(set(report["modes"]), {"mta", "time_profile", "incident_profile"})
        self.assertTrue(all(value["strict_decision"]["action"] == "UNDETERMINED"
                            for value in report["modes"].values()))


if __name__ == "__main__":
    unittest.main()
