"""As-of alert interpretation and source-evidence regression checks."""

import unittest

from data.delay_profiles.incidents import IncidentIndex, classify_alert


def alert(header="F trains are running with delays.", identifier="lmm:alert:1:26", route="F", **extra):
    value = {"id": identifier, "header": header, "description": None,
             "active_periods": [{"start": 1}], "informed_entities": [{"route_id": route}],
             "cause": None, "effect": None, "extensions": {}}
    value.update(extra)
    return value


def snapshot(at, alerts=(), **extra):
    value = {"feed_id": "subway-alerts", "kind": "alerts", "captured_at": at,
             "fetched_at": at, "source_updated_at": at - 1, "requested_at": at,
             "status": "AVAILABLE", "alerts": list(alerts)}
    value.update(extra)
    return value


class IncidentTests(unittest.TestCase):
    def test_future_severe_revision_does_not_backdate(self):
        ordinary = alert(description="We are addressing a signal malfunction.")
        severe = alert("F trains are running with severe delays.", "lmm:alert:1:30",
                       description="We are addressing a signal malfunction.")
        index = IncidentIndex([snapshot(200, [severe]), snapshot(100, [ordinary])])
        before, after = index.context_at(150, "F"), index.context_at(210, "F")
        self.assertEqual(before["state"], "DISRUPTION")
        self.assertEqual(after["state"], "SEVERE")
        self.assertEqual(before["incident_ids"], after["incident_ids"])
        self.assertEqual(after["first_observed_at"], 100)
        self.assertEqual(after["cause"], "SIGNAL")
        self.assertEqual(len(index.inventory()["incidents"]), 1)

    def test_stale_absence_is_unknown_but_stale_notice_is_conditional(self):
        empty = IncidentIndex([snapshot(100)])
        self.assertEqual(empty.context_at(200, "F")["state"], "NORMAL")
        self.assertEqual(empty.context_at(401, "F")["state"], "UNKNOWN")
        old = IncidentIndex([snapshot(100, [alert("F severe delays")])])
        context = old.context_at(401, "F")
        self.assertEqual(context["state"], "SEVERE")
        self.assertEqual(context["evidence_status"], "LAST_OBSERVED")

    def test_missing_latest_capture_never_revives_prior_notice(self):
        index = IncidentIndex([snapshot(100, [alert("F severe delays")]),
                               snapshot(200, status="MISSING")])
        self.assertEqual(index.context_at(201, "F")["evidence_status"], "UNKNOWN")
        self.assertEqual(index.context_at(201, "F")["alerts"], [])

    def test_planned_signal_maintenance_is_not_signal_failure(self):
        value = alert("F trains have service changes during signal maintenance.",
                      identifier="lmm:planned_work:44:30")
        classification = classify_alert(value)
        self.assertEqual(classification["state"], "PLANNED")
        self.assertNotEqual(classification["cause"], "SIGNAL")

    def test_shared_incident_is_visible_to_both_routes(self):
        value = alert("F and G severe delays", informed_entities=[{"route_id": "F"}, {"route_id": "G"}],
                      description="We are addressing a switch problem between Bergen St and Jay St.")
        index = IncidentIndex([snapshot(100, [value])])
        for route in ("F", "G"):
            context = index.context_at(101, route)
            self.assertEqual(context["state"], "SEVERE")
            self.assertEqual(context["cause"], "TRACK_SWITCH")
        self.assertEqual(index.context_at(101, "R")["state"], "NORMAL")

    def test_explicit_direction_and_stop_conflict_are_excluded(self):
        value = alert("Uptown F trains are running with severe delays.")
        index = IncidentIndex([snapshot(100, [value])])
        self.assertEqual(index.context_at(101, "F", ["F09S", "A41S"])["state"], "NORMAL")
        self.assertEqual(index.context_at(101, "F", ["F09N"])["state"], "SEVERE")
        value["informed_entities"] = [{"route_id": "F", "stop_id": "A41N"}]
        index = IncidentIndex([snapshot(100, [value])])
        self.assertEqual(index.context_at(101, "F", ["A41S"])["state"], "NORMAL")

    def test_unsupported_selector_is_not_a_definite_severe_match(self):
        value = alert("F severe delays", informed_entities=[{"route_id": "F", "direction_id": 1}])
        context = IncidentIndex([snapshot(100, [value])]).context_at(101, "F", ["F09S"])
        self.assertEqual(context["state"], "UNKNOWN")
        self.assertTrue(context["scope_ambiguous"])
        self.assertEqual(len(context["possible_alerts"]), 1)

    def test_full_snapshot_removal_and_recovery_are_not_old_severity(self):
        severe = alert("F trains have severe delays")
        recovered = alert("F trains are running on or close to schedule.", "lmm:alert:1:20")
        index = IncidentIndex([snapshot(100, [severe]), snapshot(200, [recovered]), snapshot(300)])
        self.assertEqual(index.context_at(201, "F")["state"], "NORMAL")
        self.assertTrue(index.context_at(201, "F")["alerts"][0]["recovery"])
        self.assertEqual(index.context_at(301, "F")["incident_ids"], [])

    def test_active_period_and_future_capture(self):
        value = alert("F severe delays", active_periods=[{"start": 150, "end": 250}])
        index = IncidentIndex([snapshot(100, [value])])
        self.assertEqual(index.context_at(99, "F")["state"], "UNKNOWN")
        self.assertEqual(index.context_at(149, "F")["state"], "NORMAL")
        self.assertEqual(index.context_at(150, "F")["state"], "SEVERE")
        self.assertEqual(index.context_at(250, "F")["state"], "NORMAL")

    def test_conflicting_equal_capture_is_unknown(self):
        index = IncidentIndex([snapshot(100, [alert()]), snapshot(100, [alert("F severe delays")])])
        self.assertEqual(index.context_at(101, "F")["state"], "UNKNOWN")
        self.assertEqual(index.inventory()["incident_count"], 0)

    def test_unchanged_versions_are_interned(self):
        index = IncidentIndex([snapshot(100, [alert()]), snapshot(200, [alert()])])
        self.assertEqual(len(index.versions), 1)
        self.assertEqual(index.inventory()["incidents"][0]["last_observed_at"], 200)

    def test_explicit_end_or_negation_of_severe_delays_is_recovery(self):
        for text in ("F severe delays have ended.",
                     "F trains are no longer experiencing severe delays.",
                     "Major delays are resolved on F trains."):
            with self.subTest(text=text):
                value = classify_alert(alert(text))
                self.assertEqual(value["state"], "NORMAL")
                self.assertTrue(value["recovery"])

    def test_restored_stops_do_not_clear_ongoing_severe_delays(self):
        value = classify_alert(alert("F regular stops resumed with severe delays."))
        self.assertEqual(value["state"], "SEVERE")
        self.assertFalse(value["recovery"])
        value = classify_alert(alert("F severe delays have ended, but minor delays remain."))
        self.assertEqual(value["state"], "DISRUPTION")

    def test_recovery_conflicting_with_structured_impact_is_unknown(self):
        value = classify_alert(alert("F severe delays have ended.", effect="NO_SERVICE"))
        self.assertEqual(value["state"], "UNKNOWN")

    def test_mixed_route_direction_clauses_are_ambiguous(self):
        value = alert("Northbound F and southbound G trains have severe delays.",
                      informed_entities=[{"route_id": "F"}, {"route_id": "G"}])
        index = IncidentIndex([snapshot(100, [value])])
        for line, stops in (("F", ["F09S"]), ("G", ["G22S"]), ("F", ["F09N"])):
            with self.subTest(line=line, stops=stops):
                context = index.context_at(101, line, stops)
                self.assertEqual(context["state"], "UNKNOWN")
                self.assertTrue(context["ambiguous_scope"])
                self.assertEqual(context["severe_incident_ids"], [])

    def test_explicit_both_directions_remains_a_definite_match(self):
        value = alert("Northbound and southbound F trains have severe delays.")
        index = IncidentIndex([snapshot(100, [value])])
        for stop in ("F09S", "F09N"):
            self.assertEqual(index.context_at(101, "F", [stop])["state"], "SEVERE")

    def test_base_line_alerts_cover_express_variants_asymmetrically(self):
        for base, express in (("F", "FX"), ("7", "7X")):
            with self.subTest(base=base):
                index = IncidentIndex([snapshot(100, [alert("Severe delays", route=base)])])
                self.assertEqual(index.context_at(101, express)["state"], "SEVERE")
                reverse = IncidentIndex([snapshot(100, [alert("Severe delays", route=express)])])
                self.assertEqual(reverse.context_at(101, base)["state"], "NORMAL")

    def test_express_alias_preserves_stop_and_direction_constraints(self):
        value = alert("Northbound F trains have severe delays.",
                      informed_entities=[{"route_id": "F", "stop_id": "F09N"}])
        index = IncidentIndex([snapshot(100, [value])])
        self.assertEqual(index.context_at(101, "FX", ["F09N"])["state"], "SEVERE")
        self.assertEqual(index.context_at(101, "FX", ["F09S"])["state"], "NORMAL")
        self.assertEqual(index.context_at(101, "FX", ["A41N"])["state"], "NORMAL")

    def test_text_route_wide_suspension_exposes_explicit_line(self):
        for header in ("G trains are not running.", "No G trains are running.",
                       "[G] trains are not operating."):
            with self.subTest(header=header):
                value = alert(header, route="G")
                context = IncidentIndex([snapshot(100, [value])]).context_at(101, "G")
                self.assertEqual(context["state"], "SEVERE")
                self.assertFalse(context["ambiguous_scope"])
                impact = context["alerts"][0]
                self.assertTrue(impact["no_service"])
                self.assertEqual(impact["no_service_scope"], "ROUTE_WIDE")
                self.assertEqual(impact["no_service_route_ids"], ["G"])

    def test_text_segment_closure_with_unparsed_boundaries_is_ambiguous(self):
        value = alert("No G trains between Court Sq and Bedford-Nostrand Avs.", route="G")
        context = IncidentIndex([snapshot(100, [value])]).context_at(101, "G", ["G22S"])
        self.assertEqual(context["state"], "UNKNOWN")
        self.assertTrue(context["ambiguous_scope"])
        self.assertEqual(context["alerts"], [])
        self.assertEqual(context["possible_alerts"][0]["state"], "SEVERE")
        self.assertEqual(context["possible_alerts"][0]["no_service_scope"], "TEXT_SEGMENT")

    def test_causal_to_does_not_create_a_geographic_service_boundary(self):
        for cause in ("due to", "owing to"):
            with self.subTest(cause=cause):
                value = alert(f"No G trains {cause} a signal problem.", route="G")
                context = IncidentIndex([snapshot(100, [value])]).context_at(101, "G")
                self.assertFalse(context["ambiguous_scope"])
                self.assertEqual(context["alerts"][0]["no_service_scope"], "ROUTE_WIDE")
                value = alert(f"No G trains from Court Sq to Church Av {cause} a signal problem.",
                              route="G")
                context = IncidentIndex([snapshot(100, [value])]).context_at(101, "G")
                self.assertTrue(context["ambiguous_scope"])
                self.assertEqual(context["possible_alerts"][0]["no_service_scope"], "TEXT_SEGMENT")

    def test_generic_suspension_uses_publisher_lines_or_explicit_global_scope(self):
        for selectors, expected in (([{"route_id": "G"}], ["G"]), ([], [])):
            with self.subTest(selectors=selectors):
                value = alert("Service is suspended.", informed_entities=selectors)
                context = IncidentIndex([snapshot(100, [value])]).context_at(101, "G")
                impact = context["alerts"][0]
                self.assertEqual(impact["no_service_scope"], "ROUTE_WIDE")
                self.assertEqual(impact["no_service_route_ids"], expected)

    def test_mixed_line_notice_does_not_expand_text_closure_to_other_lines(self):
        value = alert("G trains are not running. F trains have delays.",
                      informed_entities=[{"route_id": "F"}, {"route_id": "G"}])
        index = IncidentIndex([snapshot(100, [value])])
        self.assertEqual(index.context_at(101, "F")["alerts"][0]["no_service_route_ids"], ["G"])


if __name__ == "__main__":
    unittest.main()
