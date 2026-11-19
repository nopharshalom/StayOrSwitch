"""Train-only historical estimates and bounded component model inference."""

from collections import defaultdict
import math

from .artifacts import ROOT, read_json, repository_path, runtime_versions, verify_frozen


def _group_keys(row):
    """No key contains trip identity, dates, outcomes, or quality flags."""
    features = row["features"]
    route = row.get("route_id", features.get("route_id", "UNKNOWN"))
    day = row.get("day_type", features.get("day_type", "UNKNOWN"))
    horizon = row["horizon_bucket"]
    # Circular clock features are also the shared online representation.
    sine, cosine = features.get("time_sin"), features.get("time_cos")
    clock = math.atan2(sine, cosine) if sine is not None and cosine is not None else None
    hour_bin = "UNKNOWN" if clock is None else int(((clock % (2 * math.pi)) / (2 * math.pi) * 24) // 2)
    return [
        str((row["support_key"], day, hour_bin, horizon)),
        str((route, day, horizon)),
        str((route, horizon)),
        str((horizon,)),
        "GLOBAL",
    ]


def fit_historical(rows, min_events):
    """Fit a weighted hierarchical residual mean using training rows only."""
    totals = defaultdict(lambda: [0.0, 0.0, set()])
    for row in rows:
        if row["split"] != "train":
            raise ValueError("Historical statistics can only use training rows.")
        for key in _group_keys(row):
            total = totals[key]
            total[0] += row["weight"] * row["target_residual_seconds"]
            total[1] += row["weight"]
            total[2].add(row["event_id"])
    if not totals:
        raise ValueError("Cannot fit an empty historical baseline.")
    return {"min_events": min_events, "groups": {
        key: {"mean_residual_seconds": values[0] / values[1],
              "event_count": len(values[2]), "event_weight_sum": values[1]}
        for key, values in sorted(totals.items())}}


def historical_residual(model, row):
    for key in _group_keys(row):
        group = model["groups"].get(key)
        if group and (group["event_count"] >= model["min_events"] or key == "GLOBAL"):
            return group["mean_residual_seconds"]
    return 0.0


def fit_support(rows, min_events):
    events = defaultdict(set)
    for row in rows:
        if row["split"] != "train":
            raise ValueError("Support can only use training rows.")
        for key in row.get("support_keys", [row["support_key"]]):
            events[key].add(row["event_id"])
    return {"min_events": min_events,
            "event_counts": {key: len(value) for key, value in sorted(events.items())}}


def _finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def supported(support, row, max_horizon=1800):
    features = row["features"]
    horizon = features.get("horizon_seconds", features.get("arrival_horizon_seconds"))
    age, trip_age = features.get("feed_age_seconds"), features.get("trip_update_age_seconds")
    return (_finite(horizon) and _finite(age) and 0 <= age <= 180
            and (trip_age is None or (_finite(trip_age) and 0 <= trip_age <= 180))
            and 0 <= horizon <= max_horizon
            and support["event_counts"].get(row["support_key"], 0) >= support["min_events"])


def final_seconds(baseline, residual, floor=0.0):
    if not all(_finite(value) for value in (baseline, residual, floor)) or baseline < 0:
        raise ValueError("Component durations and corrections must be finite.")
    return max(floor, baseline + residual)


def feature_names(target, feature_set):
    from data.modeling.features import FEATURE_NAMES
    names = list(FEATURE_NAMES[target])
    if feature_set == "without_clock":
        names = [name for name in names if name not in ("time_sin", "time_cos")]
    elif feature_set != "core":
        raise ValueError("Unknown frozen feature set.")
    return names


def feature_matrix(rows, target, names):
    """Use the data-owned feature vector; never infer predictors from metadata."""
    from data.modeling.features import FEATURE_NAMES, feature_vector
    full_names = list(FEATURE_NAMES[target])
    positions = [full_names.index(name) for name in names]
    return [[vector[position] for position in positions]
            for vector in (feature_vector(target, row["features"]) for row in rows)]


def predictions(model, history, support, rows, target, names, config):
    raw = model.predict(feature_matrix(rows, target, names))
    mask = [supported(support, row, config["max_horizon_seconds"]) for row in rows]
    baseline = [row["baseline_seconds"] for row in rows]
    floor = config["prediction_floor_seconds"]
    return {
        "mta": baseline,
        "history": [final_seconds(value, historical_residual(history, row), floor)
                    for value, row in zip(baseline, rows)],
        "model": [final_seconds(value, float(delta) if allowed else 0.0, floor)
                  for value, delta, allowed in zip(baseline, raw, mask)],
        "raw_model": [final_seconds(value, float(delta), floor)
                      for value, delta in zip(baseline, raw)],
    }, mask


class ComponentPredictor:
    """Explicit experimental inference; this does not enable the live comparator.

    The caller supplies a canonical data-owned feature object and component
    baseline. Unsupported inputs return the unchanged baseline. Historical
    row labels are neither required nor read by this interface.
    """

    def __init__(self, frozen_path, target, *, root=ROOT):
        from catboost import CatBoostRegressor
        from data.modeling.features import FEATURE_NAMES, CATEGORICAL_FEATURES
        self.frozen = verify_frozen(frozen_path, root=root)["payload"]
        if self.frozen["versions"] != runtime_versions():
            raise ValueError("Runtime versions differ from the frozen model environment.")
        if target not in self.frozen["targets"]:
            raise ValueError("Target is absent from the frozen experiment.")
        self.target = target
        self.metadata = self.frozen["targets"][target]
        self.config = self.frozen["configuration"]
        self.names = self.metadata["feature_names"]
        if self.names != feature_names(target, self.metadata["candidate"]["feature_set"]):
            raise ValueError("Current feature order differs from the trained model.")
        if self.metadata["categorical_features"] != [name for name in self.names if name in CATEGORICAL_FEATURES[target]]:
            raise ValueError("Current categorical feature types differ from training.")
        self.required_features = list(FEATURE_NAMES[target])
        self.support = read_json(repository_path(self.metadata["support_path"], root))
        self.model = CatBoostRegressor()
        self.model.load_model(str(repository_path(self.metadata["model_path"], root)))

    def predict_case(self, case):
        from data.modeling.features import support_key
        features, baseline_seconds = case["features"], case["baseline_seconds"]
        if case.get("target") != self.target:
            raise ValueError("Prediction target differs from the loaded component model.")
        if set(features) != set(self.required_features):
            raise ValueError("Prediction requires exactly the canonical feature allowlist.")
        if not _finite(baseline_seconds) or baseline_seconds < 0:
            raise ValueError("Baseline component seconds must be finite and nonnegative.")
        expected = features.get("predicted_duration_seconds" if self.target == "segment" else "horizon_seconds")
        if not _finite(expected) or abs(expected - baseline_seconds) > 1e-6:
            raise ValueError("Baseline seconds disagree with the target's canonical feature.")
        if self.target == "segment":
            departure, arrival = features.get("departure_horizon_seconds"), features.get("arrival_horizon_seconds")
            if (not _finite(departure) or not _finite(arrival) or departure < 0 or arrival < departure
                    or abs(arrival - departure - baseline_seconds) > 1e-6):
                raise ValueError("Segment endpoint horizons disagree with its duration.")
        key = support_key(self.target, features, case.get("support_source"))
        if case.get("support_key") != key:
            raise ValueError("Operating support key does not match canonical feature context.")
        row = {"features": features, "support_key": key}
        allowed = supported(self.support, row, self.config["max_horizon_seconds"])
        if self.target != "arrival" and case.get("origin_prediction_basis") != "DEPARTURE_PREDICTION":
            allowed = False
        if not allowed:
            return {"target": self.target, "seconds": baseline_seconds, "correction_seconds": 0.0,
                    "method": "MTA_FALLBACK", "reason": "UNSUPPORTED_COMPONENT_OR_HORIZON",
                    "uncertainty": None, "live_enabled": False}
        raw = float(self.model.predict(feature_matrix([row], self.target, self.names))[0])
        value = final_seconds(baseline_seconds, raw, self.config["prediction_floor_seconds"])
        return {"target": self.target, "seconds": value, "correction_seconds": value - baseline_seconds,
                "raw_residual_seconds": raw, "prediction_floor_applied": value != baseline_seconds + raw,
                "method": "EXPERIMENTAL_COMPONENT_MODEL", "reason": None,
                "model_version": self.frozen["experiment_version"], "uncertainty": None, "live_enabled": False}
