"""Supplement historical inputs for newly supplied Google subway route legs."""

from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from itertools import zip_longest
from pathlib import Path

from data.october.labels import build_labels
from data.october.prepare import DailyReceiptIndex
from data.october.sources import read_snapshots
from data.preincident_inputs import augmented_configuration as previous_configuration


REPLACEMENT_FEEDS = {"numbered", "nqrw"}
ADDED_LABEL_STOPS = {
    "6": {"631S", "635S"},
    "R": {"R20S", "R28S"},
    "7": {"724S"},
    "7X": {"724S"},
}
EXTRA_LEGS = [
    {"route_id": "6", "route_ids": ["6"], "feed_id": "numbered", "from_stop_id": "631S", "to_stop_id": "635S"},
    {"route_id": "R", "route_ids": ["R"], "feed_id": "nqrw", "from_stop_id": "R20S", "to_stop_id": "R28S"},
    {"route_id": "7", "route_ids": ["7", "7X"], "feed_id": "numbered", "from_stop_id": "723S", "to_stop_id": "724S"},
]


def augmented_configuration(original):
    result = previous_configuration(original)
    result["feed_ids"] = sorted(REPLACEMENT_FEEDS)
    result["route_ids"] = sorted(set(result["route_ids"]) | {"6"})
    result["stop_ids"] = sorted(set(result["stop_ids"]) | set().union(*ADDED_LABEL_STOPS.values()))
    for index, leg in enumerate(EXTRA_LEGS):
        result["routes"].append({"id": "google_corridor_projection_" + str(index), "legs": [deepcopy(leg)]})
    return result


def _ordered_extension(old, new):
    pointer = 0
    for item in new:
        if pointer < len(old) and item == old[pointer]:
            pointer += 1
    return pointer == len(old)


def check_snapshot_extension(old, new):
    """Allow added route-6 identities and stops, never rewrite older observations."""
    omitted = {"trips", "vehicles", "normalization_projection"}
    if ({key: value for key, value in old.items() if key not in omitted}
            != {key: value for key, value in new.items() if key not in omitted}):
        raise ValueError("Supplement changed original capture metadata or raw payload identity.")
    prior = old.get("trips", [])
    current = new.get("trips", [])
    old_ids = [trip.get("id") for trip in prior]
    if not _ordered_extension(old_ids, [trip.get("id") for trip in current]):
        raise ValueError("Original trip descriptor order or coverage changed.")
    old_id_set = set(old_ids)
    added_trips = [trip for trip in current if trip.get("id") not in old_id_set]
    if any(trip.get("route_id") != "6" or trip.get("feed_id") != "numbered" for trip in added_trips):
        raise ValueError("Only newly enabled route-6 identities may be added.")
    added_stops, pointer = 0, 0
    for updated in current:
        if updated.get("id") not in old_id_set:
            continue
        trip = prior[pointer]
        pointer += 1
        if updated.get("id") != trip.get("id"):
            raise ValueError("Original trip descriptor order changed.")
        if ({key: value for key, value in trip.items() if key != "stop_updates"}
                != {key: value for key, value in updated.items() if key != "stop_updates"}):
            raise ValueError("Original trip metadata changed.")
        before, after = trip.get("stop_updates", []), updated.get("stop_updates", [])
        if not _ordered_extension(before, after):
            raise ValueError("Original stop values or order changed.")
        added_stops += len(after) - len(before)
    old_vehicles = old.get("vehicles", [])
    retained_vehicles = [vehicle for vehicle in new.get("vehicles", [])
                         if vehicle.get("trip_identity") in old_id_set]
    if retained_vehicles != old_vehicles:
        raise ValueError("Original vehicle observations changed.")
    added_ids = {trip.get("id") for trip in added_trips}
    if any(vehicle.get("trip_identity") not in old_id_set | added_ids
           for vehicle in new.get("vehicles", [])):
        raise ValueError("Added vehicle does not refer to an observed allowed trip.")
    return {"additional_route_6_trips": len(added_trips), "additional_old_trip_stop_updates": added_stops}


def verify_daily_projection(original_path, previous_path, supplemental_path):
    """Compare each replacement feed to its most complete existing projection."""
    totals = {"compared_captures": 0, "additional_route_6_trips": 0,
              "additional_old_trip_stop_updates": 0}
    for feed_id, source in (("numbered", previous_path), ("nqrw", original_path)):
        before = (row for row in read_snapshots(source) if row["feed_id"] == feed_id)
        after = (row for row in read_snapshots(supplemental_path) if row["feed_id"] == feed_id)
        for old, new in zip_longest(before, after):
            if old is None or new is None:
                raise ValueError("Supplement changed selected capture coverage.")
            values = check_snapshot_extension(old, new)
            totals["compared_captures"] += 1
            for key, value in values.items():
                totals[key] += value
    return dict(totals, selected_captures_equal=True, raw_hashes_and_capture_metadata_equal=True,
                original_trip_metadata_and_stop_order_preserved=True,
                earlier_numbered_projection_preserved=True, original_vehicle_observations_preserved=True)


def select_new_label_endpoints(trips, original_labels):
    """Keep complete identity inventory but request only observed, new endpoint keys."""
    for identity, trip in trips.items():
        allowed = ADDED_LABEL_STOPS.get(trip.get("route_id"), set())
        observed = set(trip.get("observed_stop_ids", []))
        trip["observed_stop_ids"] = (observed & allowed) - set(original_labels.get(identity, {}))


def build_additional_labels(trips, identity_days, original_days, archives, timezone):
    """Use unchanged final-prediction rules and full original receipt evidence."""
    groups = defaultdict(dict)
    for identity, trip in trips.items():
        groups[trip.get("start_date") or "UNKNOWN"][identity] = trip
    receipts = DailyReceiptIndex(original_days, timezone)
    journals = [item for item in archives if item["kind"] == "csv"]
    requested = set().union(*ADDED_LABEL_STOPS.values())
    result, quality, used = {}, {}, {}
    for service_date, subset in sorted(groups.items()):
        if not any(trip.get("observed_stop_ids") for trip in subset.values()):
            continue
        observed_days = [day for identity in subset for day in identity_days[identity]]
        first = (date.fromisoformat(min(observed_days)) - timedelta(days=1)).isoformat()
        last = (date.fromisoformat(max(observed_days)) + timedelta(days=1)).isoformat()
        selected = [item for item in journals if first <= item["archive_date"] <= last]
        used.update({item["path"]: item for item in selected})
        labels, counts = build_labels(subset, [item["path"] for item in selected], receipts, requested)
        if set(result) & set(labels):
            raise ValueError("Duplicate service-qualified identities in new endpoint labels.")
        result.update(labels)
        quality[service_date] = counts
    return result, quality, list(used.values())


def merge_label_additions(original, supplement):
    """Refuse all overwrites and endpoints unrelated to the supplied new routes."""
    result = deepcopy(original)
    for identity, endpoints in supplement.items():
        target = result.setdefault(identity, {})
        for stop_id, value in endpoints.items():
            route = value.get("route_id")
            expected_feed = "nqrw" if route == "R" else "numbered"
            if (stop_id not in ADDED_LABEL_STOPS.get(route, set()) or value.get("stop_id") != stop_id
                    or value.get("feed_id") != expected_feed):
                raise ValueError("Supplement contains an unexpected route, stop or feed.")
            if stop_id in target:
                raise ValueError("Supplement cannot overwrite an existing endpoint.")
            target[stop_id] = deepcopy(value)
    return result
