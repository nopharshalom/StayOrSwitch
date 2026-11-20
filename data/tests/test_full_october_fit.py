"""Full-month eligibility, independent-event weighting and immutable provenance."""

from collections import Counter
from copy import deepcopy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.delay_profiles.build import fit_database, profile_document
from data.delay_profiles.common import end_of_date, epoch, file_sha256, group_candidates, read_json, write_json
from data.delay_profiles.estimator import ProfileEstimator
from data.full_october_fit import (ROOT, ReusedObservationDatabase, input_inventory,
                                   remap_observation, validate_configuration)


ORIGINAL = read_json(ROOT / "data/config/october.json")
CONFIG = read_json(ROOT / "data/config/full-october-fit.json")


def row(identifier, day, residual=120, **overrides):
    cutoff = epoch(day + "T08:00:00-04:00")
    split = next(key for key, (first, last) in ORIGINAL["splits"].items() if first <= day <= last)
    result = {"id": identifier, "event_id": identifier, "trip_id": identifier,
              "canonical_event_trip_id": identifier, "route_id": "F", "target": "arrival",
              "from_stop_id": "F09S", "to_stop_id": "A41S", "decision_at": cutoff,
              "date": day, "split": split, "horizon_seconds": 1200, "residual_seconds": residual,
              "label_confirmed_at": cutoff + 1500, "outcome_at": cutoff + 1200 + residual,
              "usable": True, "quality_flags": [],
              "context": {"state": "UNKNOWN", "cause": "UNKNOWN", "incident_ids": [],
                          "severe_incident_ids": [], "evidence_status": "UNKNOWN"}}
    result.update(overrides)
    return result


class FullOctoberFitTests(unittest.TestCase):
    def test_configuration_preserves_scope_and_thresholds(self):
        validate_configuration(CONFIG, ORIGINAL)
        bad = deepcopy(CONFIG)
        bad["min_profile_events"] += 1
        with self.assertRaisesRegex(ValueError, "preserve"):
            validate_configuration(bad, ORIGINAL)
        bad = deepcopy(CONFIG)
        bad["full_month_fit"]["boundary_inputs_use_outcomes"] = True
        with self.assertRaisesRegex(ValueError, "outcomes"):
            validate_configuration(bad, ORIGINAL)

    def test_remap_keeps_all_old_forecasts_labels_and_quality(self):
        original = row("test", "2026-10-29")
        expected = deepcopy(original)
        actual = remap_observation(original, CONFIG, ORIGINAL)
        self.assertEqual(original, expected)
        self.assertEqual(actual, dict(expected, split="train"))

    def test_remap_rejects_invalid_dates_and_old_membership(self):
        original = row("test", "2026-10-29")
        for change in ({"date": "2026-11-01"}, {"date": "2026-10-28"}, {"split": "train"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                remap_observation(dict(original, **change), CONFIG, ORIGINAL)

    def test_new_training_cutoff_precedes_dst_fallback(self):
        cutoff = end_of_date("2026-10-31")
        self.assertEqual(cutoff, epoch("2026-11-01T04:00:00Z"))
        self.assertEqual(end_of_date("2026-11-01") - cutoff, 25 * 3600)

    def test_refit_admits_old_holdouts_reapplies_new_boundary_and_deduplicates(self):
        cutoff = end_of_date("2026-10-31")
        rows = [row("first", "2026-10-05", 60),
                row("second", "2026-10-20", 180),
                row("third", "2026-10-29", 360),
                row("third-later", "2026-10-29", 900, event_id="third", decision_at=epoch("2026-10-29T08:01:00-04:00")),
                row("late-label", "2026-10-31", 1000, label_confirmed_at=cutoff),
                row("cross-trip", "2026-10-31", 1000),
                row("cross-incident", "2026-10-31", 1000,
                    context={"state": "DISRUPTION", "incident_ids": ["recurring"], "cause": "SIGNAL", "evidence_status": "FRESH"})]
        rows.sort(key=lambda value: (value["decision_at"], value["id"]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            observations = path / "observations.jsonl.gz"
            with gzip.open(observations, "wt") as stream:
                for value in rows:
                    stream.write(json.dumps(value) + "\n")
            database = ReusedObservationDatabase(path / "fit.sqlite", observations, CONFIG, ORIGINAL)
            groups, quality = fit_database(database, CONFIG, "train",
                                           {"cross-trip": (cutoff - 86400, cutoff + 100)},
                                           {"recurring": (cutoff - 86400, cutoff + 19 * 86400)})
            database.close()
        counts = quality["counts"]
        self.assertEqual(counts["representative_observations"], 7)
        self.assertEqual(counts["eligible_observations"], 4)
        self.assertEqual(counts["OUTCOME_CONFIRMED_AFTER_DEVELOPMENT"], 1)
        self.assertEqual(counts["TRAIN_CROSSES_DEVELOPMENT_BOUNDARY"], 1)
        self.assertEqual(counts["INCIDENT_CROSSES_DEVELOPMENT_BOUNDARY"], 1)
        candidate = next(key for level, key, _ in group_candidates(
            "arrival", "F", "F09S", "A41S", rows[0]["decision_at"], 1200,
            {"state": "TIME_ONLY"}, CONFIG) if level == "TIME_SEGMENT")
        self.assertEqual(groups[candidate]["event_count"], 3)
        self.assertEqual(groups[candidate]["statistics"]["mean_signed_seconds"], 200)

    def test_input_inventory_never_requires_november_labels(self):
        config = deepcopy(CONFIG)
        config["start_date"] = config["end_date"] = "2026-10-31"
        config["full_month_fit"]["boundary_input_dates"] = ["2026-11-01", "2026-11-02"]
        with tempfile.TemporaryDirectory(dir=ROOT / "data/local") as temporary:
            directory = Path(temporary)
            for day in ("2026-10-31", "2026-11-01", "2026-11-02"):
                write_json(directory / (day + ".trips.json.gz"), {})
                with gzip.open(directory / (day + ".alerts.jsonl.gz"), "wt"):
                    pass
                outputs = {}
                for kind, suffix in (("trips", "trips.json.gz"), ("alerts", "alerts.jsonl.gz")):
                    path = directory / (day + "." + suffix)
                    outputs[kind] = {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path)}
                write_json(directory / (day + ".source.json"), {"date": day, "stage": "NORMALIZED", "outputs": outputs})
            _, spans, incidents, counts, sources = input_inventory(directory, directory, config)
        self.assertEqual(spans, {})
        self.assertEqual(incidents, {})
        self.assertEqual(len(sources), 9)
        self.assertTrue(all(name.endswith(("trips.json.gz", "alerts.jsonl.gz", "source.json")) for name in sources))

    def test_predictor_accepts_new_train_but_rejects_descriptive(self):
        train = profile_document(CONFIG, {}, "train", {}, {}, {})
        estimator = ProfileEstimator(train)
        self.assertEqual(estimator.config["splits"]["train"], ["2026-10-01", "2026-10-31"])
        with self.assertRaisesRegex(ValueError, "training profile"):
            ProfileEstimator(profile_document(CONFIG, {}, "month_descriptive", {}, {}, {}))

    def test_serialized_profile_seal_survives_separate_report_metadata(self):
        report = {"counts": {"eligible_observations": 1}}
        profile = profile_document(CONFIG, {}, "train", {}, {}, report)
        written_report = dict(report, elapsed_seconds=10)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.json.gz"
            write_json(path, profile)
            actual = ProfileEstimator(path)
        self.assertEqual(actual.seal, profile["seal"])
        self.assertNotIn("elapsed_seconds", profile["quality"])
        self.assertIn("elapsed_seconds", written_report)


if __name__ == "__main__":
    unittest.main()
