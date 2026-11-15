"""HTTP acquisition with a credential-free transcript and an immutable raw store.

Layout under the artifact root (``TWINSITE_DATA_DIR`` or ``<repo>/.runtime/data``)::

    raw/<source_id>/<sha256>/<filename>      original bytes exactly as received (read-only)
    raw/<source_id>/<sha256>/asset.json      RawAsset metadata
    transcripts/<source_id>/<timestamp>.jsonl  every request/response/error
    cleaned/... derived/...                  written by processing, never over raw

Transcript records contain method, URL (credential-free by construction),
range header, status, final URL host, selected response headers, byte count,
SHA-256 and elapsed seconds.  Authorization headers and cookies are never
recorded.  Errors are recorded as evidence, never swallowed.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .base import (
    AcquisitionError,
    ByteBudgetExceededError,
    ChecksumMismatchError,
    RawAsset,
    TruncatedAssetError,
)

USER_AGENT = "TwinSite-data/1.0 (NASA Space Apps research prototype)"
_SAFE_HEADERS = ("content-type", "content-length", "content-range", "last-modified", "etag", "accept-ranges")


def artifact_root() -> Path:
    env = os.environ.get("TWINSITE_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # backend/twinsite/sources/fetch.py -> repo root is parents[3]
    return (Path(__file__).resolve().parents[3] / ".runtime" / "data").resolve()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_credential_free(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.username or parts.password:
        raise AcquisitionError("URL embeds credentials; refused", host=parts.hostname)
    q = urllib.parse.parse_qs(parts.query)
    for key in q:
        if key.lower() in {"token", "access_token", "signature", "x-amz-signature", "sig", "api_key", "apikey", "key"}:
            raise AcquisitionError("URL carries a capability/signed query; refused", host=parts.hostname, key=key)


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Transcript:
    """Append-only JSONL transcript of one acquisition session."""

    def __init__(self, source_id: str, root: Optional[Path] = None) -> None:
        self.root = root or artifact_root()
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.object_key = f"transcripts/{source_id}/{stamp}.jsonl"
        self.path = self.root / self.object_key
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def log(self, **record: Any) -> None:
        record.setdefault("at", now_utc())
        with self._lock:
            self.records.append(record)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True) + "\n")


_SSL_CTX: Optional[ssl.SSLContext] = None


def ssl_context() -> ssl.SSLContext:
    """Verified TLS context: OpenSSL default bundle + (on macOS) the system root
    keychain, because some NASA/PDS hosts chain to roots missing from older
    bundled CA files.  Certificate verification is never disabled."""
    global _SSL_CTX
    if _SSL_CTX is not None:
        return _SSL_CTX
    ctx = ssl.create_default_context()
    extra = os.environ.get("TWINSITE_CA_BUNDLE")
    if extra:
        ctx.load_verify_locations(cafile=extra)
    elif sys.platform == "darwin":
        try:
            pem = subprocess.run(
                ["/usr/bin/security", "find-certificate", "-a", "-p",
                 "/System/Library/Keychains/SystemRootCertificates.keychain"],
                capture_output=True, check=True, timeout=30, text=True).stdout
            if "BEGIN CERTIFICATE" in pem:
                ctx.load_verify_locations(cadata=pem)
        except (OSError, subprocess.SubprocessError, ssl.SSLError):
            pass
    _SSL_CTX = ctx
    return ctx


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface redirects so that an auth wall (e.g. Earthdata URS) is recorded."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if new.scheme != "https":
            raise AcquisitionError("Non-HTTPS redirect refused")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and (old.hostname, old.port) != (new.hostname, new.port):
            for key in ("Authorization", "Cookie", "Proxy-authorization"):
                redirected.remove_header(key)
        return redirected


def _open(url: str, headers: Dict[str, str], timeout: float, follow_redirects: bool):
    handlers = [urllib.request.HTTPSHandler(context=ssl_context()), _SafeRedirect()]
    if not follow_redirects:
        handlers.append(_NoRedirect())
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    return opener.open(req, timeout=timeout)


def http_get(
    url: str,
    transcript: Transcript,
    *,
    byte_range: Optional[Tuple[int, int]] = None,
    max_bytes: int,
    timeout: float = 60.0,
    retries: int = 4,
    follow_redirects: bool = True,
    dest: Optional[Path] = None,
    secret_headers: Optional[Dict[str, str]] = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """GET ``url`` (optionally one inclusive byte range) with resume on retry.

    Writes to ``dest`` (a .part file) when given so a stalled large transfer can
    resume with a Range request.  Returns (bytes, final transcript record).
    """
    assert_credential_free(url)
    if secret_headers and (urllib.parse.urlsplit(url).scheme != "https" or urllib.parse.urlsplit(url).hostname != "data.lpdaac.earthdatacloud.nasa.gov"):
        raise AcquisitionError("Credential destination is not the approved NASA host")
    host = urllib.parse.urlsplit(url).hostname
    want_first = byte_range[0] if byte_range else 0
    want_last = byte_range[1] if byte_range else None
    buf = bytearray()
    if dest is not None and dest.exists():
        buf.extend(dest.read_bytes())
    attempt = 0
    last_error: Optional[str] = None
    while attempt <= retries:
        attempt += 1
        start = want_first + len(buf)
        headers: Dict[str, str] = {}
        if byte_range or buf:
            headers["Range"] = f"bytes={start}-{'' if want_last is None else want_last}"
        t0 = time.monotonic()
        try:
            resp = _open(url, {**headers, **(secret_headers or {})}, timeout, follow_redirects)
            status = resp.status
            rhead = {k.lower(): v for k, v in resp.headers.items() if k.lower() in _SAFE_HEADERS}
            if headers.get("Range") and status != 206:
                transcript.log(event="range_not_honoured", url=url, host=host, status=status, headers=rhead, attempt=attempt)
                if status == 200 and not byte_range:
                    buf.clear()  # server restarted from zero; discard partial
                    if dest is not None:
                        dest.write_bytes(b"")
                else:
                    raise AcquisitionError("server ignored Range request", url=url, status=status)
            got_this = 0
            with (open(dest, "ab") if dest is not None else _NullSink()) as sink:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    sink.write(chunk)
                    got_this += len(chunk)
                    if len(buf) > max_bytes:
                        transcript.log(event="byte_budget_exceeded", url=url, bytes=len(buf), budget=max_bytes)
                        raise ByteBudgetExceededError("transfer exceeded byte budget", url=url, budget=max_bytes)
            expected_total: Optional[int] = None
            if want_last is not None:
                expected_total = want_last - want_first + 1
            elif "content-range" in rhead and "/" in rhead["content-range"]:
                tail = rhead["content-range"].rsplit("/", 1)[1]
                expected_total = int(tail) if tail.isdigit() else None
            elif "content-length" in rhead and not headers.get("Range"):
                expected_total = int(rhead["content-length"])
            rec = dict(
                event="response",
                method="GET",
                url=url,
                host=host,
                final_host=urllib.parse.urlsplit(resp.geturl()).hostname,
                range=headers.get("Range"),
                status=status,
                headers=rhead,
                bytes_this_attempt=got_this,
                bytes_total=len(buf),
                expected_total=expected_total,
                elapsed_s=round(time.monotonic() - t0, 3),
                attempt=attempt,
            )
            if expected_total is not None and len(buf) < expected_total:
                rec["event"] = "short_read"
                transcript.log(**rec)
                last_error = f"short read {len(buf)}/{expected_total}"
                continue
            rec["sha256"] = sha256_bytes(bytes(buf))
            transcript.log(**rec)
            return bytes(buf), rec
        except urllib.error.HTTPError as exc:
            rhead = {k.lower(): v for k, v in (exc.headers or {}).items() if k.lower() in _SAFE_HEADERS}
            loc = rhead.get("location")
            if loc:
                # keep only scheme+host+path of a redirect target; queries can carry state/tokens
                p = urllib.parse.urlsplit(loc)
                rhead["location"] = f"{p.scheme}://{p.hostname}{p.path}"
            transcript.log(event="http_error", url=url, host=host, status=exc.code, headers=rhead, attempt=attempt,
                           elapsed_s=round(time.monotonic() - t0, 3))
            if exc.code in (301, 302, 303, 307, 308, 401, 403, 404):
                raise AcquisitionError(f"HTTP {exc.code} from {host}", url=url, status=exc.code,
                                       location=rhead.get("location", ""))
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
            if isinstance(exc, (ByteBudgetExceededError, AcquisitionError)):
                raise
            transcript.log(event="network_error", url=url, host=host, error=type(exc).__name__,
                           attempt=attempt, bytes_total=len(buf), elapsed_s=round(time.monotonic() - t0, 3))
            last_error = type(exc).__name__
        time.sleep(min(2 ** attempt, 20))
    raise AcquisitionError(f"giving up on {host} after {attempt} attempts: {last_error}", url=url, bytes=len(buf))


class _NullSink:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, _):
        return None


# --------------------------------------------------------------------------- raw store
def store_raw(
    data: bytes,
    *,
    filename: str,
    meta: Dict[str, Any],
    root: Optional[Path] = None,
) -> Tuple[Path, str, str]:
    """Write ``data`` immutably; returns (path, object_key, sha256).

    If the content-addressed file already exists its bytes must match; the
    existing file is never overwritten.
    """
    root = root or artifact_root()
    digest = sha256_bytes(data)
    object_key = f"raw/{meta['source_id']}/{digest}/{filename}"
    path = root / object_key
    if path.exists():
        if sha256_file(path) != digest:
            raise ChecksumMismatchError("existing raw object differs from its address", object_key=object_key)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        os.chmod(path, 0o444)
    meta_path = path.parent / "asset.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps({**meta, "sha256": digest, "object_key": object_key}, indent=2, sort_keys=True))
        os.chmod(meta_path, 0o444)
    return path, object_key, digest


def verify_raw(asset: RawAsset) -> None:
    """Re-hash stored bytes; raises on mutation or truncation."""
    p = Path(asset.path)
    if not p.exists():
        raise TruncatedAssetError("raw asset missing", object_key=asset.object_key)
    size = p.stat().st_size
    if size != asset.byte_size:
        raise TruncatedAssetError("raw asset size differs from manifest", object_key=asset.object_key,
                                  expected=asset.byte_size, actual=size)
    digest = sha256_file(p)
    if digest != asset.sha256:
        raise ChecksumMismatchError("raw asset bytes changed", object_key=asset.object_key)


def find_cached(source_id: str, granule_id: str, role: str, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Return metadata of previously stored raw assets for a granule/role."""
    root = root or artifact_root()
    out = []
    base = root / "raw" / source_id
    if not base.exists():
        return out
    for meta_path in sorted(base.glob("*/asset.json")):
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, ValueError):
            continue
        if meta.get("granule_id") == granule_id and meta.get("role") == role:
            meta["path"] = str(meta_path.parent / Path(meta["object_key"]).name)
            out.append(meta)
    return out


def asset_from_meta(meta: Dict[str, Any], observation, from_cache: bool) -> RawAsset:
    ranges = meta.get("byte_ranges")
    return RawAsset(
        asset_id=meta["asset_id"],
        source_id=meta["source_id"],
        product_id=meta["product_id"],
        product_version=meta["product_version"],
        granule_id=meta["granule_id"],
        body=meta["body"],
        role=meta["role"],
        source_url=meta["source_url"],
        object_key=meta["object_key"],
        path=meta["path"],
        sha256=meta["sha256"],
        byte_size=meta["byte_size"],
        retrieved_at=meta["retrieved_at"],
        observation=observation,
        fmt=meta["format"],
        crs=meta["crs"],
        coordinate_conventions=meta["coordinate_conventions"],
        license_url=meta["license_url"],
        byte_ranges=tuple(tuple(r) for r in ranges) if ranges else None,
        parent_asset_ids=tuple(meta.get("parent_asset_ids", ())),
        from_cache=from_cache,
    )
