"""Guard the narrow label-only migration and outcome invariance."""

import copy
import unittest

from data.scripts.rebuild_october_labels import reviewed_code_delta, expected_label_digest, label_digest


class LabelRebuildTests(unittest.TestCase):
    def test_only_reviewed_existing_producer_can_change(self):
        old = {"data/october/labels.py": "old", "data/october/prepare.py": "same"}
        self.assertEqual(reviewed_code_delta(old, dict(old, **{"data/october/labels.py": "new"})),
                         ["data/october/labels.py"])
        for new in (old, dict(old, **{"data/october/prepare.py": "changed"}),
                    dict(old, **{"new.py": "added", "data/october/labels.py": "new"})):
            with self.assertRaises(ValueError):
                reviewed_code_delta(old, new)

    def test_expected_change_preserves_outcomes_and_other_exclusions(self):
        old = {"x": {"A": {"raw_trip_id": "001000_N..S", "route_id": "W", "arrival_at": 100,
            "departure_at": 110, "confirmed_at": 120, "quality_flags": ["RAW_TRIP_ROUTE_MISMATCH"],
            "arrival_quality_flags": ["RAW_TRIP_ROUTE_MISMATCH"],
            "departure_quality_flags": ["MISSING_CSV_DEPARTURE", "RAW_TRIP_ROUTE_MISMATCH"],
            "arrival_usable": False, "departure_usable": False}}}
        expected = copy.deepcopy(old)
        row = expected["x"]["A"]
        row.update(quality_flags=[], arrival_quality_flags=[], arrival_usable=True,
                   departure_quality_flags=["MISSING_CSV_DEPARTURE"])
        self.assertEqual(expected_label_digest(old), label_digest(expected))
        row["arrival_at"] = 101
        self.assertNotEqual(expected_label_digest(old), label_digest(expected))
        self.assertIn("RAW_TRIP_ROUTE_MISMATCH", old["x"]["A"]["quality_flags"])

    def test_reverse_alias_remains_excluded(self):
        row = {"raw_trip_id": "001000_W..S", "route_id": "N", "quality_flags": ["RAW_TRIP_ROUTE_MISMATCH"],
               "arrival_quality_flags": ["RAW_TRIP_ROUTE_MISMATCH"],
               "departure_quality_flags": ["RAW_TRIP_ROUTE_MISMATCH"],
               "arrival_usable": False, "departure_usable": False}
        labels = {"x": {"A": row}}
        self.assertEqual(expected_label_digest(labels), label_digest(labels))


if __name__ == "__main__":
    unittest.main()
