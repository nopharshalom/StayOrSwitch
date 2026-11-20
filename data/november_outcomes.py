"""Additional endpoint-age screening for the new November analyses only.

Original labels and frozen October experiments remain unchanged. A usable
endpoint must also have a finite last observation within 180 seconds on either
side of its final-prediction proxy. This is a quality screen, not proof of a
physical train arrival.
"""

from collections import Counter
from copy import deepcopy
import math
from urllib.parse import unquote

from data.delay_profiles.common import epoch


MAX_ENDPOINT_AGE_SECONDS = 180


def endpoint_diagnostics(label, endpoint, max_age_seconds=MAX_ENDPOINT_AGE_SECONDS):
    """Return outcome-only observation age and exclusion without altering input."""
    if endpoint not in ("arrival", "departure"):
        raise ValueError("Endpoint must be arrival or departure.")
    if (isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, (int, float))
            or not math.isfinite(max_age_seconds) or max_age_seconds < 0):
        raise ValueError("Endpoint age limit must be finite and nonnegative.")
    try:
        observed = epoch((label or {}).get("stop_last_observed_at"))
        at = epoch((label or {}).get(endpoint + "_at"))
    except (ValueError, TypeError, OverflowError):
        observed = at = None
    age = abs(observed - at) if observed is not None and at is not None else None
    reason = ("MISSING_OR_INVALID_ENDPOINT_OBSERVATION_AGE" if age is None or not math.isfinite(age) else
              "ENDPOINT_OBSERVATION_AGE_EXCEEDS_LIMIT" if age > max_age_seconds else None)
    try:
        confirmed = epoch((label or {}).get("confirmed_at"))
    except (ValueError, TypeError, OverflowError):
        confirmed = None
    confirmation_eligible = ((label or {}).get("confirmation_status") == "CONFIRMED"
                             and confirmed is not None and math.isfinite(confirmed))
    reasons = ([reason] if reason else [])
    if not confirmation_eligible:
        reasons.append("MISSING_OR_INVALID_ARCHIVED_CONFIRMATION")
    return {"endpoint": endpoint, "absolute_observation_age_seconds": age,
            "max_age_seconds": max_age_seconds, "age_eligible": reason is None,
            "confirmation_eligible": confirmation_eligible, "eligible": not reasons,
            "reason": reasons[0] if reasons else None, "reasons": reasons}


def identity_eligible(identity, stop_id, label):
    """Check encoded normalized identity against the independent journal label."""
    parts = identity.split(":") if isinstance(identity, str) else []
    if len(parts) != 6 or parts[0] != "MTA":
        return False
    decoded = [unquote(part) for part in parts]
    expected = {"feed_id": decoded[1], "service_date": decoded[2],
                "route_id": decoded[3], "raw_trip_id": decoded[4], "stop_id": stop_id}
    return all(label.get(key) == value for key, value in expected.items())


def screen_labels(labels, max_age_seconds=MAX_ENDPOINT_AGE_SECONDS):
    """Copy nested train/stop labels and add endpoint-specific quality flags.

    Return ``(screened_labels, report)``. Existing exclusion flags and false
    usability stay false; passing this extra test never rehabilitates a label.
    Every endpoint is screened independently, including originally unusable
    endpoints, to make the quality accounting reproducible.
    """
    # Validate even when the input mapping is empty.
    endpoint_diagnostics({}, "arrival", max_age_seconds)
    result = deepcopy(labels)
    counts = Counter()
    for identity, stops in result.items():
        for stop_id, label in stops.items():
            counts["label_records"] += 1
            identity_ok = identity_eligible(identity, stop_id, label)
            for endpoint in ("arrival", "departure"):
                key = endpoint + "_usable"
                diagnostic = endpoint_diagnostics(label, endpoint, max_age_seconds)
                reasons = list(diagnostic["reasons"])
                if not identity_ok:
                    reasons.append("NORMALIZED_TRAIN_OR_STOP_LABEL_IDENTITY_MISMATCH")
                counts[endpoint + "_endpoints"] += 1
                if label.get(key) is True:
                    counts[endpoint + "_originally_usable"] += 1
                if reasons:
                    if label.get(key) is True:
                        counts[endpoint + "_newly_excluded"] += 1
                    label[key] = False
                    flag_key = endpoint + "_quality_flags"
                    label[flag_key] = sorted(set(label.get(flag_key, [])) | set(reasons))
                    for reason in reasons:
                        counts[endpoint + "_" + reason] += 1
                if label.get(key) is True:
                    counts[endpoint + "_retained_usable"] += 1
    return result, {"max_endpoint_age_seconds": max_age_seconds,
                    "uses_absolute_age": True, "original_labels_modified": False,
                    "requires_archived_confirmation": True,
                    "checks_encoded_identity": True,
                    "counts": dict(sorted(counts.items()))}
