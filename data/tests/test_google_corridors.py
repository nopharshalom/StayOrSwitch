"""Provider defaults must not change when another path has a shorter duration."""

import unittest

from data.google_corridors import duration_seconds, select_stay


class ProviderDefaultTests(unittest.TestCase):
    def test_default_is_preserved_when_an_alternative_is_faster(self):
        routes = [{"routeLabels": ["DEFAULT_ROUTE"], "duration": "1200s"},
                  {"routeLabels": ["DEFAULT_ROUTE_ALTERNATE"], "duration": "900s"}]
        self.assertEqual(select_stay(routes), {"route_index": 0, "method": "GOOGLE_DEFAULT_ROUTE"})

    def test_default_marker_is_not_a_substring_match(self):
        routes = [{"routeLabels": ["DEFAULT_ROUTE_ALTERNATE"], "duration": "900s"},
                  {"routeLabels": ["DEFAULT_ROUTE"], "duration": "1200s"}]
        self.assertEqual(select_stay(routes)["route_index"], 1)

    def test_ambiguous_defaults_do_not_silently_become_fastest(self):
        routes = [{"routeLabels": ["DEFAULT_ROUTE"], "duration": "900s"},
                  {"routeLabels": ["DEFAULT_ROUTE"], "duration": "1200s"}]
        self.assertEqual(select_stay(routes), {"route_index": None, "method": "AMBIGUOUS_GOOGLE_DEFAULT_ROUTES"})

    def test_default_with_unusable_duration_is_not_replaced(self):
        routes = [{"routeLabels": ["DEFAULT_ROUTE"]}, {"duration": "900s"}]
        self.assertEqual(select_stay(routes)["route_index"], 0)

    def test_missing_default_has_an_explicit_fastest_duration_fallback(self):
        self.assertEqual(select_stay([{"duration": "1200s"}, {"duration": "900s"}]),
                         {"route_index": 1, "method": "FASTEST_PROVIDER_DURATION_NO_EXPLICIT_DEFAULT"})

    def test_no_valid_route_retains_unknown_selection(self):
        self.assertEqual(select_stay([{"duration": "NaNs"}, {"duration": "-1s"}]),
                         {"route_index": None, "method": "NO_USABLE_PROVIDER_DURATION"})


class DurationTests(unittest.TestCase):
    def test_only_finite_nonnegative_seconds_are_available(self):
        self.assertEqual(duration_seconds("0s"), 0)
        self.assertEqual(duration_seconds("12.5s"), 12.5)
        for value in (None, True, 12, "12", "NaNs", "infs", "-1s"):
            with self.subTest(value=value):
                self.assertIsNone(duration_seconds(value))


if __name__ == "__main__":
    unittest.main()
