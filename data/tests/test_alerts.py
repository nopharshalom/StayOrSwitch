"""Regression tests for historical alert availability and selector semantics."""

import unittest

from history.alerts import AlertsIndex


BASE = 1793630000


def alert(identifier="one", *, selectors=None, start=None, end=None):
    return {"id": identifier,
            "informed_entities": [{}] if selectors is None else selectors,
            "active_periods": [{"start": start, "end": end}],
            "effect": "SIGNIFICANT_DELAYS", "cause": "MAINTENANCE",
            "extensions": {"transit_realtime.mercury_alert": {"alert_type": "Delays"}}}


def snapshot(alerts=None, *, capture=BASE, source=BASE - 10, status="AVAILABLE"):
    return {"captured_at": capture, "source_updated_at": source, "status": status,
            "alerts": [] if alerts is None else alerts}


def row(*, decision=BASE + 20, arrival=BASE + 120, route="F", stop="A41S", direction=None):
    return {"decision_at": decision, "trip_identity": "MTA:bdfm:20261102:F:030000_F..S:",
            "stop_id": stop,
            "features": {"route_id": route, "stop_id": stop, "gtfs_direction_id": direction,
                         "mta_arrival_at": arrival, "remaining_stop_pattern": ["B04S", "F11S", stop, "F20S"]}}


class HistoricalAlertsTests(unittest.TestCase):
    def test_no_prior_capture_is_unknown_not_zero(self):
        index = AlertsIndex()
        index.add(snapshot([alert()], capture=BASE + 30))
        result = index.features_for(row())
        self.assertFalse(result["service_alerts_available"])
        self.assertIsNone(result["service_alert_count"])

    def test_empty_fresh_snapshot_is_known_zero(self):
        index = AlertsIndex()
        index.add(snapshot())
        result = index.features_for(row())
        self.assertTrue(result["service_alerts_available"])
        self.assertEqual(result["service_alert_count"], 0)

    def test_minimal_alert_without_optional_extensions_is_supported(self):
        index = AlertsIndex()
        index.add(snapshot([{"id": "minimal", "informed_entities": [{"route_id": "F"}]}]))
        result = index.features_for(row())
        self.assertEqual(result["service_alert_count"], 1)
        self.assertEqual(result["service_alert_types"], [])

    def test_old_source_header_with_recent_capture_remains_fresh(self):
        index = AlertsIndex()
        index.add(snapshot([alert()], source=BASE - 86400))
        self.assertEqual(index.features_for(row())["service_alert_count"], 1)

    def test_future_header_is_unavailable(self):
        index = AlertsIndex()
        index.add(snapshot([alert()], source=BASE + 1))
        self.assertFalse(index.features_for(row())["service_alerts_available"])

    def test_latest_failure_blocks_earlier_success(self):
        index = AlertsIndex()
        index.add(snapshot([alert()]))
        index.add(snapshot(capture=BASE + 10, status="MISSING"))
        self.assertFalse(index.features_for(row())["service_alerts_available"])

    def test_stale_change_only_archive_retains_explicit_uncertain_context(self):
        index = AlertsIndex()
        index.add(snapshot([alert()]))
        result = index.features_for(row(decision=BASE + 301))
        self.assertFalse(result["service_alerts_available"])
        self.assertIsNone(result["service_alert_count"])
        self.assertEqual(result["last_observed_relevant_alert_count"], 1)
        self.assertEqual(result["service_alert_context_status"], "LAST_OBSERVED_UNVERIFIED")

    def test_freshness_boundary_is_inclusive(self):
        index = AlertsIndex()
        index.add(snapshot([alert()]))
        self.assertTrue(index.features_for(row(decision=BASE + 300))["service_alerts_available"])

    def test_future_update_does_not_change_an_earlier_row(self):
        index = AlertsIndex()
        index.add(snapshot())
        index.add(snapshot([alert()], capture=BASE + 40))
        self.assertEqual(index.features_for(row())["service_alert_count"], 0)

    def test_out_of_order_capture_insertion_is_selected_by_time(self):
        index = AlertsIndex()
        index.add(snapshot([alert()], capture=BASE + 10))
        index.add(snapshot())
        self.assertEqual(index.features_for(row())["service_alert_count"], 1)

    def test_conflicting_capture_is_unavailable(self):
        index = AlertsIndex()
        index.add(snapshot())
        index.add(snapshot([alert()]))
        result = index.features_for(row())
        self.assertEqual(result["service_alert_status"], "CONFLICTING_ALERT_CAPTURE")

    def test_identical_capture_and_content_are_deduplicated(self):
        index = AlertsIndex()
        index.add(snapshot([alert()]))
        index.add(snapshot([alert()]))
        index.add(snapshot([alert()], capture=BASE + 10))
        self.assertEqual(index.report()["indexed_captures"], 2)
        self.assertEqual(index.report()["distinct_alert_contents"], 1)

    def test_selector_route_and_stop_must_both_match(self):
        index = AlertsIndex()
        index.add(snapshot([alert(selectors=[{"route_id": "G", "stop_id": "A41S"},
                                            {"route_id": "F", "stop_id": "G22S"}])]))
        self.assertEqual(index.features_for(row())["service_alert_count"], 0)

    def test_parent_stop_selector_matches_directed_platform(self):
        index = AlertsIndex()
        index.add(snapshot([alert(selectors=[{"route_id": "F", "stop_id": "A41"}])]))
        self.assertEqual(index.features_for(row())["service_alert_count"], 1)

    def test_opposite_platform_does_not_match(self):
        index = AlertsIndex()
        index.add(snapshot([alert(selectors=[{"stop_id": "A41N"}])]))
        self.assertEqual(index.features_for(row())["service_alert_count"], 0)

    def test_station_after_target_is_not_relevant(self):
        index = AlertsIndex()
        index.add(snapshot([alert(selectors=[{"stop_id": "F20S"}])]))
        self.assertEqual(index.features_for(row())["service_alert_count"], 0)

    def test_segment_limits_stop_scope_to_its_own_interval(self):
        index = AlertsIndex()
        index.add(snapshot([alert(selectors=[{"stop_id": "B04S"}])]))
        value = row()
        value["features"]["segment_stop_pattern"] = ["F11S", "A41S"]
        self.assertEqual(index.features_for(value)["service_alert_count"], 0)

    def test_direction_restriction_does_not_guess_nyct_convention(self):
        index = AlertsIndex()
        index.add(snapshot([alert(selectors=[{"route_id": "F", "direction_id": 1}])]))
        value = row()
        value["features"]["direction"] = "SOUTH"
        result = index.features_for(value)
        self.assertEqual(result["service_alert_count"], 0)
        self.assertEqual(result["service_alert_possible_count"], 1)
        self.assertEqual(index.features_for(row(direction=1))["service_alert_count"], 1)
        self.assertEqual(index.features_for(row(direction=0))["service_alert_count"], 0)

    def test_service_qualified_trip_selector_matches_exactly(self):
        index = AlertsIndex()
        index.add(snapshot([alert(selectors=[{"trip": {"trip_id": "030000_F..S", "start_date": "20261102"}}])]))
        self.assertEqual(index.features_for(row())["service_alert_count"], 1)
        changed = row()
        changed["trip_identity"] = "MTA:bdfm:20261103:F:030000_F..S:"
        self.assertEqual(index.features_for(changed)["service_alert_count"], 0)

    def test_different_agency_does_not_match(self):
        index = AlertsIndex()
        index.add(snapshot([alert(selectors=[{"agency_id": "PATH"}])]))
        self.assertEqual(index.features_for(row())["service_alert_count"], 0)

    def test_uninterpreted_selector_extension_is_only_possible(self):
        index = AlertsIndex()
        index.add(snapshot([alert(selectors=[{"route_id": "F", "extensions": {"vendor.selector": {"track": "1"}}}])]))
        result = index.features_for(row())
        self.assertEqual(result["service_alert_count"], 0)
        self.assertEqual(result["service_alert_possible_count"], 1)

    def test_active_interval_is_half_open(self):
        index = AlertsIndex()
        index.add(snapshot([alert(start=BASE + 10, end=BASE + 20)]))
        self.assertEqual(index.features_for(row(decision=BASE + 10))["service_alert_count"], 1)
        self.assertEqual(index.features_for(row(decision=BASE + 20))["service_alert_count"], 0)

    def test_future_notice_already_captured_is_separate(self):
        index = AlertsIndex()
        index.add(snapshot([alert(start=BASE + 100, end=BASE + 200)]))
        result = index.features_for(row())
        self.assertEqual(result["service_alert_count"], 0)
        self.assertEqual(result["known_upcoming_service_alert_count"], 1)
        self.assertEqual(index.features_for(row(arrival=BASE + 99))["known_upcoming_service_alert_count"], 0)

    def test_matching_cache_respects_temporal_boundaries(self):
        index = AlertsIndex()
        index.add(snapshot([alert(start=BASE + 100, end=BASE + 200)]))
        self.assertEqual(index.features_for(row())["known_upcoming_service_alert_count"], 1)
        self.assertEqual(index.features_for(row(decision=BASE + 100))["service_alert_count"], 1)

    def test_effects_and_types_are_categorical_not_infeasibility(self):
        index = AlertsIndex()
        index.add(snapshot([alert()]))
        result = index.features_for(row())
        self.assertEqual(result["service_alert_effects"], ["SIGNIFICANT_DELAYS"])
        self.assertEqual(result["service_alert_types"], ["Delays"])
        self.assertNotIn("infeasible", result)

    def test_caller_cannot_mutate_cached_effects_for_later_rows(self):
        index = AlertsIndex()
        index.add(snapshot([alert()]))
        index.features_for(row())["service_alert_effects"].append("NO_SERVICE")
        self.assertEqual(index.features_for(row())["service_alert_effects"], ["SIGNIFICANT_DELAYS"])

    def test_invalid_period_order_makes_snapshot_unavailable(self):
        index = AlertsIndex()
        index.add(snapshot([alert(start=BASE + 20, end=BASE + 10)]))
        self.assertFalse(index.features_for(row())["service_alerts_available"])

    def test_conflicting_alert_id_is_not_double_counted(self):
        index = AlertsIndex()
        index.add(snapshot([alert(), alert(selectors=[{"route_id": "F"}])]))
        self.assertFalse(index.features_for(row())["service_alerts_available"])


if __name__ == "__main__":
    unittest.main()
