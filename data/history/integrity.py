"""Global dataset counts and conservative checks across archive boundaries.

Qualified IDs are checked exactly. Physical continuity is only an ambiguity
screen based on observed identifiers and times; it cannot prove that different
IDs refer to independent physical trains. SQLite bounds memory for row/event
deduplication and keeps all generated artifacts outside version control.
"""

from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import re
import sqlite3
import tempfile
from urllib.parse import unquote

from .features import epoch, local_date, split_for_date


AMBIGUITY_FLAG = "CROSS_SPLIT_PHYSICAL_CONTINUITY_AMBIGUOUS"


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def _kind(row):
    return "segment" if "from_stop_id" in row and "to_stop_id" in row else "arrival"


def _groups(connection, column=None):
    selection = (column + ", ") if column else ""
    grouping = (" GROUP BY " + column + " ORDER BY " + column) if column else ""
    records = connection.execute(
        "SELECT " + selection + "COUNT(*), SUM(eligible), COUNT(DISTINCT trip), "
        "COUNT(DISTINCT event), COUNT(DISTINCT CASE WHEN eligible=1 THEN event END) "
        "FROM examples" + grouping).fetchall()
    def counts(record):
        return dict(zip(("rows", "eligible_proxy_rows", "unique_trips", "unique_events",
                         "unique_eligible_events"), (int(value or 0) for value in record)))
    return {row[0]: counts(row[1:]) for row in records} if column else counts(records[0])


def audit_dataset(paths, *, maximum_continuity_gap_seconds=180,
                  require_receipt_confirmation=True):
    """Audit all gzip JSONL parts together, including ineligible coverage rows."""
    if maximum_continuity_gap_seconds < 0:
        raise ValueError("Continuity gap must be nonnegative.")
    paths = [Path(path) for path in paths]
    cache = Path(__file__).resolve().parents[1] / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    aliases, trip_splits, identity_eligible = defaultdict(dict), defaultdict(set), Counter()
    violations = Counter()
    with tempfile.TemporaryDirectory(prefix="integrity-", dir=cache) as directory:
        connection = sqlite3.connect(str(Path(directory) / "counts.sqlite"))
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute("CREATE TABLE examples (example TEXT, trip TEXT, event TEXT, "
                               "kind TEXT, route TEXT, day_type TEXT, split TEXT, eligible INTEGER)")
            batch = []
            for path in paths:
                for row in _rows(path):
                    features, provenance = row["features"], row.get("provenance", {})
                    identity, split = row["trip_identity"], row["split"]
                    capture = epoch(row["decision_at"])
                    kind = _kind(row)
                    eligible = bool(row["eligible_for_training"])
                    route = str(features.get("route_id") or "UNKNOWN")
                    event = json.dumps([kind, identity, row.get("stop_id"),
                                        row.get("from_stop_id"), row.get("to_stop_id")], separators=(",", ":"))
                    batch.append((row["example_id"], identity, event, kind, route,
                                  features.get("day_type", "UNKNOWN"), split, int(eligible)))
                    if len(batch) >= 2000:
                        connection.executemany("INSERT INTO examples VALUES (?,?,?,?,?,?,?,?)", batch)
                        batch.clear()
                    trip_splits[identity].add(split)
                    identity_eligible[identity] += int(eligible)
                    if (split_for_date(local_date(capture)) != split
                            or features.get("decision_local_date") != local_date(capture)
                            or split_for_date(features["service_date"]) != split):
                        violations["date_split_mismatches"] += 1
                    source = epoch(row.get("source_updated_at"))
                    if source is None or source > capture:
                        violations["source_after_decision_or_missing"] += 1
                    label = row.get("label", {})
                    if eligible:
                        label_times = [epoch(label[key]) for key in
                            ("arrival_at", "departure_at", "available_at", "origin_available_at",
                             "destination_available_at", "receipt_confirmed_at")
                            if label.get(key) is not None]
                        if any(value <= capture for value in label_times):
                            violations["eligible_label_not_after_decision"] += 1
                        if any(split_for_date(local_date(value)) != split for value in label_times):
                            violations["eligible_label_split_boundary"] += 1
                        if label.get("arrival_at") is None or (kind == "segment" and label.get("departure_at") is None):
                            violations["eligible_label_missing_outcome"] += 1
                        if require_receipt_confirmation and label.get("receipt_confirmed_at") is None:
                            violations["eligible_label_missing_receipt_confirmation"] += 1
                    parts = [unquote(part) for part in identity.split(":")]
                    feed = str(features.get("feed_id") or (parts[1] if len(parts) > 1 else "UNKNOWN"))
                    raw = provenance.get("raw_trip_id") or (parts[4] if len(parts) > 4 else None)
                    train = provenance.get("nyct_train_id")
                    keys = [("RAW_TRIP_ID", feed, route, raw)] if raw else []
                    if train and raw and features.get("is_assigned") is True:
                        suffix = re.sub(r"^\d{6}", "", raw)
                        keys.append(("ASSIGNED_VEHICLE_AND_PATH", feed, route, str(train), suffix))
                    for key in keys:
                        interval = aliases[key].setdefault((identity, split), [capture, capture])
                        interval[0], interval[1] = min(interval[0], capture), max(interval[1], capture)
            if batch:
                connection.executemany("INSERT INTO examples VALUES (?,?,?,?,?,?,?,?)", batch)
            duplicate_rows = connection.execute(
                "SELECT COUNT(*) - COUNT(DISTINCT example) FROM examples").fetchone()[0]
            duplicate_examples = [row[0] for row in connection.execute(
                "SELECT example FROM examples GROUP BY example HAVING COUNT(*)>1 ORDER BY example LIMIT 20")]
            conflicts = {identity: sorted(splits) for identity, splits in trip_splits.items() if len(splits) > 1}
            ambiguous, pairs = set(), {}
            for key, intervals in aliases.items():
                ordered = sorted(((start, end, identity, split)
                                  for (identity, split), (start, end) in intervals.items()))
                for index, (start, end, identity, split) in enumerate(ordered):
                    for next_start, next_end, other, other_split in ordered[index + 1:]:
                        if next_start > end + maximum_continuity_gap_seconds:
                            break
                        if identity == other or split == other_split:
                            continue
                        ambiguous.update((identity, other))
                        pair_key = tuple(sorted((identity, other)))
                        item = pairs.setdefault(pair_key, {
                            "trip_identities": list(pair_key), "splits": sorted({split, other_split}),
                            "evidence": [], "capture_interval_gap_seconds": max(0, next_start - end),
                        })
                        if key[0] not in item["evidence"]:
                            item["evidence"].append(key[0])
            ambiguous_eligible = sum(identity_eligible[identity] for identity in ambiguous)
            result = {
                "status": "PASS" if not (duplicate_rows or conflicts or violations or ambiguous_eligible) else "FAIL",
                "counts": _groups(connection),
                "by_kind": _groups(connection, "kind"), "by_route": _groups(connection, "route"),
                "by_day_type": _groups(connection, "day_type"), "by_split": _groups(connection, "split"),
                "duplicate_example_rows": duplicate_rows, "duplicate_example_id_sample": duplicate_examples,
                "qualified_trip_split_conflicts": dict(sorted(conflicts.items())),
                "temporal_violations": dict(violations),
                "ambiguous_trip_identities": sorted(ambiguous),
                "ambiguous_eligible_rows": ambiguous_eligible,
                "ambiguity_pair_count": len(pairs),
                "ambiguity_pair_sample": [pairs[key] for key in sorted(pairs)[:100]],
                "continuity_gap_seconds": maximum_continuity_gap_seconds,
                "receipt_confirmation_required": require_receipt_confirmation,
                "physical_trip_disjointness": "NOT_PROVEN_BY_IDENTIFIERS_OR_THIS_SCREEN",
                "count_semantics": "Exact distinct qualified trips and stop/segment events across all parts; repeated predictions are rows, not independent journeys.",
            }
            return result
        finally:
            connection.close()


def purge_ambiguous(paths, identities):
    """Retain ambiguous rows for coverage while excluding them from model fitting."""
    identities = set(identities)
    counts = {"files_rewritten": 0, "rows_marked": 0, "rows_eligibility_removed": 0,
              "affected_files": []}
    if not identities:
        return counts
    for value in paths:
        path = Path(value)
        if not any(row["trip_identity"] in identities for row in _rows(path)):
            continue
        temporary = path.with_name(path.name + ".purge.part")
        try:
            with temporary.open("wb") as raw:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=1, mtime=0) as output:
                    for row in _rows(path):
                        if row["trip_identity"] in identities:
                            counts["rows_marked"] += 1
                            counts["rows_eligibility_removed"] += int(bool(row["eligible_for_training"]))
                            row["eligible_for_training"] = False
                            label = row.setdefault("label", {})
                            label["usable_proxy"] = False
                            label["quality_flags"] = sorted(set(label.get("quality_flags", [])) | {AMBIGUITY_FLAG})
                        output.write((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())
            temporary.replace(path)
            counts["files_rewritten"] += 1
            counts["affected_files"].append(str(path))
        finally:
            temporary.unlink(missing_ok=True)
    return counts
