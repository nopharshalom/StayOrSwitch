"""Regression evidence keeps train failures separate from route completion."""

from copy import deepcopy
import unittest

from stayorswitch.repair_metrics import (
    boarding_diagnostic, compare_versions, operational_summary, supplementalboarding_summary,
)
from stayorswitch.severe import MODES


def inferred(seconds, identity="train"):
    return {"status": "INFERRED", "total_duration_seconds": seconds,
            "selected_legs": [{"trip_id": identity}]}


def unknown(reason="MISSING_ENDPOINT", status="UNAVAILABLE"):
    return {"status": status, "reason": reason}


def case(identity="one", *, action="SWITCH", selected="switch", outcomes=None, fixed=None):
    outcomes = outcomes or {"stay": inferred(1800), "switch": inferred(1200)}
    fixed = fixed or deepcopy(outcomes)
    if action not in {"STAY", "SWITCH"}:
        selected = None
    return {
        "id": identity, "corridor_id": "corridor", "decision_at": 1000,
        "reference_route_id": "stay", "incident_ids": ["notice"],
        "modes": {mode: {"strict_decision": {"action": action, "recommended_itinerary_id": selected},
                         "outcomes": deepcopy(outcomes)} for mode in MODES},
        "fixed_train_diagnostics": {mode: deepcopy(fixed) for mode in MODES},
    }


class OperationalMetricTests(unittest.TestCase):
    def test_eventual_route_completion_keeps_original_train_failure(self):
        fixed = {"stay": inferred(1800), "switch": unknown("DEPARTED", "MISSED_SELECTED_TRAIN")}
        row = case(fixed=fixed)
        original = deepcopy(row)
        summary = operational_summary([row])["by_mode"]["incident_profile"]
        self.assertEqual(summary["route_execution_statuses"], {"INFERRED": 1})
        self.assertEqual(summary["known_missed_selected_journeys"], 1)
        self.assertEqual(summary["known_missed_selected_switches"], 1)
        self.assertEqual(summary["fixed_train_missed_but_route_complete"], 1)
        self.assertEqual(summary["switch_fixed_train_missed_but_route_complete"], 1)
        self.assertEqual(summary["unknown_switches"]["count"], 0)
        self.assertEqual(row, original)

    def test_unknowns_partition_chosen_first_without_double_counting(self):
        rows = [
            case("both", outcomes={"stay": unknown(), "switch": unknown("GAP")}),
            case("chosen", outcomes={"stay": inferred(1800), "switch": unknown("HORIZON", "CENSORED")}),
            case("stay", outcomes={"stay": unknown("IDENTITY"), "switch": inferred(1200)}),
        ]
        summary = operational_summary(rows)["by_mode"]["mta"]
        self.assertEqual(summary["unknown_switches"]["count"], 3)
        self.assertEqual(summary["unknown_switches"]["chosen_incomplete"], 2)
        self.assertEqual(summary["unknown_switches"]["stay_incomplete_when_chosen_complete"], 1)
        self.assertEqual(sum(summary["unknown_switches"]["reason_counts"].values()), 3)
        self.assertEqual(summary["known_missed_selected_journeys"], 0)
        self.assertIn("chosen:CENSORED:HORIZON", summary["unknown_switches"]["reason_counts"])

    def test_abstentions_do_not_become_concrete_failure_denominators(self):
        summary = operational_summary([case(action="UNDETERMINED")])["by_mode"]["incident_profile"]
        self.assertEqual(summary["concrete_actions"], 0)
        self.assertIsNone(summary["known_misses_per_concrete_action"])
        self.assertIsNone(summary["known_misses_per_switch_action"])
        self.assertEqual(summary["route_execution_statuses"], {"NO_SELECTED_JOURNEY": 1})

    def test_missing_fixed_train_evidence_is_not_silently_counted_as_success(self):
        row = case()
        del row["fixed_train_diagnostics"]["mta"]["switch"]
        with self.assertRaisesRegex(ValueError, "fixed-train"):
            operational_summary([row])

    def test_inferred_nonfinite_duration_is_rejected(self):
        for value in (float("nan"), float("inf"), -1, True, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "finite nonnegative"):
                    operational_summary([case(outcomes={"stay": inferred(1800), "switch": inferred(value)})])

    def test_duplicate_case_identifiers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            operational_summary([case(), case()])


class VersionComparisonTests(unittest.TestCase):
    def test_action_change_uses_shared_route_execution_not_fixed_train_duration(self):
        outcomes = {"stay": inferred(1800, "stay-train"), "switch": inferred(1200, "switch-train")}
        old = case(action="STAY", selected="stay", outcomes=outcomes)
        new = case(outcomes=outcomes, fixed={"stay": inferred(1800),
                                            "switch": unknown("DEPARTED", "MISSED_SELECTED_TRAIN")})
        result = compare_versions([old], [new])
        self.assertEqual(result["action_pairs"], {"STAY->SWITCH": 1})
        self.assertEqual(result["classes"], {"MEANINGFUL_GAIN": 1})
        self.assertEqual(result["records"][0]["gain_seconds"], 600)
        self.assertEqual(result["new_known_missed_selected_journeys"], 1)

    def test_unknown_chosen_time_remains_unknown_and_not_zero(self):
        outcomes = {"stay": inferred(1800), "switch": unknown("GAP")}
        result = compare_versions([case(action="STAY", selected="stay", outcomes=outcomes)],
                                  [case(outcomes=outcomes)])
        self.assertEqual(result["eligible_actions"], 1)
        self.assertEqual(result["comparable"], 0)
        self.assertEqual(result["classes"], {"UNKNOWN": 1})
        self.assertIsNone(result["records"][0]["gain_seconds"])
        self.assertIsNone(result["records"][0]["new_duration_seconds"])

    def test_same_route_requires_exactly_shared_evidence_not_equal_time_only(self):
        old = case()
        new = deepcopy(old)
        new["modes"]["incident_profile"]["outcomes"]["switch"]["selected_legs"] = [{"trip_id": "another"}]
        with self.assertRaisesRegex(ValueError, "different execution evidence"):
            compare_versions([old], [new])

    def test_different_choices_still_require_identical_shared_counterfactuals(self):
        old = case(action="STAY", selected="stay")
        new = case()
        new["modes"]["incident_profile"]["outcomes"]["stay"]["total_duration_seconds"] = 1900
        with self.assertRaisesRegex(ValueError, "different execution evidence"):
            compare_versions([old], [new])

    def test_known_same_route_ties_but_unknown_same_route_stays_unknown(self):
        rows = [case("known"), case("unknown", outcomes={"stay": inferred(1800), "switch": unknown()})]
        result = compare_versions(rows, deepcopy(rows))
        self.assertEqual(result["same_recommended_route_pairs"], 2)
        self.assertEqual(result["classes"], {"PRACTICAL_TIE": 1, "UNKNOWN": 1})

    def test_three_minute_boundary_is_a_tie_and_longer_loss_is_a_loss(self):
        outcomes = {"stay": inferred(1200), "switch": inferred(1380)}
        old = case(action="STAY", selected="stay", outcomes=outcomes)
        new = case(outcomes=outcomes)
        self.assertEqual(compare_versions([old], [new])["classes"], {"PRACTICAL_TIE": 1})
        for row in (old, new):
            row["modes"]["incident_profile"]["outcomes"]["switch"]["total_duration_seconds"] = 1381
        self.assertEqual(compare_versions([old], [new])["classes"], {"MEANINGFUL_LOSS": 1})

    def test_abstention_transition_retained_outside_paired_outcome_denominator(self):
        result = compare_versions([case(action="UNDETERMINED")], [case()])
        self.assertEqual(result["action_pairs"], {"UNDETERMINED->SWITCH": 1})
        self.assertEqual(result["eligible_actions"], 0)
        self.assertEqual(result["classes"], {})
        self.assertEqual(result["records"][0]["classification"], "NOT_A_PAIRED_DECISION")

    def test_input_mismatch_order_duplicates_and_membership_are_rejected(self):
        for field, value in (("id", "changed"), ("corridor_id", "other"), ("decision_at", 1001),
                             ("reference_route_id", "other"), ("incident_ids", ["changed"])):
            with self.subTest(field=field):
                row = case()
                changed = deepcopy(row)
                changed[field] = value
                with self.assertRaisesRegex(ValueError, "ordered case inputs"):
                    compare_versions([row], [changed])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            compare_versions([case(), case()], [case(), case()])
        with self.assertRaisesRegex(ValueError, "membership"):
            compare_versions([case()], [])


def selected_route(*, transfer=False):
    return {
        "timing_eligible": True, "access_walk_seconds": 60,
        "transfer_walk_seconds": [30] if transfer else [],
        "selected_legs": [{"trip_id": "first", "from_stop_id": "A", "to_stop_id": "B"}]
        + ([{"trip_id": "second", "from_stop_id": "C", "to_stop_id": "D"}] if transfer else []),
    }


def label(*, departure=None, arrival=None):
    return {
        "departure_usable": departure is not None, "departure_at": departure,
        "arrival_usable": arrival is not None, "arrival_at": arrival,
        "quality_flags": [], "departure_quality_flags": [], "arrival_quality_flags": [],
    }


class SupplementalBoardingTests(unittest.TestCase):
    def test_bad_destination_arrival_does_not_hide_missed_first_train(self):
        labels = {"first": {"A": label(departure=1050), "B": label()}}
        result = boarding_diagnostic(selected_route(), labels, 1000)
        self.assertEqual(result["status"], "MISSED_SELECTED_TRAIN")
        self.assertEqual(result["first_boarding_status"], "MISSED_SELECTED_TRAIN")
        self.assertEqual(result["checked_boarding_count"], 1)
        self.assertEqual(result["missed_boarding_seconds"], 10)

    def test_catchable_final_boarding_requires_no_destination_arrival(self):
        labels = {"first": {"A": label(departure=1060)}}
        result = boarding_diagnostic(selected_route(), labels, 1000)
        self.assertEqual(result["status"], "ALL_BOARDINGS_CATCHABLE")
        self.assertEqual(result["first_boarding_status"], "CATCHABLE")
        self.assertEqual(result["catchable_boarding_count"], 1)
        self.assertEqual(result["checked_boardings"][0]["platform_ready_at"], 1060)

    def test_missing_prior_arrival_blocks_next_readiness_not_first_boarding(self):
        labels = {"first": {"A": label(departure=1100), "B": label()},
                  "second": {"C": label(departure=1300)}}
        result = boarding_diagnostic(selected_route(transfer=True), labels, 1000)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertEqual(result["reason"], "MISSING_OR_UNUSABLE_PREVIOUS_ARRIVAL")
        self.assertEqual(result["first_boarding_status"], "CATCHABLE")
        self.assertEqual(result["total_boardings"], 2)
        self.assertEqual(result["checked_boarding_count"], 1)

    def test_transfer_miss_is_detected_before_bad_final_arrival(self):
        labels = {"first": {"A": label(departure=1100), "B": label(arrival=1280)},
                  "second": {"C": label(departure=1300), "D": label()}}
        result = boarding_diagnostic(selected_route(transfer=True), labels, 1000)
        self.assertEqual(result["status"], "MISSED_SELECTED_TRAIN")
        self.assertEqual(result["leg_index"], 1)
        self.assertEqual(result["first_boarding_status"], "CATCHABLE")
        self.assertEqual(result["platform_ready_at"], 1310)
        self.assertEqual(result["checked_boarding_count"], 2)
        self.assertEqual(result["catchable_boarding_count"], 1)

    def test_quality_flagged_departure_cannot_be_used_to_claim_failure(self):
        labels = {"first": {"A": label(departure=1050)}}
        labels["first"]["A"]["departure_quality_flags"] = ["ENDPOINT_OBSERVATION_AGE_EXCEEDS_LIMIT"]
        result = boarding_diagnostic(selected_route(), labels, 1000)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertEqual(result["checked_boarding_count"], 0)
        self.assertEqual(result["first_boarding_status"], "UNVERIFIABLE")

    def test_nonfinite_departure_remains_unverifiable(self):
        for value in (float("nan"), float("inf"), True):
            with self.subTest(value=value):
                result = boarding_diagnostic(selected_route(), {"first": {"A": label(departure=value)}}, 1000)
                self.assertEqual(result["status"], "UNVERIFIABLE")
                self.assertEqual(result["checked_boarding_count"], 0)

    def test_nonmonotonic_previous_arrival_cannot_create_early_transfer_readiness(self):
        labels = {"first": {"A": label(departure=1100), "B": label(arrival=1090)}}
        result = boarding_diagnostic(selected_route(transfer=True), labels, 1000)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertEqual(result["reason"], "NONMONOTONIC_PREVIOUS_ENDPOINTS")
        self.assertEqual(result["first_boarding_status"], "CATCHABLE")

    def test_missing_or_invalid_walks_fail_instead_of_becoming_zero(self):
        for walks in (None, -1, True, float("inf")):
            with self.subTest(walks=walks):
                route = selected_route()
                route["access_walk_seconds"] = walks
                with self.assertRaisesRegex(ValueError, "finite and nonnegative"):
                    boarding_diagnostic(route, {}, 1000)
        route = selected_route(transfer=True)
        route["transfer_walk_seconds"] = []
        with self.assertRaisesRegex(ValueError, "transfer walking"):
            boarding_diagnostic(route, {}, 1000)

    def test_summary_retains_separate_first_all_and_switch_denominators(self):
        rows = [case("miss", action="STAY", selected="stay"), case("partial"), case("abstain", action="UNDETERMINED")]
        missed = {"status": "MISSED_SELECTED_TRAIN", "first_boarding_status": "MISSED_SELECTED_TRAIN", "reason": "DEPARTED"}
        partial = {"status": "UNVERIFIABLE", "first_boarding_status": "CATCHABLE", "reason": "MISSING_PREVIOUS_ARRIVAL"}
        for row, diagnostic in zip(rows, (missed, partial, {})):
            row["boarding_diagnostics"] = {
                mode: {"stay": deepcopy(diagnostic), "switch": deepcopy(diagnostic)} for mode in MODES
            }
        result = supplementalboarding_summary(rows)["by_mode"]["incident_profile"]
        self.assertEqual(result["concrete_actions"], 2)
        self.assertEqual(result["switch_actions"], 1)
        self.assertEqual(result["first_boarding"]["catchable"], 1)
        self.assertEqual(result["first_boarding"]["missed"], 1)
        self.assertEqual(result["all_boardings"]["unknown"], 1)
        self.assertEqual(result["switch_first_boarding"]["denominator"], 1)
        self.assertEqual(result["switch_first_boarding"]["catchable"], 1)
        self.assertEqual(result["switch_all_boardings"]["unknown"], 1)
        self.assertEqual(result["all_boardings"]["concrete_actions"], 2)
        self.assertEqual(result["all_boardings"]["denominator"], 1)
        self.assertEqual(result["all_boardings"]["evaluable"], 1)
        self.assertEqual(result["all_boardings"]["miss_fraction_among_evaluable"], 1)

    def test_summary_rejects_missing_concrete_diagnostic(self):
        row = case()
        row["boarding_diagnostics"] = {mode: {} for mode in MODES}
        with self.assertRaisesRegex(ValueError, "supplemental boarding"):
            supplementalboarding_summary([row])


if __name__ == "__main__":
    unittest.main()
