"""Extend existing NQRW captures for the additional Times Square R boarding."""

from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from itertools import zip_longest

from data.google_corridor_inputs import augmented_configuration as previous_configuration
from data.october.labels import build_labels
from data.october.prepare import DailyReceiptIndex
from data.october.sources import read_snapshots


ADDED_STOP = "R16S"


def augmented_configuration(original):
    result = previous_configuration(original)
    result["feed_ids"] = ["nqrw"]
    result["stop_ids"] = sorted(set(result["stop_ids"]) | {ADDED_STOP})
    result["routes"].append({"id": "incremental_extra_r16_projection", "legs": [{
        "route_id": "R", "route_ids": ["R"], "feed_id": "nqrw",
        "from_stop_id": ADDED_STOP, "to_stop_id": "R29S"}]})
    return result


def _ordered_extension(old, new):
    pointer = 0
    for item in new:
        if pointer < len(old) and item == old[pointer]:
            pointer += 1
    return pointer == len(old)


def check_snapshot_extension(old, new):
    omitted = {"trips", "normalization_projection"}
    if ({k: v for k, v in old.items() if k not in omitted}
            != {k: v for k, v in new.items() if k not in omitted}):
        raise ValueError("Supplement changed capture metadata or vehicle observations.")
    before, after = old.get("trips", []), new.get("trips", [])
    if len(before) != len(after):
        raise ValueError("Supplement changed existing trip coverage.")
    added, added_r16 = 0, 0
    for prior, updated in zip(before, after):
        if ({k: v for k, v in prior.items() if k != "stop_updates"}
                != {k: v for k, v in updated.items() if k != "stop_updates"}):
            raise ValueError("Supplement changed original trip metadata or order.")
        old_stops, new_stops = prior.get("stop_updates", []), updated.get("stop_updates", [])
        if not _ordered_extension(old_stops, new_stops):
            raise ValueError("Supplement changed original stop values or order.")
        added += len(new_stops) - len(old_stops)
        added_r16 += sum(s.get("stop_id") == ADDED_STOP for s in new_stops) - sum(
            s.get("stop_id") == ADDED_STOP for s in old_stops)
    return {"additional_stop_updates": added, "additional_r16_stop_updates": added_r16}


def verify_daily_projection(previous_path, supplemental_path):
    before = (s for s in read_snapshots(previous_path) if s["feed_id"] == "nqrw")
    after = (s for s in read_snapshots(supplemental_path) if s["feed_id"] == "nqrw")
    totals = {"compared_captures": 0, "additional_stop_updates": 0, "additional_r16_stop_updates": 0}
    for old, new in zip_longest(before, after):
        if old is None or new is None or new["feed_id"] != "nqrw":
            raise ValueError("Supplement changed capture coverage or selected feed.")
        values = check_snapshot_extension(old, new)
        totals["compared_captures"] += 1
        for key, value in values.items():
            totals[key] += value
    return dict(totals, selected_captures_equal=True, raw_hashes_and_capture_metadata_equal=True,
                original_trip_metadata_and_stop_order_preserved=True, original_vehicle_observations_preserved=True)


def select_new_label_endpoints(trips, existing_labels):
    for identity, trip in trips.items():
        observed = set(trip.get("observed_stop_ids", []))
        allowed = {ADDED_STOP} if trip.get("route_id") == "R" else set()
        trip["observed_stop_ids"] = (observed & allowed) - set(existing_labels.get(identity, {}))


def build_additional_labels(trips, identity_days, original_days, archives, timezone):
    groups = defaultdict(dict)
    for identity, trip in trips.items():
        groups[trip.get("start_date") or "UNKNOWN"][identity] = trip
    receipts = DailyReceiptIndex(original_days, timezone)
    journals = [item for item in archives if item["kind"] == "csv"]
    result, quality, used = {}, {}, {}
    for service_date, subset in sorted(groups.items()):
        if not any(trip.get("observed_stop_ids") for trip in subset.values()):
            continue
        days = [day for identity in subset for day in identity_days[identity]]
        first = (date.fromisoformat(min(days)) - timedelta(days=1)).isoformat()
        last = (date.fromisoformat(max(days)) + timedelta(days=1)).isoformat()
        selected = [item for item in journals if first <= item["archive_date"] <= last]
        used.update({item["path"]: item for item in selected})
        labels, counts = build_labels(subset, [item["path"] for item in selected], receipts, {ADDED_STOP})
        if set(result) & set(labels):
            raise ValueError("Duplicate service-qualified identities in new endpoint labels.")
        result.update(labels)
        quality[service_date] = counts
    return result, quality, list(used.values())


def merge_label_additions(original, supplement):
    result = deepcopy(original)
    for identity, endpoints in supplement.items():
        target = result.setdefault(identity, {})
        for stop_id, value in endpoints.items():
            if (stop_id != ADDED_STOP or value.get("stop_id") != ADDED_STOP
                    or value.get("route_id") != "R" or value.get("feed_id") != "nqrw"):
                raise ValueError("Supplement contains an unexpected endpoint, route or feed.")
            if stop_id in target:
                raise ValueError("Supplement cannot overwrite an existing endpoint.")
            target[stop_id] = deepcopy(value)
    return result
