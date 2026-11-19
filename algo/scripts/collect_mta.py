#!/usr/bin/env python3
"""Collect a finite number of MTA snapshots for later as-of matching."""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stayorswitch import mta
from stayorswitch.network import HttpClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", default="A,C,E,F,G", help="Comma-separated MTA route IDs.")
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=30)
    parser.add_argument("--cache-dir", type=Path, default=Path(__file__).resolve().parents[2] / "data/local/mta")
    args = parser.parse_args()
    if args.samples < 1 or args.interval_seconds < 15:
        parser.error("Use at least one sample and a polling interval of at least 15 seconds.")
    routes = sorted(set(item.strip() for item in args.routes.split(",") if item.strip()))
    cache = mta.SnapshotCache(args.cache_dir / "snapshots")
    with HttpClient() as client:
        for sample in range(args.samples):
            if sample:
                time.sleep(args.interval_seconds)
            snapshots = mta.collect_feeds(routes, client.get)
            for snapshot in snapshots:
                cache.put(snapshot)
            print(json.dumps({"sample": sample + 1, "feeds": [
                {"feed_id": item["feed_id"], "status": item["status"],
                 "fetched_at": item["fetched_at"], "reason_codes": item.get("reason_codes", [])}
                for item in snapshots]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
