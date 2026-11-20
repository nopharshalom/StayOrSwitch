"""Check input-only semantic parity and benchmark a configured raw source hour."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import gzip
import io
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from data.october.prepare import normalize, _merge_trip
from data.october.sources import ROOT, iter_raw_snapshots, write_json
from data.delay_profiles.build import observation_rows
from stayorswitch.matching import _timing_candidate


class InputOnlyContext:
    def context_at(self, cutoff, route_id, stop_ids=None):
        return {"state": "NORMAL", "cause": "|".join(stop_ids or []),
                "incident_ids": [], "severe_incident_ids": [],
                "evidence_status": "INPUT_ONLY_PARITY"}


def encoded(value):
    return (json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n").encode()


def parity(original, projected, config):
    excluded = {"trips", "normalization_projection"}
    if {k: v for k, v in original.items() if k not in excluded} != {k: v for k, v in projected.items() if k not in excluded}:
        raise AssertionError("Snapshot metadata changed under projection.")
    if len(original["trips"]) != len(projected["trips"]):
        raise AssertionError("Configured train descriptors were removed.")
    legs = defaultdict(list)
    for route in config["routes"]:
        for leg in route["legs"]:
            for line in leg.get("route_ids", [leg["route_id"]]):
                if leg not in legs[line]:
                    legs[line].append(leg)
    inventory_before, inventory_after, comparisons = {}, {}, 0
    for before, after in zip(original["trips"], projected["trips"]):
        if {k: v for k, v in before.items() if k != "stop_updates"} != {k: v for k, v in after.items() if k != "stop_updates"}:
            raise AssertionError("Configured train metadata changed under projection.")
        _merge_trip(inventory_before, before, set(config["stop_ids"]))
        _merge_trip(inventory_after, after, set(config["stop_ids"]))
        for leg in legs[before["route_id"]]:
            boarding = {"platform_stop_ids": [leg["from_stop_id"]]}
            alighting = {"platform_stop_ids": [leg["to_stop_id"]]}
            if _timing_candidate(before, boarding, alighting, None) != _timing_candidate(after, boarding, alighting, None):
                raise AssertionError("Configured timing candidate, path, or rejection changed.")
            comparisons += 1
    if inventory_before != inventory_after:
        raise AssertionError("Label or split inventory metadata changed under projection.")
    counts_before, counts_after = Counter(), Counter()
    before_rows = list(observation_rows(original, {}, config, InputOnlyContext(), counts_before))
    after_rows = list(observation_rows(projected, {}, config, InputOnlyContext(), counts_after))
    if before_rows != after_rows or counts_before != counts_after:
        raise AssertionError("Profile observations or exclusion counts changed under projection.")
    return comparisons, len(before_rows)


def benchmark(config, day, hour, minutes):
    acquisition = json.loads((ROOT / "data/manifests/october-acquisition.json").read_text())
    archive = next(row for row in acquisition["archives"] if row["kind"] == "gtfsrt" and row["archive_date"] == day)
    zone, samples, by_feed = ZoneInfo(config["timezone"]), [], Counter()
    for record in iter_raw_snapshots(archive["path"], config["feed_ids"], config["sample_seconds"]):
        if record["feed_id"] not in config["feed_ids"]:
            continue
        local = datetime.fromtimestamp(record["captured_at"], zone)
        if local.hour == hour and local.minute < minutes:
            samples.append(record)
            by_feed[record["feed_id"]] += 1
    if set(by_feed) != set(config["feed_ids"]):
        raise AssertionError("Representative source window is missing a configured feed.")
    originals, projected = [], []
    measurements = {}
    for name, enabled, target in (("original", False, originals), ("projected", True, projected)):
        started, plain_bytes, buffer = time.perf_counter(), 0, io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0, compresslevel=1) as compressed:
            for record in samples:
                result = normalize(record, config, project=enabled)
                body = encoded(result)
                plain_bytes += len(body)
                compressed.write(body)
                target.append(result)
        measurements[name] = {"seconds": round(time.perf_counter() - started, 3),
                              "json_bytes": plain_bytes, "gzip_bytes": len(buffer.getvalue())}
    candidates = rows = 0
    for original, revised in zip(originals, projected):
        a, b = parity(original, revised, config)
        candidates += a
        rows += b
    return {"stage": "PASSED", "date": day, "local_hour": hour, "minutes": minutes,
            "input_only": True, "source_archive_sha256": archive["sha256"],
            "samples": len(samples), "by_feed": dict(by_feed), "measurements": measurements,
            "candidate_or_rejection_comparisons": candidates, "profile_observation_comparisons": rows,
            "timing_speedup": round(measurements["original"]["seconds"] / measurements["projected"]["seconds"], 3),
            "json_size_reduction": round(measurements["original"]["json_bytes"] / measurements["projected"]["json_bytes"], 3),
            "gzip_size_reduction": round(measurements["original"]["gzip_bytes"] / measurements["projected"]["gzip_bytes"], 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "data/config/october.json"))
    parser.add_argument("--date", default="2026-10-05")
    parser.add_argument("--hour", type=int, default=7)
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--report", default=str(ROOT / "data/reports/october-projection-benchmark.json"))
    args = parser.parse_args()
    if not 0 <= args.hour <= 23 or not 1 <= args.minutes <= 60:
        parser.error("Choose an hour from 0 to 23 and minutes from 1 to 60.")
    report = benchmark(json.loads(Path(args.config).read_text()), args.date, args.hour, args.minutes)
    write_json(args.report, report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
