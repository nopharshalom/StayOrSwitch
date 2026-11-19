#!/usr/bin/env python3
"""Compare supplied journeys using current MTA predictions, without a trained model."""

import argparse
import json
import os
from pathlib import Path
import sys

from jsonschema.exceptions import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stayorswitch.baseline import evaluate_integration
from stayorswitch.integration import integrate_live, integrate_supplied, REPOSITORY
from stayorswitch.network import HttpClient, NetworkError, read_local_settings
from stayorswitch.provider_client import PILOT_ORIGIN, PILOT_DESTINATION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=REPOSITORY / ".env")
    parser.add_argument("--cache-dir", type=Path, default=REPOSITORY / "data/local/mta")
    parser.add_argument("--origin", default=PILOT_ORIGIN)
    parser.add_argument("--destination", default=PILOT_DESTINATION)
    parser.add_argument("--current-itinerary-id", help="The user's selected stable itinerary ID; no default is invented.")
    parser.add_argument("--request", type=Path, help="Use a contract Request and cached data at its cutoff; no network calls.")
    parser.add_argument("--no-provider-fallback", action="store_true", help="Return unavailable instead of display-only provider transit estimates.")
    parser.add_argument("--json", action="store_true", help="Print the version 1 contract Response only.")
    parser.add_argument("--diagnostics", action="store_true", help="Print the full report including provider attribution and diagnostic details.")
    args = parser.parse_args()
    key = ""
    try:
        if args.request:
            integration = integrate_supplied(json.loads(args.request.read_text()), args.cache_dir)
        else:
            settings = read_local_settings(args.env_file)
            key = os.environ.get("GOOGLE_ROUTES_API_KEY", settings.get("GOOGLE_ROUTES_API_KEY", ""))
            ipv4 = os.environ.get("GOOGLE_ROUTES_IPV4", settings.get("GOOGLE_ROUTES_IPV4", "true")).lower()
            if ipv4 not in {"true", "false", "1", "0"}:
                raise ValueError("GOOGLE_ROUTES_IPV4 must be true or false.")
            with HttpClient(ipv4=ipv4 in {"true", "1"}) as client:
                integration = integrate_live(client, key, args.cache_dir, origin=args.origin,
                                             destination=args.destination,
                                             current_itinerary_id=args.current_itinerary_id)
        report = evaluate_integration(integration, allow_provider_fallback=not args.no_provider_fallback)
    except NetworkError as exc:
        print(json.dumps({"status": "UPSTREAM_ERROR", "code": exc.code,
                          "http_status": exc.status_code, "message": str(exc)}), file=sys.stderr)
        return 2
    except (ValueError, OSError, ValidationError) as exc:
        message = str(exc).replace(key, "[REDACTED]") if key else str(exc)
        print(json.dumps({"status": "INPUT_ERROR", "message": message[:500]}), file=sys.stderr)
        return 2
    response = report["response"]
    if args.diagnostics:
        print(json.dumps(report, indent=2, allow_nan=False))
    elif args.json:
        print(json.dumps(response, indent=2, allow_nan=False))
    else:
        print("Step 4 baseline destination ETA comparison (no learned correction)")
        print("Provider: Google Maps" if report.get("provider", {}).get("name") == "Google Routes" else "Provider: supplied request")
        print("Provider candidates:", report.get("provider", {}).get("route_count", "supplied"),
              "Supported unique itineraries:", len(response["itineraries"]))
        print("Decision time:", response["decision_time"])
        print("Walking and platform access use provider estimates; entrances are not independently verified.")
        for route in response["itineraries"]:
            if route["status"] == "ESTIMATED":
                parts = route["components"]
                print("- %s: %.2f minutes, %s, %s" %
                      (route["id"], route["total_duration_seconds"] / 60, route["method"],
                       "comparison eligible" if route["comparison_eligible"] else "display only"))
                print("  Destination ETA: %s; walk %.2f, wait %.2f, ride %.2f minutes" %
                      (route["eta"], parts["walking_seconds"] / 60, parts["waiting_seconds"] / 60,
                       parts["riding_seconds"] / 60))
            else:
                print("-", route["id"], route["status"], ", ".join(route["reason_codes"]))
        decision = response["decision"]
        print("Decision:", decision["action"], ", ".join(decision["reason_codes"]))
        print("Recommended supplied itinerary:", decision["recommended_itinerary_id"])
        if decision["estimated_savings_seconds"] is not None:
            print("Estimated savings: %.2f minutes" % (decision["estimated_savings_seconds"] / 60))
        print("Comparison complete:", decision["comparison_complete"])
        print("Warnings:", ", ".join(response["warnings"]) or "none")
        issues = sorted({item.get("code", "UNKNOWN_PROVIDER_ISSUE")
                         for item in report.get("provider", {}).get("issues", [])})
        if issues:
            print("Provider diagnostics:", ", ".join(issues))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
