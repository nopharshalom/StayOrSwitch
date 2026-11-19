"""Event-weighted proxy-label metrics on identical held-out component cases.

Prediction values are final durations or horizons in seconds, never residuals.
Weights are supplied by the event-balanced data view. Quantiles use the inverse
weighted empirical CDF without interpolation. No independence or physical
ground-truth claim is implied by the number of retained prediction rows.
"""

from collections import defaultdict
import math


GROUP_FIELDS = (
    ("by_day_type", "day_type"),
    ("by_date", "decision_date"),
    ("by_route", "route_id"),
    ("by_horizon", "horizon_bucket"),
    ("by_disruption", "disruption_group"),
    ("by_revision", "revision_group"),
)


def _number(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool):
        raise ValueError(name + " must be numeric, not boolean.")
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(name + " must be a finite number.") from error
    if not math.isfinite(value):
        raise ValueError(name + " must be finite.")
    if positive and value <= 0:
        raise ValueError(name + " must be positive.")
    if nonnegative and value < 0:
        raise ValueError(name + " must be nonnegative.")
    return value


def weighted_quantile(values, weights, probability):
    """Return the inverse weighted empirical CDF at a probability in [0, 1]."""
    if len(values) != len(weights) or not values:
        raise ValueError("Quantiles require equally sized nonempty inputs.")
    probability = _number(probability, "probability", nonnegative=True)
    if probability > 1:
        raise ValueError("probability must not exceed one.")
    pairs = sorted((_number(value, "value"), _number(weight, "weight", positive=True))
                   for value, weight in zip(values, weights))
    threshold = probability * math.fsum(weight for _, weight in pairs)
    cumulative = 0.0
    compensation = 0.0
    for value, weight in pairs:
        # Compensated addition keeps decimal-weight boundaries stable; naive
        # accumulation can incorrectly move a quantile to the next value.
        corrected = weight - compensation
        next_total = cumulative + corrected
        compensation = (next_total - cumulative) - corrected
        cumulative = next_total
        if cumulative >= threshold:
            return value
    return pairs[-1][0]


def _metrics(errors, weights):
    weight_sum = math.fsum(weights)
    absolute = [abs(error) for error in errors]
    return {
        "mae_seconds": math.fsum(value * weight for value, weight in zip(absolute, weights)) / weight_sum,
        "rmse_seconds": math.sqrt(math.fsum(error * error * weight for error, weight in zip(errors, weights)) / weight_sum),
        "median_absolute_error_seconds": weighted_quantile(absolute, weights, 0.5),
        "p90_absolute_error_seconds": weighted_quantile(absolute, weights, 0.9),
        "bias_seconds": math.fsum(error * weight for error, weight in zip(errors, weights)) / weight_sum,
    }


def _summarize(rows, indices, errors, weights, applied):
    local_weights = [weights[index] for index in indices]
    total = math.fsum(local_weights)
    method_errors = {name: [values[index] for index in indices] for name, values in errors.items()}
    methods = {name: _metrics(values, local_weights) for name, values in method_errors.items()}
    result = {
        "row_count": len(indices),
        "event_count": len({rows[index]["event_id"] for index in indices}),
        "trip_count": len({rows[index]["trip_identity"] for index in indices}),
        "date_count": len({rows[index]["decision_date"] for index in indices
                           if rows[index].get("decision_date")}),
        "event_weight_sum": total,
        "methods": methods,
        "uncertainty": None,
        "paired_improvements": {},
    }
    for reference in ("mta", "history"):
        if reference not in methods:
            continue
        result["paired_improvements"][reference] = {}
        reference_errors = method_errors[reference]
        for name, values in method_errors.items():
            if name == reference:
                continue
            result["paired_improvements"][reference][name] = {
                "mae_reduction_seconds": methods[reference]["mae_seconds"] - methods[name]["mae_seconds"],
                "rmse_reduction_seconds": methods[reference]["rmse_seconds"] - methods[name]["rmse_seconds"],
                "p90_reduction_seconds": methods[reference]["p90_absolute_error_seconds"] - methods[name]["p90_absolute_error_seconds"],
                "lower_absolute_error_weight_fraction": math.fsum(
                    weight for value, ref, weight in zip(values, reference_errors, local_weights)
                    if abs(value) < abs(ref)) / total,
                "equal_absolute_error_weight_fraction": math.fsum(
                    weight for value, ref, weight in zip(values, reference_errors, local_weights)
                    if abs(value) == abs(ref)) / total,
            }
    if applied:
        result["model_coverage"] = {}
        for name, mask in applied.items():
            used = [index for index in indices if mask[index]]
            applied_weight = math.fsum(weights[index] for index in used)
            result["model_coverage"][name] = {
                "applied_rows": len(used),
                "fallback_rows": len(indices) - len(used),
                "applied_row_fraction": len(used) / len(indices),
                "applied_event_weight_fraction": applied_weight / total,
            }
    return result


def evaluate_predictions(rows, predictions, model_applied=None):
    """Compare final-second predictions on the same event-weighted examples.

    ``predictions`` maps method names to equally sized numerical sequences.
    ``model_applied`` may be one boolean sequence (reported as ``model``) or a
    mapping from method names to boolean sequences. False marks a fallback;
    fallback predictions remain in every accuracy metric and denominator.
    Missing group metadata is reported under ``UNKNOWN`` rather than omitted.
    """
    if not rows or not predictions:
        raise ValueError("Evaluation requires nonempty rows and predictions.")
    targets = {row.get("target") for row in rows}
    if len(targets) != 1:
        raise ValueError("Evaluate component targets separately.")
    for row in rows:
        if not row.get("event_id") or not row.get("trip_identity"):
            raise ValueError("Each evaluation row needs event and trip identity.")
    weights = [_number(row["weight"], "weight", positive=True) for row in rows]
    labels = [_number(row["label_seconds"], "label_seconds", nonnegative=True) for row in rows]
    errors = {}
    for name, values in predictions.items():
        if not isinstance(name, str) or not name or len(values) != len(rows):
            raise ValueError("Every named prediction method must cover every row.")
        actual = [_number(value, "prediction", nonnegative=True) for value in values]
        errors[name] = [label - value for label, value in zip(labels, actual)]
    applied = {}
    if model_applied is not None:
        masks = model_applied if isinstance(model_applied, dict) else {"model": model_applied}
        for name, mask in masks.items():
            if len(mask) != len(rows) or any(not isinstance(value, bool) for value in mask):
                raise ValueError("Model applicability masks must be boolean and cover every row.")
            applied[name] = [bool(value) for value in mask]
    result = {
        "weighting": "EVENT_BALANCED_VIEW_WEIGHTS",
        "error_sign": "LABEL_MINUS_PREDICTION",
        "quantile_method": "INVERSE_WEIGHTED_EMPIRICAL_CDF",
        "label_evidence": "INFERRED_MTA_FINAL_PREDICTION_PROXY",
        "physical_ground_truth": False,
        "uncertainty_note": "No confidence interval: prediction rows share events, trips, dates and incidents.",
        "overall": _summarize(rows, list(range(len(rows))), errors, weights, applied),
    }
    for output, field in GROUP_FIELDS:
        groups = defaultdict(list)
        for index, row in enumerate(rows):
            value = row.get(field)
            groups["UNKNOWN" if value is None or value == "" else str(value)].append(index)
        result[output] = {
            name: _summarize(rows, indices, errors, weights, applied)
            for name, indices in sorted(groups.items())
        }
    return result
