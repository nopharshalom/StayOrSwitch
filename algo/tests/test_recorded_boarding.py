"""Regression tests for chronological historical boarding and the November cohort."""
import json
from pathlib import Path
import tempfile
import unittest

from algo.scripts import evaluate_recorded_boarding as experiment
from stayorswitch.recorded_boarding import DepartureIndex, replay_side


LEG = dict(from_stop_id="a", to_stop_id="b", route_ids=["7"])
TEMPLATE = dict(legs=[LEG], access_walk_seconds=0, egress_walk_seconds=0)


def time_record(low, high=None):
    return dict(bounds=[low, low if high is None else high],source="JOURNAL")


def train(low, high, arrival):
    calls = {"a":{"departure":time_record(low,high)}}
    if arrival:
        calls["b"] = {"arrival":time_record(arrival),"possible_window":[arrival,arrival]}
    return dict(line="7",calls=calls)


class Screen:
    def screen(self, event):
        return {"outcome_quality":{"status":"PASSED"}}


class RecordedBoardingTests(unittest.TestCase):
    def test_first_departure_with_equality_and_no_arrival_based_ranking(self):
        index = DepartureIndex({"past":train(9,9,17),"first":train(10,10,40),"express":train(12,12,30)})
        result = replay_side(index,Screen(),TEMPLATE,10)
        self.assertEqual(result["bounds"],[30,30])
        self.assertEqual(result["trace"][0]["train"],"first")

    def test_first_departure_with_missing_arrival_keeps_outcome_unknown(self):
        index = DepartureIndex({"first":train(10,10,None),"next":train(12,12,20)})
        self.assertIsNone(replay_side(index,Screen(),TEMPLATE,10)["bounds"])

    def test_overlapping_order_and_readiness_are_unresolved(self):
        index = DepartureIndex({"one":train(10,14,23),"two":train(13,13,21)})
        self.assertEqual(index.first(LEG,[9,9],60)[1],"UNRESOLVED_DEPARTURE_ORDER")
        self.assertEqual(index.first(LEG,[12,12],60)[1],"UNCERTAIN_BOARDING_AT_READINESS")

    def test_possible_earlier_unresolved_train_is_not_skipped(self):
        uncertain = dict(line="7",calls={"a":{"possible_window":[8,15]}})
        index = DepartureIndex({"unknown":uncertain,"later":train(16,16,27)})
        self.assertEqual(index.first(LEG,[12,12],60)[1],"UNRESOLVED_EARLIER_DEPARTURE")
        self.assertEqual(index.first(LEG,[16,16],60)[0]["train"],"later")

    def test_transfer_restarts_at_arrival_plus_walk(self):
        def onward(dep):
            return {"line":"2","calls":{"c":{"departure":time_record(dep)},
                                        "d":{"arrival":time_record(dep+20),"possible_window":[dep+20,dep+20]}}}
        index = DepartureIndex({"seven":train(10,10,25),"missed":onward(29),"next":onward(31)})
        route = dict(TEMPLATE,legs=[LEG,dict(from_stop_id="c",to_stop_id="d",route_ids=["2"])],
                     transfer_walk_seconds=[5])
        result = replay_side(index,Screen(),route,10)
        self.assertEqual([e["train"] for e in result["trace"]],["seven","next"])

    def test_frozen_recommendations_and_published_results(self):
        old = json.loads((experiment.ROOT/"algo/reports/november-all-forecast-boarding.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/experiment.REPORT.name
            experiment.main(path)
            for suffix in (".json",".md"):
                self.assertEqual(path.with_suffix(suffix).read_bytes(),
                                 experiment.REPORT.with_suffix(suffix).read_bytes())
            rows = json.loads(path.read_text())["cases"]
            example = next(r for r in rows if r["id"] ==
                           "courtsquare_timessquare--lmm-alert-275669--1794312155738")
            self.assertEqual(example["replay"][0]["trace"][0]["train"], "1794292470_7..S")
            self.assertEqual(example["bounds"][1][0] - example["bounds"][0][0], 75)
            self.assertEqual(example["category"], "tie")
            keys = ("id","local_time","corridor","reference","alternative","action")
            self.assertEqual([[r[k] for k in keys] for r in rows],
                             [[r[k] for k in keys] for r in old["cases"]])
