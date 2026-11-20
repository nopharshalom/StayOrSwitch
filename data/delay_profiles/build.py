"""Build independently weighted monthly profiles from as-of observations."""

from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
import gzip
import json
import sqlite3

from .common import (canonical, digest, end_of_date, epoch,
                     group_candidates, horizon_group, local_fields, read_json)
from .incidents import IncidentIndex
from data.october.labels import canonical_event_trip_id


@lru_cache(maxsize=100000)
def _canonical_identity(feed_id, start_date, route_id, trip_id):
    return canonical_event_trip_id(dict(feed_id=feed_id, start_date=start_date,
                                       route_id=route_id, trip_id=trip_id))


def canonical_trip(trip):
    return _canonical_identity(*(trip.get(name) for name in ("feed_id", "start_date", "route_id", "trip_id")))


def retain_earlier(row, earliest):
    """Mirror SQLite's strict earlier-cutoff update, including invalid rows."""
    previous = earliest.get(row["id"])
    if previous is not None and previous <= row["decision_at"]:
        return False
    earliest[row["id"]] = row["decision_at"]
    return True


def dates_between(first, last):
    current, end = date.fromisoformat(first), date.fromisoformat(last)
    while current <= end:
        yield current.isoformat()
        current += timedelta(days=1)


def distinct_legs(config):
    values = {}
    for route in config["routes"]:
        for leg in route["legs"]:
            for route_id in leg.get("route_ids", [leg["route_id"]]):
                item = dict(leg, route_id=route_id)
                values[(route_id, leg["from_stop_id"], leg["to_stop_id"])] = item
    return list(values.values())


def source_files(directory, dates):
    paths = []
    for day in dates:
        for kind in ("snapshots.jsonl.gz", "alerts.jsonl.gz", "trips.json.gz", "labels.json.gz", "source.json"):
            path = directory / (day + "." + kind)
            if not path.is_file():
                raise ValueError("Required prepared source is missing: " + str(path))
            paths.append(path)
    return paths


def snapshot_stream(path):
    from data.october.sources import read_snapshots
    yield from read_snapshots(path)


def scan_input_inventory(directory, dates, config):
    """Read inputs only: labels and outcome-derived statistics stay unopened."""
    spans, counts = {}, Counter()
    for day in dates:
        # Daily archives are New York calendar dates. Day membership is enough
        # to purge a train observed on both sides of the date-based split; these
        # conservative intervals are not advertised as exact observation times.
        previous_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        first = end_of_date(previous_day, config["timezone"])
        last = end_of_date(day, config["timezone"]) - .001
        for trip in read_json(directory / (day + ".trips.json.gz")).values():
            identity = canonical_trip(trip)
            if identity is None:
                counts["unresolved_trip_day_identities"] += 1
                continue
            old = spans.get(identity)
            spans[identity] = (first, last) if old is None else (min(old[0], first), max(old[1], last))
            counts["trip_day_memberships"] += 1

    def alert_snapshots():
        for day in dates:
            for snap in snapshot_stream(directory / (day + ".alerts.jsonl.gz")):
                counts["input_alert_snapshots"] += 1
                yield snap

    index = IncidentIndex(alert_snapshots(), max_age_seconds=config["alerts_max_age_seconds"])
    return index, spans, counts


def _incident_spans(index, observation_end):
    """Extend observed incidents through removal; censor unresolved ones at end.

    A notice captured before midnight and removed after midnight crosses the
    split even when its final content version was last seen on the earlier day.
    Invalid captures do not establish removal. Repeated publisher family IDs
    retain their whole observed episode span for conservative split purging.
    """
    # The held-out incident task concerns unplanned disruptions. Planned-only
    # and unknown-only notices retain their context but do not remove a month
    # of normal time-profile observations merely because their notice persists.
    qualifying = {value["incident_id"] for value in index.versions.values()
                  if value["state"] in {"DISRUPTION", "SEVERE"}}
    result, active = {}, set()
    for entry in index.entries:
        if not entry["valid"]:
            continue
        current = {index.versions[key]["incident_id"] for key in entry["version_ids"]}
        at = entry["captured_at"]
        for identifier in active - current:
            result[identifier] = (result[identifier][0], at)
        for identifier in current:
            result[identifier] = (result.get(identifier, (at, at))[0], at)
        active = current
    for identifier in active:
        result[identifier] = (result[identifier][0], observation_end)
    return {identifier: span for identifier, span in result.items() if identifier in qualifying}


def _boundary_inventory(index, spans, config):
    cutoff = end_of_date(config["splits"]["train"][1], config["timezone"])
    counts = Counter()
    for family in index.families.values():
        states = "+".join(sorted(family["states"]))
        counts["all_families:" + states] += 1
        span = spans.get(family["incident_id"])
        if span and span[0] < cutoff <= span[1]:
            counts["purged_crossing_families:" + states] += 1
    return dict(sorted(counts.items()))


def _split(day, config):
    return next((key for key, (start, end) in config["splits"].items() if start <= day <= end), None)


def _label_flags(label, target):
    prefix = "arrival" if target == "arrival" else "departure"
    flags = list((label or {}).get("quality_flags") or [])
    flags.extend((label or {}).get(prefix + "_quality_flags") or [])
    if not label or label.get(prefix + "_usable") is not True:
        flags.append("UNUSABLE_" + prefix.upper() + "_LABEL")
    return sorted(set(flags))


def observation_rows(snapshot, labels, config, incidents, counts):
    """Select forecast context before reading endpoint labels for scoring."""
    cutoff = epoch(snapshot.get("captured_at", snapshot.get("fetched_at")))
    if cutoff is None:
        counts["missing_cutoff_snapshots"] += 1
        return
    local = local_fields(cutoff, config)
    if not config["start_date"] <= local["date"] <= config["end_date"]:
        counts["outside_october_snapshots"] += 1
        return
    source = epoch(snapshot.get("source_updated_at"))
    snapshot_valid = snapshot.get("status") == "AVAILABLE" and source is not None and 0 <= cutoff - source <= config["train_max_age_seconds"]
    if not snapshot_valid:
        counts["missing_or_stale_train_snapshots"] += 1
        return
    by_route = defaultdict(list)
    for leg in distinct_legs(config):
        by_route[leg["route_id"]].append(leg)
    identity_counts = Counter(trip.get("id") for trip in snapshot.get("trips", []))
    canonical_counts = Counter(canonical_trip(trip) for trip in snapshot.get("trips", []))
    for trip in snapshot.get("trips", []):
        route_id, identity = trip.get("route_id"), trip.get("id")
        if route_id not in by_route:
            continue
        counts["train_observations"] += 1
        canonical_identity = canonical_trip(trip)
        if not identity or identity_counts[identity] != 1:
            counts["ambiguous_train_identity"] += 1
            continue
        status = trip.get("schedule_relationship")
        if status in {"CANCELED", "DELETED"}:
            counts["canceled_train_observations"] += 1
            continue
        update_time = epoch(trip.get("timestamp"))
        if update_time is not None and not 0 <= cutoff - update_time <= config["train_max_age_seconds"]:
            counts["stale_or_future_trip_updates"] += 1
            continue
        stops = trip.get("stop_updates") or []
        positions = defaultdict(list)
        for i, stop in enumerate(stops):
            positions[stop.get("stop_id")].append(i)
        for leg in by_route[route_id]:
            start, end = leg["from_stop_id"], leg["to_stop_id"]
            if len(positions[start]) != 1 or len(positions[end]) != 1 or positions[start][0] >= positions[end][0]:
                counts["missing_or_ambiguous_leg_path"] += 1
                continue
            path = stops[positions[start][0]:positions[end][0] + 1]
            if any(x.get("schedule_relationship") in {"SKIPPED", "NO_DATA"} for x in path):
                counts["skipped_or_no_data_leg_path"] += 1
                continue
            departure, arrival = epoch(path[0].get("departure_time")), epoch(path[-1].get("arrival_time"))
            if departure is None or arrival is None or arrival < departure:
                counts["missing_or_nonmonotonic_leg_prediction"] += 1
                continue
            segment_ids = [x["stop_id"] for x in path]
            context = incidents.context_at(cutoff, route_id, stop_ids=segment_ids)
            # Keep the context compact in millions of observations. The
            # separately retained inventory provides every original message.
            context = {key: context.get(key) for key in (
                "state", "cause", "incident_ids", "severe_incident_ids", "evidence_status", "first_observed_at",
                "age_seconds", "ambiguous_scope", "scope_uncertain", "applicable")}
            trip_labels = labels.get(identity, {})
            for target, stop_id, predicted in (("departure", start, departure), ("arrival", end, arrival)):
                label = trip_labels.get(stop_id)
                flags = _label_flags(label, target)
                if canonical_identity is None:
                    flags.append("UNRESOLVED_CANONICAL_TRIP_IDENTITY")
                elif canonical_counts[canonical_identity] != 1:
                    flags.append("SIMULTANEOUS_CANONICAL_TRIP_ALIASES")
                if label and label.get("canonical_event_trip_id") not in (None, canonical_identity):
                    flags.append("LABEL_CANONICAL_IDENTITY_MISMATCH")
                outcome = epoch((label or {}).get(target + "_at"))
                if outcome is None:
                    flags.append("MISSING_ENDPOINT_OUTCOME")
                horizon = predicted - cutoff
                forecast_state = "FUTURE" if departure >= cutoff and horizon >= 0 else "EXPIRED_OR_PAST_BOARDING"
                if forecast_state != "FUTURE":
                    flags.append("EXPIRED_OR_PAST_BOARDING_FORECAST")
                event = digest([canonical_identity or identity, target, stop_id])[:32]
                group_context = {key: context.get(key) for key in ("state", "cause", "evidence_status")}
                row_key = digest([event, start, end, horizon_group(horizon), local["date"], local["period"], group_context])[:32]
                row = {"id": row_key, "event_id": event, "trip_id": identity, "route_id": route_id,
                       "canonical_event_trip_id": canonical_identity,
                       "target": target, "from_stop_id": start, "to_stop_id": end,
                       "decision_at": cutoff, "date": local["date"], "split": _split(local["date"], config),
                       "day_type": local["day_type"], "period": local["period"], "hour": local["hour"],
                       "minute": local["minute"], "horizon_seconds": horizon, "horizon_group": horizon_group(horizon),
                       "predicted_at": predicted, "outcome_at": outcome,
                       "residual_seconds": None if outcome is None else outcome - predicted,
                       "label_confirmed_at": epoch((label or {}).get("confirmed_at")),
                       "label_available_at": epoch((label or {}).get("available_at")),
                       "forecast_state": forecast_state, "context": context,
                       "quality_flags": sorted(set(flags)), "usable": not flags,
                       "source_capture_at": cutoff, "source_updated_at": source,
                       "label_evidence": "MTA_FINAL_PREDICTION_PROXY"}
                counts["forecast_rows_considered"] += 1
                yield row


class ProfileDatabase:
    """Disk-backed deduplication at both observation and aggregate-event levels."""

    def __init__(self, path):
        self.connection = sqlite3.connect(str(path))
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, cutoff REAL NOT NULL, body TEXT NOT NULL)")
        self.connection.execute("CREATE INDEX IF NOT EXISTS observation_cutoff ON observations(cutoff,id)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS members (scope TEXT NOT NULL, group_key TEXT NOT NULL, event_id TEXT NOT NULL, cutoff REAL NOT NULL, residual REAL NOT NULL, day TEXT NOT NULL, incidents TEXT NOT NULL, PRIMARY KEY(scope,group_key,event_id)) WITHOUT ROWID")
        self.connection.execute("CREATE TABLE IF NOT EXISTS coverage (scope TEXT NOT NULL, group_key TEXT NOT NULL, event_id TEXT NOT NULL, cutoff REAL NOT NULL, usable INTEGER NOT NULL, label_known INTEGER NOT NULL, PRIMARY KEY(scope,group_key,event_id)) WITHOUT ROWID")

    def add_observation(self, row):
        self.connection.execute("INSERT INTO observations VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET cutoff=excluded.cutoff,body=excluded.body WHERE excluded.cutoff<observations.cutoff",
                                (row["id"], row["decision_at"], canonical(row).decode()))

    def rows(self):
        for body, in self.connection.execute("SELECT body FROM observations ORDER BY cutoff,id"):
            yield json.loads(body)

    def add_member(self, scope, key, row):
        incident_key = "severe_incident_ids" if json.loads(key)["state"] == "SEVERE" else "incident_ids"
        self.connection.execute("INSERT INTO members VALUES (?,?,?,?,?,?,?) ON CONFLICT(scope,group_key,event_id) DO UPDATE SET cutoff=excluded.cutoff,residual=excluded.residual,day=excluded.day,incidents=excluded.incidents WHERE excluded.cutoff<members.cutoff",
            (scope, key, row["event_id"], row["decision_at"], row["residual_seconds"], row["date"],
             json.dumps(sorted(set(row["context"].get(incident_key) or [])))))

    def add_coverage(self, scope, key, row):
        known = row.get("outcome_at") is not None and not any(
            flag.startswith("UNUSABLE_") and flag.endswith("_LABEL") for flag in row["quality_flags"])
        self.connection.execute("INSERT INTO coverage VALUES (?,?,?,?,?,?) ON CONFLICT(scope,group_key,event_id) DO UPDATE SET cutoff=excluded.cutoff,usable=excluded.usable,label_known=excluded.label_known WHERE excluded.cutoff<coverage.cutoff",
            (scope, key, row["event_id"], row["decision_at"], int(row["usable"]), int(known)))

    def coverage(self, scope):
        return {key: {"forecast_events": total, "usable_events": usable,
                      "unusable_events": total - usable, "unknown_label_events": total - known,
                      "unknown_label_fraction": (total - known) / total}
                for key, total, usable, known in self.connection.execute(
                    "SELECT group_key,COUNT(*),SUM(usable),SUM(label_known) FROM coverage WHERE scope=? GROUP BY group_key", (scope,))}

    def groups(self, scope):
        key, errors, dates, incidents = None, [], set(), set()
        for group, error, day, ids in self.connection.execute(
                "SELECT group_key,residual,day,incidents FROM members WHERE scope=? ORDER BY group_key,event_id", (scope,)):
            if key is not None and group != key:
                yield key, summarize_errors(errors, dates, incidents)
                errors, dates, incidents = [], set(), set()
            key = group
            errors.append(error)
            dates.add(day)
            incidents.update(json.loads(ids))
        if key is not None:
            yield key, summarize_errors(errors, dates, incidents)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


def summarize_errors(errors, dates=(), incidents=()):
    values = sorted(errors)
    count = len(values)
    if not count:
        raise ValueError("Cannot summarize an empty profile group.")

    def quantile(q):
        position = (count - 1) * q
        low, fraction = int(position), position - int(position)
        return values[low] * (1 - fraction) + values[min(low + 1, count - 1)] * fraction

    late = [x for x in values if x > 0]
    return {"event_count": count, "date_count": len(set(dates)), "incident_count": len(set(incidents)),
            "statistics": {"mean_signed_seconds": sum(values) / count,
                "mean_positive_seconds": sum(late) / count,
                "mean_if_late_seconds": sum(late) / len(late) if late else None,
                "median_seconds": quantile(.5), "p80_seconds": quantile(.8), "p90_seconds": quantile(.9),
                "probability_over_5_minutes": sum(x > 300 for x in values) / count,
                "probability_over_10_minutes": sum(x > 600 for x in values) / count,
                "late_fraction": len(late) / count}}


def train_eligible(row, config, trip_spans, incident_spans):
    if row["split"] != "train":
        return False, "NOT_DEVELOPMENT_DATE"
    cutoff = end_of_date(config["splits"]["train"][1], config["timezone"])
    if row.get("label_confirmed_at") is None:
        return False, "OUTCOME_RECEIPT_NOT_CONFIRMED"
    if row["label_confirmed_at"] >= cutoff:
        return False, "OUTCOME_CONFIRMED_AFTER_DEVELOPMENT"
    if trip_spans.get(row.get("canonical_event_trip_id") or row["trip_id"], (0, 0))[1] >= cutoff:
        return False, "TRAIN_CROSSES_DEVELOPMENT_BOUNDARY"
    for identifier in row["context"].get("incident_ids") or []:
        if incident_spans.get(identifier, (0, 0))[1] >= cutoff:
            return False, "INCIDENT_CROSSES_DEVELOPMENT_BOUNDARY"
    return True, None


def fit_database(database, config, scope, trip_spans, incident_spans):
    counts, flags, contexts = Counter(), Counter(), defaultdict(Counter)
    database.connection.execute("DELETE FROM members WHERE scope=?", (scope,))
    database.connection.execute("DELETE FROM coverage WHERE scope=?", (scope,))
    for row in database.rows():
        counts["representative_observations"] += 1
        context_key = "|".join(str(row["context"].get(key) or "UNKNOWN")
                               for key in ("state", "cause", "evidence_status"))
        context_counts = contexts[context_key]
        context_counts["representative_observations"] += 1
        candidates = group_candidates(row["target"], row["route_id"], row["from_stop_id"], row["to_stop_id"],
            row["decision_at"], row["horizon_seconds"], row["context"], config)
        for level, key, identity in candidates:
            if level == "TIME_EXACT":
                database.add_coverage(scope, key, row)
        if not row["usable"]:
            counts["unusable_observations"] += 1
            flags.update(row["quality_flags"])
            context_counts["unusable_observations"] += 1
            context_counts.update("flag:" + flag for flag in row["quality_flags"])
            continue
        if scope == "train":
            allowed, reason = train_eligible(row, config, trip_spans, incident_spans)
            if not allowed:
                counts[reason] += 1
                context_counts["purged:" + reason] += 1
                continue
        counts["eligible_observations"] += 1
        context_counts["eligible_observations"] += 1
        for level, key, identity in candidates:
            database.add_member(scope, key, row)
    database.commit()
    groups = dict(database.groups(scope))
    counts["profile_groups"] = len(groups)
    return groups, {"counts": dict(counts), "quality_flags": dict(flags),
                    "quality_by_context": {key: dict(value) for key, value in sorted(contexts.items())},
                    "coverage_by_time_group": database.coverage(scope)}


def profile_document(config, groups, fit_split, source_hashes, code_hashes, report):
    result = {"schema_version": "delay-profiles-v1", "fit_split": fit_split,
              "configuration": config, "groups": groups, "source_hashes": source_hashes,
              "code_hashes": code_hashes, "quality": report,
              "event_policy": "EARLIEST_FORECAST_PER_PHYSICAL_COMPONENT_EVENT_WITHIN_EACH_HIERARCHY_GROUP",
              "boundary_train_policy": "PURGE_ANY_TRAIN_OBSERVED_ON_A_POST_TRAINING_CALENDAR_DATE",
              "boundary_incident_policy": "PURGE_CROSSING_FAMILIES_WITH_ANY_UNPLANNED_DISRUPTION_OR_SEVERE_VERSION_INCLUDING_EARLIER_UNKNOWN_OR_RECOVERY_ROWS",
              "label_evidence": "MTA_FINAL_PREDICTION_PROXY", "physical_passenger_outcomes": False}
    result["seal"] = digest(result)
    return result
