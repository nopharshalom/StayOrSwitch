#!/usr/bin/env python3
"""Compare explicit supplied routes with conservative boarding and historical ETA profiles."""

import argparse
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY / "algo"))

from data.delay_profiles import IncidentIndex, ProfileEstimator
from algo.scripts.run_severe import load_asof
from stayorswitch.boarding_safe import predict_routes
from stayorswitch.matching import _epoch
from stayorswitch.severe import MODES, _seconds, decide, validate_templates


DEFAULT_PROFILE = REPOSITORY / "data/artifacts/october-2026-profiles-full-train.json.gz"


def unavailable_templates(config):
    """Retain unresolved provider candidates instead of silently omitting them."""
    values = config.get("unavailable_candidates", [])
    if not isinstance(values, list):
        raise ValueError("Unavailable provider candidates must be a list.")
    identifiers = {route["id"] for route in config["routes"]}
    for value in values:
        identifier = value.get("id") if isinstance(value, dict) else None
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("Unavailable candidate identifiers must be nonempty and unique.")
        identifiers.add(identifier)
    return values


def append_unavailable(prediction, candidates, mode):
    for candidate in candidates:
        prediction["routes"].append({
            "id": candidate["id"], "name": candidate.get("name", candidate["id"]),
            "family": candidate.get("family", "UNRESOLVED_PROVIDER_PATH"),
            "status": "UNAVAILABLE", "mode": mode, "eta": None,
            "total_duration_seconds": None, "timing_eligible": False,
            "comparison_eligible": False, "selected_legs": [], "rejected": [],
            "leg_candidate_counts": [], "components": None,
            "reason_codes": candidate.get("reason_codes", ["PROVIDER_PATH_NORMALIZATION_FAILED"]),
            "context": {"state": "UNKNOWN", "evidence_status": "UNKNOWN",
                        "incident_ids": [], "severe_incident_ids": [], "ambiguous_scope": True},
            "severe_incident_ids": [], "provider_unavailable_candidate": deepcopy(candidate),
        })


def training_cutoff(estimator):
    """Read the frozen profile's temporal boundary without opening source labels."""
    recorded = estimator.profile.get("training_cutoff_at")
    if recorded is not None:
        return _epoch(recorded)
    end = date.fromisoformat(estimator.config["splits"]["train"][-1])
    boundary = datetime.combine(end + timedelta(days=1), time.min,
                                tzinfo=ZoneInfo(estimator.config["timezone"]))
    return boundary.timestamp()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", nargs="+", type=Path, required=True,
                        help="Normalized .snapshots.jsonl.gz files, including relevant alert history.")
    parser.add_argument("--config", type=Path, required=True,
                        help="JSON configuration containing all supplied route templates and walking times.")
    parser.add_argument("--profiles", type=Path,
                        default=DEFAULT_PROFILE,
                        help="Frozen October 1-31 training profiles; unused in mta mode.")
    parser.add_argument("--cutoff", required=True, help="Timezone-aware ISO timestamp or Unix seconds.")
    parser.add_argument("--current-route-id", required=True,
                        help="Explicit Stay reference from the supplied route configuration.")
    parser.add_argument("--mode", choices=("all",) + MODES, default="all")
    parser.add_argument("--boarding-margin-seconds", type=float, default=120,
                        help="Required conservative boarding slack; default 120 seconds.")
    parser.add_argument("--severe-only", action="store_true",
                        help="Require applicable severe evidence before recommending Switch.")
    parser.add_argument("--output", type=Path, help="Save the complete diagnostic report as JSON.")
    parser.add_argument("--json", action="store_true", help="Print the complete diagnostic report.")
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text())
        validate_templates(config["routes"])
        unavailable = unavailable_templates(config)
        margin = _seconds(args.boarding_margin_seconds, "boarding_margin_seconds")
        train_age = _seconds(config.get("train_max_age_seconds", 180), "train_max_age_seconds")
        alert_age = _seconds(config.get("alerts_max_age_seconds", 300), "alerts_max_age_seconds")
        switch_margin = _seconds(config.get("switch_margin_seconds", 300), "switch_margin_seconds")
        try:
            cutoff_value = float(args.cutoff)
        except ValueError:
            cutoff_value = args.cutoff
        cutoff = _epoch(cutoff_value)
        if args.current_route_id not in {route["id"] for route in config["routes"] + unavailable}:
            raise ValueError("Current route ID is absent from the supplied route configuration.")
        snapshots, alerts = load_asof(args.snapshots, cutoff)
        estimator = None if args.mode == "mta" else ProfileEstimator(args.profiles)
        profile_cutoff = None if estimator is None else training_cutoff(estimator)
        if profile_cutoff is not None and cutoff < profile_cutoff:
            raise ValueError("The prediction cutoff precedes the profile's training boundary.")
        incident_index = IncidentIndex(alerts, max_age_seconds=alert_age)
        modes = MODES if args.mode == "all" else (args.mode,)
        reports = {}
        for mode in modes:
            prediction = predict_routes(snapshots, config["routes"], cutoff, mode=mode,
                estimator=estimator, incident_index=incident_index,
                train_max_age_seconds=train_age, alerts_max_age_seconds=alert_age,
                boarding_margin_seconds=margin)
            append_unavailable(prediction, unavailable, mode)
            reports[mode] = dict(prediction, **decide(prediction, args.current_route_id,
                switch_margin_seconds=switch_margin, require_severe=args.severe_only))
        report = {"schema_version": "boarding-safe-comparison-report-v2", "cutoff": cutoff,
                  "boarding_margin_seconds": margin, "require_severe": args.severe_only,
                  "prediction_uses_outcomes": False, "actual_travel_time_computed": False,
                  "current_route_id": args.current_route_id,
                  "input_paths": [str(path.resolve()) for path in args.snapshots],
                  "configuration_path": str(args.config.resolve()),
                  "walking_policy": config.get("walking_policy"),
                  "profile": None if estimator is None else {
                      "path": str(args.profiles.resolve()), "seal": estimator.seal,
                      "fit_split": estimator.fit_split, "training_cutoff_at": profile_cutoff},
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
        print("Boarding-safe supplied-route forecasts; no external API calls or outcome labels.")
        print("Boarding margin:", margin, "seconds; severe-only advice:", args.severe_only)
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
