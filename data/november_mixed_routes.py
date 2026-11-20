"""Prepare sampled long-corridor feeds from the archived November protobufs."""
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import gzip
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2 as gtfs
from data.october.prepare import normalize, raw_receipt
from data.october.sources import iter_raw_snapshots, ROOT, sha256
from stayorswitch.mta import ROUTE_FEEDS

LOCAL = ROOT / "data/processed/november-mixed-relative"
BASE = ROOT / "algo/reports/november-feed-replay-test.json"
ZONE = ZoneInfo("America/New_York")
SOURCES = {
    "kewgardens_tandon": "pilot_hayden_tandon",
    "inwood207_boroughhall": "portauthority_tandon",
}
PAIRS = {
    "A": ("A02S", "A41S"),
    "1": ("108S", "123S"),
    "3": ("123S", "232S"),
    "F": ("F06S", "A41S"),
    "FX": ("F06S", "A41S"),
    "E": ("F06S", "E01S"),
    "R": ("R25S", "R29S"),
}
COHORTS = (
    "courtsquare_timessquare",
    "portauthority_tandon",
    "grandcentral_boroughhall",
)
CONFIG = ROOT / "data/config/november-mixed-relative-routes.json"


def configure():
    corridors = []
    for key, folder in [
        ("inwood207_boroughhall", "long-preview"),
        ("kewgardens_tandon", "long-preview-kew"),
    ]:
        path = ROOT / "data/local/google-corridors" / folder / (key + ".summary.json")
        s = json.loads(path.read_text())
        routes = []
        for itinerary in s["normalization"]["request"]["itineraries"]:
            legs, walks, walk = [], [], 0
            for step in itinerary["legs"]:
                if step["mode"] == "WALK":
                    walk += step["provider_duration_seconds"]
                    continue
                line = step["transit"]["route_short_name"]
                start, end = PAIRS[line]
                legs.append(
                    dict(
                        route_id=line,
                        route_ids=[line],
                        feed_id=ROUTE_FEEDS[line],
                        from_stop_id=start,
                        to_stop_id=end,
                    )
                )
                walks.append(walk)
                walk = 0
            lines = [leg["route_id"] for leg in legs]
            routes.append(
                dict(
                    id=itinerary["id"],
                    name=" then ".join(lines),
                    family="GOOGLE_" + "_".join(lines),
                    legs=legs,
                    access_walk_seconds=walks[0],
                    egress_walk_seconds=walk,
                    transfer_walk_seconds=walks[1:],
                )
            )
        ref = next(r for r in s["routes"] if r["selected_as_stay"])
        rejected = [
            dict(
                id=key + "-unavailable-" + str(r["route_index"]),
                reason_codes=["PROVIDER_PATH_NORMALIZATION_FAILED"],
            )
            for r in s["routes"]
            if r["normalization_status"] == "REJECTED"
        ]
        corridors.append(
            dict(
                s["corridor"],
                routes=routes,
                reference_route_id=ref["normalized_itinerary_id"],
                unavailable_candidates=rejected,
                capture_path=str(path.relative_to(ROOT)),
                capture_sha256=sha256(path),
            )
        )
    CONFIG.write_text(json.dumps(corridors, indent=2) + "\n")


def write_day(args):
    day, times, archive = args
    target = LOCAL / (day + ".jsonl.gz")
    if target.exists():
        return
    assert sha256(archive["path"]) == archive["sha256"]
    feeds = {ROUTE_FEEDS[r] for r in PAIRS}
    config = dict(
        route_ids=list(PAIRS), train_max_age_seconds=180, alerts_max_age_seconds=300
    )
    tmp = target.with_suffix(".tmp")
    with gzip.open(tmp, "wt", compresslevel=1) as out:
        for raw in iter_raw_snapshots(
            archive["path"], feeds, 60, receipt_callback=raw_receipt
        ):
            t = raw["captured_at"]
            i = bisect_right(times, t + 180) - 1
            if raw["feed_id"] == "subway-alerts" or i < 0 or times[i] + 7200 < t:
                continue
            if not raw.get("invalid_reason"):
                feed = gtfs.FeedMessage.FromString(raw["payload"])
                if not feed.IsInitialized():
                    raw["invalid_reason"] = "INVALID_ARCHIVED_PAYLOAD"
                else:
                    # Keep all same-line identities (including cancellations and aliases).
                    # Only trips advertising an origin can supply a timing candidate.
                    view = gtfs.FeedMessage()
                    view.header.CopyFrom(feed.header)
                    for entity in feed.entity:
                        update = entity.trip_update
                        pair = PAIRS.get(update.trip.route_id)
                        if pair is None:
                            continue
                        item = view.entity.add()
                        item.CopyFrom(entity)
                        if pair[0].encode() not in update.SerializeToString():
                            item.trip_update.ClearField("stop_time_update")
                    raw["payload"] = view.SerializeToString()
            row = normalize(raw, config, project=False)
            # Retain all intermediate stop IDs, relations and original ordering.
            for trip in row["trips"]:
                for stop in trip["stop_updates"]:
                    for field in (
                        "arrival_uncertainty",
                        "departure_uncertainty",
                        "scheduled_track",
                        "actual_track",
                    ):
                        stop.pop(field, None)
            out.write(json.dumps(row, separators=(",", ":")) + "\n")
    tmp.replace(target)
    print(day, target.stat().st_size, flush=True)


def prepare():
    if not CONFIG.exists():
        configure()
    LOCAL.mkdir(exist_ok=True, parents=True)
    p = json.loads(BASE.read_text())
    times = sorted(
        {c["decision_at"] for c in p["cases"] if c["corridor_id"] in SOURCES.values()}
    )
    acquisition = json.loads(
        (ROOT / "data/manifests/november-2026-acquisition.json").read_text()
    )
    jobs = []
    for a in acquisition["archives"]:
        if a["kind"] != "gtfsrt":
            continue
        day = a["archive_date"]
        relevant = [
            t
            for t in times
            if datetime.fromtimestamp(t - 180, ZONE).date().isoformat()
            <= day
            <= datetime.fromtimestamp(t + 7200, ZONE).date().isoformat()
        ]
        if relevant:
            jobs.append((day, relevant, a))
    with ProcessPoolExecutor(6) as pool:
        list(pool.map(write_day, jobs))


def daily_evidence(paths, day, manifest, day_reports, templates, coordinates):
    """Rebuild guarded trip labels and visible-frame membership for the long routes."""
    from datetime import date, timedelta
    from itertools import chain
    from data.feed_route_archive import FeedRouteArchive
    from data.october.prepare import DailyReceiptIndex, _merge_trip
    from data.october.labels import build_labels
    from data.october.sources import read_snapshots, read_labels
    from data.route_archive import build_from_snapshots
    from data.route_outcome_sanity import OutcomeQualityScreen

    stops = {s for p in PAIRS.values() for s in p}
    first = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    last = (date.fromisoformat(paths[-1].name[:10]) + timedelta(days=1)).isoformat()
    identities = {}
    for row in day_reports:
        if first <= row["date"] <= last:
            for trip in read_labels(ROOT / row["outputs"]["trips"]["path"]).values():
                _merge_trip(identities, trip, stops)
                identities[trip["id"]]["observed_stop_ids"].update(
                    stops.intersection(trip["observed_stop_ids"])
                )
                identities[trip["id"]]["identity_conflict"] |= trip.get(
                    "identity_conflict", False
                )

    def records():
        return chain.from_iterable(read_snapshots(p) for p in paths)

    for snapshot in records():
        for trip in snapshot["trips"]:
            _merge_trip(identities, trip, stops)
    journals = [
        r["path"]
        for r in manifest["archives"]
        if r["kind"] == "csv" and first <= r["archive_date"] <= last
    ]
    labels, _ = build_labels(
        identities, journals, DailyReceiptIndex(day_reports, "America/New_York"), stops
    )
    payload = build_from_snapshots(records(), templates, labels)
    return FeedRouteArchive(payload, quality_screen=OutcomeQualityScreen(coordinates))


if __name__ == "__main__":
    prepare()
