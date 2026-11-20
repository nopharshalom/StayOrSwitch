"""Physical endpoint sanity must not alter feed-driven train selection."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from data.feed_route_archive import FeedRouteArchive
from data.route_archive import build_from_snapshots
from data.route_outcome_sanity import (IMPLAUSIBLE_FLAG, MISSING_COORDINATES_FLAG,
                                       OutcomeQualityScreen, haversine_km,
                                       load_outcome_quality)
from data.tests.test_route_archive import BASE, LEG, TEMPLATE, labels_for, snapshot, trip


ROOT = Path(__file__).resolve().parents[2]
COORDS = {
    "A27S": {"latitude": 40.757308, "longitude": -73.989735},
    "A41S": {"latitude": 40.692338, "longitude": -73.987342},
    "723S": {"latitude": 40.755477, "longitude": -73.987691},
    "724S": {"latitude": 40.75529, "longitude": -73.981817},
}


def event(first="A27S", last="A41S", duration=600):
    return {"from_stop_id": first, "to_stop_id": last,
            "departure_at": BASE, "arrival_at": BASE + duration,
            "endpoint_flags": {"boarding": [], "alighting": []}}


class RouteOutcomeSanityTests(unittest.TestCase):
    def test_haversine_known_equatorial_degree(self):
        distance = haversine_km({"latitude": 0, "longitude": 0},
                                {"latitude": 0, "longitude": 1})
        self.assertAlmostEqual(distance, 111.19508, places=4)

    def test_distance_symmetric_and_zero_at_same_coordinate(self):
        first, last = COORDS["A27S"], COORDS["A41S"]
        self.assertAlmostEqual(haversine_km(first, last), haversine_km(last, first))
        self.assertEqual(haversine_km(first, first), 0)

    def test_collapsed_long_segment_rejected_without_replacing_timestamps(self):
        source = event(duration=10)
        result = OutcomeQualityScreen(COORDS).screen(source)
        self.assertEqual(result["departure_at"], source["departure_at"])
        self.assertEqual(result["arrival_at"], source["arrival_at"])
        self.assertEqual(result["endpoint_flags"]["boarding"], [])
        self.assertEqual(result["endpoint_flags"]["alighting"], [IMPLAUSIBLE_FLAG])
        self.assertGreater(result["outcome_quality"]["implied_speed_kmh"], 300)

    def test_ordinary_long_segment_passes(self):
        result = OutcomeQualityScreen(COORDS).screen(event(duration=600))
        self.assertEqual(result["outcome_quality"]["status"], "PASSED")
        self.assertEqual(result["endpoint_flags"]["alighting"], [])

    def test_short_leg_is_not_rejected_by_blanket_duration_cutoff(self):
        result = OutcomeQualityScreen(COORDS).screen(event("723S", "724S", duration=35))
        self.assertEqual(result["outcome_quality"]["status"], "PASSED")

    def test_limit_applies_by_distance_and_duration_not_route_or_gain(self):
        screen = OutcomeQualityScreen(COORDS)
        first = event(duration=8)
        second = dict(first, from_stop_id="A41S", to_stop_id="A27S", route_id="C", comparison="LOSS")
        for item in (first, second):
            self.assertIn(IMPLAUSIBLE_FLAG, screen.screen(item)["endpoint_flags"]["alighting"])

    def test_zero_duration_positive_distance_rejected_with_json_safe_speed(self):
        result = OutcomeQualityScreen(COORDS).screen(event(duration=0))
        self.assertIn(IMPLAUSIBLE_FLAG, result["endpoint_flags"]["alighting"])
        self.assertIsNone(result["outcome_quality"]["implied_speed_kmh"])
        json.dumps(result, allow_nan=False)

    def test_negative_duration_rejected(self):
        result = OutcomeQualityScreen(COORDS).screen(event(duration=-1))
        self.assertIn(IMPLAUSIBLE_FLAG, result["endpoint_flags"]["alighting"])

    def test_same_coordinate_zero_duration_not_assigned_infinite_speed(self):
        result = OutcomeQualityScreen(COORDS).screen(event("A27S", "A27S", 0))
        self.assertEqual(result["outcome_quality"]["status"], "PASSED")
        self.assertEqual(result["outcome_quality"]["implied_speed_kmh"], 0)

    def test_missing_coordinates_make_complete_outcome_explicitly_unusable(self):
        result = OutcomeQualityScreen({}).screen(event())
        self.assertEqual(result["outcome_quality"]["status"], "UNAVAILABLE_COORDINATES")
        self.assertIn(MISSING_COORDINATES_FLAG, result["endpoint_flags"]["alighting"])
        self.assertEqual(result["outcome_quality"]["missing_stop_ids"], ["A27S", "A41S"])

    def test_original_invalid_endpoint_is_not_rehabilitated_or_reclassified(self):
        source = event(duration=10)
        source["endpoint_flags"]["boarding"] = ["ORIGINAL_BAD_ENDPOINT"]
        result = OutcomeQualityScreen(COORDS).screen(source)
        self.assertEqual(result["outcome_quality"]["status"], "NOT_APPLIED_ENDPOINTS_ALREADY_UNUSABLE")
        self.assertEqual(result["endpoint_flags"], source["endpoint_flags"])

    def test_missing_original_endpoint_remains_missing(self):
        source = event()
        source["arrival_at"] = None
        result = OutcomeQualityScreen(COORDS).screen(source)
        self.assertEqual(result["outcome_quality"]["status"], "NOT_APPLIED_ENDPOINTS_ALREADY_UNUSABLE")
        self.assertIsNone(result["arrival_at"])

    def test_screen_does_not_mutate_original_evidence(self):
        source = event(duration=10)
        before = deepcopy(source)
        OutcomeQualityScreen(COORDS).screen(source)
        self.assertEqual(source, before)

    def test_none_endpoint_flags_normalized_before_adding_rejection(self):
        source = event(duration=10)
        source["endpoint_flags"] = None
        result = OutcomeQualityScreen(COORDS).screen(source)
        self.assertEqual(result["endpoint_flags"]["alighting"], [IMPLAUSIBLE_FLAG])
        self.assertIsNone(source["endpoint_flags"])

    def test_optional_adapter_quality_screen_leaves_every_frame_identical(self):
        value = trip(departure=100, arrival=110)
        payload = build_from_snapshots([snapshot(0, [value]), snapshot(60, [value])], [TEMPLATE],
                                      labels_for(value, departure=100, arrival=110))
        original = FeedRouteArchive(payload)
        guarded = FeedRouteArchive(payload, quality_screen=OutcomeQualityScreen(COORDS))
        frames = list(original.frames_for(LEG, BASE + 10, BASE + 120))
        self.assertEqual(frames, list(guarded.frames_for(LEG, BASE + 10, BASE + 120)))
        key = frames[0]["candidates"][0]["event_key"]
        self.assertEqual(original.event_for(LEG, key)["endpoint_flags"]["alighting"], [])
        self.assertIn(IMPLAUSIBLE_FLAG, guarded.event_for(LEG, key)["endpoint_flags"]["alighting"])
        self.assertEqual(original.event_for(LEG, key)["arrival_at"], guarded.event_for(LEG, key)["arrival_at"])

    def test_reject_bad_coordinate_or_nonfinite_quality_configuration(self):
        for bad in ({"latitude": 91, "longitude": 0}, {"latitude": 0, "longitude": 181},
                    {"latitude": float("nan"), "longitude": 0}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                OutcomeQualityScreen({"X": bad})
        for bound in (0, -1, float("inf"), True):
            with self.subTest(bound=bound), self.assertRaises(ValueError):
                OutcomeQualityScreen(COORDS, max_straight_line_speed_kmh=bound)

    def test_portable_official_station_subset_covers_all_approved_endpoints(self):
        screen = load_outcome_quality(ROOT)
        report = json.loads((ROOT / "algo/reports/november-repair-test.json").read_text())
        stops = {leg[endpoint] for corridor in report["corridors"] for route in corridor["routes"]
                 for leg in route["legs"] for endpoint in ("from_stop_id", "to_stop_id")}
        self.assertEqual(stops, set(screen.coordinates))
        self.assertEqual(screen.max_speed, 300)
        self.assertEqual(len(stops), 22)


if __name__ == "__main__":
    unittest.main()
