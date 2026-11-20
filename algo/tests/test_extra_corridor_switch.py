"""Protect the user-authorized corridor cap and deterministic input-only grid."""

import importlib.util
from copy import deepcopy
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "scripts/evaluate_extra_corridor_switch.py"
SPEC = importlib.util.spec_from_file_location("extra_corridor_runner", PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def corridor(identity):
    return {"id": identity, "reference_route_id": "stay", "google": {"capture": "test"},
            "routes": [{"id": "stay", "name": "Exact line", "family": "DIRECT",
                "access_walk_seconds": 60, "egress_walk_seconds": 60, "transfer_walk_seconds": [],
                "legs": [{"route_id": "2", "feed_id": "numbered", "from_stop_id": "127S",
                          "to_stop_id": "232S", "route_ids": ["2"]}]}]}


class ExtraCorridorPolicyTests(unittest.TestCase):
    def setUp(self):
        self.existing = {"corridors": [corridor(x) for x in ("a", "b", "c")]}

    def test_two_additional_corridors_fit_user_cap(self):
        extra = {"corridors": [corridor("d"), corridor("e")]}
        self.assertEqual(len(RUNNER.validate_extra(extra, self.existing)), 2)

    def test_three_additional_corridors_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Only two"):
            RUNNER.validate_extra({"corridors": [corridor(x) for x in ("d", "e", "f")]}, self.existing)

    def test_reusing_an_existing_corridor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            RUNNER.validate_extra({"corridors": [corridor("a")]}, self.existing)

    def test_total_cap_applies_even_with_two_new_corridors(self):
        self.existing["corridors"].append(corridor("d"))
        with self.assertRaisesRegex(ValueError, "five-corridor"):
            RUNNER.validate_extra({"corridors": [corridor("e"), corridor("f")]}, self.existing)

    def test_missing_current_google_reference_is_rejected(self):
        item = corridor("d")
        item["reference_route_id"] = "not supplied"
        with self.assertRaisesRegex(ValueError, "Google Stay"):
            RUNNER.validate_extra({"corridors": [item]}, self.existing)

    def test_dense_grid_is_predeclared_and_outcomes_do_not_select(self):
        self.assertEqual(RUNNER.POLICY["decision_lags_seconds"], list(range(0, 7201, 300)))
        self.assertFalse(RUNNER.POLICY["selection_uses_outcomes_or_recommendations"])
        self.assertFalse(RUNNER.POLICY["raw_mta_advice_is_official_mta_recommendation"])
        self.assertEqual(RUNNER.POLICY["switch_margin_seconds"], 300)
        self.assertEqual(RUNNER.POLICY["tie_margin_seconds"], 180)

    def port_routes(self):
        value = corridor("portauthority_tandon")
        value["routes"] = []
        for line, access in (("A", 120), ("C", 120), ("R", 383)):
            route = deepcopy(corridor("unused")["routes"][0])
            route["id"] = line
            route["access_walk_seconds"] = access
            route["legs"][0].update(route_id=line, route_ids=[line], from_stop_id="A27S" if line != "R" else "R16S")
            value["routes"].append(route)
        return value

    def test_platform_variants_change_a_and_c_together_preserving_r(self):
        original = self.port_routes()
        adjusted, changed = RUNNER.platform_variant(original, 240)
        self.assertEqual(set(changed), {"A", "C"})
        self.assertEqual([r["access_walk_seconds"] for r in adjusted["routes"]], [240, 240, 383])
        self.assertEqual([r["access_walk_seconds"] for r in original["routes"]], [120, 120, 383])

    def test_platform_variant_requires_equal_declared_baselines(self):
        original = self.port_routes()
        original["routes"][1]["access_walk_seconds"] = 0
        with self.assertRaisesRegex(ValueError, "120-second"):
            RUNNER.platform_variant(original, 240)

    def test_platform_variant_requires_both_services(self):
        original = self.port_routes()
        original["routes"] = original["routes"][1:]
        with self.assertRaisesRegex(ValueError, "both exact A and C"):
            RUNNER.platform_variant(original, 0)


if __name__ == "__main__":
    unittest.main()
