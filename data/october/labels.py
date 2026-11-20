"""Separate journal outcome labels from archived decision-time observations.

CSV journal IDs encode UTC-based source identifiers, not local departure times.
Only a later archived receipt can establish when an inferred outcome was
available. Neither a future journal outcome nor its quality flags is a feature.
"""

from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
import math
import re
from urllib.parse import quote


def timestamp(value):
    """Parse a nonnegative timestamp without assigning a timezone implicitly."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean values are not timestamps.")
    if isinstance(value, (float, int)):
        number = float(value)
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Timestamp requires an explicit timezone.")
            number = parsed.timestamp()
    if not math.isfinite(number) or number < 0:
        raise ValueError("Timestamp must be finite and nonnegative.")
    return int(number) if number.is_integer() else number


def source_trip_uid(trip):
    """Reconstruct the publisher's opaque UTC-based service-qualified CSV UID."""
    match = re.fullmatch(r"([0-9]{6})(_.+)", str(trip.get("trip_id") or ""))
    service_date = trip.get("start_date")
    if not match or not isinstance(service_date, str) or not re.fullmatch(r"\d{8}", service_date):
        return None
    try:
        origin = datetime.strptime(service_date, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    # The archive publisher truncates the tenths-of-a-minute offset to seconds.
    seconds = int(origin.timestamp()) + int(match.group(1)) * 6 // 10
    return str(seconds) + match.group(2)


def canonical_event_trip_id(trip):
    """Identify one encoded-start service run independently of start-time jitter.

    The publisher joins these runs through the encoded raw trip ID and service
    date. Keep the actual feed and route in the identity: different services
    must not share support or outcome labels merely because their CSV UID does.
    This helper uses observation metadata only and is safe for split inventory.
    """
    values = [trip.get(name) for name in ("feed_id", "start_date", "route_id", "trip_id")]
    if source_trip_uid(trip) is None or any(not isinstance(value, str) or not value for value in values):
        return None
    return "MTA_EVENT:" + ":".join(quote(value, safe="") for value in values)


def _identity_flags(trip):
    flags = []
    raw = re.fullmatch(r"[0-9]{6}_([^_.]+)\.\.([NS]).*", str(trip.get("trip_id") or ""))
    if raw is None:
        flags.append("UNRECOGNIZED_ENCODED_TRIP_IDENTITY")
    else:
        # Express service descriptors use the base line in their encoded raw
        # IDs (observed in October input feeds). Keep the actual express route
        # in canonical identities; this is only raw-suffix validation.
        encoded_route = {"FX": "F", "7X": "7"}.get(trip.get("route_id"), trip.get("route_id"))
        if raw.group(1) != encoded_route:
            flags.append("RAW_TRIP_ROUTE_MISMATCH")
        cardinal = {"NORTH": "N", "SOUTH": "S"}.get(trip.get("nyct_direction"))
        if cardinal is not None and cardinal != raw.group(2):
            flags.append("RAW_TRIP_DIRECTION_MISMATCH")
    if canonical_event_trip_id(trip) is None:
        flags.append("UNRESOLVED_CANONICAL_TRIP_IDENTITY")
    if trip.get("schedule_relationship") in {"ADDED", "UNSCHEDULED", "DUPLICATED"}:
        flags.append("AMBIGUOUS_UNSCHEDULED_TRIP_IDENTITY")
    return flags


class ReceiptIndex:
    """Find the first archived receipt confirming a journal source timestamp."""

    def __init__(self, receipts):
        self.values = {}
        for feed_id, records in receipts.items():
            sources_by_capture = {}
            for record in records:
                if isinstance(record, dict):
                    if record.get("status", "AVAILABLE") not in {"AVAILABLE", "FRESH"}:
                        continue
                    capture = record.get("captured_at", record.get("fetched_at"))
                    source = record.get("source_updated_at", record.get("source_at"))
                else:
                    capture, source = record
                try:
                    capture, source = timestamp(capture), timestamp(source)
                except (ValueError, TypeError, OverflowError):
                    continue
                if capture is None or source is None or source > capture:
                    continue
                sources_by_capture.setdefault(capture, set()).add(source)
            captures, maxima = [], []
            maximum = -1
            for capture, sources in sorted(sources_by_capture.items()):
                if len(sources) != 1:
                    continue
                maximum = max(maximum, next(iter(sources)))
                captures.append(capture)
                maxima.append(maximum)
            self.values[feed_id] = captures, maxima

    def confirm(self, feed_id, available_at):
        if available_at is None:
            return None
        captures, maxima = self.values.get(feed_id, ([], []))
        # Source timestamps have one-second precision. Require a subsequent
        # source update, rather than equating an identical timestamp with receipt
        # of the journal's post-stop state.
        index = bisect_right(maxima, available_at)
        return captures[index] if index < len(captures) else None


def _csv_rows(path, kind):
    from .sources import iter_csv_rows
    return iter_csv_rows(path, kind)


def _schedule_flags(journal_trip):
    flags = []
    for key, changed in (("num_schedule_changes", "CSV_SCHEDULE_CHANGED"),
                         ("num_schedule_rewrites", "CSV_SCHEDULE_REWRITTEN")):
        value = journal_trip.get(key)
        if value is None or value == "":
            flags.append("MISSING_CSV_SCHEDULE_HISTORY")
            continue
        try:
            count = int(value)
            if isinstance(value, bool) or count < 0 or str(count) != str(value):
                raise ValueError("Invalid count.")
        except (ValueError, TypeError):
            flags.append("INVALID_CSV_SCHEDULE_HISTORY")
            continue
        if count:
            flags.append(changed)
    return flags


def _read_time(row, name, flags):
    try:
        return timestamp(row.get(name))
    except (ValueError, TypeError, OverflowError):
        flags.append("INVALID_CSV_" + name.upper())
        return None


def _endpoint(trip, stop_id, uid, journal_trip, journal_stop,
              conflicting_trips, conflicting_stops, ambiguous_uids, alias_count, receipts):
    common = _identity_flags(trip)
    if uid is None:
        common.append("UNRESOLVED_SOURCE_TRIP_UID")
    elif journal_trip is None or journal_stop is None:
        common.append("MISSING_CSV_LABEL")
    if uid in conflicting_trips or (uid, stop_id) in conflicting_stops:
        common.append("AMBIGUOUS_CSV_LABEL")
    if uid in ambiguous_uids:
        common.append("AMBIGUOUS_NORMALIZED_TRIP_FOR_CSV_UID")
    if trip.get("identity_conflict") or trip.get("conflicting_identity"):
        common.append("CONFLICTING_ARCHIVED_TRIP_IDENTITY")
    if journal_trip:
        if journal_trip.get("route_id") != trip.get("route_id"):
            common.append("CSV_ROUTE_MISMATCH")
        if journal_trip.get("trip_id") != trip.get("trip_id"):
            common.append("CSV_TRIP_ID_MISMATCH")
        common.extend(_schedule_flags(journal_trip))
    journal_stop = journal_stop or {}
    observed = _read_time(journal_stop, "last_observed", common)
    available = _read_time(journal_stop, "marked_past", common)
    if observed is None or available is None:
        common.append("MISSING_STOP_PASSAGE_CONFIRMATION")
    elif available < observed:
        common.append("INVALID_STOP_PASSAGE_ORDER")
    elif available - observed > 180:
        common.append("LARGE_STOP_OBSERVATION_GAP")
    arrival_flags, departure_flags = [], []
    arrival = _read_time(journal_stop, "arrival_time", arrival_flags)
    departure = _read_time(journal_stop, "departure_time", departure_flags)
    if arrival is None:
        arrival_flags.append("MISSING_CSV_ARRIVAL")
    if departure is None:
        departure_flags.append("MISSING_CSV_DEPARTURE")
    if arrival is not None and available is not None and arrival > available:
        arrival_flags.append("PREDICTED_ARRIVAL_AFTER_STOP_DISAPPEARANCE")
    if departure is not None and available is not None and departure > available:
        departure_flags.append("PREDICTED_DEPARTURE_AFTER_STOP_DISAPPEARANCE")
    if arrival is not None and departure is not None and departure < arrival:
        departure_flags.append("CSV_DEPARTURE_BEFORE_ARRIVAL")
    common = sorted(set(common))
    arrival_flags = sorted(set(common + arrival_flags))
    departure_flags = sorted(set(common + departure_flags))
    confirmed = receipts.confirm(trip.get("feed_id"), available)
    return {
        "arrival_at": arrival, "departure_at": departure,
        "available_at": available, "confirmed_at": confirmed,
        "confirmation_status": "CONFIRMED" if confirmed is not None else "UNVERIFIED",
        "available_at_basis": "JOURNAL_SOURCE_TIMESTAMP_NOT_RECEIPT",
        "confirmed_at_basis": "FIRST_ARCHIVED_SAME_FEED_RECEIPT_WITH_SOURCE_AFTER_MARKED_PAST",
        "stop_last_observed_at": observed,
        "observation_gap_seconds": None if available is None or observed is None else available - observed,
        "arrival_usable": not arrival_flags, "departure_usable": not departure_flags,
        "quality_flags": common, "arrival_quality_flags": arrival_flags,
        "departure_quality_flags": departure_flags,
        "source_trip_uid": uid, "raw_trip_id": trip.get("trip_id"),
        "canonical_event_trip_id": canonical_event_trip_id(trip),
        "normalized_alias_count": alias_count,
        "route_id": trip.get("route_id"), "feed_id": trip.get("feed_id"),
        "service_date": trip.get("start_date"), "stop_id": stop_id,
        "evidence_class": "MTA_FINAL_PREDICTION_PROXY", "physical_ground_truth": False,
    }


def build_labels(trips, csv_archives, receipts, stop_ids):
    """Return separate endpoint labels and coverage counts for observed trains.

    `trips` maps normalized train IDs to metadata plus the union of observed
    stop IDs. Outcome usability reflects journal integrity. An unverified
    receipt leaves `confirmed_at` null: callers must additionally check that
    field against their fitting cutoff to prevent temporal leakage.
    """
    identities_by_uid, canonical_by_uid, directions_by_uid = {}, {}, {}
    conflicted_identity_uids = set()
    for identity, trip in trips.items():
        uid = source_trip_uid(trip)
        if uid is not None:
            identities_by_uid.setdefault(uid, set()).add(identity)
            canonical_by_uid.setdefault(uid, set()).add(canonical_event_trip_id(trip))
            if (trip.get("identity_conflict") or trip.get("conflicting_identity")
                    or trip.get("schedule_relationship") in {"ADDED", "UNSCHEDULED", "DUPLICATED"}):
                conflicted_identity_uids.add(uid)
            directions = directions_by_uid.setdefault(uid, {"direction_id": set(), "nyct_direction": set()})
            for name in directions:
                value = trip.get(name)
                if value is not None:
                    directions[name].add(str(value))
    wanted = set(identities_by_uid)
    ambiguous_uids = conflicted_identity_uids | {uid for uid in wanted
                      if len(canonical_by_uid[uid]) != 1 or None in canonical_by_uid[uid]
                      or any(len(values) > 1 for values in directions_by_uid[uid].values())}
    stop_ids = set(stop_ids)
    journal_trips, journal_stops = {}, {}
    conflicting_trips, conflicting_stops = set(), set()
    counts = Counter()
    for path in csv_archives:
        for row in _csv_rows(path, "trips"):
            uid = row.get("trip_uid")
            if uid not in wanted:
                continue
            previous = journal_trips.get(uid)
            if previous is not None:
                if previous != row:
                    conflicting_trips.add(uid)
                else:
                    counts["identical_trip_duplicates"] += 1
            else:
                journal_trips[uid] = row
        for row in _csv_rows(path, "stop_times"):
            uid, stop = row.get("trip_uid"), row.get("stop_id")
            if uid not in wanted or stop not in stop_ids:
                continue
            key = uid, stop
            previous = journal_stops.get(key)
            if previous is not None:
                if previous != row:
                    conflicting_stops.add(key)
                else:
                    counts["identical_stop_duplicates"] += 1
            else:
                journal_stops[key] = row
    receipt_index = receipts if callable(getattr(receipts, "confirm", None)) else ReceiptIndex(receipts)
    result = {}
    for identity, trip in sorted(trips.items()):
        uid = source_trip_uid(trip)
        observed = trip.get("observed_stop_ids")
        if observed is None:
            observed = {stop.get("stop_id") for stop in trip.get("stop_updates", [])}
        endpoints = {}
        for stop in sorted(set(observed) & stop_ids):
            endpoint = _endpoint(trip, stop, uid, journal_trips.get(uid),
                                 journal_stops.get((uid, stop)), conflicting_trips,
                                 conflicting_stops, ambiguous_uids,
                                 len(identities_by_uid.get(uid, ())), receipt_index)
            endpoints[stop] = endpoint
            counts["endpoint_rows"] += 1
            counts["usable_arrival_rows"] += endpoint["arrival_usable"]
            counts["usable_departure_rows"] += endpoint["departure_usable"]
            counts["confirmed_endpoint_rows"] += endpoint["confirmed_at"] is not None
            for flag in set(endpoint["arrival_quality_flags"] + endpoint["departure_quality_flags"]):
                counts["flag:" + flag] += 1
        if endpoints:
            result[identity] = endpoints
        else:
            counts["trips_without_configured_observed_endpoints"] += 1
    counts["requested_trips"] = len(trips)
    counts["matched_journal_trips"] = len(journal_trips)
    counts["conflicting_journal_trips"] = len(conflicting_trips)
    counts["conflicting_journal_stops"] = len(conflicting_stops)
    counts["ambiguous_source_uids"] = len(ambiguous_uids)
    counts["canonical_service_runs"] = len({canonical_event_trip_id(trip) for trip in trips.values()} - {None})
    counts["aliased_source_uids"] = sum(len(identities) > 1 and uid not in ambiguous_uids
                                       for uid, identities in identities_by_uid.items())
    counts["extra_normalized_aliases"] = sum(len(identities) - 1 for uid, identities in identities_by_uid.items()
                                             if uid not in ambiguous_uids)
    return result, dict(counts)
