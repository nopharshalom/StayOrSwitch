"""Bounded HTTP requests without exposing credentials in logs or exceptions."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlsplit

import httpx


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class FetchResult:
    url: str
    body: bytes
    requested_at: str
    fetched_at: str
    status_code: int


class NetworkError(RuntimeError):
    """A safe error description, never a request/header dump."""

    def __init__(self, code, message, status_code=None):
        self.code = code
        self.status_code = status_code
        super().__init__(message)


def read_local_settings(path):
    """Read plain KEY=value settings; never execute or interpolate their contents."""
    path = Path(path)
    if not path.exists():
        return {}
    values = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("Invalid local settings entry on line %s." % number)
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name or not name.replace("_", "a").isalnum():
            raise ValueError("Invalid setting name on line %s." % number)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


class HttpClient:
    """Use IPv4 by default to match the development key's IPv4 allowlist.

    No automatic retries: a user-triggered provider query should not silently
    multiply billable calls. TLS verification stays enabled. Each response has
    a collection timestamp recorded only after its body has been received.
    """

    def __init__(self, *, ipv4=True, timeout_seconds=30, max_bytes=64 * 1024 * 1024,
                 transport=None):
        if timeout_seconds <= 0 or max_bytes <= 0:
            raise ValueError("Timeout and response size limit must be positive.")
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds
        if transport is None:
            transport = httpx.HTTPTransport(local_address="0.0.0.0" if ipv4 else None,
                                            retries=0)
        self.client = httpx.Client(transport=transport, timeout=timeout_seconds,
                                   follow_redirects=False)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.client.close()

    def get(self, url):
        return self.request("GET", url)

    def post_json(self, url, body, headers=None):
        return self.request("POST", url, body=body, headers=headers)

    def request(self, method, url, *, body=None, headers: Optional[Mapping] = None):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ValueError("Only HTTPS URLs without embedded credentials are supported.")
        headers = dict(headers or {})
        secrets = [str(v) for k, v in headers.items()
                   if k.lower() in {"x-goog-api-key", "authorization"}]
        requested_at = utc_now()
        try:
            with self.client.stream(method, url, json=body, headers=headers) as response:
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise NetworkError("RESPONSE_TOO_LARGE", "Upstream response exceeded its size limit.")
                    chunks.append(chunk)
                content = b"".join(chunks)
                fetched_at = utc_now()
                if not 200 <= response.status_code < 300:
                    code = "HTTP_%s" % response.status_code
                    message = "Upstream request returned HTTP %s." % response.status_code
                    try:
                        error = json.loads(content).get("error", {})
                        if isinstance(error, dict):
                            message = str(error.get("message", message))
                            reasons = [d.get("reason") for d in error.get("details", [])
                                       if isinstance(d, dict) and d.get("reason")]
                            if reasons:
                                code = str(reasons[0])
                    except (ValueError, AttributeError):
                        pass
                    for secret in secrets:
                        if secret:
                            message = message.replace(secret, "[REDACTED]")
                            code = code.replace(secret, "[REDACTED]")
                    raise NetworkError(code[:160], message[:600], response.status_code)
                return FetchResult(url, content, requested_at, fetched_at, response.status_code)
        except httpx.HTTPError as exc:
            # HTTP libraries can include URLs and request objects in exceptions.
            # Report only the exception class, not its potentially sensitive text.
            raise NetworkError("TRANSPORT_ERROR", "Network request failed (%s)." % type(exc).__name__) from None
