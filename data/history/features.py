"""As-of train-arrival examples and explicitly inferred archive labels.

The input feature object never contains CSV journal outcomes. CSV journals use
the last arrival prediction, so these labels cannot establish physical accuracy.
"""

from collections import Counter, OrderedDict, defaultdict, deque
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
import hashlib
import math
import re
from zoneinfo import ZoneInfo

from google.protobuf.message import DecodeError
from stayorswitch import mta


LOCAL_ZONE = ZoneInfo("America/New_York")
SPLITS = {
    "train": ("2026-11-02", "2026-11-08"),
    "validation": ("2026-11-09", "2026-11-11"),
    "test": ("2026-11-12", "2026-11-15"),
}
DEFAULT_ROUTES = ("A", "C", "E", "B", "D", "F", "FX", "M", "G",
                  "N", "Q", "R", "W", "7", "7X")
SCHEMA_VERSION = "historical-arrival-v1"


def epoch(value):
    """Parse a timestamp without silently assigning a local timezone."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Timestamp requires a timezone.")
        number = value.timestamp()
    else:
        try:
            number = float(value)
        except ValueError:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Timestamp requires a timezone.")
            number = parsed.timestamp()
    if not math.isfinite(number) or number < 0:
        raise ValueError("Timestamp must be finite and nonnegative.")
    return int(number) if number.is_integer() else number


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


@lru_cache(maxsize=65536)
def local_date(value):
    return datetime.fromtimestamp(value, LOCAL_ZONE).date().isoformat()


@lru_cache(maxsize=128)
def split_for_date(value):
    value = str(value)
    if len(value) == 8 and value.isdigit():
        value = datetime.strptime(value, "%Y%m%d").date().isoformat()
    date.fromisoformat(value)
    return next((name for name, (start, end) in SPLITS.items() if start <= value <= end), None)


def source_trip_uid(trip):
    """Reconstruct the documented CSV UID from an explicit service date.

    The publisher's journal parses the service-date identifier at UTC midnight
    and adds the NYCT trip-ID offset. This reproduces its CSV identity, not the
    physical departure time. In particular, 24+ hour IDs can have a CSV start_time
    later than their observations. See jamespfennell/gtfs journal/journal.go,
    realtime.go, and extensions/nycttrips/nycttrips.go.
    """
    return _source_trip_uid(trip.get("trip_id") or "", trip.get("start_date"))


@lru_cache(maxsize=32768)
def _source_trip_uid(trip_id, service_date):
    match = re.fullmatch(r"([0-9]{6})(_.+)", trip_id)
    if not match or not service_date:
        return None
    try:
        day = datetime.strptime(service_date, "%Y%m%d").date()
    except (TypeError, ValueError):
        return None
    origin = datetime.combine(day, time(), timezone.utc) + timedelta(seconds=int(match[1]) * 6 // 10)
    origin_epoch = origin.timestamp()
    if not origin_epoch.is_integer():
        return None
    return str(int(origin_epoch)) + match[2]


class LabelIndex:
    """Journal labels keyed by the source's service-qualified trip UID and stop."""

    def __init__(self, trip_rows=(), stop_rows=(), *, cache_size=100000):
        if cache_size < 0:
            raise ValueError("Label cache size must be nonnegative.")
        self.trips = {}
        self.stops = {}
        self.counts = Counter()
        self.conflicting_trips = set()
        self.conflicting_stops = set()
        self._label_cache = OrderedDict()
        self.cache_size = cache_size
        for row in trip_rows:
            self.add_trip(row)
        for row in stop_rows:
            self.add_stop(row)

    def add_trip(self, row):
        self.cache_clear()
        value = dict(row)
        uid = value.get("trip_uid")
        if not uid:
            self.counts["trip_rows_missing_uid"] += 1
            return
        old = self.trips.get(uid)
        if old is not None:
            if old == value:
                self.counts["identical_trip_duplicates"] += 1
            else:
                self.conflicting_trips.add(uid)
                self.counts["conflicting_trip_duplicates"] += 1
            return
        self.trips[uid] = value
        self.counts["trip_rows"] += 1

    def add_stop(self, row):
        self.cache_clear()
        value = dict(row)
        key = (value.get("trip_uid"), value.get("stop_id"))
        if not all(key):
            self.counts["stop_rows_missing_identity"] += 1
            return
        old = self.stops.get(key)
        if old is not None:
            if old == value:
                self.counts["identical_stop_duplicates"] += 1
            else:
                self.conflicting_stops.add(key)
                self.counts["conflicting_stop_duplicates"] += 1
            return
        self.stops[key] = value
        self.counts["stop_rows"] += 1

    def lookup(self, trip, stop_id):
        """Return an isolated mutable label, caching only immutable base values."""
        key = (trip.get("route_id"), trip.get("trip_id"), trip.get("start_date"), stop_id)
        cached = self._label_cache.get(key)
        if cached is None:
            cached = self._lookup_uncached(trip, stop_id)
            cached["quality_flags"] = tuple(cached["quality_flags"])
            if self.cache_size:
                self._label_cache[key] = cached
                if len(self._label_cache) > self.cache_size:
                    self._label_cache.popitem(last=False)
        elif self.cache_size:
            self._label_cache.move_to_end(key)
        result = dict(cached)
        result["quality_flags"] = list(cached["quality_flags"])
        return result

    def cache_clear(self):
        """Invalidate cached labels after journal records change."""
        self._label_cache.clear()

    def _lookup_uncached(self, trip, stop_id):
        uid = source_trip_uid(trip)
        journal_trip = self.trips.get(uid)
        journal_stop = self.stops.get((uid, stop_id))
        result = {
            "method": "CSV_LAST_PREDICTION_PROXY", "physical_ground_truth": False,
            "source_trip_uid": uid, "arrival_at": None, "available_at": None,
            "available_at_basis": "JOURNAL_SOURCE_TIMESTAMP_NOT_RECEIPT",
            "residual_seconds": None, "quality_flags": [], "usable_proxy": False,
        }
        flags = result["quality_flags"]
        if uid is None:
            flags.append("UNRESOLVED_SOURCE_TRIP_UID")
        elif journal_trip is None or journal_stop is None:
            flags.append("MISSING_CSV_LABEL")
        if uid in self.conflicting_trips or (uid, stop_id) in self.conflicting_stops:
            flags.append("AMBIGUOUS_CSV_LABEL")
        if not journal_trip or not journal_stop:
            return result
        if journal_trip.get("route_id") != trip.get("route_id"):
            flags.append("CSV_ROUTE_MISMATCH")
        if journal_trip.get("trip_id") != trip.get("trip_id"):
            flags.append("CSV_TRIP_ID_MISMATCH")
        for field, changed_flag in (("num_schedule_changes", "CSV_SCHEDULE_CHANGED"),
                                    ("num_schedule_rewrites", "CSV_SCHEDULE_REWRITTEN")):
            raw_count = journal_trip.get(field)
            if raw_count is None or raw_count == "":
                if "MISSING_CSV_SCHEDULE_HISTORY" not in flags:
                    flags.append("MISSING_CSV_SCHEDULE_HISTORY")
                continue
            try:
                count = int(raw_count)
                if isinstance(raw_count, bool) or count < 0 or str(count) != str(raw_count):
                    raise ValueError("Invalid journal count.")
            except (ValueError, TypeError):
                if "INVALID_CSV_SCHEDULE_HISTORY" not in flags:
                    flags.append("INVALID_CSV_SCHEDULE_HISTORY")
                continue
            if count:
                flags.append(changed_flag)
        try:
            arrival = epoch(journal_stop.get("arrival_time"))
            observed = epoch(journal_stop.get("last_observed"))
            passed = epoch(journal_stop.get("marked_past"))
        except (ValueError, TypeError):
            flags.append("INVALID_CSV_TIMESTAMP")
            return result
        result.update(arrival_at=arrival, available_at=passed,
                      stop_last_observed_at=observed,
                      observation_gap_seconds=(passed - observed if passed is not None and observed is not None else None))
        if arrival is None:
            flags.append("MISSING_CSV_ARRIVAL")
        if passed is None or observed is None:
            flags.append("MISSING_STOP_PASSAGE_CONFIRMATION")
        elif passed < observed:
            flags.append("INVALID_STOP_PASSAGE_ORDER")
        elif passed - observed > 180:
            flags.append("LARGE_STOP_OBSERVATION_GAP")
        if arrival is not None and passed is not None and arrival > passed:
            flags.append("PREDICTED_ARRIVAL_AFTER_STOP_DISAPPEARANCE")
        result["usable_proxy"] = not flags
        return result

    def report(self):
        return dict(self.counts, unique_trips=len(self.trips), unique_stop_events=len(self.stops),
                    conflicting_trips=len(self.conflicting_trips), conflicting_stop_events=len(self.conflicting_stops))


class FeatureBuilder:
    """Build examples from monotonically captured snapshots for each feed.

    `sample_seconds` belongs to the archive reader. This builder never infers
    missing observations between samples. It uses only prior sampled updates for
    revision features and retains unusable label rows for coverage reporting.
    """

    def __init__(self, labels, *, route_ids=None, stop_ids=None, horizon_seconds=1800,
                 source_max_age_seconds=180):
        if horizon_seconds <= 0 or source_max_age_seconds < 0:
            raise ValueError("Horizon must be positive and maximum source age nonnegative.")
        self.labels = labels
        self.route_ids = set(DEFAULT_ROUTES if route_ids is None else route_ids)
        self.stop_ids = None if stop_ids is None else set(stop_ids)
        self.horizon_seconds = horizon_seconds
        self.source_max_age_seconds = source_max_age_seconds
        self.counts = Counter()
        self.by_date = defaultdict(Counter)
        self.by_route = defaultdict(Counter)
        self.by_day_type = defaultdict(Counter)
        self.label_flags = Counter()
        self.unique_trips = set()
        self.unique_events = set()
        self.eligible_events = set()
        self.trip_splits = {}
        self.previous = {}
        self.trip_patterns = {}
        self.last_capture = {}
        self.last_source = {}
        self._seen_payloads = {}

    def _parse(self, snapshot):
        capture = epoch(snapshot.get("captured_at", snapshot.get("fetched_at")))
        if capture is None:
            raise ValueError("A historical collector capture timestamp is required.")
        feed_id = snapshot["feed_id"]
        if "payload" in snapshot:
            parsed = mta.parse_train_feed(snapshot["payload"], feed_id, iso(capture))
        else:
            parsed = snapshot
        return parsed, feed_id, capture

    def process(self, snapshot):
        self.counts["snapshots_seen"] += 1
        try:
            parsed, feed_id, capture = self._parse(snapshot)
            source = epoch(parsed.get("source_updated_at"))
        except (ValueError, TypeError, KeyError, DecodeError):
            self.counts["invalid_snapshot"] += 1
            return []
        if parsed.get("status", "AVAILABLE") != "AVAILABLE":
            self.counts["unavailable_snapshot"] += 1
            return []
        previous_capture = self.last_capture.get(feed_id)
        if previous_capture is not None and capture <= previous_capture:
            self.counts["duplicate_or_out_of_order_capture"] += 1
            return []
        self.last_capture[feed_id] = capture
        if source is None or source > capture:
            self.counts["missing_or_future_source"] += 1
            return []
        if capture - source > self.source_max_age_seconds:
            self.counts["stale_source"] += 1
            return []
        if source < self.last_source.get(feed_id, 0):
            self.counts["source_time_regression"] += 1
            return []
        digest = parsed.get("sha256")
        if digest and self._seen_payloads.get(feed_id) == (source, digest):
            self.counts["duplicate_source_payload"] += 1
            return []
        self._seen_payloads[feed_id] = (source, digest)
        self.last_source[feed_id] = source
        self.counts["snapshots_used"] += 1
        local = datetime.fromtimestamp(capture, LOCAL_ZONE)
        day_type = ("WEEKDAY", "SATURDAY", "SUNDAY")[0 if local.weekday() < 5 else local.weekday() - 4]
        capture_date = local.date().isoformat()
        capture_split = split_for_date(capture_date)
        if capture_split is None:
            self.counts["capture_outside_window"] += 1
            return []
        vehicles = {vehicle.get("trip_identity"): vehicle for vehicle in parsed.get("vehicles", [])
                    if vehicle.get("trip_identity")}
        trips = []
        headways = defaultdict(list)
        identity_counts = Counter(trip.get("id") for trip in parsed.get("trips", []))
        for trip in parsed.get("trips", []):
            identity = trip.get("id")
            if not identity or trip.get("route_id") not in self.route_ids:
                self.counts["unselected_or_unidentified_trip"] += 1
                continue
            if identity_counts[identity] > 1:
                self.counts["duplicate_trip_entity"] += 1
                continue
            try:
                trip_split = split_for_date(trip.get("start_date", ""))
                trip_stamp = epoch(trip.get("timestamp"))
            except (ValueError, TypeError):
                self.counts["invalid_trip_metadata"] += 1
                continue
            if trip_split != capture_split:
                self.counts["trip_capture_split_boundary"] += 1
                continue
            if trip_stamp is not None and (trip_stamp > capture or capture - trip_stamp > self.source_max_age_seconds):
                self.counts["future_or_stale_trip_timestamp"] += 1
                continue
            if trip.get("schedule_relationship") in ("CANCELED", "DELETED"):
                self.counts["canceled_trip"] += 1
                continue
            stop_counts = Counter(stop.get("stop_id") for stop in trip.get("stop_updates", []))
            stops = []
            for stop in trip.get("stop_updates", []):
                stop_id = stop.get("stop_id")
                if not stop_id or stop_counts[stop_id] > 1:
                    self.counts["missing_or_repeated_stop"] += 1
                    continue
                if stop.get("schedule_relationship") in ("SKIPPED", "NO_DATA"):
                    self.counts["skipped_or_no_data_stop"] += 1
                    continue
                arrival = stop.get("arrival_time")
                if arrival is None:
                    self.counts["missing_arrival_prediction"] += 1
                    continue
                if self.stop_ids is not None and stop_id not in self.stop_ids:
                    self.counts["unselected_stop"] += 1
                    continue
                if arrival >= capture:
                    headways[(trip["route_id"], stop_id)].append((arrival, identity))
                stops.append(stop)
            trips.append((trip, stops, trip_split))
        headway_values = {}
        for (_, stop_id), entries in headways.items():
            ordered = sorted(entries)
            for index, (arrival, identity) in enumerate(ordered):
                # This is the gap between forecast arrivals, not observed service frequency.
                headway_values[(identity, stop_id, arrival)] = (
                    arrival - ordered[index - 1][0] if index else None,
                    ordered[index + 1][0] - arrival if index + 1 < len(ordered) else None)
        rows = []
        for trip, stops, split in trips:
            identity = trip["id"]
            service_date = trip["start_date"]
            service_date_iso = service_date[:4] + "-" + service_date[4:6] + "-" + service_date[6:8]
            pattern = tuple(stop.get("stop_id") for stop in trip.get("stop_updates", []) if stop.get("stop_id"))
            old_pattern = self.trip_patterns.get(identity)
            # Normal progress removes a prefix; only a non-suffix change is evidence of a change.
            pattern_changed = (old_pattern is not None and pattern != old_pattern
                               and not any(old_pattern[index:] == pattern for index in range(len(old_pattern) + 1)))
            self.trip_patterns[identity] = pattern
            vehicle = vehicles.get(identity, {})
            vehicle_stamp = vehicle.get("timestamp")
            if vehicle_stamp is not None and vehicle_stamp > capture:
                self.counts["future_vehicle_observation"] += 1
                vehicle = {}
                vehicle_stamp = None
            for stop in stops:
                stop_id = stop["stop_id"]
                arrival = stop["arrival_time"]
                event_key = (identity, stop_id)
                history = self.previous.setdefault(event_key, deque())
                while history and capture - history[0][0] > 600:
                    history.popleft()
                previous = history[-1] if history else None
                delta = arrival - previous[1] if previous else None
                elapsed = capture - previous[0] if previous else None
                revision_count = sum(history[index][1] != history[index - 1][1] for index in range(1, len(history)))
                if previous and arrival != previous[1]:
                    revision_count += 1
                history.append((capture, arrival))
                horizon = arrival - capture
                if not 0 <= horizon <= self.horizon_seconds:
                    self.counts["outside_prediction_horizon"] += 1
                    continue
                label = self.labels.lookup(trip, stop_id)
                eligible = label["usable_proxy"]
                flags = label["quality_flags"]
                if label["arrival_at"] is not None:
                    label["residual_seconds"] = label["arrival_at"] - arrival
                    if label["arrival_at"] <= capture:
                        flags.append("LABEL_NOT_AFTER_DECISION")
                        eligible = False
                if label["available_at"] is not None and split_for_date(local_date(label["available_at"])) != split:
                    flags.append("LABEL_AVAILABILITY_SPLIT_BOUNDARY")
                    eligible = False
                prior_gap, next_gap = headway_values.get((identity, stop_id, arrival), (None, None))
                direction = trip.get("nyct_direction")
                direction_source = "NYCT_DESCRIPTOR" if direction is not None else "UNKNOWN"
                if direction is None and stop_id.endswith(("N", "S")):
                    direction = "NORTH" if stop_id.endswith("N") else "SOUTH"
                    direction_source = "PLATFORM_SUFFIX"
                features = {
                    "route_id": trip["route_id"], "feed_id": feed_id,
                    "stop_id": stop_id, "direction": direction,
                    "direction_source": direction_source, "gtfs_direction_id": trip.get("direction_id"),
                    "service_date": service_date_iso,
                    "decision_local_date": capture_date, "day_type": day_type,
                    "day_of_week": local.weekday(), "seconds_since_local_midnight": local.hour * 3600 + local.minute * 60 + local.second,
                    "mta_arrival_at": arrival, "prediction_horizon_seconds": horizon,
                    "feed_age_seconds": capture - source,
                    "trip_update_age_seconds": capture - trip["timestamp"] if trip.get("timestamp") is not None else None,
                    "previous_prediction_delta_seconds": delta,
                    "seconds_since_previous_prediction": elapsed,
                    "prediction_revisions_last_10_minutes": revision_count,
                    "sampled_updates_last_10_minutes": len(history),
                    "forecast_gap_to_previous_train_seconds": prior_gap,
                    "forecast_gap_to_next_train_seconds": next_gap,
                    "vehicle_stop_id": vehicle.get("stop_id"), "vehicle_status": vehicle.get("current_status"),
                    "vehicle_observation_age_seconds": capture - vehicle_stamp if vehicle_stamp is not None else None,
                    "is_assigned": trip.get("is_assigned"),
                    "remaining_stop_pattern": list(pattern),
                    "remaining_stop_pattern_changed": pattern_changed,
                    "scheduled_track": stop.get("scheduled_track"), "actual_track": stop.get("actual_track"),
                    "service_alerts_available": False, "service_alert_count": None,
                }
                row = {"schema_version": SCHEMA_VERSION,
                       "example_id": hashlib.sha256((identity + "|" + stop_id + "|" + str(capture)).encode()).hexdigest()[:24],
                       "trip_identity": identity, "stop_id": stop_id,
                       "decision_at": capture, "source_updated_at": source, "split": split,
                       "features": features, "label": label, "eligible_for_training": bool(eligible),
                       "provenance": {"archive_member": snapshot.get("member_name", snapshot.get("member")),
                                      "raw_trip_id": trip.get("trip_id"),
                                      "nyct_train_id": trip.get("nyct_train_id"),
                                      "capture_time_basis": "ARCHIVE_COLLECTOR_TIMESTAMP",
                                      "label_source": "SUBWAY_DATA_NYC_CSV_JOURNAL"}}
                rows.append(row)
                self.counts["rows"] += 1
                self.counts["eligible_proxy_rows" if eligible else "ineligible_proxy_rows"] += 1
                for grouping, key in ((self.by_date, capture_date), (self.by_route, trip["route_id"]), (self.by_day_type, day_type)):
                    grouping[key]["rows"] += 1
                    grouping[key]["eligible_proxy_rows" if eligible else "ineligible_proxy_rows"] += 1
                self.label_flags.update(flags)
                self.unique_trips.add(identity)
                self.unique_events.add(event_key)
                if eligible:
                    self.eligible_events.add(event_key)
                previous_split = self.trip_splits.setdefault(identity, split)
                if previous_split != split:
                    raise AssertionError("A trip cannot appear in multiple evaluation splits.")
        # Old event history is only needed for recent revisions. Prune each hour.
        if self.counts["snapshots_used"] % 60 == 0:
            self.previous = {key: history for key, history in self.previous.items()
                             if history and capture - history[-1][0] <= 600}
        return rows

    def report(self):
        return {"schema_version": SCHEMA_VERSION, "counts": dict(self.counts),
                "unique_trips": len(self.unique_trips), "unique_stop_events": len(self.unique_events),
                "unique_eligible_stop_events": len(self.eligible_events),
                "by_date": {key: dict(value) for key, value in sorted(self.by_date.items())},
                "by_route": {key: dict(value) for key, value in sorted(self.by_route.items())},
                "by_day_type": {key: dict(value) for key, value in sorted(self.by_day_type.items())},
                "label_quality_flags": dict(self.label_flags),
                "trip_split_counts": dict(Counter(self.trip_splits.values())),
                "policy": {"horizon_seconds": self.horizon_seconds,
                           "source_max_age_seconds": self.source_max_age_seconds,
                           "selected_route_ids": sorted(self.route_ids),
                           "selected_stop_ids": sorted(self.stop_ids) if self.stop_ids is not None else None,
                           "splits": SPLITS, "timezone": "America/New_York",
                           "label_method": "CSV_LAST_PREDICTION_PROXY",
                           "physical_ground_truth": False,
                           "service_alerts": "NOT_JOINED_YET",
                           "revision_window_seconds": 600,
                           "headway_method": "WITHIN_SNAPSHOT_FORECAST_ARRIVAL_GAPS"}}
