#!/usr/bin/env python3
"""Run Step 2 input integration; this does not serve /v1/evaluate or compare ETAs."""

import argparse
import json
import os
from pathlib import Path
import sys
from jsonschema.exceptions import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stayorswitch.integration import integrate_live, integrate_supplied, REPOSITORY
from stayorswitch.network import HttpClient, NetworkError, read_local_settings
from stayorswitch.provider_client import PILOT_ORIGIN, PILOT_DESTINATION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=REPOSITORY / ".env")
    parser.add_argument("--cache-dir", type=Path, default=REPOSITORY / "data/local/mta")
    parser.add_argument("--origin", default=PILOT_ORIGIN)
    parser.add_argument("--destination", default=PILOT_DESTINATION)
    parser.add_argument("--current-itinerary-id", help="An explicitly selected stable itinerary ID; never defaults to the first route.")
    parser.add_argument("--request", type=Path, help="Read a contract Request and only use cached observations at its cutoff.")
    parser.add_argument("--json", action="store_true", help="Print the in-memory integration report, including provider-derived route details.")
    args = parser.parse_args()
    key = ""
    try:
        if args.request:
            report = integrate_supplied(json.loads(args.request.read_text()), args.cache_dir)
        else:
            settings = read_local_settings(args.env_file)
            key = os.environ.get("GOOGLE_ROUTES_API_KEY", settings.get("GOOGLE_ROUTES_API_KEY", ""))
            ipv4 = os.environ.get("GOOGLE_ROUTES_IPV4", settings.get("GOOGLE_ROUTES_IPV4", "true")).lower()
            if ipv4 not in {"true", "false", "1", "0"}:
                raise ValueError("GOOGLE_ROUTES_IPV4 must be true or false.")
            with HttpClient(ipv4=ipv4 in {"true", "1"}) as client:
                report = integrate_live(client, key, args.cache_dir, origin=args.origin,
                                        destination=args.destination,
                                        current_itinerary_id=args.current_itinerary_id)
    except NetworkError as exc:
        print(json.dumps({"status": "UPSTREAM_ERROR", "code": exc.code,
                          "http_status": exc.status_code, "message": str(exc)}), file=sys.stderr)
        return 2
    except (ValueError, OSError, ValidationError) as exc:
        message = str(exc).replace(key, "[REDACTED]") if key else str(exc)
        print(json.dumps({"status": "INPUT_ERROR", "message": message[:500]}), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, allow_nan=False))
    else:
        matching = report.get("matching") or {}
        print("Step 2 live-data integration (not an ETA estimate or Stay/Switch decision)")
        print("Provider: Google Maps" if report["provider"].get("name") else "Provider: supplied request")
        print("Provider candidates:", report["provider"].get("route_count", "supplied"))
        print("Accepted unique itineraries:", len((report.get("request") or {}).get("itineraries", [])))
        for feed in matching.get("feed_status", []):
            print("Feed:", feed["feed_id"], feed["status"])
        for route in matching.get("itineraries", []):
            print("-", route["id"], route["status"], ", ".join(route.get("reason_codes", [])))
            for leg in route.get("legs", []):
                if leg["mode"] == "SUBWAY":
                    print("  Subway:", leg["status"], "candidate services:", len(leg.get("candidates", [])),
                          "reasons:", ", ".join(leg.get("reason_codes", [])))
        for issue in report["provider"].get("issues", []):
            print("Provider issue:", issue.get("code"), "route", issue.get("route_index"))
    return 0 if report.get("request") is not None else 3


if __name__ == "__main__":
    raise SystemExit(main())
