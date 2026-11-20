"""Choose a commuter action from boarding-safe route forecasts at one cutoff."""
import math

from .severe import decide


def timed(route):
    value = route.get("total_duration_seconds")
    return (
        route.get("timing_eligible") is True
        and isinstance(value, (float, int))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def commuter_advice(model, raw, reference):
    """Keep supported strict advice; compare usable paths when coverage is partial."""
    if (
        model["cutoff"] != raw["cutoff"]
        or model["mode"] != "incident_profile"
        or raw["mode"] != "mta"
    ):
        raise ValueError("Incident-profile and raw-MTA forecasts must share a cutoff.")
    by_model = {r["id"]: r for r in model["routes"]}
    by_raw = {r["id"]: r for r in raw["routes"]}
    if len(by_model) != len(model["routes"]) or len(by_raw) != len(raw["routes"]):
        raise ValueError("Each forecast must have unique route IDs.")
    if set(by_model) != set(by_raw) or reference not in by_model:
        raise ValueError(
            "Both policies must describe the same routes and Stay reference."
        )
    raw_only = not timed(by_model[reference]) and timed(by_raw[reference])
    routes = by_raw if raw_only else by_model
    current = routes[reference]
    valid = [r for rid, r in routes.items() if rid != reference and timed(r)]
    valid.sort(key=lambda r: (r["total_duration_seconds"], r["id"]))
    best = valid[0] if valid else None
    seconds = current.get("total_duration_seconds") if timed(current) else None
    strict = decide(
        model,
        reference,
        switch_margin_seconds=0.10
        * (by_model[reference].get("total_duration_seconds") or 0),
        require_severe=False,
    )["strict_decision"]
    result = dict(
        action="UNDETERMINED",
        route_id=None,
        reference=reference,
        stay_seconds=seconds,
        alternative_id=best["id"] if best else None,
        alternative_seconds=best["total_duration_seconds"] if best else None,
        timed_alternatives=len(valid),
        supplied_alternatives=len(routes) - 1,
        forecast_source="raw" if raw_only else "model",
        strict_action=strict["action"],
    )
    if strict["action"] in {"STAY", "SWITCH"}:
        result.update(
            action=strict["action"],
            route_id=strict["recommended_itinerary_id"],
            basis="STRICT",
        )
    elif seconds is None:
        result.update(basis="NO_USABLE_STAY_ETA")
    elif best is None:
        result.update(action="MONITOR", route_id=reference, basis="ONLY_STAY_TIMED")
    elif seconds - best["total_duration_seconds"] < 0.10 * seconds:
        result.update(action="STAY", route_id=reference, basis="COMPARED_AVAILABLE")
    else:
        # Uncertain service notices can coexist with sound train timing. For an
        # added Switch, require both forecasts to support this same alternative.
        raw_ref, raw_alt = by_raw[reference], by_raw[best["id"]]
        supported = all(timed(r) for r in (raw_ref, raw_alt)) and (
            raw_ref["total_duration_seconds"] - raw_alt["total_duration_seconds"]
            >= 0.10 * raw_ref["total_duration_seconds"]
        )
        if raw_only or not supported:
            result.update(
                action="MONITOR", route_id=reference, basis="SWITCH_NOT_CORROBORATED"
            )
        else:
            result.update(
                action="SWITCH", route_id=best["id"], basis="MODEL_AND_RAW_TIMING"
            )
    return result
