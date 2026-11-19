"""Source time must not stand in for historical collector receipt."""

import unittest

from history.features import epoch
from history.label_receipts import LabelReceiptIndex


class LabelReceiptTests(unittest.TestCase):
    def test_source_before_boundary_received_after_boundary_is_ineligible(self):
        index = LabelReceiptIndex()
        source = epoch("2026-11-09T04:59:59Z")
        index.add({"feed_id": "g", "source_updated_at": source, "captured_at": source + 2})
        index.add({"feed_id": "g", "source_updated_at": source + 20, "captured_at": source + 22})
        row = {"split": "train", "features": {"feed_id": "g"},
               "label": {"available_at": source, "quality_flags": []}, "eligible_for_training": True}
        index.apply(row)
        self.assertFalse(row["eligible_for_training"])
        self.assertIn("LABEL_RECEIPT_SPLIT_BOUNDARY", row["label"]["quality_flags"])

    def test_receipt_requires_source_at_or_after_marker(self):
        index = LabelReceiptIndex()
        source = epoch("2026-11-02T15:00:00Z")
        index.add({"feed_id": "g", "source_updated_at": source, "captured_at": source + 3})
        self.assertIsNone(index.receipt("g", source + 1))
        index.add({"feed_id": "g", "source_updated_at": source + 60, "captured_at": source + 65})
        self.assertEqual(source + 65, index.receipt("g", source + 1))

    def test_both_segment_endpoints_require_confirmation(self):
        index = LabelReceiptIndex()
        source = epoch("2026-11-02T15:00:00Z")
        index.add({"feed_id": "g", "source_updated_at": source, "captured_at": source + 3})
        row = {"split": "train", "features": {"feed_id": "g"},
               "label": {"origin_available_at": source, "destination_available_at": source + 60,
                         "quality_flags": []}, "eligible_for_training": True}
        index.apply(row)
        self.assertFalse(row["eligible_for_training"])
        self.assertIsNone(row["label"]["receipt_confirmed_at"])
