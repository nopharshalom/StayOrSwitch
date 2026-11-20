"""Shared profile identities, time windows, and deterministic serialization."""

from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo


DEFAULT_PERIODS = (
    (0, 6, "OVERNIGHT"), (6, 10, "MORNING_PEAK"),
    (10, 11, "LATE_MORNING"), (11, 14, "MIDDAY"),
    (14, 16, "AFTERNOON"), (16, 20, "EVENING_PEAK"),
    (20, 24, "LATE_EVENING"),
)


def epoch(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("A timestamp cannot be boolean.")
    if isinstance(value, (float, int)):
        result = float(value)
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timestamp must specify a timezone.")
        result = parsed.timestamp()
    if not math.isfinite(result) or result < 0:
        raise ValueError("Timestamp must be finite and nonnegative.")
    return result


def local_fields(cutoff, config):
    local = datetime.fromtimestamp(epoch(cutoff), ZoneInfo(config.get("timezone", "America/New_York")))
    day = "SATURDAY" if local.weekday() == 5 else "SUNDAY" if local.weekday() == 6 else "WEEKDAY"
    periods = [(x["start_hour"], x["end_hour"], x["id"]) for x in config.get("periods", [])] or DEFAULT_PERIODS
    band = next((name for start, end, name in periods if start <= local.hour < end), None)
    if band is None:
        raise ValueError("The configured periods do not cover the query clock.")
    return {"date": local.date().isoformat(), "day_type": day, "period": band,
            "hour": local.hour, "minute": local.minute, "weekday": local.weekday()}


def horizon_group(seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds):
        return "UNAVAILABLE"
    if seconds < 0:
        return "EXPIRED"
    for upper, name in ((300, "00_05_MIN"), (900, "05_15_MIN"), (1800, "15_30_MIN"), (3600, "30_60_MIN")):
        if seconds < upper:
            return name
    return "OVER_60_MIN"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def read_json(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        return json.load(stream)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    if path.suffix == ".gz":
        with temporary.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            stream.write(canonical(value))
    else:
        temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def context_fields(context):
    state = context.get("state", "UNKNOWN")
    if state in {"TIME_ONLY", "ANY"}:
        return "ANY", "ANY", "ANY"
    evidence = context.get("evidence_status", "UNKNOWN")
    cause = context.get("cause") or "UNKNOWN"
    return state, cause, evidence


def group_candidates(target, route_id, start, end, cutoff, horizon_seconds, context, config):
    """Ordered hierarchy; every aggregate retains target, route and horizon."""
    fields = local_fields(cutoff, config)
    horizon = horizon_group(horizon_seconds)
    if target not in ("arrival", "departure"):
        raise ValueError("Profile target must be arrival or departure.")
    direction = start[-1] if start and start[-1] in "NS" else "UNKNOWN"
    base = {"target": target, "route_id": route_id, "direction": direction,
            "from_stop_id": start, "to_stop_id": end, "horizon": horizon,
            "day_type": fields["day_type"], "period": fields["period"]}
    state, cause, evidence = context_fields(context)
    output = []

    def add(level, state_value, cause_value, evidence_value, day, period, pair=True):
        key = dict(base, state=state_value, cause=cause_value, evidence_status=evidence_value,
                   day_type=day, period=period,
                   from_stop_id=start if pair else "ANY", to_stop_id=end if pair else "ANY")
        output.append((level, canonical(key).decode(), key))

    if state != "ANY":
        add("CONTEXT_EXACT", state, cause, evidence, fields["day_type"], fields["period"])
        add("CONTEXT_DAY", state, cause, evidence, fields["day_type"], "ANY")
        add("CONTEXT_SEGMENT", state, cause, evidence, "ANY", "ANY")
        add("STATE_SEGMENT", state, "ANY", evidence, "ANY", "ANY")
    add("TIME_EXACT", "ANY", "ANY", "ANY", fields["day_type"], fields["period"])
    add("TIME_DAY", "ANY", "ANY", "ANY", fields["day_type"], "ANY")
    add("TIME_SEGMENT", "ANY", "ANY", "ANY", "ANY", "ANY")
    add("TIME_ROUTE", "ANY", "ANY", "ANY", "ANY", "ANY", pair=False)
    return output


def end_of_date(value, zone="America/New_York"):
    from datetime import timedelta
    day = datetime.fromisoformat(value).date() + timedelta(days=1)
    return datetime.combine(day, datetime.min.time(), ZoneInfo(zone)).timestamp()
