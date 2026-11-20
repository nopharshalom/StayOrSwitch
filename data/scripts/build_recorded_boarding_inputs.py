"""Build a stop-passage index for the two November corridors from archived MTA data."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
import gzip
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from google.transit import gtfs_realtime_pb2 as gtfs
from google.protobuf.message import DecodeError
from data.experiment_evidence import INPUTS, stop_bounds
from data.recorded_passages import BUNDLE, build_index, load_json
from data.october.labels import source_trip_uid
from data.october.sources import iter_raw_snapshots, sha256


def vehicle_day(job):
    path, digest, lines, stops, windows, output = job
    if sha256(path) != digest:
        raise ValueError("Vehicle archive checksum mismatch")
    points = defaultdict(set)
    for snap in iter_raw_snapshots(path, set(lines.values()), 1):
        feed = snap["feed_id"]
        if feed not in lines.values() or snap.get("invalid_reason"):
            continue
        at = snap["captured_at"]
        if not any(first <= at <= last for first, last in windows):
            continue
        try:
            msg = gtfs.FeedMessage.FromString(snap["payload"])
        except DecodeError:
            continue
        if not msg.IsInitialized() or msg.header.incrementality or not 0 <= at-msg.header.timestamp <= 120:
            continue
        for entity in msg.entity:
            if not entity.HasField("vehicle"):
                continue
            v = entity.vehicle
            if (lines.get(v.trip.route_id) != feed or not v.stop_id or
                    not v.HasField("current_stop_sequence") or not v.HasField("current_status") or
                    not v.HasField("timestamp") or not 0 <= msg.header.timestamp-v.timestamp <= 120):
                continue
            uid = source_trip_uid(dict(trip_id=v.trip.trip_id, start_date=v.trip.start_date))
            if uid:
                points[(v.trip.route_id, uid)].add((v.timestamp, v.current_stop_sequence,
                                                    v.stop_id, v.current_status))
    visits = {}
    for (line, uid), obs in points.items():
        target = {stop for _, _, stop, status in obs if stop in stops and status == 1}
        if target:
            visits[uid] = {"line": line, "stops": {
                s: dict(stop_bounds(obs, s), stopped=[min(t for t, _, st, status in obs if st == s and status == 1),
                                                       max(t for t, _, st, status in obs if st == s and status == 1)])
                for s in sorted(target)}}
    output.write_text(json.dumps(visits))
    print(output.stem, len(visits), flush=True)


def prepare_vehicles():
    with gzip.open(INPUTS, "rt") as stream:
        cohort = json.load(stream)
    legs = [leg for r in cohort["routes"].values() for leg in r["legs"]]
    lines = {line: leg["feed_id"] for leg in legs for line in leg["route_ids"]}
    stops = {leg[key] for leg in legs for key in ("from_stop_id","to_stop_id")}
    by_day = defaultdict(list)
    local = ZoneInfo("America/New_York")
    for case in cohort["cases"]:
        first, last = case["cutoff"]-240, case["cutoff"]+7200+240
        day = datetime.fromtimestamp(first,local).date()
        while day <= datetime.fromtimestamp(last,local).date():
            by_day[day.isoformat()].append((first,last))
            day += timedelta(days=1)
    archives = json.loads((ROOT/"data/manifests/november-2026-acquisition.json").read_text())["archives"]
    directory = ROOT/"data/processed/recorded-boarding-vehicles"
    directory.mkdir(exist_ok=True, parents=True)
    jobs = []
    for a in archives:
        day = a["archive_date"]
        if day not in by_day or a["kind"] != "gtfsrt":
            continue
        merged = []
        for first,last in sorted(by_day[day]):
            if merged and first <= merged[-1][1]:
                merged[-1][1] = max(last,merged[-1][1])
            else:
                merged.append([first,last])
        jobs.append((a["path"],a["sha256"],lines,stops,merged,directory/(day+".json")))
    if len(jobs) != len(by_day):
        raise ValueError("Missing daily vehicle archive")
    with ProcessPoolExecutor(max_workers=5) as pool:
        list(pool.map(vehicle_day,jobs))


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-vehicles", action="store_true",
                        help="Reuse the completed per-day vehicle extraction in data/processed.")
    args = parser.parse_args()
    if not args.reuse_vehicles:
        prepare_vehicles()
    bundle = build_index(load_json(INPUTS), ROOT/"data/processed/recorded-boarding-vehicles")
    packed = json.dumps(bundle, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    BUNDLE.write_bytes(gzip.compress(packed, mtime=0))
    print(f"Saved {len(bundle['trains'])} service runs for {len(bundle['cases'])} recommendations.")


if __name__ == "__main__":
    main()
