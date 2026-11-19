"""Bounded, label-independent selection of chronological component examples."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from data.history.features import LOCAL_ZONE, split_for_date
from .features import (FEATURE_VERSION, ROLLING_FEATURE_NAMES, approach_pattern, build_features,
                       disruption_group, horizon_bucket, revision_group, support_key, support_keys)


TARGETS = ("arrival", "departure", "segment")
SPLITS = ("train", "validation", "test")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def trip_selected(trip_identity, percent, seed):
    if not 0 <= percent <= 100:
        raise ValueError("Trip sample percent must be in [0, 100].")
    digest = hashlib.sha256((seed + "|trip|" + trip_identity).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64 < percent / 100


def event_id(row, target):
    if target == "arrival":
        stops = [row["stop_id"]]
    elif target == "departure":
        stops = [row["from_stop_id"]]
    elif target == "segment":
        stops = [row["from_stop_id"], row["to_stop_id"]]
    else:
        raise ValueError("Unsupported model target.")
    return hashlib.sha256("|".join([target, row["trip_identity"]] + stops).encode()).hexdigest()[:32]


def selection_priority(example, seed):
    return hashlib.sha256((seed + "|snapshot|" + example["event_id"] + "|" +
                           repr(float(example["decision_at"]))).encode()).hexdigest()


def make_example(row, target):
    """Normalize a candidate without discarding its unsupported/invalid label."""
    if target not in TARGETS:
        raise ValueError("Unsupported model target.")
    source, label = row["features"], row["label"]
    decision = row["decision_at"]
    if not _finite(decision):
        raise ValueError("A finite collection-time cutoff is required.")
    local = datetime.fromtimestamp(decision, LOCAL_ZONE)
    decision_date = local.date().isoformat()
    split = row.get("split")
    if (split not in SPLITS or split_for_date(decision_date) != split or
            split_for_date(source.get("service_date", "")) != split or
            source.get("decision_local_date") != decision_date):
        raise ValueError("Decision and service dates must belong to the declared split.")
    expected_day = "WEEKDAY" if local.weekday() < 5 else "SATURDAY" if local.weekday() == 5 else "SUNDAY"
    if source.get("day_type") != expected_day:
        raise ValueError("Day type does not match the collection-time cutoff.")
    if not _finite(row.get("source_updated_at")) or not 0 <= decision - row["source_updated_at"] <= 180:
        raise ValueError("Source update must be fresh and known at the decision cutoff.")
    reasons = []
    if not row.get("eligible_for_training") or not label.get("usable_proxy") or label.get("quality_flags"):
        reasons.append("SOURCE_LABEL_INELIGIBLE")
    if target != "arrival" and source.get("origin_prediction_basis") != "DEPARTURE_PREDICTION":
        reasons.append("UNSUPPORTED_DEPARTURE_BASIS")
    if target == "arrival":
        baseline = source.get("prediction_horizon_seconds")
        endpoint = label.get("arrival_at")
        outcome = endpoint - decision if _finite(endpoint) else None
        horizon = baseline
    elif target == "departure":
        baseline = source.get("departure_horizon_seconds")
        endpoint = label.get("departure_at")
        outcome = endpoint - decision if _finite(endpoint) else None
        horizon = baseline
    else:
        baseline = source.get("predicted_duration_seconds")
        outcome = label.get("duration_seconds")
        horizon = source.get("departure_horizon_seconds")
    if not _finite(baseline) or baseline < 0 or horizon_bucket(horizon) is None:
        reasons.append("INVALID_BASELINE_OR_HORIZON")
    if not _finite(outcome) or outcome < 0 or (target != "segment" and outcome <= 0):
        reasons.append("INVALID_OR_NONFUTURE_LABEL")
    receipt = label.get("receipt_confirmed_at")
    if not _finite(receipt) or receipt < decision or split_for_date(
            datetime.fromtimestamp(receipt, LOCAL_ZONE).date().isoformat()) != split:
        reasons.append("LABEL_RECEIPT_NOT_CONFIRMED_WITHIN_SPLIT")
    features = build_features(target, source)
    event = event_id(row, target)
    result = {
        "schema_version": "model-example-v1", "feature_version": FEATURE_VERSION,
        "target": target, "split": split,
        "example_id": hashlib.sha256((event + "|" + repr(float(decision))).encode()).hexdigest()[:32],
        "event_id": event, "trip_identity": row["trip_identity"],
        "decision_at": decision, "decision_date": decision_date,
        "service_date": source["service_date"], "day_type": expected_day,
        "route_id": source["route_id"], "horizon_bucket": horizon_bucket(horizon),
        "disruption_group": disruption_group(source, target),
        "revision_group": revision_group(source, target),
        "baseline_seconds": baseline if _finite(baseline) else None,
        "label_seconds": outcome if _finite(outcome) else None,
        "target_residual_seconds": outcome - baseline if _finite(outcome) and _finite(baseline) else None,
        "eligible": not reasons, "exclusion_reasons": reasons,
        "weight": None, "features": features, "support_key": support_key(target, features, source),
        "support_keys": support_keys(target, features, source),
        "origin_prediction_basis": source.get("origin_prediction_basis") if target != "arrival" else None,
        "support_source": {"remaining_stop_pattern": approach_pattern(features, source)} if target != "segment" else {},
        "label_method": label.get("method"), "physical_ground_truth": False,
    }
    if target == "arrival":
        rolling = build_features(target, source, include_rolling=True)
        result["rolling_features"] = {key: rolling[key] for key in ROLLING_FEATURE_NAMES}
    return result


def _semantic(example):
    fields = ("split", "event_id", "trip_identity", "decision_at", "baseline_seconds",
              "label_seconds", "target_residual_seconds", "features", "support_key", "support_keys",
              "eligible", "exclusion_reasons")
    return {key: example.get(key) for key in fields}


class SelectionStore:
    """Keep one hash-selected candidate per event/bucket before label filtering."""

    def __init__(self, path, seed):
        self.seed = seed
        self.connection = sqlite3.connect(str(path))
        self.connection.execute("PRAGMA journal_mode=OFF")
        self.connection.execute("PRAGMA synchronous=OFF")
        self.connection.execute("PRAGMA temp_store=FILE")
        self.connection.execute("CREATE TABLE IF NOT EXISTS selected (target TEXT, event TEXT, bucket TEXT, priority TEXT, payload TEXT, PRIMARY KEY(target,event,bucket))")
        self.conflicting_duplicates = 0

    def consider(self, example):
        if example["horizon_bucket"] is None:
            return
        priority = selection_priority(example, self.seed)
        key = (example["target"], example["event_id"], example["horizon_bucket"])
        previous = self.connection.execute("SELECT priority,payload FROM selected WHERE target=? AND event=? AND bucket=?", key).fetchone()
        if previous and previous[0] < priority:
            return
        if previous and previous[0] == priority:
            old = json.loads(previous[1])
            if "CONFLICTING_DUPLICATE" in old.get("exclusion_reasons", []):
                return
            if _semantic(old) == _semantic(example):
                return
            example = dict(example, eligible=False, exclusion_reasons=sorted(set(
                old.get("exclusion_reasons", []) + example.get("exclusion_reasons", []) + ["CONFLICTING_DUPLICATE"])))
            self.conflicting_duplicates += 1
        payload = json.dumps(example, sort_keys=True, separators=(",", ":"), allow_nan=False)
        self.connection.execute("INSERT OR REPLACE INTO selected VALUES (?,?,?,?,?)", key + (priority, payload))

    def selected(self):
        self.connection.commit()
        for (payload,) in self.connection.execute("SELECT payload FROM selected ORDER BY target,event,bucket"):
            yield json.loads(payload)

    def close(self):
        self.connection.close()


def write_views(store, output_root):
    """Write selected eligible rows; each retained event has total weight one."""
    output_root = Path(output_root)
    streams, paths, counts = {}, {}, defaultdict(Counter)
    selected_counts, exclusions = Counter(), Counter()
    event_counts = defaultdict(int)
    trips = defaultdict(set)
    groups = defaultdict(Counter)
    for target in TARGETS:
        for split in SPLITS:
            path = output_root / target / (split + ".jsonl.gz")
            path.parent.mkdir(parents=True, exist_ok=True)
            paths[(target, split)] = path
            streams[(target, split)] = gzip.open(path, "wt", encoding="utf-8", compresslevel=6)

    def emit_event(rows):
        eligible = [row for row in rows if row["eligible"]]
        if not eligible:
            return
        n = len(eligible)
        target, split = eligible[0]["target"], eligible[0]["split"]
        if any(row["split"] != split for row in rows):
            raise ValueError("One event cannot appear in multiple splits.")
        event_counts[(target, split)] += 1
        for row in eligible:
            row["weight"] = 1.0 / n
            streams[(target, split)].write(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
            counts[(target, split)]["rows"] += 1
            trips[(target, split)].add(row["trip_identity"])
            for group in ("day_type", "route_id", "horizon_bucket", "disruption_group", "revision_group"):
                groups[(target, split, group)][row[group]] += 1

    try:
        rows, previous = [], None
        trip_splits = {}
        for row in store.selected():
            key = (row["target"], row["event_id"])
            prior = trip_splits.setdefault(row["trip_identity"], row["split"])
            if prior != row["split"]:
                raise ValueError("A selected trip appears in multiple splits.")
            selected_counts[row["target"] + "/" + row["split"]] += 1
            for reason in row["exclusion_reasons"]:
                exclusions[row["target"] + "/" + row["split"] + "/" + reason] += 1
            if previous is not None and key != previous:
                emit_event(rows)
                rows = []
            previous = key
            rows.append(row)
        emit_event(rows)
    finally:
        for stream in streams.values():
            stream.close()
    outputs = []
    for (target, split), path in sorted(paths.items()):
        outputs.append({"target": target, "split": split, "path": str(path), "bytes": path.stat().st_size,
                        "sha256": sha256(path), "rows": counts[(target, split)]["rows"],
                        "events": event_counts[(target, split)], "trips": len(trips[(target, split)]),
                        "groups": {group: dict(groups[(target, split, group)]) for group in (
                            "day_type", "route_id", "horizon_bucket", "disruption_group", "revision_group")}})
    conflicts = sum(count for name, count in exclusions.items() if name.endswith("/CONFLICTING_DUPLICATE"))
    return outputs, {"selected_before_label_filter": dict(selected_counts), "selected_exclusions": dict(exclusions),
                     "conflicting_selected_duplicates": conflicts}
