"""Download and stream Subway Data NYC archives without extracting them.

Archive filenames carry the original collector's UTC download time. This is
different from the feed header timestamp and from our archive retrieval time.
Train sampling retains the first unambiguous snapshot in each fixed UTC bucket.
All distinct alert captures are retained because each can change service state.
Files are chronological within a feed, but feeds are not globally interleaved.
"""

import codecs
import csv
from datetime import date, datetime, timezone
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import tarfile
import time
from urllib.parse import urljoin, urlsplit

import httpx
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2


SOURCE_BASE = "https://subwaydata.nyc/data/"
ALLOWED_HOSTS = {"subwaydata.nyc", "data.subwaydata.nyc"}
ARCHIVE_FEEDS = {
    "1234567": "numbered", "ACE": "ace", "BDFM": "bdfm", "G": "g",
    "JZ": "jz", "L": "l", "NQRW": "nqrw", "SIR": "si",
    "alerts": "subway-alerts",
}
SNAPSHOT_NAME = re.compile(
    r"^nycsubway_(1234567|ACE|BDFM|G|JZ|L|NQRW|SIR|alerts)_"
    r"(\d{8}T\d{6}(?:\.\d+)?Z)_([A-Za-z0-9]+)\.gtfsrt$")
MAX_DOWNLOAD_BYTES = 1024 ** 3
MAX_MEMBER_BYTES = 256 * 1024 ** 2
MAX_SNAPSHOT_BYTES = 16 * 1024 ** 2
MAX_UNCOMPRESSED_BYTES = 128 * 1024 ** 3


class ArchiveError(ValueError):
    """The source archive cannot be handled with the documented guarantees."""


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 ** 2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_url(service_date, kind):
    if not isinstance(service_date, str):
        service_date = service_date.isoformat()
    try:
        parsed = date.fromisoformat(service_date)
    except (TypeError, ValueError) as exc:
        raise ArchiveError("The archive date must be YYYY-MM-DD.") from exc
    if parsed.isoformat() != service_date or kind not in {"csv", "gtfsrt"}:
        raise ArchiveError("Invalid archive date or kind.")
    return SOURCE_BASE + "subwaydatanyc_" + service_date + "_" + kind + ".tar.xz"


def _check_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise ArchiveError("Archive download redirected outside the approved HTTPS hosts.")


def _read_cached(path, metadata_path, url):
    if not path.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(metadata["fetched_at"].replace("Z", "+00:00"))
        if (fetched.tzinfo is None or metadata["url"] != url
                or metadata["bytes"] != path.stat().st_size
                or metadata["sha256"] != sha256_file(path)):
            return None
        _check_url(metadata["resolved_url"])
        metadata["path"] = str(path)
        metadata["cache_verified"] = True
        return metadata
    except (OSError, ValueError, TypeError, KeyError):
        return None


def download_archive(service_date, kind, root, *, client=None, retries=2,
                     max_bytes=MAX_DOWNLOAD_BYTES):
    """Return download provenance; verify a sidecar before reusing cached bytes.

    Checksums establish local reproducibility, not publisher authentication.
    Redirects are followed only between the two observed source hostnames.
    """
    url = _source_url(service_date, kind)
    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / url.rsplit("/", 1)[1]
    metadata_path = path.with_name(path.name + ".metadata.json")
    cached = _read_cached(path, metadata_path, url)
    if cached is not None:
        return cached
    if retries < 0 or retries > 5 or max_bytes <= 0:
        raise ArchiveError("Invalid download retry or size limit.")
    owns_client = client is None
    if client is None:
        transport = httpx.HTTPTransport(local_address="0.0.0.0", retries=0)
        client = httpx.Client(transport=transport, timeout=120, follow_redirects=False,
                              headers={"User-Agent": "StayOrSwitch-history/0.1"})
    temporary = path.with_name(path.name + ".part")
    try:
        for attempt in range(retries + 1):
            requested_at = _utc_now()
            try:
                current_url = url
                for redirect_index in range(5):
                    _check_url(current_url)
                    with client.stream("GET", current_url, follow_redirects=False) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location or redirect_index == 4:
                                raise ArchiveError("Archive redirect is missing or excessive.")
                            current_url = urljoin(current_url, location)
                            _check_url(current_url)
                            continue
                        response.raise_for_status()
                        length = response.headers.get("content-length")
                        if length is not None and int(length) > max_bytes:
                            raise ArchiveError("Archive exceeds the download size limit.")
                        digest = hashlib.sha256()
                        byte_count = 0
                        with temporary.open("wb") as output:
                            for chunk in response.iter_bytes(1024 ** 2):
                                byte_count += len(chunk)
                                if byte_count > max_bytes:
                                    raise ArchiveError("Archive exceeds the download size limit.")
                                digest.update(chunk)
                                output.write(chunk)
                        with temporary.open("rb") as downloaded:
                            magic = downloaded.read(6)
                        if byte_count < 6 or magic != b"\xfd7zXZ\x00":
                            raise ArchiveError("The response is not an XZ archive.")
                        metadata = {
                            "source": "Subway Data NYC", "url": url,
                            "resolved_url": current_url, "archive_date": str(service_date),
                            "archive_date_timezone": "America/New_York", "kind": kind,
                            "requested_at": requested_at, "fetched_at": _utc_now(),
                            "bytes": byte_count, "sha256": digest.hexdigest(),
                            "path": str(path), "cache_verified": False,
                        }
                        temporary.replace(path)
                        temporary_metadata = metadata_path.with_name(metadata_path.name + ".part")
                        temporary_metadata.write_text(json.dumps(metadata, indent=2) + "\n",
                                                      encoding="utf-8")
                        temporary_metadata.replace(metadata_path)
                        return metadata
            except (httpx.HTTPError, OSError) as exc:
                if attempt == retries:
                    raise ArchiveError("Archive download failed after bounded retries.") from exc
                time.sleep(min(attempt + 1, 3))
            finally:
                temporary.unlink(missing_ok=True)
        raise ArchiveError("Archive download did not complete.")
    finally:
        if owns_client:
            client.close()


def download_day(service_date, root, kinds=("csv", "gtfsrt"), **kwargs):
    """Download the selected archive kinds for one New York calendar date."""
    return [download_archive(service_date, kind, root, **kwargs) for kind in kinds]


def _safe_member(member):
    path = PurePosixPath(member.name)
    if (path.is_absolute() or ".." in path.parts or "\\" in member.name
            or member.issym() or member.islnk() or not (member.isfile() or member.isdir())):
        raise ArchiveError("Unsafe or unsupported tar member: " + member.name)
    if member.size < 0 or member.size > MAX_MEMBER_BYTES:
        raise ArchiveError("Tar member exceeds the streaming size limit.")


def _members(archive):
    total = 0
    while True:
        member = archive.next()
        if member is None:
            break
        _safe_member(member)
        total += member.size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ArchiveError("Archive exceeds the uncompressed streaming limit.")
        # TarFile otherwise retains every header even in streaming mode.
        archive.members.clear()
        yield member


def iter_csv_rows(path, kind="trips"):
    """Yield the named CSV table without extraction or whole-file materialization."""
    if kind not in {"trips", "stop_times"}:
        raise ArchiveError("CSV kind must be trips or stop_times.")
    found = False
    with lzma.open(path, "rb") as decoded, tarfile.open(fileobj=decoded, mode="r|") as archive:
        for member in _members(archive):
            if not member.isfile() or not member.name.endswith("_" + kind + ".csv"):
                continue
            if found:
                raise ArchiveError("The archive contains duplicate requested CSV tables.")
            found = True
            source = archive.extractfile(member)
            # codecs preserves streaming and avoids TextIOWrapper calling the
            # unsupported seekable() method on Python 3.9's tar _Stream.
            with codecs.getreader("utf-8")(source) as text:
                reader = csv.DictReader(text)
                if not reader.fieldnames or "trip_uid" not in reader.fieldnames:
                    raise ArchiveError("CSV table has no trip_uid header.")
                for row in reader:
                    if None in row:
                        raise ArchiveError("CSV row contains more fields than its header.")
                    yield row
    if not found:
        raise ArchiveError("Requested CSV table is missing from the archive.")


def _parse_capture(value):
    pattern = "%Y%m%dT%H%M%S.%fZ" if "." in value else "%Y%m%dT%H%M%SZ"
    try:
        return datetime.strptime(value, pattern).replace(tzinfo=timezone.utc).timestamp()
    except ValueError as exc:
        raise ArchiveError("Invalid collector timestamp in archive member.") from exc


def iter_snapshots(path, feed_ids=None, sample_seconds=60, stats=None):
    """Yield sampled protobuf payloads using collector availability timestamps.

    Equal-capture duplicates collapse. Conflicting payloads at one capture time
    are excluded before any payload for that time is emitted. Sampling does not
    imply an independent trip or incident, and cannot establish arrival truth.
    """
    if sample_seconds < 0 or not isinstance(sample_seconds, int):
        raise ArchiveError("sample_seconds must be a nonnegative integer.")
    wanted = set(feed_ids) if feed_ids is not None else set(ARCHIVE_FEEDS.values())
    if not wanted.issubset(set(ARCHIVE_FEEDS.values())):
        raise ArchiveError("Unknown archive feed identifier.")
    stats = stats if stats is not None else {}
    for key in ("members", "snapshot_members", "selected_snapshots", "skipped_feed",
                "skipped_sampling", "duplicate_capture", "conflicting_capture",
                "invalid_protobuf", "missing_source_timestamp"):
        stats.setdefault(key, 0)
    stats.setdefault("feeds", {})
    stats.setdefault("capture_gap_diagnostic", {
        "threshold_seconds": 60,
        "measurement": "Consecutive archived collector captures before sampling.",
        "interpretation": "Content deduplication can create gaps; these are not proven collection outages.",
        "alerts": "Alert captures are change-only after collector content deduplication.",
        "boundary_gaps": "Time before the first and after the last archive capture is not inferred.",
    })
    pending = {}
    previous_capture = {}
    selected_bucket = {}

    def finish(feed_id):
        item = pending.pop(feed_id, None)
        if item is None:
            return None
        if item.pop("conflict", False):
            stats["conflicting_capture"] += 1
            return None
        if item.pop("invalid_protobuf", False):
            return None
        interval = 0 if feed_id == "subway-alerts" else sample_seconds
        bucket = int(item["captured_at"] // interval) if interval else item["captured_at"]
        if selected_bucket.get(feed_id) == bucket:
            stats["skipped_sampling"] += 1
            return None
        selected_bucket[feed_id] = bucket
        stats["selected_snapshots"] += 1
        return item

    with lzma.open(path, "rb") as decoded, tarfile.open(fileobj=decoded, mode="r|") as archive:
        for member in _members(archive):
            stats["members"] += 1
            if not member.isfile():
                continue
            match = SNAPSHOT_NAME.fullmatch(PurePosixPath(member.name).name)
            if not match:
                if member.name.endswith(".gtfsrt"):
                    raise ArchiveError("Unknown GTFS-Realtime member filename: " + member.name)
                continue
            stats["snapshot_members"] += 1
            feed_id = ARCHIVE_FEEDS[match.group(1)]
            captured_at = _parse_capture(match.group(2))
            if captured_at < previous_capture.get(feed_id, captured_at):
                raise ArchiveError("Snapshots are not chronological within a feed.")
            previous_capture[feed_id] = captured_at
            feed_stats = stats["feeds"].setdefault(feed_id, {
                "snapshot_members": 0, "first_captured_at": captured_at,
                "last_captured_at": captured_at,
                "max_capture_gap_seconds": 0,
                "capture_gaps_over_60_seconds": 0,
                "cumulative_capture_gap_seconds_over_60": 0,
                "capture_gap_examples": [],
            })
            if feed_stats["snapshot_members"]:
                previous_time = feed_stats["last_captured_at"]
                gap = round(captured_at - previous_time, 6)
                feed_stats["max_capture_gap_seconds"] = max(
                    feed_stats["max_capture_gap_seconds"], gap)
                if gap > 60:
                    feed_stats["capture_gaps_over_60_seconds"] += 1
                    feed_stats["cumulative_capture_gap_seconds_over_60"] = round(
                        feed_stats["cumulative_capture_gap_seconds_over_60"] + gap, 6)
                    if len(feed_stats["capture_gap_examples"]) < 10:
                        feed_stats["capture_gap_examples"].append({
                            "previous_captured_at": previous_time,
                            "next_captured_at": captured_at,
                            "gap_seconds": gap,
                        })
            feed_stats["snapshot_members"] += 1
            feed_stats["first_captured_at"] = min(feed_stats["first_captured_at"], captured_at)
            feed_stats["last_captured_at"] = max(feed_stats["last_captured_at"], captured_at)
            if feed_id not in wanted:
                stats["skipped_feed"] += 1
                continue
            previous = pending.get(feed_id)
            if previous is not None and captured_at != previous["captured_at"]:
                completed = finish(feed_id)
                if completed is not None:
                    yield completed
            interval = 0 if feed_id == "subway-alerts" else sample_seconds
            bucket = int(captured_at // interval) if interval else captured_at
            # Skip body decoding once this bucket has a selected record, except
            # a pending equal-capture group whose ambiguity still needs checking.
            if selected_bucket.get(feed_id) == bucket and feed_id not in pending:
                stats["skipped_sampling"] += 1
                continue
            if member.size > MAX_SNAPSHOT_BYTES:
                raise ArchiveError("GTFS-Realtime member exceeds the payload limit.")
            payload = archive.extractfile(member).read()
            digest = hashlib.sha256(payload).hexdigest()
            previous = pending.get(feed_id)
            if previous is not None:
                if previous["content_sha256"] == digest:
                    stats["duplicate_capture"] += 1
                else:
                    previous["conflict"] = True
                continue
            message = gtfs_realtime_pb2.FeedMessage()
            invalid_protobuf = False
            try:
                message.ParseFromString(payload)
                if not message.IsInitialized():
                    raise DecodeError("Required protobuf fields are absent.")
            except DecodeError:
                stats["invalid_protobuf"] += 1
                invalid_protobuf = True
            source_time = (message.header.timestamp if not invalid_protobuf
                           and message.header.HasField("timestamp") else None)
            if source_time is None:
                stats["missing_source_timestamp"] += 1
            pending[feed_id] = {
                "captured_at": captured_at, "source_updated_at": source_time,
                "feed_id": feed_id, "payload": payload, "member_name": member.name,
                "content_sha256": digest, "archive_content_hash": match.group(3),
                "archive_name": Path(path).name,
                "capture_time_basis": "ARCHIVE_FILENAME_DOWNLOAD_TIME",
                "invalid_protobuf": invalid_protobuf,
            }
    for feed_id in list(pending):
        completed = finish(feed_id)
        if completed is not None:
            yield completed
