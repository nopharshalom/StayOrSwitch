"""Passage quality and fallback rules for retrospective boarding."""
import unittest

from data.october.labels import ReceiptIndex
from data.recorded_passages import journal_time, merge_endpoint


class RecordedPassageTests(unittest.TestCase):
    def test_journal_endpoint_needs_nearby_observation_and_following_receipt(self):
        receipts = ReceiptIndex({"numbered":[[230,225]]})
        self.assertEqual(journal_time([195,200,203,207],"departure",receipts,"numbered"),
                         [200,200])
        self.assertIsNone(journal_time([165,201,195,198],"departure",receipts,"numbered"))
        self.assertIsNone(journal_time([195,200,203,207],"arrival",receipts,"other"))

    def test_vehicle_interval_can_supply_only_its_documented_endpoint(self):
        observation = {"arrival":[41,50],"stopped":[50,70]}
        self.assertEqual(merge_endpoint(None,observation,"arrival"),
                         {"bounds":[41,50],"source":"VEHICLE"})
        self.assertIsNone(merge_endpoint(None,observation,"departure"))
