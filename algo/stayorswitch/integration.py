"""Collect and link live inputs without estimating destination ETA or decisions."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .google_routes import normalize_google_response
from .matching import match_request
from . import mta
from .network import utc_now
from .provider_client import query_routes, PILOT_ORIGIN, PILOT_DESTINATION


REPOSITORY = Path(__file__).resolve().parents[2]


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires a timezone offset.")
    return parsed


def validate_request(request):
    # Reuse the Step 1 validator; the live integration must not fork its contract.
    from scripts.validate_contract import load_json, schema_validate, request_invariants
    schema = load_json(REPOSITORY / "algo/contracts/evaluate.schema.json")
    schema_validate(request, "Request", schema)
    request_invariants(request)


def endpoint(identifier, address):
    suffix = hashlib.sha256(" ".join(address.lower().split()).encode()).hexdigest()[:16]
    return {"id": identifier + "-" + suffix, "name": address, "coordinates": None,
            "provider_place_id": None, "mta_stop_id": None}


def load_static(cache_dir, client=None, *, cutoff=None, max_age_seconds=86400):
    """Reuse a checked local download; static data is for matching, not routing."""
    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "gtfs_subway.zip"
    metadata_path = directory / "static-metadata.json"
    metadata = None
    if archive.exists() and metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text())
            reference = instant(cutoff or utc_now())
            age = (reference - instant(metadata["fetched_at"])).total_seconds()
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            if age < 0 or age > max_age_seconds or metadata.get("sha256") != digest:
                metadata = None
        except (ValueError, KeyError, TypeError):
            metadata = None
    if metadata is None:
        if client is None:
            raise ValueError("No verified static data was available at the supplied cutoff; collect current inputs first.")
        result = client.get(mta.STATIC_GTFS_URL)
        metadata = {"url": result.url, "requested_at": result.requested_at,
                    "fetched_at": result.fetched_at, "bytes": len(result.body),
                    "sha256": hashlib.sha256(result.body).hexdigest()}
        archive.write_bytes(result.body)
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return mta.load_static_gtfs(archive.read_bytes()), metadata


def route_ids(request, static_data=None):
    labels = {leg["transit"]["route_short_name"].upper()
              for route in request["itineraries"] for leg in route["legs"]
              if leg["mode"] == "SUBWAY"}
    resolved = set()
    for label in labels:
        # S is not one unique MTA service. Collect all compatible feed groups;
        # station and stopping-pattern evidence must disambiguate it downstream.
        aliases = {route_id for route_id, route in (static_data or {}).get("routes", {}).items()
                   if route_id.upper() == label or str(route.get("short_name") or "").upper() == label}
        resolved.update(aliases or {label})
    return sorted(resolved)


def snapshot_cache(cache_dir):
    return mta.SnapshotCache(Path(cache_dir) / "snapshots")


def snapshots_as_of(cache, routes, cutoff):
    feed_ids = list(mta.route_feed_ids(routes)) + [mta.ALERTS_FEED_ID]
    feed_ids.extend("unsupported:" + route for route in routes if route not in mta.ROUTE_FEEDS)
    return [snapshot for feed_id in dict.fromkeys(feed_ids)
            for snapshot in [cache.latest(feed_id, cutoff)] if snapshot is not None]


def integrate_live(client, api_key, cache_dir, *, origin=PILOT_ORIGIN,
                   destination=PILOT_DESTINATION, current_itinerary_id=None):
    static_data, static_metadata = load_static(cache_dir, client)
    provider = query_routes(client, api_key, origin, destination)
    normalize_args = {"queried_at": provider["requested_at"],
                      "received_at": provider["received_at"],
                      "origin": endpoint("origin", origin),
                      "destination": endpoint("destination", destination),
                      "current_itinerary_id": current_itinerary_id}
    normalized = normalize_google_response(provider["response"], decision_time=utc_now(), **normalize_args)
    if normalized["request"] is None:
        return {"stage": "LIVE_DATA_MATCHING", "integration_version": "0.1",
                "request": None, "matching": None,
                "provider": {"http_status": provider["http_status"],
                             "received_at": provider["received_at"],
                             "route_count": len(provider["response"].get("routes", [])),
                             "issues": normalized["issues"], "provenance": normalized["provenance"]}}
    routes = route_ids(normalized["request"], static_data)
    cache = snapshot_cache(cache_dir)
    collected = mta.collect_feeds(routes, client.get)
    for snapshot in collected:
        cache.put(snapshot)
    # This CLI establishes the common cutoff AFTER collection. A future API
    # receiving a fixed cutoff must instead read the continuously collected cache.
    cutoff = utc_now()
    normalized = normalize_google_response(provider["response"], decision_time=cutoff, **normalize_args)
    request = normalized["request"]
    validate_request(request)
    snapshots = snapshots_as_of(cache, routes, cutoff)
    matching = match_request(request, static_data, snapshots)
    return {"stage": "LIVE_DATA_MATCHING", "integration_version": "0.1",
            "request": request, "matching": matching,
            "static_data": static_metadata,
            "limitations": ["NOT_A_DESTINATION_ETA_OR_STAY_SWITCH_RESULT",
                            "BUILDING_ENTRANCES_NOT_INDEPENDENTLY_VERIFIED",
                            "UNSUPPORTED_CANDIDATES_ARE_EXPLICITLY_REPORTED",
                            "PROVIDER_AND_FEED_PREDICTIONS_ARE_NOT_OBSERVED_ARRIVALS"],
            "provider": {"name": "Google Routes", "attribution": "Google Maps",
                         "http_status": provider["http_status"],
                         "received_at": provider["received_at"],
                         "route_count": len(provider["response"].get("routes", [])),
                         "issues": normalized["issues"], "provenance": normalized["provenance"]}}


def integrate_supplied(request, cache_dir):
    """Evaluate available matching evidence for a fixed cutoff without fetching ahead."""
    validate_request(request)
    cutoff = request["decision_time"]
    if instant(cutoff) > datetime.now(timezone.utc):
        raise ValueError("A supplied snapshot cutoff cannot be in the future.")
    static_data, metadata = load_static(cache_dir, cutoff=cutoff)
    snapshots = snapshots_as_of(snapshot_cache(cache_dir), route_ids(request, static_data), cutoff)
    return {"stage": "LIVE_DATA_MATCHING", "integration_version": "0.1",
            "request": request, "static_data": metadata,
            "matching": match_request(request, static_data, snapshots),
            "provider": {"source": "SUPPLIED_REQUEST"}}
