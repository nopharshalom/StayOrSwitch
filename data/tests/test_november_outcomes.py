"""Tests for independent, non-mutating November endpoint-quality screening."""

from copy import deepcopy
import unittest

from data.november_outcomes import endpoint_diagnostics, screen_labels


IDENTITY = "MTA:numbered:20261101:5:060000_5..S03R:"


class NovemberOutcomeTests(unittest.TestCase):
    def label(self, **changes):
        row = {"arrival_at": 1000, "departure_at": 1100,
               "stop_last_observed_at": 1180, "quality_flags": [],
               "confirmed_at": 1185, "confirmation_status": "CONFIRMED",
               "feed_id": "numbered", "service_date": "20261101", "route_id": "5",
               "raw_trip_id": "060000_5..S03R", "stop_id": "s",
               "arrival_usable": True, "departure_usable": True,
               "arrival_quality_flags": [], "departure_quality_flags": []}
        row.update(changes)
        return row

    def test_inclusive_limit_and_independent_endpoints(self):
        row = self.label(stop_last_observed_at=1181)
        screened, report = screen_labels({IDENTITY: {"s": row}})
        self.assertFalse(screened[IDENTITY]["s"]["arrival_usable"])
        self.assertTrue(screened[IDENTITY]["s"]["departure_usable"])
        self.assertEqual(report["counts"]["arrival_newly_excluded"], 1)
        self.assertTrue(endpoint_diagnostics(self.label(), "arrival")["age_eligible"])

    def test_earlier_observation_uses_absolute_age(self):
        self.assertFalse(endpoint_diagnostics(self.label(stop_last_observed_at=819), "arrival")["age_eligible"])
        self.assertTrue(endpoint_diagnostics(self.label(stop_last_observed_at=820), "arrival")["age_eligible"])

    def test_missing_nonfinite_and_boolean_values_are_unknown(self):
        for value in (None, float("nan"), float("inf"), True, "invalid"):
            with self.subTest(value=value):
                self.assertFalse(endpoint_diagnostics(self.label(stop_last_observed_at=value), "arrival")["age_eligible"])

    def test_input_unchanged_and_existing_rejection_preserved(self):
        original = {IDENTITY: {"s": self.label(arrival_usable=False, arrival_quality_flags=["EXISTING"])}}
        before = deepcopy(original)
        screened, _ = screen_labels(original)
        self.assertEqual(original, before)
        self.assertFalse(screened[IDENTITY]["s"]["arrival_usable"])
        self.assertEqual(screened[IDENTITY]["s"]["arrival_quality_flags"], ["EXISTING"])
        screened[IDENTITY]["s"]["arrival_quality_flags"].append("NEW")
        self.assertEqual(original, before)

    def test_invalid_limit_rejected_even_for_empty_mapping(self):
        for value in (-1, float("nan"), True):
            with self.assertRaises(ValueError):
                screen_labels({}, value)

    def test_confirmation_is_required_and_finite(self):
        for value in (None, True, float("nan"), float("inf")):
            screened, _ = screen_labels({IDENTITY: {"s": self.label(confirmed_at=value)}})
            self.assertFalse(screened[IDENTITY]["s"]["arrival_usable"])
            self.assertFalse(screened[IDENTITY]["s"]["departure_usable"])
        screened, _ = screen_labels({IDENTITY: {"s": self.label(confirmation_status="UNVERIFIED")}})
        self.assertFalse(screened[IDENTITY]["s"]["arrival_usable"])

    def test_route_service_and_stop_identity_mismatches_are_excluded(self):
        for key, value in (("route_id", "4"), ("service_date", "20261102"),
                           ("feed_id", "ace"), ("raw_trip_id", "different"), ("stop_id", "other")):
            with self.subTest(key=key):
                screened, _ = screen_labels({IDENTITY: {"s": self.label(**{key: value})}})
                self.assertFalse(screened[IDENTITY]["s"]["arrival_usable"])
                self.assertIn("NORMALIZED_TRAIN_OR_STOP_LABEL_IDENTITY_MISMATCH",
                              screened[IDENTITY]["s"]["departure_quality_flags"])


if __name__ == "__main__":
    unittest.main()
