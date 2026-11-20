"""Symmetric physical sanity checks for an already selected train outcome.

The straight-line speed ceiling is a permissive data-quality screen, not a
subway operating-speed claim. It neither changes predictions nor selects a
replacement train. Raw endpoint timestamps remain available for audit.
"""

from copy import deepcopy
import json
import math
from pathlib import Path

from data.october.sources import sha256


SCHEMA_VERSION = "selected-route-outcome-sanity-v1"
DEFAULT_CONFIG = "data/config/november-feed-outcome-quality.json"
IMPLAUSIBLE_FLAG = "IMPLAUSIBLE_LEG_TRAVEL_TIME"
MISSING_COORDINATES_FLAG = "MISSING_OUTCOME_STATION_COORDINATES"


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def haversine_km(first, second, radius_km=6371.0088):
    """Compute great-circle station distance without inferring track length."""
    lat1, lon1 = math.radians(first["latitude"]), math.radians(first["longitude"])
    lat2, lon2 = math.radians(second["latitude"]), math.radians(second["longitude"])
    term = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(min(1.0, max(0.0, term))))


class OutcomeQualityScreen:
    """Add outcome evidence/flags without altering any original timestamp."""

    def __init__(self, coordinates, *, max_straight_line_speed_kmh=300.0,
                 earth_radius_km=6371.0088, provenance=None):
        for name, value in (("Speed ceiling", max_straight_line_speed_kmh), ("Earth radius", earth_radius_km)):
            if not _finite(value) or value <= 0:
                raise ValueError(name + " must be finite and positive.")
        self.coordinates = deepcopy(coordinates)
        for stop_id, row in self.coordinates.items():
            if (not isinstance(stop_id, str) or not stop_id
                    or not _finite(row.get("latitude")) or not -90 <= row["latitude"] <= 90
                    or not _finite(row.get("longitude")) or not -180 <= row["longitude"] <= 180):
                raise ValueError("Station coordinates must be finite geographic values.")
        self.max_speed = float(max_straight_line_speed_kmh)
        self.radius = float(earth_radius_km)
        self.provenance = deepcopy(provenance or {})

    def screen(self, event):
        result = deepcopy(event)
        departure, arrival = event.get("departure_at"), event.get("arrival_at")
        flags = event.get("endpoint_flags") or {}
        result["endpoint_flags"] = deepcopy(flags)
        quality = {
            "schema_version": SCHEMA_VERSION,
            "rule": "MAXIMUM_STRAIGHT_LINE_AVERAGE_SPEED",
            "max_straight_line_speed_kmh": self.max_speed,
            "earth_radius_km": self.radius,
            "from_stop_id": event.get("from_stop_id"), "to_stop_id": event.get("to_stop_id"),
            "raw_departure_at": departure, "raw_arrival_at": arrival,
            "distance_km": None, "duration_seconds": None, "implied_speed_kmh": None,
            "flags": [], "selection_affected": False,
        }
        result["outcome_quality"] = quality
        if (not _finite(departure) or not _finite(arrival)
                or flags.get("boarding") or flags.get("alighting")):
            quality["status"] = "NOT_APPLIED_ENDPOINTS_ALREADY_UNUSABLE"
            return result
        quality["duration_seconds"] = arrival - departure
        missing = [stop for stop in (event.get("from_stop_id"), event.get("to_stop_id"))
                   if stop not in self.coordinates]
        if missing:
            quality.update(status="UNAVAILABLE_COORDINATES", missing_stop_ids=missing,
                           flags=[MISSING_COORDINATES_FLAG])
        else:
            distance = haversine_km(self.coordinates[event["from_stop_id"]],
                                    self.coordinates[event["to_stop_id"]], self.radius)
            duration = arrival - departure
            speed = distance * 3600 / duration if duration > 0 else (0.0 if distance == 0 and duration == 0 else None)
            quality.update(distance_km=distance, implied_speed_kmh=speed)
            impossible = duration < 0 or (duration == 0 and distance > 0) or (speed is not None and speed > self.max_speed)
            quality.update(status="REJECTED_IMPLAUSIBLE_TRAVEL_TIME" if impossible else "PASSED",
                           flags=[IMPLAUSIBLE_FLAG] if impossible else [])
        if quality["flags"]:
            endpoint_flags = result.setdefault("endpoint_flags", {})
            endpoint_flags["alighting"] = sorted(set(endpoint_flags.get("alighting", [])) | set(quality["flags"]))
        return result


def load_outcome_quality(root, config_path=DEFAULT_CONFIG):
    """Load the portable station subset and verify its exact recorded hash."""
    root = Path(root)
    config_path = Path(config_path)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = json.loads(config_path.read_text())
    if (config.get("schema_version") != "feed-following-outcome-quality-v1"
            or config.get("scope") != "POST_SELECTION_SELECTED_TRAIN_OUTCOME_ONLY"
            or config.get("rule") != "MAXIMUM_STRAIGHT_LINE_AVERAGE_SPEED"
            or config.get("flag_endpoint") != "alighting"
            or config.get("implausible_flag") != IMPLAUSIBLE_FLAG
            or config.get("missing_coordinates_flag") != MISSING_COORDINATES_FLAG
            or config.get("retain_raw_endpoint_values") is not True
            or config.get("changes_forecasts_or_candidate_selection") is not False):
        raise ValueError("Outcome quality configuration has an unsupported scope.")
    station_source = config["station_source"]
    station_path = Path(station_source["path"])
    if not station_path.is_absolute():
        station_path = root / station_path
    if sha256(station_path) != station_source["sha256"]:
        raise ValueError("Station-coordinate subset hash mismatch.")
    stations = json.loads(station_path.read_text())
    if (stations.get("schema_version") != "approved-route-station-coordinates-v1"
            or stations.get("station_count") != len(stations["coordinates"])):
        raise ValueError("Station-coordinate subset is inconsistent.")
    provenance = {
        "config": {"path": str(config_path.relative_to(root)), "sha256": sha256(config_path)},
        "station_source": {"path": str(station_path.relative_to(root)), "sha256": sha256(station_path)},
        "producer": {"path": "data/route_outcome_sanity.py", "sha256": sha256(root / "data/route_outcome_sanity.py")},
        "raw_official_source": stations["raw_official_source"],
    }
    return OutcomeQualityScreen(stations["coordinates"],
        max_straight_line_speed_kmh=config["max_straight_line_speed_kmh"],
        earth_radius_km=config["earth_radius_km"], provenance=provenance)
