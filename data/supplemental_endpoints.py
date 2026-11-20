"""Add outcome endpoints without changing the frozen October source artifacts."""

from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

from data.october.labels import build_labels, source_trip_uid
from data.october.prepare import DailyReceiptIndex
from data.october.sources import read_labels, read_snapshots


def merge_trip_inventory(day_reports, root):
    """Match the original full-month identity merge and cross-date UID checks."""
    trips, identity_days = {}, defaultdict(list)
    for report in day_reports:
        day_trips = read_labels(Path(root) / report["outputs"]["trips"]["path"])
        for identity, value in day_trips.items():
            identity_days[identity].append(report["date"])
            if identity not in trips:
                trips[identity] = deepcopy(value)
                trips[identity]["observed_stop_ids"] = set(value["observed_stop_ids"])
                continue
            old = trips[identity]
            old["identity_conflict"] |= value.get("identity_conflict", False) or any(
                old.get(key) != value.get(key)
                for key in ("trip_id", "route_id", "feed_id", "start_date", "start_time"))
            for key in ("direction_id", "nyct_direction", "schedule_relationship"):
                if old.get(key) is not None and value.get(key) is not None and old[key] != value[key]:
                    old["identity_conflict"] = True
                elif old.get(key) is None:
                    old[key] = value.get(key)
            old["observed_stop_ids"].update(value["observed_stop_ids"])
    uid_identities = defaultdict(set)
    for trip in trips.values():
        uid = source_trip_uid(trip)
        if uid is not None:
            uid_identities[uid].add(tuple(trip.get(key) for key in
                                          ("feed_id", "start_date", "route_id", "trip_id")))
    for trip in trips.values():
        if len(uid_identities.get(source_trip_uid(trip), set())) > 1:
            trip["identity_conflict"] = True
    return trips, dict(identity_days)


def collect_observed_stop(path, stop_id):
    """A CSV endpoint alone does not establish an observed prediction endpoint."""
    identities = set()
    for snapshot in read_snapshots(path):
        for trip in snapshot.get("trips", []):
            if trip.get("id") and any(stop.get("stop_id") == stop_id
                                      for stop in trip.get("stop_updates", [])):
                identities.add(trip["id"])
    return identities


def mark_supplemental_observations(trips, observed_ids, stop_id):
    """Retain every identity for collision checks; add only observed new stops."""
    if not set(observed_ids).issubset(trips):
        raise ValueError("Supplemental stop observation lacks an original trip identity.")
    for identity, trip in trips.items():
        trip["observed_stop_ids"] = {stop_id} if identity in observed_ids else set()


def build_supplemental_labels(trips, identity_days, day_reports, archives, timezone, stop_id):
    """Use unchanged endpoint rules and the original service-date journal windows."""
    groups = defaultdict(dict)
    for identity, trip in trips.items():
        groups[trip.get("start_date") or "UNKNOWN"][identity] = trip
    receipts = DailyReceiptIndex(day_reports, timezone)
    journals = [item for item in archives if item["kind"] == "csv"]
    result, quality, used_journals = {}, {}, {}
    for service_date, subset in sorted(groups.items()):
        if not any(stop_id in trip["observed_stop_ids"] for trip in subset.values()):
            continue
        observed_days = [day for identity in subset for day in identity_days[identity]]
        first = (date.fromisoformat(min(observed_days)) - timedelta(days=1)).isoformat()
        last = (date.fromisoformat(max(observed_days)) + timedelta(days=1)).isoformat()
        selected = [item for item in journals if first <= item["archive_date"] <= last]
        for item in selected:
            used_journals[item["path"]] = item
        labels, counts = build_labels(subset, [item["path"] for item in selected], receipts, {stop_id})
        if set(result) & set(labels):
            raise ValueError("Supplemental labels duplicate service-qualified identities.")
        result.update(labels)
        quality[service_date] = counts
    return result, quality, list(used_journals.values())


def merge_endpoint_labels(original, supplement, stop_id):
    """Return a copy, refusing any overwrite of an already-present endpoint."""
    result = deepcopy(original)
    for identity, endpoints in supplement.items():
        if set(endpoints) != {stop_id}:
            raise ValueError("Supplement contains an unexpected endpoint.")
        target = result.setdefault(identity, {})
        if stop_id in target:
            raise ValueError("Supplement cannot overwrite an existing endpoint.")
        target[stop_id] = deepcopy(endpoints[stop_id])
    return result
