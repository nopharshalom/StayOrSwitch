"""Extend projected train input coverage for new research route legs."""

from copy import deepcopy
from itertools import zip_longest

from data.october.sources import read_snapshots


REPLACEMENT_FEEDS = {"bdfm", "numbered"}
EXTRA_LEGS = [
    {"route_id": "F", "route_ids": ["F", "FX"], "feed_id": "bdfm", "from_stop_id": "F09S", "to_stop_id": "D16S"},
    {"route_id": "F", "route_ids": ["F", "FX"], "feed_id": "bdfm", "from_stop_id": "D16S", "to_stop_id": "A41S"},
    {"route_id": "7", "route_ids": ["7", "7X"], "feed_id": "numbered", "from_stop_id": "723S", "to_stop_id": "725S"},
]


def augmented_configuration(original):
    result = deepcopy(original)
    result["feed_ids"] = sorted(REPLACEMENT_FEEDS)
    result["stop_ids"] = sorted(set(result["stop_ids"]) | {"D16S"})
    for index, leg in enumerate(EXTRA_LEGS):
        result["routes"].append({"id": "supplemental_projection_" + str(index),
                                 "legs": [deepcopy(leg)]})
    return result


def check_snapshot_extension(old, new):
    """Permit added ordered stops only, preserving raw capture and trip facts."""
    before = {key: value for key, value in old.items() if key not in {"trips", "normalization_projection"}}
    after = {key: value for key, value in new.items() if key not in {"trips", "normalization_projection"}}
    if before != after:
        raise ValueError("Supplement changed capture identity, raw payload, or snapshot metadata.")
    if len(old.get("trips", [])) != len(new.get("trips", [])):
        raise ValueError("Supplement changed retained trip descriptor coverage.")
    added = 0
    for old_trip, new_trip in zip(old.get("trips", []), new.get("trips", [])):
        if ({key: value for key, value in old_trip.items() if key != "stop_updates"}
                != {key: value for key, value in new_trip.items() if key != "stop_updates"}):
            raise ValueError("Supplement changed trip identity, status, or other metadata.")
        old_stops, new_stops = old_trip.get("stop_updates", []), new_trip.get("stop_updates", [])
        pointer = 0
        for stop in new_stops:
            if pointer < len(old_stops) and stop == old_stops[pointer]:
                pointer += 1
        if pointer != len(old_stops):
            raise ValueError("An original stop value or its order changed.")
        added += len(new_stops) - len(old_stops)
    return added


def verify_daily_projection(original_path, supplemental_path):
    before = (row for row in read_snapshots(original_path)
              if row["feed_id"] in REPLACEMENT_FEEDS | {"subway-alerts"})
    after = read_snapshots(supplemental_path)
    count, added_stops, examples = 0, 0, {}
    for old, new in zip_longest(before, after):
        if old is None or new is None:
            raise ValueError("Supplement changed selected capture coverage.")
        added_stops += check_snapshot_extension(old, new)
        count += 1
        for old_trip, new_trip in zip(old.get("trips", []), new.get("trips", [])):
            previous = [stop["stop_id"] for stop in old_trip.get("stop_updates", [])]
            current = [stop["stop_id"] for stop in new_trip.get("stop_updates", [])]
            kind = None
            if (new_trip.get("route_id") in {"F", "FX"} and "F09S" not in current
                    and "D16S" not in previous and "D16S" in current and "A41S" in current):
                kind = "F_AFTER_COURT_SQUARE_NEW_BRYANT_PARK_BOARDING"
            if (new_trip.get("route_id") in {"7", "7X"} and "719S" not in current
                    and "724S" not in previous and all(stop in current for stop in ("723S", "724S", "725S"))):
                kind = "7_AFTER_COURT_SQUARE_NEW_GRAND_CENTRAL_LEG"
            if kind and kind not in examples:
                examples[kind] = {"kind": kind, "feed_id": new["feed_id"], "captured_at": new["captured_at"],
                    "trip_id": new_trip["id"], "raw_trip_id": new_trip["trip_id"],
                    "route_id": new_trip["route_id"], "raw_sha256": new.get("sha256"),
                    "archive_provenance": new["archive_provenance"],
                    "original_retained_stop_ids": previous, "supplemental_retained_stop_ids": current}
    return {"selected_captures_equal": True, "raw_hashes_and_capture_metadata_equal": True,
            "trip_descriptors_and_statuses_equal": True, "original_stop_values_and_order_preserved": True,
            "compared_captures": count, "additional_stop_updates": added_stops,
            "restored_coverage_examples": list(examples.values())}
