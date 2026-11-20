"""Build independently weighted monthly profiles from as-of observations."""

from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
import gzip
import json
from pathlib import Path
import sqlite3
import time

from .common import (canonical, digest, end_of_date, epoch, file_sha256,
                     group_candidates, horizon_group, local_fields, read_json, write_json)
from .incidents import IncidentIndex
from data.october.labels import canonical_event_trip_id


ROOT = Path(__file__).resolve().parents[2]


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


def verify_protocol_freeze(config_path, required=True):
    """Require a complete algorithm/data protocol seal before holdout access."""
    path = ROOT / "algo/reports/october-protocol-frozen.json"
    if not path.is_file():
        if required:
            raise ValueError("Freeze the complete October algorithm/data protocol before building full-month profiles.")
        return None
    value = read_json(path)
    if value.get("schema_version") != "october-protocol-freeze-v1":
        raise ValueError("Unsupported October protocol freeze.")
    if value.get("config_sha256") != file_sha256(config_path):
        raise ValueError("Configuration differs from the October protocol freeze.")
    for name, expected in value["code_sha256"].items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("Code differs from the October protocol freeze: " + name)
    return file_sha256(path)


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


def _markdown_report(path, train, month, inventory, completeness):
    lines = ["# October historical delay profiles", "",
        "This report describes MTA final-prediction proxies, not physical passenger arrivals. "
        "The full-month descriptive profile must never be used to predict its own validation or test outcomes.", "",
        f"Requested month complete: **{completeness}**. Training-only profile seal: `{train['seal']}`.", "",
        f"Development representative observations: {train['quality']['counts'].get('representative_observations', 0)}; "
        f"eligible: {train['quality']['counts'].get('eligible_observations', 0)}. "
        f"Monthly representative observations: {month['quality']['counts'].get('representative_observations', 0)}; "
        f"eligible: {month['quality']['counts'].get('eligible_observations', 0)}.", "",
        "## Weekday morning, midday and evening endpoint profiles", "",
        "Rows below use the 15–30 minute prediction horizon and retain segment, direction and weekday class. "
        "Mean positive delay averages max(error, 0) across all cases; it differs from the conditional late-only mean. "
        "These are endpoint ETA residuals for listed subway segments, not door-to-door journey averages. "
        "Unknown and disrupted service are included in these time-only descriptive groups, not relabeled normal. "
        "Events/days/incidents describe usable outcomes. Unknown labels include missing or ambiguous endpoint proxies; "
        "their denominator includes all independent forecast events in the same time group, before quality exclusion.", ""]
    coverage = month["quality"].get("coverage_by_time_group", {})

    def append_table(primary):
        lines.extend(["| Route | Segment | Day | Period | Events | Days | Incidents | Mean signed min | Mean positive min | P90 min | Unknown labels |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|"])
        for key in sorted(coverage):
            identity = json.loads(key)
            if identity["target"] != "arrival" or identity["horizon"] != "15_30_MIN":
                continue
            priority = identity["day_type"] == "WEEKDAY" and identity["period"] in {"MORNING_PEAK", "MIDDAY", "EVENING_PEAK"}
            if priority != primary:
                continue
            value, observed = month["groups"].get(key, {}), coverage[key]
            stats = value.get("statistics")
            summaries = " | ".join(f"{stats[name]/60:.2f}" for name in
                ("mean_signed_seconds", "mean_positive_seconds", "p90_seconds")) if stats else "unavailable | unavailable | unavailable"
            lines.append(f"| {identity['route_id']} | {identity['from_stop_id']} → {identity['to_stop_id']} | "
                f"{identity['day_type']} | {identity['period']} | {value.get('event_count', 0)} | "
                f"{value.get('date_count', 0)} | {value.get('incident_count', 0)} | {summaries} | "
                f"{observed['unknown_label_events']}/{observed['forecast_events']} ({observed['unknown_label_fraction']:.1%}) |")

    append_table(True)
    lines.extend(["", "## Other weekday periods and separate weekend profiles", ""])
    append_table(False)
    lines += ["", "## Interpretation", "",
        "- Each hierarchy group counts a physical component event only once, including broader fallback groups.",
        "- Sparse severe groups require both the configured event count and independent incident count; fallback is explicit.",
        "- Incident text classification is rule-based and may remain unknown; it does not establish physical disruption extent.",
        "- Last-observed alerts are separate from fresh evidence. Missing alerts are not normal service.",
        "- Training labels must have a confirmed receipt before the development cutoff; crossing trains and unplanned disruption/severe incident families are purged.",
        "- Planned-only and unknown-only notices remain explicit context; independent-incident generalization is not claimed for those categories.",
        "- Unusable, expired, missing, canceled and changed-schedule observations remain counted in source/quality reports.", ""]
    path.write_text("\n".join(lines))


def build(config_path, directory, *, dates=None, smoke=False):
    started = time.monotonic()
    config_path, directory = Path(config_path).resolve(), Path(directory).resolve()
    config = read_json(config_path)
    all_dates = list(dates_between(config["start_date"], config["end_date"]))
    selected_dates = sorted(set(dates or all_dates))
    if not set(selected_dates).issubset(all_dates):
        raise ValueError("Profile dates must stay in the configured October window.")
    complete = selected_dates == all_dates
    if not complete and not smoke:
        raise ValueError("A partial-month profile requires explicit smoke mode.")
    if smoke and any(_split(day, config) != "train" for day in selected_dates):
        raise ValueError("Profile smoke runs may use only development dates; use the frozen full-month pipeline for held-out dates.")
    protocol_hash = verify_protocol_freeze(config_path, required=not smoke)
    files = source_files(directory, selected_dates)
    source_hashes = {str(path.relative_to(ROOT)): file_sha256(path) for path in files}
    for day in selected_dates:
        prepared = read_json(directory / (day + ".source.json"))
        for name in ("snapshots", "alerts", "trips"):
            item = prepared["outputs"][name]
            if source_hashes.get(item["path"]) != item["sha256"]:
                raise ValueError("Prepared projection differs from its source manifest: " + item["path"])
    code_paths = (sorted(Path(__file__).parent.glob("*.py")) + sorted((ROOT / "data/october").glob("*.py"))
                  + [ROOT / "data/scripts/build_delay_profiles.py"])
    code_hashes = {str(path.relative_to(ROOT)): file_sha256(path) for path in code_paths}
    config_hash = file_sha256(config_path)

    def verify_build_inputs():
        if config_hash != file_sha256(config_path) or any(file_sha256(ROOT / key) != value for key, value in code_hashes.items()):
            raise ValueError("Profile code or configuration changed during preparation.")
        if any(file_sha256(ROOT / key) != value for key, value in source_hashes.items()):
            raise ValueError("A prepared source changed during profile preparation.")
        if protocol_hash != verify_protocol_freeze(config_path, required=not smoke):
            raise ValueError("The October protocol freeze changed during preparation.")

    incidents, trip_spans, inventory_counts = scan_input_inventory(directory, selected_dates, config)
    inventory = incidents.inventory()
    incident_spans = _incident_spans(incidents, end_of_date(selected_dates[-1], config["timezone"]))
    boundary_inventory = _boundary_inventory(incidents, incident_spans, config)
    print(json.dumps({"stage": "INPUT_ONLY_BOUNDARY_INVENTORY", "families": boundary_inventory}), flush=True)
    prefix = "smoke-" if smoke else ""
    inventory_path = directory / (prefix + "incidents.json.gz")
    write_json(inventory_path, inventory)
    db_path = directory / (prefix + "profile-observations.sqlite")
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    database = ProfileDatabase(db_path)
    considered = Counter()
    working_peak_bytes = 0

    def note_working_size():
        nonlocal working_peak_bytes
        size = sum(path.stat().st_size for path in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")) if path.exists())
        working_peak_bytes = max(working_peak_bytes, size)
        return size

    def add_days(days):
        from data.october.sources import read_labels
        for day in days:
            labels = read_labels(directory / (day + ".labels.json.gz"))
            earliest = {}
            for snapshot in snapshot_stream(directory / (day + ".snapshots.jsonl.gz")):
                if snapshot.get("feed_id") == "subway-alerts" or snapshot.get("kind") == "alerts":
                    continue
                for row in observation_rows(snapshot, labels, config, incidents, considered):
                    # Most minute-by-minute rows repeat the same representative
                    # event. Avoid serializing them into SQLite again. This
                    # cache is bounded to one day and still permits an earlier
                    # cutoff when different feed blocks arrive out of order.
                    if not retain_earlier(row, earliest):
                        continue
                    database.add_observation(row)
            database.commit()
            print(json.dumps({"stage": "PROFILE_OBSERVATIONS", "date": day,
                              "elapsed_seconds": round(time.monotonic() - started, 1),
                              "working_database_bytes": note_working_size()}), flush=True)

    train_days = [day for day in selected_dates if _split(day, config) == "train"]
    add_days(train_days)
    groups, train_report = fit_database(database, config, "train", trip_spans, incident_spans)
    note_working_size()
    train_report["input_only_boundary_families"] = boundary_inventory
    verify_build_inputs()
    train_sources = {key: value for key, value in source_hashes.items()
                     if any(day in key for day in train_days) or key.endswith(("alerts.jsonl.gz", "trips.json.gz"))}
    train = profile_document(config, groups, "train", train_sources, code_hashes, train_report)
    train["complete_month_inputs"] = complete
    train["protocol_freeze_sha256"] = protocol_hash
    train["seal"] = digest({key: value for key, value in train.items() if key != "seal"})
    train_path = directory / (prefix + "profiles-train.json.gz")
    write_json(train_path, train)
    seal_path = ROOT / "data/manifests" / (prefix + "profiles-frozen.json")
    frozen = {"stage": "FROZEN_BEFORE_MONTH_DESCRIPTIVE_STATISTICS_AND_TEST_SCORING",
              "profile_seal": train["seal"], "train_profile": {"path": str(train_path.relative_to(ROOT)),
              "sha256": file_sha256(train_path)}, "config_sha256": config_hash,
              "code_sha256": code_hashes, "source_sha256": train_sources,
              "protocol_freeze_sha256": protocol_hash,
              "complete_month_inputs": complete}
    write_json(seal_path, frozen)
    print(json.dumps({"stage": "TRAIN_PROFILE_FROZEN", "seal": train["seal"]}), flush=True)
    # The sealed JSON is the predictive artifact; discard its disk memberships
    # before descriptive fitting so the same SQLite pages can be reused.
    database.connection.execute("DELETE FROM members WHERE scope='train'")
    database.connection.execute("DELETE FROM coverage WHERE scope='train'")
    database.commit()
    database.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # Only now open validation/final-test outcome journals for descriptive work.
    if protocol_hash != verify_protocol_freeze(config_path, required=not smoke):
        raise ValueError("The protocol changed before descriptive outcome access.")
    add_days([day for day in selected_dates if day not in train_days])
    groups, month_report = fit_database(database, config, "month_descriptive", trip_spans, incident_spans)
    note_working_size()
    month = profile_document(config, groups, "month_descriptive", source_hashes, code_hashes, month_report)
    month_path = directory / (prefix + "profiles-month.json.gz")
    write_json(month_path, month)
    observations_path = directory / (prefix + "profile-observations.jsonl.gz")
    with observations_path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
        for row in database.rows():
            stream.write(canonical(row) + b"\n")
    database.close()
    for suffix in ("", "-wal", "-shm"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    verify_build_inputs()
    report = {"stage": "PREPARED", "requested_month_complete": complete, "dates": selected_dates,
              "inventory": dict(inventory_counts), "observations_considered": dict(considered),
              "train": train_report, "month_descriptive": month_report,
              "incident_inventory_counts": inventory.get("counts", {}),
              "working_database_peak_bytes": working_peak_bytes,
              "working_database_retained": False,
              "elapsed_seconds": round(time.monotonic() - started, 1)}
    report_path = ROOT / "data/reports" / (prefix + "profiles.json")
    write_json(report_path, report)
    _markdown_report(report_path.with_suffix(".md"), train, month, inventory, complete)
    manifest = dict(frozen, stage="PREPARED", source_sha256=source_hashes,
                    month_profile={"path": str(month_path.relative_to(ROOT)), "sha256": file_sha256(month_path)},
                    observations={"path": str(observations_path.relative_to(ROOT)), "sha256": file_sha256(observations_path)},
                    incidents={"path": str(inventory_path.relative_to(ROOT)), "sha256": file_sha256(inventory_path)},
                    report={"path": str(report_path.relative_to(ROOT)), "sha256": file_sha256(report_path)})
    write_json(ROOT / "data/manifests" / (prefix + "profiles.json"), manifest)
    print(json.dumps({"stage": "PROFILES_PREPARED", "elapsed_seconds": report["elapsed_seconds"]}), flush=True)
    return manifest
