"""Global split, event-count, and physical-continuity ambiguity tests."""

from copy import deepcopy
from datetime import datetime
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from history.integrity import AMBIGUITY_FLAG, audit_dataset, purge_ambiguous
from history.features import split_for_date


def example(identifier, date, clock="12:00:00", *, identity=None, raw="030000_G..S",
            train=None, eligible=True, segment=False):
    at = datetime.fromisoformat(date + "T" + clock).replace(tzinfo=ZoneInfo("America/New_York")).timestamp()
    result = {
        "example_id": identifier,
        "trip_identity": identity or "MTA:g:" + date.replace("-", "") + ":G:" + raw + ":",
        "stop_id": "G21S", "decision_at": at, "source_updated_at": at - 5,
        "split": split_for_date(date), "eligible_for_training": eligible,
        "features": {"feed_id": "g", "route_id": "G", "day_type": "WEEKDAY",
                     "service_date": date, "decision_local_date": date, "is_assigned": train is not None},
        "label": {"arrival_at": at + 60, "available_at": at + 90, "receipt_confirmed_at": at + 120,
                  "usable_proxy": eligible, "quality_flags": []},
        "provenance": {"raw_trip_id": raw, "nyct_train_id": train},
    }
    if segment:
        result.pop("stop_id")
        result.update(from_stop_id="G21S", to_stop_id="G22S")
        result["label"]["departure_at"] = at + 30
    return result


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, rows):
        path = self.directory / (name + ".jsonl.gz")
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row) + "\n")
        return path

    def test_global_counts_do_not_sum_daily_unique_counts(self):
        first = example("one", "2026-11-02")
        second = example("two", "2026-11-03", identity=first["trip_identity"], eligible=False)
        second["features"]["service_date"] = "2026-11-02"
        segment = example("three", "2026-11-03", identity=first["trip_identity"], segment=True)
        segment["features"]["service_date"] = "2026-11-02"
        paths = [self.write("day1", [first]), self.write("day2", [second, segment])]
        result = audit_dataset(paths)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["counts"], {"rows": 3, "eligible_proxy_rows": 2,
                         "unique_trips": 1, "unique_events": 2, "unique_eligible_events": 2})
        self.assertEqual(result["by_kind"]["arrival"]["rows"], 2)
        self.assertEqual(result["by_kind"]["arrival"]["unique_events"], 1)
        self.assertEqual(result["by_kind"]["segment"]["rows"], 1)

    def test_one_qualified_identity_cannot_appear_in_two_splits(self):
        first = example("one", "2026-11-08")
        second = example("two", "2026-11-09", identity=first["trip_identity"])
        paths = [self.write("both", [first, second])]
        result = audit_dataset(paths)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["qualified_trip_split_conflicts"][first["trip_identity"]], ["train", "validation"])

    def test_near_boundary_raw_id_aliases_are_marked_then_excluded(self):
        first = example("one", "2026-11-08", "23:59:00")
        second = example("two", "2026-11-09", "00:01:00")
        paths = [self.write("first", [first]), self.write("second", [second])]
        before = audit_dataset(paths)
        self.assertEqual(before["status"], "FAIL")
        self.assertEqual(before["ambiguous_eligible_rows"], 2)
        result = purge_ambiguous(paths, before["ambiguous_trip_identities"])
        self.assertEqual(result["rows_eligibility_removed"], 2)
        after = audit_dataset(paths)
        self.assertEqual(after["status"], "PASS")
        self.assertEqual(after["counts"]["rows"], 2)
        self.assertEqual(after["counts"]["eligible_proxy_rows"], 0)
        with gzip.open(paths[0], "rt") as stream:
            self.assertIn(AMBIGUITY_FLAG, json.loads(next(stream))["label"]["quality_flags"])
        bytes_before = [path.read_bytes() for path in paths]
        purge_ambiguous(paths, before["ambiguous_trip_identities"])
        self.assertEqual(bytes_before, [path.read_bytes() for path in paths])

    def test_assigned_vehicle_and_path_detect_changed_trip_time(self):
        first = example("one", "2026-11-08", "23:59:00", raw="144000_G..S", train="TRAIN-A")
        second = example("two", "2026-11-09", "00:01:00", raw="000000_G..S", train="TRAIN-A")
        result = audit_dataset([self.write("both", [first, second])])
        self.assertEqual(len(result["ambiguous_trip_identities"]), 2)
        self.assertEqual(result["ambiguity_pair_sample"][0]["evidence"], ["ASSIGNED_VEHICLE_AND_PATH"])

    def test_normal_daily_id_reuse_is_not_a_continuity_alias(self):
        first = example("one", "2026-11-08", train="TRAIN-A")
        second = example("two", "2026-11-09", train="TRAIN-A")
        result = audit_dataset([self.write("both", [first, second])])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["ambiguous_trip_identities"], [])

    def test_duplicate_examples_and_future_sources_fail_audit(self):
        first = example("duplicate", "2026-11-02")
        second = deepcopy(first)
        second["source_updated_at"] = second["decision_at"] + 1
        result = audit_dataset([self.write("both", [first, second])])
        self.assertEqual(result["duplicate_example_rows"], 1)
        self.assertEqual(result["temporal_violations"]["source_after_decision_or_missing"], 1)
        self.assertEqual(result["status"], "FAIL")

    def test_capture_date_must_match_declared_split(self):
        row = example("one", "2026-11-12")
        row["split"] = "train"
        result = audit_dataset([self.write("one", [row])])
        self.assertEqual(result["temporal_violations"]["date_split_mismatches"], 1)

    def test_eligible_labels_and_receipts_cannot_cross_split_boundary(self):
        row = example("one", "2026-11-08", "23:59:00")
        result = audit_dataset([self.write("one", [row])])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["temporal_violations"]["eligible_label_split_boundary"], 1)

    def test_final_eligible_rows_require_collector_receipt_confirmation(self):
        row = example("one", "2026-11-02")
        row["label"].pop("receipt_confirmed_at")
        path = self.write("one", [row])
        result = audit_dataset([path])
        self.assertEqual(result["temporal_violations"]["eligible_label_missing_receipt_confirmation"], 1)
        self.assertEqual(audit_dataset([path], require_receipt_confirmation=False)["status"], "PASS")

    def test_empty_input_is_reported_without_invented_events(self):
        result = audit_dataset([])
        self.assertEqual(result["counts"]["rows"], 0)
        self.assertEqual(result["counts"]["unique_events"], 0)


if __name__ == "__main__":
    unittest.main()
