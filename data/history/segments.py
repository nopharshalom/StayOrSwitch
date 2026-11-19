"""Riding-time examples between adjacent selected stops in an observed pattern.

The CSV endpoints are final-prediction proxies, not physical arrivals. A segment
is one train's departure-to-arrival interval; it is not a passenger journey and
does not include waiting, walking, or transfers.
"""

from collections import Counter, defaultdict
from datetime import datetime
import hashlib

from .features import DEFAULT_ROUTES, LOCAL_ZONE, epoch, local_date, split_for_date


class SegmentBuilder:
    """Build sampled segment examples without using CSV outcomes as features."""

    def __init__(self, labels, *, route_ids=None, stop_ids=None,
                 horizon_seconds=1800, source_max_age_seconds=180):
        if horizon_seconds <= 0 or source_max_age_seconds < 0:
            raise ValueError("Horizon must be positive and source age nonnegative.")
        self.labels = labels
        self.route_ids = set(DEFAULT_ROUTES if route_ids is None else route_ids)
        self.stop_ids = None if stop_ids is None else set(stop_ids)
        self.horizon_seconds = horizon_seconds
        self.source_max_age_seconds = source_max_age_seconds
        self.counts = Counter()
        self.flags = Counter()
        self.by_date = defaultdict(Counter)
        self.by_route = defaultdict(Counter)
        self.by_day_type = defaultdict(Counter)
        self.last_capture = {}
        self.last_source = {}
        self.last_payload = {}
        self.unique_events = set()
        self.eligible_events = set()
        self.trip_splits = {}

    def _label(self, trip, origin, destination, capture, split, forecast):
        first = self.labels.lookup(trip, origin)
        last = self.labels.lookup(trip, destination)
        flags = ["ORIGIN_" + value for value in first["quality_flags"]
                 if value != "MISSING_CSV_ARRIVAL"]
        flags.extend("DESTINATION_" + value for value in last["quality_flags"])
        uid = first.get("source_trip_uid")
        source = self.labels.stops.get((uid, origin), {})
        target = self.labels.stops.get((last.get("source_trip_uid"), destination), {})
        try:
            departure = epoch(source.get("departure_time"))
        except (ValueError, TypeError):
            departure = None
            flags.append("INVALID_CSV_DEPARTURE")
        arrival = last.get("arrival_at")
        origin_arrival = first.get("arrival_at")
        try:
            destination_departure = epoch(target.get("departure_time"))
        except (ValueError, TypeError):
            destination_departure = None
            flags.append("INVALID_DESTINATION_CSV_DEPARTURE")
        if departure is not None and origin_arrival is not None and origin_arrival > departure:
            flags.append("ORIGIN_CSV_ARRIVAL_AFTER_DEPARTURE")
        if arrival is not None and destination_departure is not None and arrival > destination_departure:
            flags.append("DESTINATION_CSV_ARRIVAL_AFTER_DEPARTURE")
        if departure is None:
            flags.append("MISSING_CSV_DEPARTURE")
        if uid != last.get("source_trip_uid"):
            flags.append("CSV_ENDPOINT_TRIP_MISMATCH")
        origin_available = first.get("available_at")
        destination_available = last.get("available_at")
        for name, available in (("ORIGIN", origin_available), ("DESTINATION", destination_available)):
            if available is None:
                flags.append(name + "_LABEL_AVAILABILITY_MISSING")
            elif split_for_date(local_date(available)) != split:
                flags.append(name + "_LABEL_AVAILABILITY_SPLIT_BOUNDARY")
        if departure is not None:
            if departure <= capture:
                flags.append("ORIGIN_LABEL_NOT_AFTER_DECISION")
            if origin_available is not None and departure > origin_available:
                flags.append("CSV_DEPARTURE_AFTER_STOP_DISAPPEARANCE")
        duration = None
        if departure is not None and arrival is not None:
            if arrival < departure:
                flags.append("NEGATIVE_CSV_SEGMENT_DURATION")
            else:
                duration = arrival - departure
        if arrival is not None and arrival <= capture:
            flags.append("DESTINATION_LABEL_NOT_AFTER_DECISION")
        flags = sorted(set(flags))
        return {
            "method": "CSV_DEPARTURE_TO_ARRIVAL_PROXY",
            "physical_ground_truth": False,
            "source_trip_uid": uid,
            "departure_at": departure,
            "arrival_at": arrival,
            "duration_seconds": duration,
            "residual_seconds": duration - forecast if duration is not None else None,
            "origin_available_at": origin_available,
            "destination_available_at": destination_available,
            "quality_flags": flags,
            "usable_proxy": not flags,
        }

    def process(self, snapshot):
        """Accept one already parsed MTA snapshot with collector capture time."""
        self.counts["snapshots_seen"] += 1
        try:
            capture = epoch(snapshot.get("captured_at", snapshot.get("fetched_at")))
            source = epoch(snapshot.get("source_updated_at"))
            feed = snapshot["feed_id"]
        except (KeyError, TypeError, ValueError):
            self.counts["invalid_snapshot"] += 1
            return []
        if capture is None or source is None or snapshot.get("status", "AVAILABLE") != "AVAILABLE":
            self.counts["unavailable_snapshot"] += 1
            return []
        if capture <= self.last_capture.get(feed, -1):
            self.counts["duplicate_or_out_of_order_capture"] += 1
            return []
        self.last_capture[feed] = capture
        if not 0 <= capture - source <= self.source_max_age_seconds:
            self.counts["future_or_stale_source"] += 1
            return []
        if source < self.last_source.get(feed, -1):
            self.counts["source_time_regression"] += 1
            return []
        digest = snapshot.get("sha256")
        if digest and self.last_payload.get(feed) == (source, digest):
            self.counts["duplicate_source_payload"] += 1
            return []
        self.last_source[feed] = source
        self.last_payload[feed] = (source, digest)
        self.counts["snapshots_used"] += 1
        local = datetime.fromtimestamp(capture, LOCAL_ZONE)
        capture_date = local.date().isoformat()
        capture_split = split_for_date(capture_date)
        if capture_split is None:
            self.counts["capture_outside_window"] += 1
            return []
        day_type = "WEEKDAY" if local.weekday() < 5 else "SATURDAY" if local.weekday() == 5 else "SUNDAY"
        trips = snapshot.get("trips", [])
        identities = Counter(trip.get("id") for trip in trips)
        rows = []
        for trip in trips:
            identity = trip.get("id")
            if not identity or trip.get("route_id") not in self.route_ids:
                self.counts["unselected_or_unidentified_trip"] += 1
                continue
            if identities[identity] != 1:
                self.counts["duplicate_trip_entity"] += 1
                continue
            try:
                split = split_for_date(trip.get("start_date", ""))
                trip_stamp = epoch(trip.get("timestamp"))
            except (ValueError, TypeError):
                self.counts["invalid_trip_metadata"] += 1
                continue
            if split != capture_split:
                self.counts["trip_capture_split_boundary"] += 1
                continue
            if trip_stamp is not None and not 0 <= capture - trip_stamp <= self.source_max_age_seconds:
                self.counts["future_or_stale_trip_timestamp"] += 1
                continue
            if trip.get("schedule_relationship") in ("CANCELED", "DELETED"):
                self.counts["canceled_trip"] += 1
                continue
            stops = trip.get("stop_updates", [])
            pattern = [stop.get("stop_id") for stop in stops]
            if any(value is None for value in pattern) or len(set(pattern)) != len(pattern):
                self.counts["missing_or_repeated_stop"] += 1
                continue
            selected = [(index, stop) for index, stop in enumerate(stops)
                        if self.stop_ids is None or stop["stop_id"] in self.stop_ids]
            for (first_index, first), (last_index, last) in zip(selected, selected[1:]):
                if any(stop.get("schedule_relationship") in ("SKIPPED", "NO_DATA") for stop in (first, last)):
                    self.counts["skipped_or_no_data_endpoint"] += 1
                    continue
                try:
                    departure = epoch(first.get("departure_time"))
                    departure_basis = "DEPARTURE_PREDICTION"
                    if departure is None:
                        departure = epoch(first.get("arrival_time"))
                        departure_basis = "ARRIVAL_AS_DEPARTURE_PROXY"
                    arrival = epoch(last.get("arrival_time"))
                except (TypeError, ValueError):
                    self.counts["invalid_endpoint_prediction"] += 1
                    continue
                if departure is None or arrival is None:
                    self.counts["missing_endpoint_prediction"] += 1
                    continue
                if not capture <= departure <= arrival <= capture + self.horizon_seconds:
                    self.counts["outside_horizon_or_negative_prediction"] += 1
                    continue
                forecast = arrival - departure
                origin, destination = first["stop_id"], last["stop_id"]
                label = self._label(trip, origin, destination, capture, split, forecast)
                eligible = label["usable_proxy"]
                features = {
                    "feed_id": feed, "route_id": trip["route_id"],
                    "direction": trip.get("nyct_direction") or trip.get("direction_id"),
                    "gtfs_direction_id": trip.get("direction_id"),
                    "from_stop_id": origin, "to_stop_id": destination,
                    "service_date": datetime.strptime(trip["start_date"], "%Y%m%d").date().isoformat(),
                    "decision_local_date": capture_date, "day_type": day_type,
                    "day_of_week": local.weekday(),
                    "seconds_since_local_midnight": local.hour * 3600 + local.minute * 60 + local.second,
                    "mta_departure_at": departure, "mta_arrival_at": arrival,
                    "origin_prediction_basis": departure_basis,
                    "predicted_duration_seconds": forecast,
                    "departure_horizon_seconds": departure - capture,
                    "arrival_horizon_seconds": arrival - capture,
                    "feed_age_seconds": capture - source,
                    "trip_update_age_seconds": capture - trip_stamp if trip_stamp is not None else None,
                    "segment_stop_pattern": pattern[first_index:last_index + 1],
                    "remaining_stop_pattern": pattern,
                    "service_alerts_available": False,
                    "is_assigned": trip.get("is_assigned"),
                }
                key = (identity, origin, destination)
                identifier = "|".join((identity, origin, destination, str(capture)))
                rows.append({
                    "schema_version": "historical-segment-v1",
                    "example_id": hashlib.sha256(identifier.encode()).hexdigest()[:24],
                    "trip_identity": identity, "from_stop_id": origin, "to_stop_id": destination,
                    "decision_at": capture, "source_updated_at": source, "split": split,
                    "features": features, "label": label, "eligible_for_training": bool(eligible),
                    "provenance": {"archive_member": snapshot.get("member_name", snapshot.get("member")),
                                   "capture_time_basis": "ARCHIVE_COLLECTOR_TIMESTAMP",
                                   "raw_trip_id": trip.get("trip_id"),
                                   "nyct_train_id": trip.get("nyct_train_id"),
                                   "label_source": "SUBWAY_DATA_NYC_CSV_JOURNAL"},
                })
                self.counts["rows"] += 1
                status = "eligible_proxy_rows" if eligible else "ineligible_proxy_rows"
                self.counts[status] += 1
                if departure_basis == "ARRIVAL_AS_DEPARTURE_PROXY":
                    self.counts["origin_arrival_prediction_proxy_rows"] += 1
                for grouping, group in ((self.by_date, capture_date), (self.by_route, trip["route_id"]), (self.by_day_type, day_type)):
                    grouping[group]["rows"] += 1
                    grouping[group][status] += 1
                self.flags.update(label["quality_flags"])
                self.unique_events.add(key)
                if eligible:
                    self.eligible_events.add(key)
                previous_split = self.trip_splits.setdefault(identity, split)
                if previous_split != split:
                    raise AssertionError("A trip cannot appear in multiple evaluation splits.")
        return rows

    def report(self):
        return {
            "schema_version": "historical-segment-v1", "counts": dict(self.counts),
            "unique_trips": len(self.trip_splits), "unique_segment_events": len(self.unique_events),
            "unique_eligible_segment_events": len(self.eligible_events),
            "trip_split_counts": dict(Counter(self.trip_splits.values())),
            "by_date": {key: dict(value) for key, value in sorted(self.by_date.items())},
            "by_route": {key: dict(value) for key, value in sorted(self.by_route.items())},
            "by_day_type": {key: dict(value) for key, value in sorted(self.by_day_type.items())},
            "label_quality_flags": dict(self.flags),
            "policy": {"selection": "ADJACENT_TARGET_STOPS_IN_CURRENT_REMAINING_PATTERN",
                       "horizon_seconds": self.horizon_seconds,
                       "label_method": "CSV_DEPARTURE_TO_ARRIVAL_PROXY",
                       "physical_ground_truth": False,
                       "includes_waiting_walking_or_transfers": False,
                       "origin_prediction_fallback": "ARRIVAL_AS_DEPARTURE_PROXY_EXPLICITLY_MARKED"},
        }
