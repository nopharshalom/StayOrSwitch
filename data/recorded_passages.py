"""Index retrospective trip-journal endpoints and observed vehicle visits."""
from collections import defaultdict
from datetime import date
import gzip
import json
import re
from pathlib import Path

from data.october.labels import ReceiptIndex
from data.october.sources import iter_csv_rows, sha256

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data/artifacts/november-recorded-passages.json.gz"


def load_json(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as stream:
            return json.load(stream)
    return json.loads(path.read_text())


def day_inventory(job):
    archive, digest, lines, stops = job
    if sha256(archive) != digest:
        raise ValueError("Journal archive checksum mismatch")
    trips = {}
    for row in iter_csv_rows(archive, "trips"):
        if row["route_id"] in lines:
            descriptor = [row[k] for k in ("route_id", "trip_id", "num_schedule_changes", "num_schedule_rewrites")]
            uid = row["trip_uid"]
            if uid in trips and trips[uid] != descriptor:
                raise ValueError("Conflicting journal trip identity")
            trips[uid] = descriptor
    calls = defaultdict(dict)
    for row in iter_csv_rows(archive, "stop_times"):
        uid, stop = row["trip_uid"], row["stop_id"]
        if uid not in trips or stop not in stops:
            continue
        values = tuple(int(row[k]) if row[k] else None for k in
                       ("arrival_time","departure_time","last_observed","marked_past"))
        calls[uid].setdefault(stop, set()).add(values)
    return {uid: (trips[uid], passages) for uid, passages in calls.items()}


def journal_time(row, endpoint, receipts, feed):
    arrival, departure, observed, passed = row
    at = arrival if endpoint == "arrival" else departure
    if (None in (at, observed, passed) or not 0 <= passed-observed <= 180 or
            abs(at-observed) > 180 or at > passed or receipts.confirm(feed, passed) is None):
        return None
    if endpoint == "departure" and arrival is not None and departure < arrival:
        return None
    return [at, at]


def merge_endpoint(journal, vehicle, endpoint):
    if journal:
        return {"bounds": journal, "source": "JOURNAL"}
    bracket = vehicle.get(endpoint)
    if bracket:
        return {"bounds": bracket, "source": "VEHICLE"}
    return None


def build_index(cohort, vehicle_directory, workers=4):
    from concurrent.futures import ProcessPoolExecutor
    from datetime import timedelta

    used = {c[k] for c in cohort["cases"] for k in ("reference","alternative")}
    routes = {rid:cohort["routes"][rid] for rid in sorted(used)}
    legs = [leg for route in routes.values() for leg in route["legs"]]
    lines = {line:leg["feed_id"] for leg in legs for line in leg["route_ids"]}
    stops = {leg[k] for leg in legs for k in ("from_stop_id","to_stop_id")}
    test_days = {date.fromisoformat(c["local_time"][:10]) for c in cohort["cases"]}
    dates = {(day+timedelta(days=offset)).isoformat() for day in test_days for offset in (-1,0,1)}
    manifest = load_json(ROOT/"data/manifests/november-2026-acquisition.json")["archives"]
    archives = [a for a in manifest if a["kind"]=="csv" and a["archive_date"] in dates]
    if {a["archive_date"] for a in archives} != dates:
        raise ValueError("Missing journal boundary archive")
    journal, descriptors = defaultdict(lambda: defaultdict(set)), {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = [(a["path"],a["sha256"],lines,stops) for a in archives]
        for inventory in pool.map(day_inventory,jobs):
            for uid,(trip,passages) in inventory.items():
                if uid in descriptors and descriptors[uid] != trip:
                    raise ValueError("Conflicting trip descriptor across journal archives")
                descriptors[uid] = trip
                for stop, entries in passages.items():
                    journal[uid][stop].update(entries)
    receipt_rows = defaultdict(list)
    sources = {Path(a["path"]).name:a["sha256"] for a in archives}
    for day in sorted(dates):
        source_dir = ROOT/"data/processed/november-2026"
        path = source_dir/(day+".receipts.json.gz")
        digest = sha256(path)
        if digest != load_json(source_dir/(day+".source.json"))["outputs"]["receipts"]["sha256"]:
            raise ValueError("Receipt checksum mismatch")
        sources[path.name] = digest
        for feed, rows in load_json(path).items():
            if feed in lines.values():
                receipt_rows[feed].extend(rows)
    receipts = ReceiptIndex(receipt_rows)
    vehicles = defaultdict(dict)
    vehicle_lines = {}
    for day in sorted(test_days):
        day = day.isoformat()
        archive = next(a for a in manifest if a["kind"]=="gtfsrt" and a["archive_date"]==day)
        sources[Path(archive["path"]).name] = archive["sha256"]
        for uid, row in load_json(vehicle_directory/(day+".json")).items():
            vehicle_lines[uid] = row["line"]
            for stop, value in row["stops"].items():
                if stop not in stops:
                    continue
                prior = vehicles[uid].get(stop)
                if prior:
                    first_seen = min(value["stopped"][0], prior["stopped"][0])
                    last_seen = max(value["stopped"][1], prior["stopped"][1])
                    joined = {"stopped": [first_seen,last_seen]}
                    for endpoint in ("arrival","departure"):
                        bounds = [record[endpoint] for record in (prior,value) if endpoint in record]
                        if bounds:
                            low, high = max(b[0] for b in bounds), min(b[1] for b in bounds)
                            if low <= high:
                                joined[endpoint] = [low,high]
                    value = joined
                vehicles[uid][stop] = value
    first = min(c["cutoff"] for c in cohort["cases"])-7200
    last = max(c["cutoff"] for c in cohort["cases"])+7200
    trains = {}
    for uid in sorted(set(journal)|set(vehicles)):
        desc = descriptors.get(uid)
        line = desc[0] if desc else vehicle_lines[uid]
        if line not in lines:
            continue
        if uid in vehicle_lines and vehicle_lines[uid] != line:
            raise ValueError("Journal and vehicle routes disagree")
        direction = re.search(r"\.\.([NS])", uid)
        if direction is None:
            continue
        calls = {}
        for stop in sorted(set(journal[uid])|set(vehicles[uid])):
            if not stop.endswith(direction.group(1)):
                continue
            rows = journal[uid].get(stop, set())
            vehicle = vehicles[uid].get(stop, {})
            # A changed service pattern needs independently observed stop visits.
            stable = desc and desc[2:] == ["0","0"] and len(rows) == 1
            row = next(iter(rows)) if stable else None
            visit = {}
            for endpoint in ("arrival","departure"):
                point = journal_time(row,endpoint,receipts,lines[line]) if row else None
                value = merge_endpoint(point,vehicle,endpoint)
                if value:
                    visit[endpoint] = value
            # An unresolved departure may still precede a confirmed one. Keep its
            # journal timing envelope as an ordering veto, never as a boarding time.
            anchors = [v for values in rows for v in values if v is not None]
            anchors += vehicle.get("stopped",[])
            if not anchors:
                continue
            window = [min(anchors)-180,max(anchors)+180]
            if visit.get("arrival"):
                window[0] = max(window[0], visit["arrival"]["bounds"][0])
            if window[1] < first or window[0] > last:
                continue
            visit["possible_window"] = window
            calls[stop] = visit
        if calls:
            trains[uid] = {"line":line,"calls":calls}
    return dict(decision_source_sha256=cohort["decision_source_sha256"],sources=sources,
                cases=cohort["cases"], routes=routes, trains=trains)
