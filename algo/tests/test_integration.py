"""Collection selection and snapshot cutoffs must survive orchestration."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from stayorswitch.integration import endpoint, route_ids, snapshots_as_of, integrate_supplied


class FakeCache:
    def __init__(self):
        self.calls = []

    def latest(self, feed_id, cutoff):
        self.calls.append((feed_id, cutoff))
        return {"feed_id": feed_id, "status": "MISSING"}


class IntegrationTests(unittest.TestCase):
    def test_endpoint_identity_changes_when_the_address_changes(self):
        first = endpoint("origin", "1 Example Street")
        self.assertEqual(first["id"], endpoint("origin", " 1 EXAMPLE Street ")["id"])
        self.assertNotEqual(first["id"], endpoint("origin", "2 Example Street")["id"])

    def test_shuttle_label_collects_each_compatible_group(self):
        request = {"itineraries": [{"legs": [{"mode": "SUBWAY", "transit": {"route_short_name": "S"}}]}]}
        static = {"routes": {route: {"short_name": "S"} for route in ("FS", "GS", "H")}}
        routes = route_ids(request, static)
        cache = FakeCache()
        snapshots_as_of(cache, routes, "2026-11-19T15:00:00Z")
        self.assertEqual({call[0] for call in cache.calls}, {"bdfm", "numbered", "ace", "subway-alerts"})

    def test_unknown_route_diagnostic_survives_cache_selection(self):
        cache = FakeCache()
        snapshots = snapshots_as_of(cache, ["UNKNOWN"], "2026-11-19T15:00:00Z")
        self.assertIn("unsupported:UNKNOWN", {item["feed_id"] for item in snapshots})

    def test_supplied_cutoff_uses_cache_without_live_fetch(self):
        fixture = Path(__file__).resolve().parents[1] / "examples/01-switch.json"
        request = json.loads(fixture.read_text())["request"]
        cache = FakeCache()
        with patch("stayorswitch.integration.load_static", return_value=({"routes": {}}, {})), \
                patch("stayorswitch.integration.snapshot_cache", return_value=cache), \
                patch("stayorswitch.integration.match_request", return_value={"itineraries": []}), \
                patch("stayorswitch.integration.query_routes") as query, \
                patch("stayorswitch.integration.mta.collect_feeds") as collect:
            report = integrate_supplied(request, Path("unused"))
        query.assert_not_called()
        collect.assert_not_called()
        self.assertTrue(cache.calls)
        self.assertTrue(all(cutoff == request["decision_time"] for _, cutoff in cache.calls))
        self.assertEqual(report["request"]["current_itinerary_id"], request["current_itinerary_id"])


if __name__ == "__main__":
    unittest.main()
