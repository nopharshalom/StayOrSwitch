"""Print commuter advice from an existing boarding-safe forecast report."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stayorswitch.commuter_advice import commuter_advice


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "forecast_report",
        type=Path,
        help="JSON output of run_boarding_safe.py in all modes.",
    )
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.forecast_report.read_text())
        result = commuter_advice(
            report["modes"]["incident_profile"],
            report["modes"]["mta"],
            report["current_route_id"],
        )
        print(json.dumps(result, allow_nan=False))
    except (KeyError, OSError, TypeError, ValueError) as exc:
        parser.exit(2, f"Invalid boarding-safe report: {exc}\n")


if __name__ == "__main__":
    main()
