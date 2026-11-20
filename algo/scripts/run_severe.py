#!/usr/bin/env python3
"""Compare supplied routes using local as-of feeds and frozen delay profiles."""

import argparse
import json
from pathlib import Path
import sys


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY / "algo"))

from data.delay_profiles import IncidentIndex, ProfileEstimator
from data.october import read_snapshots
from stayorswitch.matching import _choose_snapshots, _epoch
from stayorswitch.mta import ALERTS_FEED_ID
from stayorswitch.severe import MODES, decide, predict_routes


def load_asof(paths, cutoff):
    """Bound train memory while retaining all supplied as-of alert versions."""
    alerts = []

    def records():
        for path in paths:
            for snapshot in read_snapshots(path):
                if _epoch(snapshot["fetched_at"]) <= cutoff:
                    if snapshot["feed_id"] == ALERTS_FEED_ID:
                        alerts.append(snapshot)
                    yield snapshot

    return list(_choose_snapshots(records(), cutoff).values()), alerts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", nargs="+", type=Path, required=True,
                        help="Normalized .snapshots.jsonl.gz files, including relevant alert history.")
    parser.add_argument("--config", type=Path, default=REPOSITORY / "data/config/october.json")
    parser.add_argument("--profiles", type=Path,
                        default=REPOSITORY / "data/processed/october/profiles-train.json.gz",
                        help="Frozen development-only profiles; unused in mta mode.")
    parser.add_argument("--cutoff", required=True, help="Timezone-aware ISO timestamp or Unix seconds.")
    parser.add_argument("--current-route-id", required=True,
                        help="Explicit Stay reference from the supplied route configuration.")
    parser.add_argument("--mode", choices=("all",) + MODES, default="all")
    parser.add_argument("--output", type=Path, help="Save the complete diagnostic report as JSON.")
    parser.add_argument("--json", action="store_true", help="Print the complete diagnostic report.")
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text())
        try:
            cutoff_value = float(args.cutoff)
        except ValueError:
            cutoff_value = args.cutoff
        cutoff = _epoch(cutoff_value)
        if args.current_route_id not in {route["id"] for route in config["routes"]}:
            raise ValueError("Current route ID is absent from the supplied route configuration.")
        snapshots, alerts = load_asof(args.snapshots, cutoff)
        estimator = None if args.mode == "mta" else ProfileEstimator(args.profiles)
        incident_index = IncidentIndex(alerts, max_age_seconds=config["alerts_max_age_seconds"])
        modes = MODES if args.mode == "all" else (args.mode,)
        reports = {}
        for mode in modes:
            prediction = predict_routes(snapshots, config["routes"], cutoff, mode=mode,
                estimator=estimator, incident_index=incident_index,
                train_max_age_seconds=config["train_max_age_seconds"],
                alerts_max_age_seconds=config["alerts_max_age_seconds"])
            reports[mode] = dict(prediction, **decide(prediction, args.current_route_id,
                switch_margin_seconds=config["switch_margin_seconds"]))
        report = {"schema_version": "severe-comparison-report-v1", "cutoff": cutoff,
                  "current_route_id": args.current_route_id,
                  "input_paths": [str(path.resolve()) for path in args.snapshots],
                  "configuration_path": str(args.config.resolve()),
                  "walking_policy": config.get("walking_policy"),
                  "profile": None if estimator is None else {
                      "path": str(args.profiles.resolve()), "seal": estimator.seal,
                      "fit_split": estimator.fit_split},
                  "modes": reports}
        serialized = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "INPUT_ERROR", "message": str(exc)[:500]}), file=sys.stderr)
        return 2
    if args.json:
        print(serialized, end="")
    else:
        print("Supplied-route ETA comparison; no external API calls or outcome labels.")
        print("Stay reference:", args.current_route_id)
        print("Walking assumptions:", report["walking_policy"] or "See supplied configuration.")
        for mode, prediction in reports.items():
            print("Mode:", mode)
            for route in prediction["routes"]:
                detail = ("%.2f minutes" % (route["total_duration_seconds"] / 60)
                          if route["timing_eligible"] else "unavailable")
                print("- %s: %s; %s" % (route["id"], detail,
                    "service evidence verified" if route["comparison_eligible"] else "service evidence unverified"))
            for key in ("strict_decision", "conditional_timing_decision"):
                decision = prediction[key]
                print("%s: %s; route=%s; %s" % (key, decision["action"],
                    decision["recommended_itinerary_id"], ", ".join(decision["reason_codes"])))
        if args.output:
            print("Diagnostic report:", str(args.output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
