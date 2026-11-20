"""Project raw GTFS-RT payloads to the configured October research paths.

Projection reduces normalization work without deciding which trains are
eligible. It retains trip identities and statuses, observed endpoint duplicates,
complete candidate-path stop sequences, and non-trip feed evidence. Raw payload
hashes remain the caller's responsibility: these bytes are a derived view.
"""

from google.transit import gtfs_realtime_pb2 as gtfs

from stayorswitch.mta import NYCT_EXTENSIONS


PROJECTION_POLICY = "CONFIGURED_TRIPS_GLOBAL_ENDPOINTS_FULL_LEG_SPANS_TRACK_CHANGES_V1"


def _leg_pairs(config, feed_id):
    pairs = {}
    for route in config.get("routes", []):
        for leg in route.get("legs", []):
            if leg.get("feed_id") != feed_id:
                continue
            for route_id in leg.get("route_ids") or [leg["route_id"]]:
                pairs.setdefault(route_id, set()).add((leg["from_stop_id"], leg["to_stop_id"]))
    return pairs


def _track_changed(stop):
    extension = NYCT_EXTENSIONS["nyct_stop_time_update"]
    if not stop.HasExtension(extension):
        return False
    details = stop.Extensions[extension]
    return bool(details.scheduled_track and details.actual_track
                and details.scheduled_track != details.actual_track)


def project_payload(payload, feed_id, config):
    """Return projected protobuf bytes and explicit input/output scope counts.

    Validate the original message before removing anything, including malformed
    off-scope trips. Preserve all entity shells, header fields and extensions,
    alerts, vehicles and unknown protobuf fields. Clearing an off-scope trip
    update never clears other submessages in the same entity.

    For retained trips, preserve every globally configured endpoint occurrence.
    When both endpoints of a matching configured leg occur, preserve the whole
    slice from their earliest occurrence to their latest occurrence. This keeps
    reverse paths, duplicate endpoints and intermediate skipped/no-data stops
    visible to the existing matcher. Track-change stops outside those slices
    remain present so the normalizer emits the same trip-level reason code.
    """
    feed = gtfs.FeedMessage()
    feed.ParseFromString(payload)
    if not feed.IsInitialized():
        raise ValueError("The GTFS-realtime message is missing required fields.")

    routes = set(config["route_ids"])
    global_stops = set(config["stop_ids"])
    leg_pairs = _leg_pairs(config, feed_id)
    counts = {"projection_policy": PROJECTION_POLICY, "feed_id": feed_id,
              "original_message_validated": True,
              "entities_before": len(feed.entity), "entities_after": len(feed.entity),
              "trips_before": 0, "trips_after": 0,
              "stops_before": 0, "stops_after": 0}
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        counts["trips_before"] += 1
        counts["stops_before"] += len(update.stop_time_update)
        actual_route = update.trip.route_id
        if actual_route not in routes:
            entity.ClearField("trip_update")
            continue
        counts["trips_after"] += 1
        if actual_route not in leg_pairs:
            # Unexpected route/feed combinations still reach route-based
            # profile processing. Without an exact configured feed/route leg,
            # retain their complete stop context rather than guessing a scope.
            counts["stops_after"] += len(update.stop_time_update)
            continue
        positions = {}
        retained = set()
        for index, stop in enumerate(update.stop_time_update):
            positions.setdefault(stop.stop_id, []).append(index)
            if stop.stop_id in global_stops or _track_changed(stop):
                retained.add(index)
        for origin, destination in leg_pairs.get(actual_route, ()):
            origins, destinations = positions.get(origin), positions.get(destination)
            if origins and destinations:
                first = min(origins[0], destinations[0])
                last = max(origins[-1], destinations[-1])
                retained.update(range(first, last + 1))
        if len(retained) != len(update.stop_time_update):
            stops = [stop for index, stop in enumerate(update.stop_time_update) if index in retained]
            del update.stop_time_update[:]
            update.stop_time_update.extend(stops)
        counts["stops_after"] += len(update.stop_time_update)
    return feed.SerializeToString(), counts
