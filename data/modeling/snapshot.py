"""Construct model inputs from one as-of normalized MTA train snapshot.

This adapter is shared data processing, not live collection or model inference.
It deliberately does not read outcomes, CSV journals, or future snapshots.
"""

from datetime import datetime
import math
from zoneinfo import ZoneInfo

from .features import (FEATURE_VERSION, build_features, horizon_bucket,
                       support_key, support_keys)


LOCAL_ZONE = ZoneInfo("America/New_York")


def _epoch(value):
    if isinstance(value, bool):
        raise ValueError("Timestamps cannot be boolean.")
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError:
            raise ValueError("A finite timestamp is required.") from None
        if not math.isfinite(number):
            raise ValueError("A finite timestamp is required.")
        return number
    if not isinstance(value, str):
        raise ValueError("A timezone-aware timestamp is required.")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("A timezone-aware timestamp is required.")
    return instant.timestamp()


def build_snapshot_case(snapshot, trip_identity, target, *, decision_at,
                        stop_id=None, from_stop_id=None, to_stop_id=None):
    """Return a label-free case suitable for ComponentPredictor.predict_case.

    Use the exact normalized trip identity, not a raw provider trip identifier.
    Arrival and departure need a stop_id (from_stop_id is also accepted for
    departure). A segment needs from_stop_id and to_stop_id. Invalid or stale
    evidence raises ValueError; callers retain their existing unavailable or
    baseline policy instead of manufacturing a model input.
    """
    if target not in {"arrival", "departure", "segment"}:
        raise ValueError("Unsupported component target.")
    if not isinstance(snapshot, dict) or snapshot.get("kind") != "train" or snapshot.get("status") != "AVAILABLE":
        raise ValueError("An available normalized train snapshot is required.")
    decision = _epoch(decision_at)
    source_time = _epoch(snapshot.get("source_updated_at"))
    fetched = _epoch(snapshot.get("fetched_at"))
    requested = _epoch(snapshot.get("requested_at", snapshot.get("fetched_at")))
    if not requested <= fetched <= decision or not source_time <= fetched:
        raise ValueError("Snapshot observations must be available by the decision cutoff.")
    if not 0 <= decision - source_time <= 180:
        raise ValueError("Train snapshot exceeds the model freshness scope.")
    trips = [trip for trip in snapshot.get("trips", []) if trip.get("id") == trip_identity]
    if len(trips) != 1 or not isinstance(trip_identity, str) or not trip_identity:
        raise ValueError("Exactly one service-qualified trip must match.")
    trip = trips[0]
    if trip.get("schedule_relationship") in {"CANCELED", "DELETED"}:
        raise ValueError("Canceled or deleted trains have no supported prediction.")
    if not trip.get("route_id") or not snapshot.get("feed_id"):
        raise ValueError("Route and feed identity are required.")
    if trip.get("feed_id") is not None and trip["feed_id"] != snapshot["feed_id"]:
        raise ValueError("Trip belongs to a different feed.")
    observed = trip.get("timestamp")
    trip_age = None
    if observed is not None:
        observed = _epoch(observed)
        trip_age = decision - observed
        if observed > fetched or not 0 <= trip_age <= 180:
            raise ValueError("Trip observation is stale or not available at the cutoff.")
    updates = trip.get("stop_updates", [])
    pattern = [item.get("stop_id") for item in updates]
    if not pattern or any(not isinstance(item, str) or not item for item in pattern) or len(set(pattern)) != len(pattern):
        raise ValueError("A unique ordered stop pattern is required.")
    origin = stop_id if target == "arrival" else from_stop_id or stop_id
    destination = to_stop_id if target == "segment" else origin
    if origin not in pattern or destination not in pattern:
        raise ValueError("Requested component endpoints must exist in the trip.")
    first, last = pattern.index(origin), pattern.index(destination)
    if target == "segment" and first >= last:
        raise ValueError("Segment destination must follow its departure stop.")
    relevant_start = first if target == "segment" else 0
    for index in range(relevant_start, last + 1):
        if updates[index].get("schedule_relationship") in {"SKIPPED", "NO_DATA"}:
            raise ValueError("Skipped or unavailable stops in this component's path are unsupported.")
    try:
        local = datetime.fromtimestamp(decision, LOCAL_ZONE)
    except (OverflowError, OSError, ValueError):
        raise ValueError("Decision timestamp is outside the supported calendar.") from None
    day_type = "WEEKDAY" if local.weekday() < 5 else "SATURDAY" if local.weekday() == 5 else "SUNDAY"
    canonical = {
        "route_id": trip["route_id"], "feed_id": snapshot["feed_id"],
        "direction": trip.get("nyct_direction"), "gtfs_direction_id": trip.get("direction_id"),
        "day_type": day_type,
        "seconds_since_local_midnight": local.hour * 3600 + local.minute * 60 + local.second,
        "feed_age_seconds": decision - source_time, "trip_update_age_seconds": trip_age,
        "is_assigned": trip.get("is_assigned"), "remaining_stop_pattern": pattern,
    }
    basis = None
    if target == "arrival":
        arrival = _epoch(updates[first].get("arrival_time"))
        baseline = horizon = arrival - decision
        canonical.update(stop_id=origin, prediction_horizon_seconds=horizon)
    else:
        # Arrival is not a substitute for the departure target used in training.
        departure = _epoch(updates[first].get("departure_time"))
        horizon = departure - decision
        basis = "DEPARTURE_PREDICTION"
        canonical.update(from_stop_id=origin, departure_horizon_seconds=horizon,
                         origin_prediction_basis=basis)
        baseline = horizon
        if target == "segment":
            arrival = _epoch(updates[last].get("arrival_time"))
            baseline = arrival - departure
            if baseline < 0 or horizon_bucket(arrival - decision) is None:
                raise ValueError("Segment time order or arrival horizon is unsupported.")
            canonical.update(to_stop_id=destination, predicted_duration_seconds=baseline,
                             arrival_horizon_seconds=arrival - decision,
                             segment_stop_pattern=pattern[first:last + 1])
    if horizon_bucket(horizon) is None:
        raise ValueError("Component lies outside the zero-to-thirty-minute horizon.")
    features = build_features(target, canonical)
    return {
        "schema_version": "model-inference-case-v1", "feature_version": FEATURE_VERSION,
        "target": target, "trip_identity": trip_identity, "decision_at": decision,
        "route_id": trip["route_id"], "day_type": day_type,
        "baseline_seconds": baseline, "horizon_bucket": horizon_bucket(horizon),
        "origin_prediction_basis": basis, "features": features,
        "support_key": support_key(target, features, canonical),
        "support_keys": support_keys(target, features, canonical),
        "support_source": {"remaining_stop_pattern": pattern},
        "source_updated_at": source_time, "fetched_at": fetched,
        "label_evidence": None,
    }
