"""Ride the first recorded departure on each fixed leg, including transfers."""
from bisect import bisect_left
from collections import defaultdict

HORIZON_SECONDS = 7200


class DepartureIndex:
    def __init__(self, trains):
        by_platform = defaultdict(list)
        for uid, train in trains.items():
            for stop, call in train["calls"].items():
                departure = call.get("departure")
                bounds = departure["bounds"] if departure else call["possible_window"]
                by_platform[stop,train["line"]].append((bounds[0],bounds[1],uid,departure))
        self.trains = trains
        self.groups = {}
        for key, rows in by_platform.items():
            rows.sort(key=lambda row: (row[0],row[1],row[2]))
            highest = []
            for row in rows:
                highest.append(max(highest[-1],row[1]) if highest else row[1])
            self.groups[key] = (rows,highest)

    def first(self, leg, ready, limit):
        candidates = []
        for line in leg["route_ids"]:
            rows, highest = self.groups.get((leg["from_stop_id"],line), ([],[]))
            # Inclusive equality means a passenger already on the platform can board.
            start = bisect_left(highest, ready[0])
            for low,high,uid,departure in rows[start:]:
                if low > limit:
                    break
                if high >= ready[0]:
                    candidates.append((low,high,uid,departure))
        candidates.sort(key=lambda row: (row[0],row[1],row[2]))
        if not candidates:
            return None, "NO_RECORDED_DEPARTURE"
        low,high,uid,departure = candidates[0]
        trace = dict(train=uid, platform_ready=ready, departure_bounds=[low,high])
        if not departure:
            trace["possible_departure_window"] = trace.pop("departure_bounds")
            return trace, "UNRESOLVED_EARLIER_DEPARTURE"
        trace["departure_source"] = departure["source"]
        if low < ready[1]:
            return trace, "UNCERTAIN_BOARDING_AT_READINESS"
        if len(candidates) > 1 and candidates[1][0] <= high:
            trace["competing_train"] = candidates[1][2]
            return trace, "UNRESOLVED_DEPARTURE_ORDER"
        return trace, None


def replay_side(index, screen, template, start):
    limit = start + HORIZON_SECONDS
    ready = [start+template["access_walk_seconds"]]*2
    trace = []
    for i,leg in enumerate(template["legs"]):
        entry,reason = index.first(leg,ready,limit)
        if entry:
            trace.append(entry)
        if reason:
            return dict(bounds=None,reason=reason,trace=trace)
        stop = index.trains[entry["train"]]["calls"].get(leg["to_stop_id"])
        if not stop or not stop.get("arrival"):
            return dict(bounds=None,reason="UNCONFIRMED_DESTINATION_CALL_OR_ARRIVAL",trace=trace)
        arrival = stop["arrival"]["bounds"]
        entry.update(arrival_bounds=arrival,arrival_source=stop["arrival"]["source"])
        event = dict(from_stop_id=leg["from_stop_id"],to_stop_id=leg["to_stop_id"],
                     departure_at=entry["departure_bounds"][1],arrival_at=arrival[0],
                     endpoint_flags={"boarding":[],"alighting":[]})
        if screen.screen(event)["outcome_quality"]["status"] != "PASSED":
            return dict(bounds=None,reason="IMPLAUSIBLE_ENDPOINTS",trace=trace)
        if i == len(template["legs"])-1:
            ends = [at+template["egress_walk_seconds"] for at in arrival]
            if ends[1] > limit:
                return dict(bounds=None,reason="HORIZON",trace=trace)
            return dict(bounds=[at-start for at in ends],trace=trace)
        ready = [at+template["transfer_walk_seconds"][i] for at in arrival]
    raise ValueError("A route must contain at least one leg.")
