"""Independent behavioral checks for conservative boarding and elapsed time."""

from copy import deepcopy
import unittest

from algo.tests.test_severe import (
    NOW, IncidentFake, ProfileFake, leg, route, snapshot, train,
)
from stayorswitch.boarding_safe import predict_routes


class IndependentBoardingSafetyTests(unittest.TestCase):
    def predict(self, templates, feeds, *, mode="incident_profile", corrections=None,
                margin=120):
        return predict_routes(
            [*feeds, snapshot(feed="subway-alerts")], templates, NOW,
            mode=mode, estimator=ProfileFake(corrections),
            incident_index=IncidentFake(), boarding_margin_seconds=margin,
        )["routes"][0]

    def test_positive_departure_delay_cannot_expand_raw_boarding_window(self):
        for slack in (-300, -1, 0, 60, 119, 120, 121, 600):
            for correction in (0, 60, 300, 900):
                with self.subTest(raw_slack=slack, positive_delay=correction):
                    result = self.predict(
                        [route(access=300)],
                        [snapshot([train(departure=300 + slack, arrival=2400)])],
                        corrections={("F", "departure"): correction},
                    )
                    self.assertEqual(result["timing_eligible"], slack >= 120)

    def test_earlier_departure_information_tightens_the_window(self):
        for correction, eligible in ((-600, False), (-300, False), (-180, True),
                                     (-120, True), (0, True), (300, True)):
            with self.subTest(correction=correction):
                result = self.predict(
                    [route(access=300)],
                    [snapshot([train(departure=600, arrival=2400)])],
                    corrections={("F", "departure"): correction},
                )
                self.assertEqual(result["timing_eligible"], eligible)

    def test_optimistic_arrival_does_not_create_transfer_but_keeps_expected_eta(self):
        template = route(access=300, legs=[leg(), leg("G", "P2S", "P3S")],
                         transfers=[100])
        feeds = [snapshot([train("first", departure=500, arrival=1000)]),
                 snapshot([
                     train("too-tight", "G", 1200, 1800, "P2S", "P3S"),
                     train("safe", "G", 1250, 1900, "P2S", "P3S"),
                 ], feed="g")]
        result = self.predict([template], feeds, corrections={
            ("F", "arrival"): -300, ("G", "departure"): 100,
        })
        self.assertTrue(result["timing_eligible"])
        second = result["selected_legs"][1]
        self.assertTrue(second["trip_id"].endswith(":safe"))
        self.assertEqual(second["platform_ready_at"], NOW + 800)
        self.assertEqual(second["boarding_gate"]["conservative_platform_ready_at"],
                         NOW + 1100)
        self.assertEqual(result["total_duration_seconds"], 1960)
        self.assertEqual(result["components"], {
            "walking_seconds": 460, "waiting_seconds": 750, "riding_seconds": 750,
        })

    def test_margin_only_filters_candidates_and_does_not_add_elapsed_time(self):
        feeds = [snapshot([train(departure=900, arrival=1800)])]
        for mode in ("mta", "time_profile", "incident_profile"):
            for margin in (0, 60, 120, 180, 600):
                with self.subTest(mode=mode, margin=margin):
                    result = self.predict([route(access=300)], feeds,
                                          mode=mode, margin=margin)
                    self.assertTrue(result["timing_eligible"])
                    self.assertEqual(result["total_duration_seconds"], 1860)
                    self.assertEqual(sum(result["components"].values()), 1860)

    def test_later_feed_and_outcomes_cannot_change_the_original_decision(self):
        original = snapshot([train("now", departure=600, arrival=1200)])
        poisoned = deepcopy(original)
        poisoned["trips"][0]["actual_departure_at"] = NOW - 100
        poisoned["trips"][0]["later_outcome"] = {"arrival_at": NOW + 10000}
        future = snapshot([train("future", departure=500, arrival=600)],
                          fetched=10, source=5)
        self.assertEqual(
            self.predict([route(access=300)], [original]),
            self.predict([route(access=300)], [poisoned, future]),
        )


if __name__ == "__main__":
    unittest.main()
