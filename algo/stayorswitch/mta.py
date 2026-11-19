"""Public MTA ingestion and as-of snapshots; no schedule-based route planning.

Source links and provisional freshness settings are listed in data/mta-sources.json.
The normal static schedule is used only for station identity and advisory line
membership. Live stopping patterns may legitimately differ during reroutes.
"""

import copy
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

from google.protobuf import descriptor_pb2, descriptor_pool
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2 as gtfs

STATIC_GTFS_URL = "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip"
FEED_BASE = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/"
ALERTS_FEED_ID = "subway-alerts"
ALERTS_URL = FEED_BASE + "camsys%2Fsubway-alerts.json"
FEED_ROUTES = {
    "ace": ("A", "C", "E", "H"),
    "bdfm": ("B", "D", "F", "FX", "M", "FS"),
    "g": ("G",),
    "jz": ("J", "Z"),
    "nqrw": ("N", "Q", "R", "W"),
    "l": ("L",),
    "numbered": ("1", "2", "3", "4", "5", "6", "6X", "7", "7X", "GS"),
    "si": ("SI", "SIR"),
}
FEED_URLS = {
    feed_id: FEED_BASE + "nyct%2Fgtfs" + ("" if feed_id == "numbered" else "-" + feed_id)
    for feed_id in FEED_ROUTES
}
ROUTE_FEEDS = {route: feed_id for feed_id, routes in FEED_ROUTES.items() for route in routes}


def _instant(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)):
        result = datetime.fromtimestamp(value, timezone.utc)
    else:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("A timezone-aware timestamp is required.")
    return result.astimezone(timezone.utc)


def _iso(value):
    return _instant(value).isoformat().replace("+00:00", "Z")


def _now():
    return _iso(datetime.now(timezone.utc))


def _epoch(value):
    if value is None or value == "":
        return None
    number = int(value)
    return number if number >= 0 else None


def route_feed_ids(route_ids):
    """Return known feed groups; unqualified S is ambiguous and is not guessed."""
    return sorted({ROUTE_FEEDS[str(route).upper()] for route in route_ids
                   if str(route).upper() in ROUTE_FEEDS})


def _register_nyct_extensions():
    """Register the MTA-published NYCT proto fields without a runtime compiler.

    Wire definitions: MTA's linked gtfs-realtime-NYCT.proto, copyright 2012 MTA.
    Only descriptors are reproduced; the standard GTFS binding owns message code.
    """
    pool = descriptor_pool.Default()
    try:
        return {name: pool.FindExtensionByName("transit_realtime." + name)
                for name in ("nyct_feed_header", "nyct_trip_descriptor", "nyct_stop_time_update")}
    except KeyError:
        pass
    f = descriptor_pb2.FileDescriptorProto(
        name="stayorswitch-nyct.proto", package="transit_realtime", syntax="proto2")
    f.dependency.append(gtfs.DESCRIPTOR.name)
    optional = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    repeated = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
    required = descriptor_pb2.FieldDescriptorProto.LABEL_REQUIRED
    string = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    message = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    boolean = descriptor_pb2.FieldDescriptorProto.TYPE_BOOL
    enum = descriptor_pb2.FieldDescriptorProto.TYPE_ENUM

    def field(owner, name, number, kind, label=optional, type_name=None):
        result = owner.field.add(name=name, number=number, type=kind, label=label)
        if type_name:
            result.type_name = type_name

    period = f.message_type.add(name="TripReplacementPeriod")
    field(period, "route_id", 1, string)
    field(period, "replacement_period", 2, message, type_name=".transit_realtime.TimeRange")
    header = f.message_type.add(name="NyctFeedHeader")
    field(header, "nyct_subway_version", 1, string, required)
    field(header, "trip_replacement_period", 2, message, repeated,
          ".transit_realtime.TripReplacementPeriod")
    trip = f.message_type.add(name="NyctTripDescriptor")
    field(trip, "train_id", 1, string)
    field(trip, "is_assigned", 2, boolean)
    direction = trip.enum_type.add(name="Direction")
    for name, number in (("NORTH", 1), ("EAST", 2), ("SOUTH", 3), ("WEST", 4)):
        direction.value.add(name=name, number=number)
    field(trip, "direction", 3, enum, type_name=".transit_realtime.NyctTripDescriptor.Direction")
    stop = f.message_type.add(name="NyctStopTimeUpdate")
    field(stop, "scheduled_track", 1, string)
    field(stop, "actual_track", 2, string)
    for name, owner, kind in (
            ("nyct_feed_header", "FeedHeader", "NyctFeedHeader"),
            ("nyct_trip_descriptor", "TripDescriptor", "NyctTripDescriptor"),
            ("nyct_stop_time_update", "TripUpdate.StopTimeUpdate", "NyctStopTimeUpdate")):
        f.extension.add(name=name, number=1001, label=optional, type=message,
                        extendee=".transit_realtime." + owner,
                        type_name=".transit_realtime." + kind)
    pool.AddSerializedFile(f.SerializeToString())
    return {name: pool.FindExtensionByName("transit_realtime." + name)
            for name in ("nyct_feed_header", "nyct_trip_descriptor", "nyct_stop_time_update")}


NYCT_EXTENSIONS = _register_nyct_extensions()


def _present(message, field):
    return getattr(message, field) if message.HasField(field) else None


def _enum(message, field):
    number = getattr(message, field)
    descriptor = message.DESCRIPTOR.fields_by_name[field].enum_type
    entry = descriptor.values_by_number.get(number)
    return entry.name if entry else "UNKNOWN_" + str(number)


def _extension(message, name):
    descriptor = NYCT_EXTENSIONS[name]
    return message.Extensions[descriptor] if message.HasExtension(descriptor) else None


def _trip_identity(feed_id, descriptor):
    trip_id = _present(descriptor, "trip_id")
    route_id = _present(descriptor, "route_id")
    service_date = _present(descriptor, "start_date")
    if not trip_id or not route_id or not service_date or len(service_date) != 8 or not service_date.isdigit():
        return None
    try:
        datetime.strptime(service_date, "%Y%m%d")
    except ValueError:
        return None
    parts = ("MTA", feed_id, service_date, route_id, trip_id,
             _present(descriptor, "start_time") or "")
    return ":".join(quote(value, safe="") for value in parts)


def _base_snapshot(feed_id, kind, fetched_at, requested_at=None, url=None):
    return {"feed_id": feed_id, "kind": kind, "url": url,
            "requested_at": _iso(requested_at or fetched_at), "fetched_at": _iso(fetched_at),
            "source_updated_at": None, "status": "AVAILABLE", "reason_codes": [],
            "trips": [], "alerts": [], "vehicles": [], "trip_replacement_periods": []}


def _missing(snapshot, code):
    result = copy.deepcopy(snapshot)
    result["status"] = "MISSING"
    result["reason_codes"] = list(dict.fromkeys(result.get("reason_codes", []) + [code]))
    result["trips"] = []
    result["alerts"] = []
    result["vehicles"] = []
    return result


def _translation(value):
    entries = (value or {}).get("translation", [])
    for entry in entries:
        if entry.get("language", "").lower().split("-")[0] == "en":
            return entry.get("text")
    for entry in entries:
        if not entry.get("language"):
            return entry.get("text")
    return entries[0].get("text") if entries else None


def _normalize_alert(entity):
    alert = entity.get("alert", {})
    selectors = []
    for selector in alert.get("informed_entity", []):
        selectors.append({
            "agency_id": selector.get("agency_id"), "route_id": selector.get("route_id"),
            "stop_id": selector.get("stop_id"), "direction_id": selector.get("direction_id"),
            "trip": selector.get("trip"),
            "extensions": {key: value for key, value in selector.items() if "." in key},
        })
    return {"id": entity.get("id"),
            "active_periods": [{"start": _epoch(period.get("start")),
                                "end": _epoch(period.get("end"))}
                               for period in alert.get("active_period", [])],
            "informed_entities": selectors,
            "cause": alert.get("cause"), "effect": alert.get("effect"),
            "header": _translation(alert.get("header_text")),
            "description": _translation(alert.get("description_text")),
            "url": _translation(alert.get("url")),
            "extensions": {key: value for key, value in alert.items() if "." in key}}


def parse_train_feed(data, feed_id, fetched_at, requested_at=None, url=None):
    """Decode a whole feed; never merge its entities with a previous full feed."""
    snapshot = _base_snapshot(feed_id, "train", fetched_at, requested_at,
                              url or FEED_URLS.get(feed_id))
    feed = gtfs.FeedMessage()
    feed.ParseFromString(data)
    if not feed.IsInitialized():
        raise ValueError("The GTFS-realtime message is missing required fields.")
    snapshot["sha256"] = hashlib.sha256(data).hexdigest()
    stamp = _epoch(_present(feed.header, "timestamp"))
    snapshot["source_updated_at"] = _iso(stamp) if stamp else None
    snapshot["incrementality"] = _enum(feed.header, "incrementality")
    if snapshot["incrementality"] != "FULL_DATASET":
        return _missing(snapshot, "UNSUPPORTED_INCREMENTAL_FEED")
    header_ext = _extension(feed.header, "nyct_feed_header")
    if header_ext is not None:
        for period in header_ext.trip_replacement_period:
            snapshot["trip_replacement_periods"].append({
                "route_id": _present(period, "route_id"),
                "start": _epoch(_present(period.replacement_period, "start")),
                "end": _epoch(_present(period.replacement_period, "end")),
            })
    for entity in feed.entity:
        if entity.is_deleted:
            snapshot["reason_codes"].append("DELETED_ENTITY_IGNORED")
            continue
        if entity.HasField("alert"):
            snapshot["alerts"].append(_normalize_alert(
                MessageToDict(entity, preserving_proto_field_name=True)))
        if entity.HasField("vehicle"):
            vehicle = entity.vehicle
            snapshot["vehicles"].append({
                "entity_id": entity.id,
                "trip_identity": _trip_identity(feed_id, vehicle.trip) if vehicle.HasField("trip") else None,
                "trip_id": _present(vehicle.trip, "trip_id") if vehicle.HasField("trip") else None,
                "route_id": _present(vehicle.trip, "route_id") if vehicle.HasField("trip") else None,
                "stop_id": _present(vehicle, "stop_id"),
                "current_stop_sequence": _present(vehicle, "current_stop_sequence"),
                "current_status": _enum(vehicle, "current_status") if vehicle.HasField("current_status") else None,
                "timestamp": _epoch(_present(vehicle, "timestamp")),
            })
        if not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        descriptor = update.trip
        ext = _extension(descriptor, "nyct_trip_descriptor")
        trip = {"id": _trip_identity(feed_id, descriptor), "entity_id": entity.id,
                "feed_id": feed_id, "agency": "MTA New York City Transit",
                "route_id": _present(descriptor, "route_id"),
                "trip_id": _present(descriptor, "trip_id"),
                "start_date": _present(descriptor, "start_date"),
                "start_time": _present(descriptor, "start_time"),
                "direction_id": _present(descriptor, "direction_id"),
                "schedule_relationship": _enum(descriptor, "schedule_relationship"),
                "nyct_direction": _enum(ext, "direction") if ext and ext.HasField("direction") else None,
                "nyct_train_id": _present(ext, "train_id") if ext else None,
                "is_assigned": _present(ext, "is_assigned") if ext else None,
                "timestamp": _epoch(_present(update, "timestamp")),
                "stop_updates": [], "reason_codes": []}
        if trip["id"] is None:
            trip["reason_codes"].append("MISSING_SERVICE_DATE_OR_TRIP_IDENTITY")
        for stop in update.stop_time_update:
            stop_ext = _extension(stop, "nyct_stop_time_update")
            scheduled = _present(stop_ext, "scheduled_track") if stop_ext else None
            actual = _present(stop_ext, "actual_track") if stop_ext else None
            if actual and scheduled and actual != scheduled:
                trip["reason_codes"].append("TRACK_CHANGE_OBSERVED")
            trip["stop_updates"].append({
                "stop_id": _present(stop, "stop_id"),
                "stop_sequence": _present(stop, "stop_sequence"),
                "arrival_time": _epoch(_present(stop.arrival, "time")) if stop.HasField("arrival") else None,
                "departure_time": _epoch(_present(stop.departure, "time")) if stop.HasField("departure") else None,
                "arrival_uncertainty": _present(stop.arrival, "uncertainty") if stop.HasField("arrival") else None,
                "departure_uncertainty": _present(stop.departure, "uncertainty") if stop.HasField("departure") else None,
                "schedule_relationship": _enum(stop, "schedule_relationship"),
                "scheduled_track": scheduled, "actual_track": actual,
            })
        trip["reason_codes"] = list(dict.fromkeys(trip["reason_codes"]))
        snapshot["trips"].append(trip)
    snapshot["reason_codes"] = list(dict.fromkeys(snapshot["reason_codes"]))
    return snapshot


def parse_alerts_feed(data, fetched_at, requested_at=None, feed_id=ALERTS_FEED_ID, url=ALERTS_URL):
    """Parse official alerts JSON, preserving selector and Mercury metadata."""
    snapshot = _base_snapshot(feed_id, "alerts", fetched_at, requested_at, url)
    payload = json.loads(data)
    if not isinstance(payload, dict) or not isinstance(payload.get("header"), dict):
        raise ValueError("An alert feed must contain a GTFS-realtime header.")
    snapshot["sha256"] = hashlib.sha256(data).hexdigest()
    stamp = _epoch(payload["header"].get("timestamp"))
    snapshot["source_updated_at"] = _iso(stamp) if stamp else None
    incrementality = payload["header"].get("incrementality", "FULL_DATASET")
    snapshot["incrementality"] = incrementality
    if incrementality not in ("FULL_DATASET", 0):
        return _missing(snapshot, "UNSUPPORTED_INCREMENTAL_FEED")
    for entity in payload.get("entity", []):
        if entity.get("is_deleted"):
            snapshot["reason_codes"].append("DELETED_ENTITY_IGNORED")
        elif "alert" in entity:
            snapshot["alerts"].append(_normalize_alert(entity))
    return snapshot


def alert_is_active(alert, when):
    """Active periods are half-open; absent boundaries are unbounded."""
    instant = _instant(when).timestamp()
    periods = alert.get("active_periods", [])
    return not periods or any(
        (period.get("start") is None or period["start"] <= instant)
        and (period.get("end") is None or instant < period["end"])
        for period in periods)


def snapshot_status(snapshot, cutoff, train_max_age_seconds=180, alerts_max_fetch_age_seconds=300):
    """Conservative as-of freshness; defaults are provisional integration settings.

    An unchanged service-alert source timestamp is normal. A recent successful
    fetch can therefore keep it fresh, but a missing or future source time cannot.
    """
    if not snapshot or snapshot.get("status") != "AVAILABLE":
        return "MISSING"
    try:
        at = _instant(cutoff)
        fetched = _instant(snapshot["fetched_at"])
        source = _instant(snapshot["source_updated_at"])
        requested = _instant(snapshot.get("requested_at") or snapshot["fetched_at"])
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
        return "MISSING"
    if source > fetched or fetched > at or requested > fetched:
        return "MISSING"
    if snapshot.get("kind") == "alerts":
        return "STALE" if (at - fetched).total_seconds() > alerts_max_fetch_age_seconds else "FRESH"
    age = max((at - source).total_seconds(), (at - fetched).total_seconds())
    return "STALE" if age > train_max_age_seconds else "FRESH"


def collect_feeds(route_ids, fetch):
    """Fetch relevant train groups and subway alerts; isolate per-feed failures.

    ``fetch`` accepts a public URL and returns a FetchResult with body, requested_at,
    fetched_at and status_code. Failed fetches are observations, not empty trains.
    """
    result = []
    requested_routes = sorted({str(route).upper() for route in route_ids})
    jobs = [(feed, "train", FEED_URLS[feed]) for feed in route_feed_ids(requested_routes)]
    jobs.append((ALERTS_FEED_ID, "alerts", ALERTS_URL))
    for feed_id, kind, url in jobs:
        requested_at = _now()
        try:
            response = fetch(url)
            if response.status_code != 200:
                raise ValueError("The feed response did not have HTTP status 200.")
            if kind == "train":
                snapshot = parse_train_feed(response.body, feed_id, response.fetched_at,
                                            response.requested_at, url)
            else:
                snapshot = parse_alerts_feed(response.body, response.fetched_at,
                                             response.requested_at, feed_id, url)
        except Exception as exc:
            snapshot = _missing(_base_snapshot(feed_id, kind, _now(), requested_at, url),
                                "FEED_FETCH_OR_PARSE_FAILED")
            # Record the exception class, never an arbitrary transport message or credentials.
            snapshot["error_type"] = type(exc).__name__
        result.append(snapshot)
    for route in requested_routes:
        if route not in ROUTE_FEEDS:
            result.append(_missing(_base_snapshot("unsupported:" + route, "train", _now()),
                                   "UNSUPPORTED_ROUTE_FEED"))
    return result


def load_static_gtfs(data):
    """Read stops and advisory route membership without extracting ZIP paths."""
    with ZipFile(io.BytesIO(data)) as archive:
        def rows(name):
            with archive.open(name) as stream:
                yield from csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
        stops = {}
        for row in rows("stops.txt"):
            latitude = float(row["stop_lat"]) if row.get("stop_lat") else None
            longitude = float(row["stop_lon"]) if row.get("stop_lon") else None
            stops[row["stop_id"]] = {
                "id": row["stop_id"], "name": row.get("stop_name") or row["stop_id"],
                "latitude": latitude, "longitude": longitude,
                "parent_station": row.get("parent_station") or None,
                "location_type": int(row.get("location_type") or 0),
            }
        routes = {row["route_id"]: {"short_name": row.get("route_short_name"),
                                   "long_name": row.get("route_long_name"),
                                   "agency_id": row.get("agency_id"),
                                   "route_type": row.get("route_type")}
                  for row in rows("routes.txt")}
        trip_routes = {row["trip_id"]: row["route_id"] for row in rows("trips.txt")}
        route_stops = {route_id: set() for route_id in routes}
        for row in rows("stop_times.txt"):
            route_id = trip_routes.get(row["trip_id"])
            stop_id = row["stop_id"]
            if route_id and stop_id in stops:
                route_stops.setdefault(route_id, set()).add(stop_id)
                parent = stops[stop_id]["parent_station"]
                if parent:
                    route_stops[route_id].add(parent)
    return {"stops": stops, "routes": routes,
            "route_stops": {key: sorted(value) for key, value in route_stops.items()},
            "sha256": hashlib.sha256(data).hexdigest(), "source_url": STATIC_GTFS_URL,
            "scope": "STATION_IDENTITIES_AND_ADVISORY_ROUTE_MEMBERSHIP"}


class SnapshotCache:
    """Append complete observations and retrieve the latest known result as of time.

    A failed latest fetch is returned as missing instead of silently reviving older
    entities. The cache is not a continuously running collector; callers poll it.
    """
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _prefix(feed_id):
        return hashlib.sha256(feed_id.encode()).hexdigest()[:16]

    def put(self, snapshot):
        _instant(snapshot["fetched_at"])
        content = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(content.encode()).hexdigest()
        name = self._prefix(snapshot["feed_id"]) + "-" + digest + ".json"
        target = self.directory / name
        temporary = self.directory / (name + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)
        return target

    def latest(self, feed_id, cutoff):
        at = _instant(cutoff)
        snapshots = []
        for path in self.directory.glob(self._prefix(feed_id) + "-*.json"):
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            if snapshot.get("feed_id") == feed_id and _instant(snapshot["fetched_at"]) <= at:
                snapshots.append(snapshot)
        if not snapshots:
            return None
        newest = max(_instant(value["fetched_at"]) for value in snapshots)
        tied = sorted((value for value in snapshots if _instant(value["fetched_at"]) == newest),
                      key=lambda value: json.dumps(value, sort_keys=True))
        # Equal collection times do not establish an ordering. A known failure or
        # invalid timestamp must never lose to success because of directory order.
        unavailable = []
        for result in tied:
            if result.get("status") != "AVAILABLE":
                unavailable.append(result)
            elif snapshot_status(result, cutoff) == "MISSING":
                unavailable.append(_missing(result, "INVALID_SNAPSHOT_TIMESTAMPS"))
        if unavailable:
            return unavailable[0]
        contents = {json.dumps({key: value for key, value in result.items()
                                if key not in {"requested_at", "fetched_at"}}, sort_keys=True)
                    for result in tied}
        if len(contents) > 1:
            return _missing(tied[0], "AMBIGUOUS_SNAPSHOT_ORDER")
        return tied[0]
