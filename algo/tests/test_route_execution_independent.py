"""Independent behavioral checks for fixed-route archive execution."""

from copy import deepcopy
import unittest

from stayorswitch.route_execution import execute_route


LEG = {"feed_id": "ace", "route_id": "A", "route_ids": ["A"],
       "from_stop_id": "A27S", "to_stop_id": "A41S"}


def template(*, access=0, egress=0, second_leg=None, transfer=0):
    return {"id": "independent_route", "family": "A", "name": "Independent route",
            "legs": [LEG] if second_leg is None else [LEG, second_leg],
            "access_walk_seconds": access, "egress_walk_seconds": egress,
            "transfer_walk_seconds": [] if second_leg is None else [transfer]}


def event(identity, departure, arrival, *, at=None, leg=None, status="COMPATIBLE"):
    leg = leg or LEG
    at = departure - 10 if at is None and departure is not None else (0 if at is None else at)
    return {"trip_id": identity, "canonical_trip_id": identity,
            "feed_id": leg["feed_id"], "route_id": leg["route_id"],
            "from_stop_id": leg["from_stop_id"], "to_stop_id": leg["to_stop_id"],
            "departure_at": departure, "arrival_at": arrival,
            "observations": [{"at": at, "source_at": at,
                              "path_status": status, "trip_id": identity}]}


class Evidence:
    """A deliberately unsorted, complete synthetic archive."""

    def __init__(self, events, *, covered=True):
        self.events = events
        self.covered = covered

    def events_for(self, leg, ready_at, end_at, *, observation_start_at=None):
        return [row for row in self.events
                if row["from_stop_id"] == leg["from_stop_id"]]

    def coverage_for(self, feed_id, start_at, end_at, **kwargs):
        return {"eligible": self.covered, "feed_id": feed_id,
                "start_at": start_at, "end_at": end_at}


class RouteExecutionIndependentTests(unittest.TestCase):
    def test_later_train_destination_speed_cannot_change_first_boarding(self):
        early = event("early_slow", 100, 700)
        later = event("later_fast", 200, 300)
        data = Evidence([later, early])
        first = execute_route(template(), data, 0)
        data.events[0]["arrival_at"] = 201
        faster_later = execute_route(template(), data, 0)
        self.assertEqual(first["selected_legs"][0]["trip_id"], "early_slow")
        self.assertEqual(first["destination_arrival_at"], 700)
        self.assertEqual(first, faster_later)

    def test_missing_first_arrival_is_not_repaired_with_later_good_train(self):
        result = execute_route(template(), Evidence([
            event("later_complete", 200, 300), event("earlier_incomplete", 100, None)]), 0)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "FIRST_BOARDABLE_TRAIN_ARRIVAL_UNAVAILABLE")
        self.assertEqual(result["event"]["trip_id"], "earlier_incomplete")

    def test_future_path_evidence_cannot_resolve_boarding(self):
        train = event("unresolved_then_clear", 100, 400, at=90, status="UNKNOWN")
        train["observations"].append({"at": 101, "source_at": 101,
                                      "path_status": "COMPATIBLE", "trip_id": train["trip_id"]})
        result = execute_route(template(), Evidence([train]), 0)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "UNRESOLVED_EARLIER_BOARDING")

    def test_future_unknown_train_does_not_prevent_already_completed_boarding(self):
        result = execute_route(template(), Evidence([
            event("later_unknown", None, None, at=200), event("first", 100, 300)]), 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual(result["selected_legs"][0]["trip_id"], "first")

    def test_transfer_follows_actual_arrival_and_walk_without_prediction_buffer(self):
        second = {"feed_id": "ace", "route_id": "C", "route_ids": ["C"],
                  "from_stop_id": "A41S", "to_stop_id": "A42S"}
        result = execute_route(template(access=20, egress=30, second_leg=second, transfer=40),
                               Evidence([event("first", 25, 100),
                                         event("already_left", 130, 190, leg=second),
                                         event("connection", 145, 200, leg=second)]), 0)
        self.assertEqual(result["status"], "INFERRED")
        self.assertEqual([row["trip_id"] for row in result["selected_legs"]],
                         ["first", "connection"])
        self.assertEqual(result["selected_legs"][1]["platform_ready_at"], 140)
        self.assertEqual(result["total_duration_seconds"], 230)
        self.assertEqual(result["components"],
                         {"walking_seconds": 90, "waiting_seconds": 10, "riding_seconds": 130})

    def test_egress_is_inside_horizon_and_is_not_an_invented_complete_duration(self):
        result = execute_route(template(egress=40), Evidence([event("first", 50, 100)]),
                               0, max_elapsed_seconds=120)
        self.assertEqual(result["status"], "CENSORED")
        self.assertEqual(result["reason"], "DESTINATION_AFTER_HORIZON")
        self.assertNotIn("total_duration_seconds", result)

    def test_coverage_gap_cannot_be_filled_by_complete_endpoint_labels(self):
        result = execute_route(template(), Evidence([event("first", 100, 300)], covered=False), 0)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "INSUFFICIENT_FEED_COVERAGE")

    def test_no_input_or_future_event_mutation(self):
        route = template()
        data = Evidence([event("first", 100, 300)])
        before = deepcopy((route, data.events))
        execute_route(route, data, 0)
        self.assertEqual((route, data.events), before)


if __name__ == "__main__":
    unittest.main()
