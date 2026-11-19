"""Compare CSV endpoint proxies with separately derived vehicle-status evidence.

The vehicle records share the MTA source with the CSV and are not independent
physical observations. This is a consistency audit, never an accuracy claim.
"""

from collections import Counter
from datetime import datetime


def epoch(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


class VehicleLabelAudit:
    """Use sampled, fresh vehicle status transitions as uncertain brackets."""

    def __init__(self, labels, *, maximum_gap_seconds=600, sample_limit=100):
        self.labels = labels
        self.maximum_gap_seconds = maximum_gap_seconds
        self.sample_limit = sample_limit
        self.previous = {}
        self.seen = set()
        self.counts = Counter()
        self.samples = []

    def process(self, snapshot):
        captured = epoch(snapshot.get("fetched_at"))
        source = epoch(snapshot.get("source_updated_at"))
        if captured is None or source is None or not 0 <= captured - source <= 180:
            self.counts["unusable_snapshot"] += 1
            return
        trips = {trip["id"]: trip for trip in snapshot.get("trips", []) if trip.get("id")}
        for vehicle in snapshot.get("vehicles", []):
            identity = vehicle.get("trip_identity")
            stop = vehicle.get("stop_id")
            stamp = epoch(vehicle.get("timestamp"))
            if not identity or not stop or stamp is None or not 0 <= captured - stamp <= 180:
                self.counts["unusable_vehicle"] += 1
                continue
            state = vehicle.get("current_status")
            key = (identity, stop)
            previous = self.previous.get(key)
            if state in ("IN_TRANSIT_TO", "INCOMING_AT"):
                self.previous[key] = (captured, stamp, state)
            elif state == "STOPPED_AT" and previous and key not in self.seen:
                self.seen.add(key)
                lower = previous[1]
                if captured < previous[0] or captured - lower > self.maximum_gap_seconds:
                    self.counts["transition_gap_too_large"] += 1
                    continue
                trip = trips.get(identity)
                label = self.labels.lookup(trip, stop) if trip else None
                arrival = None if not label else label.get("arrival_at")
                if arrival is None:
                    self.counts["transition_without_csv_label"] += 1
                    continue
                arrival = float(arrival)
                agreement = lower <= arrival <= captured
                self.counts["transitions_compared"] += 1
                self.counts["proxy_inside_status_bracket" if agreement else "proxy_outside_status_bracket"] += 1
                if len(self.samples) < self.sample_limit:
                    self.samples.append({
                        "trip_identity": identity,
                        "stop_id": stop,
                        "previous_vehicle_status": previous[2],
                        "lower_vehicle_observation_epoch": lower,
                        "first_stopped_collection_epoch": captured,
                        "bracket_width_seconds": captured - lower,
                        "csv_arrival_proxy_epoch": arrival,
                        "proxy_inside_bracket": agreement,
                        "evidence_class": "SAMPLED_VEHICLE_STATUS_CONSISTENCY_ONLY",
                    })
        # Bound state across long archives; no cross-day audit claim is needed.
        if len(self.previous) > 20000:
            self.previous = {key: value for key, value in self.previous.items()
                             if captured - value[0] <= self.maximum_gap_seconds}

    def report(self):
        return {
            "method": "CSV_LAST_PREDICTION_VS_SAMPLED_VEHICLE_STATUS_TRANSITION",
            "counts": dict(self.counts),
            "samples": self.samples,
            "limitations": [
                "Both derivations originate from the same MTA feed; no independent physical arrivals were supplied.",
                "Vehicle timestamps describe observations or last movement, not a verified arrival event.",
                "Sampling can miss short station stops; compared transitions are a selected subset.",
                "Bracket agreement is a consistency check and is not a model accuracy metric.",
            ],
        }
