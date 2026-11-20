"""Verified downloads and bounded streaming readers for Subway Data NYC."""

import codecs
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import json
import lzma
import math
from pathlib import Path, PurePosixPath
import re
import tarfile
import time
from urllib.parse import urljoin, urlsplit

import httpx


ROOT = Path(__file__).resolve().parents[2]
SOURCE_BASE = "https://subwaydata.nyc/data/"
HOSTS = {"subwaydata.nyc", "data.subwaydata.nyc"}
FEEDS = {"1234567": "numbered", "ACE": "ace", "BDFM": "bdfm", "G": "g",
         "NQRW": "nqrw", "JZ": "jz", "L": "l", "SIR": "si", "alerts": "subway-alerts"}
NAME = re.compile(r"^nycsubway_(1234567|ACE|BDFM|G|NQRW|JZ|L|SIR|alerts)_"
                  r"(\d{8}T\d{6}(?:\.\d+)?Z)_[A-Za-z0-9]+\.gtfsrt$")
MAX_DOWNLOAD = 1024 ** 3
MAX_MEMBER = 256 * 1024 ** 2
MAX_SNAPSHOT = 16 * 1024 ** 2
MAX_EXPANDED = 128 * 1024 ** 3


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def epoch(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean values are not timestamps.")
    try:
        number = float(value)
    except (ValueError, TypeError):
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timestamps require an explicit timezone.")
        number = parsed.timestamp()
    if not math.isfinite(number) or number < 0:
        raise ValueError("Timestamps must be finite and nonnegative.")
    return number


def dates_between(first, last):
    current, end = date.fromisoformat(first), date.fromisoformat(last)
    if current > end:
        raise ValueError("Date window is reversed.")
    while current <= end:
        yield current.isoformat()
        current += timedelta(days=1)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 ** 2), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def write_gzip_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("wb") as binary, gzip.GzipFile(fileobj=binary, mode="wb", filename="", mtime=0) as compressed:
        compressed.write(json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode())
    temporary.replace(path)


def read_snapshots(path):
    with gzip.open(path, "rt") as handle:
        for line in handle:
            yield json.loads(line)


def read_labels(path):
    with gzip.open(path, "rt") as handle:
        return json.load(handle)


def checked_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in HOSTS or parts.username or
            parts.password or parts.port not in (None, 443)):
        raise ValueError("Archive URL left the approved public HTTPS source.")


def download_archive(day, kind, directory, *, retries=2):
    if date.fromisoformat(day).isoformat() != day or kind not in {"csv", "gtfsrt"}:
        raise ValueError("Invalid archive date or kind.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("subwaydatanyc_" + day + "_" + kind + ".tar.xz")
    sidecar = path.with_suffix(path.suffix + ".metadata.json")
    url = SOURCE_BASE + path.name
    if path.is_file() and sidecar.is_file():
        metadata = json.loads(sidecar.read_text())
        checked_url(metadata.get("resolved_url", ""))
        if (metadata.get("url") == url and metadata.get("bytes") == path.stat().st_size
                and metadata.get("sha256") == sha256(path)):
            return dict(metadata, path=str(path.resolve()), cache_verified=True)
    temporary = path.with_suffix(path.suffix + ".part")
    transport = httpx.HTTPTransport(local_address="0.0.0.0", retries=0)
    with httpx.Client(transport=transport, timeout=180, follow_redirects=False,
                      headers={"User-Agent": "StayOrSwitch-October/1.0"}) as client:
        for attempt in range(retries + 1):
            try:
                current = url
                for _ in range(5):
                    checked_url(current)
                    with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            current = urljoin(current, response.headers["location"])
                            continue
                        response.raise_for_status()
                        size = response.headers.get("content-length")
                        if size and int(size) > MAX_DOWNLOAD:
                            raise ValueError("Archive exceeds the download limit.")
                        digest, total = hashlib.sha256(), 0
                        with temporary.open("wb") as output:
                            for block in response.iter_bytes(1024 ** 2):
                                total += len(block)
                                if total > MAX_DOWNLOAD:
                                    raise ValueError("Archive exceeds the download limit.")
                                output.write(block)
                                digest.update(block)
                        with temporary.open("rb") as handle:
                            if handle.read(6) != b"\xfd7zXZ\x00":
                                raise ValueError("Downloaded payload is not an XZ archive.")
                        temporary.replace(path)
                        metadata = {"source": "Subway Data NYC", "archive_date": day, "kind": kind,
                                    "url": url, "resolved_url": current, "fetched_at": now(),
                                    "bytes": total, "sha256": digest.hexdigest(),
                                    "path": str(path.resolve()), "cache_verified": False}
                        write_json(sidecar, metadata)
                        return metadata
                raise ValueError("Too many archive redirects.")
            except (httpx.HTTPError, OSError):
                if attempt == retries:
                    raise
                time.sleep(min(3, attempt + 1))
            finally:
                temporary.unlink(missing_ok=True)
    raise RuntimeError("Archive download did not complete.")


def acquire(config, directory, workers=2):
    days = list(dates_between(config["start_date"], config["end_date"]))
    first = (date.fromisoformat(days[0]) - timedelta(days=1)).isoformat()
    last = (date.fromisoformat(days[-1]) + timedelta(days=1)).isoformat()
    # Representative smoke dates arrive first so parsing can begin promptly.
    priority = [day for day in ("2026-10-04", "2026-10-05") if day in days]
    ordered = priority + [day for day in days if day not in priority]
    jobs = [(day, kind) for day in ordered for kind in ("csv", "gtfsrt")]
    jobs += [(first, "csv"), (last, "csv")]
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {executor.submit(download_archive, day, kind, directory): (day, kind) for day, kind in jobs}
        for future in as_completed(pending):
            day, kind = pending[future]
            try:
                result = future.result()
                results.append(result)
                print(json.dumps({"stage": "ARCHIVE_VERIFIED", "date": day, "kind": kind,
                                  "bytes": result["bytes"], "completed": len(results), "total": len(jobs)}), flush=True)
            except Exception as error:
                errors.append({"date": day, "kind": kind, "error": type(error).__name__ + ": " + str(error)})
                print(json.dumps({"stage": "ARCHIVE_FAILED", **errors[-1]}), flush=True)
    return sorted(results, key=lambda item: (item["archive_date"], item["kind"])), errors


def safe_members(archive):
    total = 0
    for member in archive:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or ".." in path.parts or "\\" in member.name or
                member.issym() or member.islnk() or not (member.isfile() or member.isdir())):
            raise ValueError("Unsafe archive member.")
        if member.size < 0 or member.size > MAX_MEMBER:
            raise ValueError("Archive member exceeds its streaming limit.")
        total += member.size
        if total > MAX_EXPANDED:
            raise ValueError("Archive exceeds its expanded streaming limit.")
        archive.members.clear()
        yield member


def iter_csv_rows(path, kind):
    import csv
    if kind not in {"trips", "stop_times"}:
        raise ValueError("CSV table must be trips or stop_times.")
    found = False
    with lzma.open(path, "rb") as decoded, tarfile.open(fileobj=decoded, mode="r|") as archive:
        for member in safe_members(archive):
            if not member.isfile() or not member.name.endswith("_" + kind + ".csv"):
                continue
            if found:
                raise ValueError("Duplicate requested CSV table.")
            found = True
            with codecs.getreader("utf-8")(archive.extractfile(member)) as stream:
                reader = csv.DictReader(stream)
                if not reader.fieldnames or "trip_uid" not in reader.fieldnames:
                    raise ValueError("CSV table has no trip_uid column.")
                for row in reader:
                    if None in row:
                        raise ValueError("CSV row exceeds its header.")
                    yield row
    if not found:
        raise ValueError("Requested CSV table is absent.")


def iter_raw_snapshots(path, feed_ids, sample_seconds=60, counts=None, receipt_callback=None):
    """Emit first capture per train bucket, every alert, and ambiguous failures.

    The archive groups feeds separately. Within each feed captures must be
    chronological. Equal-time conflicting payloads produce an explicit invalid
    item rather than resurrecting an earlier successfully parsed observation.
    An optional callback receives every unique train capture before sampling,
    including invalid captures, to establish raw collector receipt provenance.
    """
    if isinstance(sample_seconds, bool) or not isinstance(sample_seconds, int) or sample_seconds <= 0:
        raise ValueError("Sampling interval must be positive.")
    wanted = set(feed_ids) | {"subway-alerts"}
    if not wanted.issubset(set(FEEDS.values())):
        raise ValueError("Unrecognized requested feed.")
    counts = counts if counts is not None else {}
    pending, previous, buckets, failed = {}, {}, {}, {}

    def finish(feed):
        record = pending.pop(feed, None)
        if record is None:
            return None
        if feed != "subway-alerts" and receipt_callback is not None:
            receipt_callback(record)
        bucket = record["captured_at"] if feed == "subway-alerts" else int(record["captured_at"] // sample_seconds)
        unavailable = bool(record.get("invalid_reason")) or record.get("receipt_freshness") in {"MISSING", "STALE"}
        if buckets.get(feed) == bucket and not unavailable and not failed.get(feed, False):
            return None
        buckets[feed] = bucket
        failed[feed] = unavailable
        return record

    with lzma.open(path, "rb") as decoded, tarfile.open(fileobj=decoded, mode="r|") as archive:
        for member in safe_members(archive):
            counts["members"] = counts.get("members", 0) + 1
            if not member.isfile():
                continue
            match = NAME.fullmatch(PurePosixPath(member.name).name)
            if not match:
                if member.name.endswith(".gtfsrt"):
                    raise ValueError("Unrecognized realtime archive filename.")
                continue
            feed = FEEDS[match[1]]
            if feed not in wanted:
                continue
            pattern = "%Y%m%dT%H%M%S.%fZ" if "." in match[2] else "%Y%m%dT%H%M%SZ"
            capture = datetime.strptime(match[2], pattern).replace(tzinfo=timezone.utc).timestamp()
            if capture < previous.get(feed, capture):
                raise ValueError("Archive captures are not ordered within a feed.")
            previous[feed] = capture
            old = pending.get(feed)
            if old is not None and old["captured_at"] != capture:
                ready = finish(feed)
                if ready is not None:
                    yield ready
            if member.size > MAX_SNAPSHOT:
                raise ValueError("Realtime payload exceeds its size limit.")
            payload = archive.extractfile(member).read()
            digest = hashlib.sha256(payload).hexdigest()
            old = pending.get(feed)
            if old is not None and old["captured_at"] == capture:
                if digest != old["sha256"]:
                    old["invalid_reason"] = "CONFLICTING_EQUAL_TIME_PAYLOADS"
                continue
            pending[feed] = {"feed_id": feed, "captured_at": capture, "payload": payload,
                             "sha256": digest, "archive_member": member.name,
                             "archive": Path(path).name, "invalid_reason": None}
        for feed in sorted(pending):
            ready = finish(feed)
            if ready is not None:
                yield ready
