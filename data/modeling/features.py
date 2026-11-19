"""Pure feature construction shared by offline preparation and inference.

The input is a canonical snapshot-derived feature dictionary, not a labeled row.
Callers must construct the dictionary at one collection-time cutoff. No outcomes,
raw trip identifiers, absolute dates, or absolute timestamps are model inputs.
"""

import json
import math


FEATURE_VERSION = "snapshot-core-v1"
COMMON_CATEGORICAL = ("route_id", "feed_id", "direction", "day_type")
COMMON_NUMERIC = ("time_sin", "time_cos", "feed_age_seconds",
                  "trip_update_age_seconds", "is_assigned")
CATEGORICAL_FEATURES = {
    "arrival": COMMON_CATEGORICAL + ("stop_id",),
    "departure": COMMON_CATEGORICAL + ("stop_id",),
    "segment": COMMON_CATEGORICAL + ("from_stop_id", "to_stop_id", "segment_pattern"),
}
FEATURE_NAMES = {
    "arrival": CATEGORICAL_FEATURES["arrival"] + COMMON_NUMERIC + ("horizon_seconds", "stops_until_target"),
    "departure": CATEGORICAL_FEATURES["departure"] + COMMON_NUMERIC + ("horizon_seconds", "stops_until_target"),
    "segment": CATEGORICAL_FEATURES["segment"] + COMMON_NUMERIC + (
        "predicted_duration_seconds", "departure_horizon_seconds", "arrival_horizon_seconds", "segment_stop_count"),
}
ROLLING_FEATURE_NAMES = ("previous_prediction_delta_seconds", "seconds_since_previous_prediction",
                         "prediction_revisions_last_10_minutes", "sampled_updates_last_10_minutes")


def _number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (float, int)) and math.isfinite(value):
        return value
    return None


def _category(value):
    return "UNKNOWN" if value is None or value == "" else str(value)


def normalized_direction(source, stop_id):
    """Platform direction has stable semantics; other namespaces stay distinct."""
    if isinstance(stop_id, str) and stop_id.endswith(("N", "S")):
        return "PLATFORM_" + stop_id[-1]
    direction = source.get("direction")
    if isinstance(direction, str) and direction.upper() in ("NORTH", "SOUTH", "EAST", "WEST"):
        return "NYCT_" + direction.upper()
    gtfs = source.get("gtfs_direction_id")
    if gtfs in (0, 1) and not isinstance(gtfs, bool):
        return "GTFS_" + str(gtfs)
    # Numeric direction without an explicit namespace is not interpreted.
    return "UNKNOWN"


def horizon_bucket(seconds):
    value = _number(seconds)
    if value is None or value < 0 or value > 1800:
        return None
    return "00_05_MIN" if value < 300 else "05_15_MIN" if value < 900 else "15_30_MIN"


def build_features(target, source, include_rolling=False):
    """Project canonical snapshot fields onto an explicit predictor allowlist."""
    if target not in FEATURE_NAMES:
        raise ValueError("Unsupported model target.")
    stop = source.get("stop_id") if target == "arrival" else source.get("from_stop_id", source.get("stop_id"))
    time = _number(source.get("seconds_since_local_midnight"))
    angle = None if time is None or not 0 <= time < 86400 else time * 2 * math.pi / 86400
    values = {key: _category(source.get(key)) for key in ("route_id", "feed_id", "day_type")}
    values.update(direction=normalized_direction(source, stop),
                  time_sin=None if angle is None else math.sin(angle),
                  time_cos=None if angle is None else math.cos(angle),
                  feed_age_seconds=_number(source.get("feed_age_seconds")),
                  trip_update_age_seconds=_number(source.get("trip_update_age_seconds")),
                  is_assigned=_number(source.get("is_assigned")))
    if target in ("arrival", "departure"):
        pattern = source.get("remaining_stop_pattern") or []
        horizon = source.get("prediction_horizon_seconds" if target == "arrival" else "departure_horizon_seconds")
        values.update(stop_id=_category(stop), horizon_seconds=_number(horizon),
                      stops_until_target=pattern.index(stop) if stop in pattern else None)
    else:
        pattern = source.get("segment_stop_pattern") or []
        values.update(from_stop_id=_category(source.get("from_stop_id")),
                      to_stop_id=_category(source.get("to_stop_id")),
                      segment_pattern="|".join(str(stop) for stop in pattern) if pattern else "UNKNOWN",
                      segment_stop_count=max(0, len(pattern) - 1) if pattern else None)
        for key in ("predicted_duration_seconds", "departure_horizon_seconds", "arrival_horizon_seconds"):
            values[key] = _number(source.get(key))
    result = {key: values[key] for key in FEATURE_NAMES[target]}
    if include_rolling:
        if target != "arrival":
            raise ValueError("Rolling features are defined only for arrival research.")
        result.update({key: _number(source.get(key)) for key in ROLLING_FEATURE_NAMES})
    return result


def feature_vector(target, features):
    """Return ordered core values; missing numerics are NaN, never zero."""
    return [(_category(features.get(key)) if key in CATEGORICAL_FEATURES[target]
             else float("nan") if _number(features.get(key)) is None else features[key])
            for key in FEATURE_NAMES[target]]


def support_key(target, features, source=None):
    """A concrete operating pattern key, separate from the predictor allowlist."""
    keys = ("route_id", "stop_id", "direction") if target != "segment" else (
        "route_id", "from_stop_id", "to_stop_id", "direction", "segment_pattern")
    values = [features.get(key, "UNKNOWN") for key in keys]
    if target != "segment":
        values.append(approach_pattern(features, source) if source is not None else ["UNSPECIFIED_PATTERN"])
    return json.dumps(values, separators=(",", ":"))


def approach_pattern(features, source):
    pattern = source.get("remaining_stop_pattern") or []
    stop = features["stop_id"]
    return pattern[:pattern.index(stop) + 1] if stop in pattern else ["UNKNOWN_PATTERN", stop]


def support_keys(target, features, source):
    """Training permits normal progress by learning each observed prefix suffix.

    Each event must contribute at most once to each key's support count. New
    stops or reordered paths do not match these suffixes and require fallback.
    """
    if target == "segment":
        return [support_key(target, features, source)]
    pattern = approach_pattern(features, source)
    if pattern[0] == "UNKNOWN_PATTERN":
        return [support_key(target, features, source)]
    return [support_key(target, features, {"remaining_stop_pattern": pattern[index:]})
            for index in range(len(pattern))]


def disruption_group(source, target):
    """Evaluation context only; absence of a fresh alert is not normal service."""
    if target == "departure":
        return "UNKNOWN_ALERT_STATE"
    if not source.get("service_alerts_available") or source.get("service_alert_status") != "FRESH":
        return "UNKNOWN_ALERT_STATE"
    if (source.get("service_alert_count") or 0) > 0:
        return "KNOWN_DISRUPTION"
    if (source.get("known_upcoming_service_alert_count") or 0) > 0:
        return "KNOWN_UPCOMING_ONLY"
    if (source.get("service_alert_possible_count") or 0) > 0 or (source.get("known_upcoming_service_alert_possible_count") or 0) > 0:
        return "POSSIBLE_DISRUPTION"
    return "FRESH_NO_KNOWN_DISRUPTION"


def revision_group(source, target):
    if (target != "arrival" or (source.get("sampled_updates_last_10_minutes") or 0) < 2
            or source.get("prediction_revisions_last_10_minutes") is None):
        return "UNAVAILABLE"
    return "REVISED" if (source.get("prediction_revisions_last_10_minutes") or 0) > 0 else "NOT_REVISED_IN_OBSERVED_WINDOW"
