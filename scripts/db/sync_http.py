"""
HTTP transport for cr-sqlite changeset exchange (Phase 2.1b #3c-2).

Each machine runs a pull-only HTTP server bound to its own Tailscale
IP. Peers GET ``/crsql/changes?since=N&exclude_site=HEX`` and stream
back NDJSON rows from the ``crsql_changes`` virtual table — one row
per line, with BLOB columns (``pk``, ``site_id``, binary ``val``)
base64-encoded. There is no POST path; replication is symmetric —
both sides pull from each other on their own interval. Simpler auth
model, simpler code, no ordering constraints between the two halves.

Authorization is the Tailscale mesh itself. We bind to the tailnet
``100.x.x.x`` IP via ``tailscale ip -4``; binding to ``0.0.0.0`` would
expose the endpoint on every interface including home LAN, which is
*not* what we want even though WireGuard gates most paths.

Wire format (one JSON object per line):

    {
        "table":       str,
        "pk":          {"b64": str},
        "cid":         str,
        "val":         str | int | float | null | {"b64": str},
        "col_version": int,
        "db_version":  int,
        "site_id":     {"b64": str},
        "cl":          int,
        "seq":         int
    }

The ``{"b64": "..."}`` tagged-object form is used for any BLOB column;
primitive types pass through as JSON primitives. Decoding logic has
one branch: if the value is a dict with a "b64" key, base64-decode it;
otherwise keep as-is. No special-casing of column names.
"""

from __future__ import annotations

import base64
import json
import logging
import shutil
import socket
import sqlite3
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Iterator, Optional

log = logging.getLogger("pt.sync_http")

DEFAULT_PORT = 8765

# Errnos that signal "the process's DNS resolver cache has gone stale and
# a fresh lookup is required." On macOS, ``[Errno 8]`` is ``EAI_NONAME``
# ("nodename nor servname provided") and is the symptom we've observed
# in pt #6042 — after Tailscale GUI restart / machine sleep / long idle,
# the daemon's long-lived ``urllib`` state holds a resolver handle that
# no longer maps the peer hostname, while fresh Python processes resolve
# it fine.
#
# We also include ``EAI_NODATA`` so Linux hosts see the same recovery
# path. The bare literal ``8`` is a belt-and-suspenders: the symbolic
# name is the right form for portability, but macOS has historically
# been inconsistent about which constants are exported, and it costs
# nothing to also match by integer.
#
# We deliberately do NOT include ``EAI_AGAIN`` (temporary failure). That
# indicates real upstream DNS trouble where a retry accomplishes nothing
# useful — masking it would hurt observability more than it helps.
_STALE_RESOLVER_ERRNOS = frozenset(
    {getattr(socket, "EAI_NONAME", 8), getattr(socket, "EAI_NODATA", 7), 8}
)


# Column indexes in the crsql_changes tuple. Keep in sync with
# `iter_changes_for_peer`'s SELECT and `json_to_row`'s positional
# return; downstream callers (e.g. sync_daemon._sync_round) use these
# to read without duplicating the magic 5 / 6 integers.
CHANGES_IDX_TABLE = 0
CHANGES_IDX_PK = 1
CHANGES_IDX_CID = 2
CHANGES_IDX_VAL = 3
CHANGES_IDX_COL_VERSION = 4
CHANGES_IDX_DB_VERSION = 5
CHANGES_IDX_SITE_ID = 6
CHANGES_IDX_CL = 7
CHANGES_IDX_SEQ = 8


# ---------------------------------------------------------------------
# Encoding helpers — symmetric between server and client.
# ---------------------------------------------------------------------


def _encode_val(v: object) -> object:
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"b64": base64.b64encode(bytes(v)).decode("ascii")}
    return v  # str/int/float/None pass through; JSON can encode them


def _decode_val(v: object) -> object:
    if isinstance(v, dict) and set(v.keys()) == {"b64"}:
        return base64.b64decode(v["b64"])
    return v


def row_to_json(row: tuple) -> str:
    """Encode one crsql_changes row to a single NDJSON line."""
    table, pk, cid, val, col_version, db_version, site_id, cl, seq = row
    payload = {
        "table": table,
        "pk": _encode_val(pk),
        "cid": cid,
        "val": _encode_val(val),
        "col_version": col_version,
        "db_version": db_version,
        "site_id": _encode_val(site_id),
        "cl": cl,
        "seq": seq,
    }
    return json.dumps(payload, separators=(",", ":"))


def json_to_row(line: str) -> tuple:
    """Decode one NDJSON line back into the crsql_changes row tuple."""
    d = json.loads(line)
    return (
        d["table"],
        _decode_val(d["pk"]),
        d["cid"],
        _decode_val(d["val"]),
        d["col_version"],
        d["db_version"],
        _decode_val(d["site_id"]),
        d["cl"],
        d["seq"],
    )


# ---------------------------------------------------------------------
# Server-side query: what rows does the peer want?
# ---------------------------------------------------------------------


def iter_changes_for_peer(
    conn: sqlite3.Connection, since: int, exclude_site_hex: str
) -> Iterator[tuple]:
    """Yield ``crsql_changes`` rows the peer doesn't have yet.

    Filters out rows the peer originated (``site_id = exclude_site``)
    — those rows came from the peer in the first place and replaying
    them would just echo the peer's own writes back. The
    ``db_version > since`` predicate is the peer's watermark on our
    data plane; on first call it's 0.
    """
    try:
        site_blob = bytes.fromhex(exclude_site_hex)
    except ValueError as err:
        raise ValueError(
            f"exclude_site must be hex, got {exclude_site_hex!r}"
        ) from err
    # `table` is a SQL reserved word — cr-sqlite exposes the column
    # with that exact name, so double-quote it here and in the INSERT
    # back on the client side (apply_changes).
    cur = conn.execute(
        'SELECT "table", pk, cid, val, col_version, db_version, site_id, cl, seq '
        "FROM crsql_changes "
        "WHERE db_version > ? AND site_id != ? "
        "ORDER BY db_version, seq",
        (since, site_blob),
    )
    while True:
        rows = cur.fetchmany(1000)
        if not rows:
            break
        for row in rows:
            yield row


# ---------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------


@dataclass
class _ServerConfig:
    conn_factory: Callable[[], sqlite3.Connection]


class _ChangesHandler(BaseHTTPRequestHandler):
    """One request per incoming ``GET /crsql/changes``.

    Opens a fresh read-only sqlite connection per request so the
    daemon's main connection isn't shared across threads — sqlite3
    connections are thread-affine.
    """

    server_version = "pt-sync/1"
    # Silence the default per-request stderr line; our log is already
    # verbose enough. BaseHTTPRequestHandler's default spams one line
    # per request which floods sync-daemon.err.
    def log_message(self, format: str, *args) -> None:  # noqa: N802, A002
        log.debug("http: " + format, *args)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/crsql/changes":
            self._send_simple(HTTPStatus.NOT_FOUND, "not found")
            return
        params = urllib.parse.parse_qs(parsed.query)
        try:
            since = int(params.get("since", ["0"])[0])
            exclude_site = params["exclude_site"][0]
        except (KeyError, IndexError, ValueError):
            self._send_simple(
                HTTPStatus.BAD_REQUEST,
                "usage: /crsql/changes?since=N&exclude_site=HEX",
            )
            return

        cfg: _ServerConfig = self.server._cfg  # type: ignore[attr-defined]
        conn = cfg.conn_factory()
        try:
            try:
                rows = list(iter_changes_for_peer(conn, since, exclude_site))
            except ValueError as err:
                self._send_simple(HTTPStatus.BAD_REQUEST, str(err))
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("X-PT-Row-Count", str(len(rows)))
            self.end_headers()
            for row in rows:
                self.wfile.write(row_to_json(row).encode("utf-8"))
                self.wfile.write(b"\n")
        finally:
            conn.close()

    def _send_simple(self, status: HTTPStatus, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def tailnet_ip() -> Optional[str]:
    """Return this machine's tailnet IPv4 address, or None.

    Uses ``tailscale ip -4``. Binding to this IP (not ``0.0.0.0``)
    keeps the sync endpoint off home LAN and public interfaces even
    though the tunnel would still screen unrelated traffic — belt and
    suspenders.
    """
    ts = shutil.which("tailscale") or "/usr/local/bin/tailscale"
    if not Path(ts).exists():
        return None
    try:
        proc = subprocess.run(
            [ts, "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    ip = (proc.stdout or "").strip().splitlines()[0] if proc.stdout else ""
    return ip or None


def make_server(
    conn_factory: Callable[[], sqlite3.Connection],
    port: int = DEFAULT_PORT,
    host: Optional[str] = None,
) -> ThreadingHTTPServer:
    """Construct (but don't start) the HTTP server.

    ``host`` defaults to this machine's tailnet IP; pass an explicit
    value (e.g. ``127.0.0.1`` for tests) to override. ``conn_factory``
    is called per request to open a fresh sqlite connection (with
    cr-sqlite loaded) — sqlite connections are not thread-safe, so we
    don't share the daemon's main connection with request threads.
    """
    bind_host = host if host is not None else (tailnet_ip() or "127.0.0.1")
    srv = ThreadingHTTPServer((bind_host, port), _ChangesHandler)
    srv._cfg = _ServerConfig(conn_factory=conn_factory)  # type: ignore[attr-defined]
    return srv


def serve_forever_in_thread(server: ThreadingHTTPServer) -> threading.Thread:
    """Start ``server`` on a background daemon thread and return it.

    The thread is marked daemon so it doesn't block process exit if
    ``server.shutdown()`` is missed — shouldn't happen via SyncDaemon,
    but belt-and-suspenders for SIGKILL / hard aborts.
    """
    t = threading.Thread(
        target=server.serve_forever, name="pt-sync-http", daemon=True
    )
    t.start()
    return t


# ---------------------------------------------------------------------
# Client: pull from peer, apply to local DB
# ---------------------------------------------------------------------


PULL_TIMEOUT_S = 20.0


def _is_stale_resolver_error(err: BaseException) -> bool:
    """Return True if ``err`` is a DNS-resolver-cache-is-stale symptom.

    Handles both the bare ``socket.gaierror`` form and the ``urllib``
    wrapper (``URLError(gaierror(...))``). Matches only the errno
    whitelist in ``_STALE_RESOLVER_ERRNOS`` — real upstream DNS failures
    (``EAI_AGAIN`` etc.) propagate untouched.
    """
    if isinstance(err, urllib.error.URLError):
        err = err.reason if isinstance(err.reason, BaseException) else err
    if not isinstance(err, socket.gaierror):
        return False
    return err.errno in _STALE_RESOLVER_ERRNOS


def _do_pull(
    opener: urllib.request.OpenerDirector | None,
    url: str,
    timeout_s: float,
) -> list[tuple]:
    """Issue the HTTP GET and parse the NDJSON body into decoded rows.

    Factored out of ``pull_from_peer`` so the retry path (which uses
    a freshly-built opener) can share the exact same request and
    parse logic. When ``opener`` is ``None`` we fall through to the
    module-default ``urllib.request.urlopen`` — that's the normal,
    healthy path. When the caller passes an opener, we route through
    it; that's the recovery path from ``_is_stale_resolver_error``
    AND the test-injection path for unit tests that don't want to
    touch the real network.
    """
    req = urllib.request.Request(url, method="GET")
    if opener is None:
        cm = urllib.request.urlopen(req, timeout=timeout_s)
    else:
        cm = opener.open(req, timeout=timeout_s)
    with cm as resp:
        if resp.status != 200:
            raise RuntimeError(
                f"peer returned HTTP {resp.status}: "
                f"{resp.read().decode('utf-8', errors='replace')[:200]}"
            )
        body = resp.read().decode("utf-8")

    rows: list[tuple] = []
    for line_no, line in enumerate(body.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json_to_row(line))
        except (KeyError, ValueError, json.JSONDecodeError) as err:
            raise ValueError(
                f"peer response line {line_no} malformed: {err!r}"
            ) from err
    return rows


def pull_from_peer(
    peer_host: str,
    port: int,
    since: int,
    exclude_site_hex: str,
    timeout_s: float = PULL_TIMEOUT_S,
    *,
    opener: urllib.request.OpenerDirector | None = None,
) -> list[tuple]:
    """HTTP GET the peer's ``/crsql/changes`` endpoint and decode the response.

    Returns a list of fully-decoded rows in the same shape
    ``iter_changes_for_peer`` emits. Raises ``urllib.error.URLError``
    on transport failure; raises ``ValueError`` on malformed NDJSON
    so callers can surface the issue rather than silently apply bad
    rows.

    On a stale-resolver error (pt #6042 — ``socket.gaierror`` with
    errno in ``_STALE_RESOLVER_ERRNOS``), we do ONE recovery attempt:
    force a fresh ``getaddrinfo`` lookup, build a brand-new local
    ``OpenerDirector``, and retry. A successful retry is logged at
    INFO so the daemon operator can see that recovery happened. If the
    retry ALSO fails, we re-raise — the daemon's outer catch (in
    ``sync_daemon.SyncDaemon.start``) logs ``sync round raised;
    continuing`` and the next 30s round tries anew.

    The optional ``opener`` kwarg is for tests to inject a mock
    ``OpenerDirector``. Production callers should leave it at ``None``
    (the default), which uses ``urllib.request.urlopen``.
    """
    url = (
        f"http://{peer_host}:{port}/crsql/changes"
        f"?since={since}"
        f"&exclude_site={exclude_site_hex}"
    )
    try:
        return _do_pull(opener, url, timeout_s)
    except (socket.gaierror, urllib.error.URLError) as err:
        if not _is_stale_resolver_error(err):
            raise
        log.info(
            "resolver stale on %s; refreshing via fresh opener "
            "(errno=%r)",
            peer_host,
            getattr(err, "errno", None)
            or getattr(getattr(err, "reason", None), "errno", None),
        )
        # Force a fresh DNS lookup. If the resolver is still stale,
        # this raises the exact ``gaierror`` and we propagate — no
        # point building an opener we'd never successfully use.
        socket.getaddrinfo(peer_host, port, type=socket.SOCK_STREAM)
        # Build a new local opener. We DO NOT touch ``urllib``'s
        # global default (``urllib.request._opener``) — other code
        # paths in this process may depend on it, and mutating
        # module-level state in the middle of exception handling is
        # an anti-pattern.
        fresh_opener = urllib.request.build_opener()
        try:
            return _do_pull(fresh_opener, url, timeout_s)
        except Exception as retry_err:
            log.error(
                "resolver refresh on %s did not recover: %r",
                peer_host,
                retry_err,
            )
            raise


def apply_changes(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """Apply a batch of peer changesets to the local DB inside one transaction.

    Returns the number of rows applied (= ``len(rows)`` on success;
    ``0`` on empty batch). Raises on any apply failure — the
    transaction rolls back, the watermark doesn't advance, and the
    daemon's next round re-pulls the same ``since`` and tries again.
    """
    if not rows:
        return 0
    conn.execute("BEGIN")
    try:
        conn.executemany(
            "INSERT INTO crsql_changes "
            "(\"table\", pk, cid, val, col_version, db_version, site_id, cl, seq) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(rows)


# ---------------------------------------------------------------------
# Watermark: what's the highest db_version we've pulled from this peer?
# ---------------------------------------------------------------------


_WATERMARK_KEY_PREFIX = "sync.peer_watermark."


def watermark_for(conn: sqlite3.Connection, peer_site_hex: str) -> int:
    """Read the last ``db_version`` we successfully pulled from ``peer_site_hex``."""
    key = _WATERMARK_KEY_PREFIX + peer_site_hex.lower()
    try:
        row = conn.execute(
            "SELECT value FROM _metadata WHERE key = ?", (key,)
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    if not row or not row[0]:
        return 0
    try:
        return int(row[0])
    except ValueError:
        return 0


def set_watermark(
    conn: sqlite3.Connection, peer_site_hex: str, version: int
) -> None:
    """Persist the new post-round ``db_version`` watermark for the peer."""
    from datetime import datetime, timezone
    key = _WATERMARK_KEY_PREFIX + peer_site_hex.lower()
    conn.execute(
        "INSERT OR REPLACE INTO _metadata (key, value, created_at) "
        "VALUES (?, ?, ?)",
        (
            key,
            str(version),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
