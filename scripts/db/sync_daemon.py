"""
Long-running sync daemon (Phase 2.1b — scaffolding).

The daemon is the process that — eventually — reads cr-sqlite
changesets from ``tracker.db``, pushes them to the peer over Tailscale,
pulls the peer's changesets, and applies them locally. PR #3c-1 ships
the *scaffolding*: startup sequence, hygiene checks, pause/resume
respect, round cadence, clean shutdown, tests. The actual changeset
exchange is a stub (:func:`_sync_round_placeholder`) until the §2.4
trial table proves cr-sqlite's bootstrap semantics are safe to rely on.

That split is deliberate. Shipping the daemon shell *before* the
replication payload lets the launchd plist land, the pause/resume
plumbing get exercised in production, and the manifest-hash parity
check run on every machine start — none of which change when the
replication code lands. When PR #3c-2 adds the transport, only
:func:`_sync_round_placeholder` changes; the outer loop, hygiene
checks, pause state, and lifecycle are already proven.

Lifecycle
---------
1. ``SyncDaemon(db_path, peer_host, interval_seconds)`` — construct.
2. ``.start()`` — run preflight checks, enter the main loop. Blocks
   until stopped. Meant to be invoked from a LaunchAgent or from
   ``python -m scripts.db.sync_daemon``; **do not** call from a web
   request handler or anywhere else in-process.
3. ``.stop()`` — signal the loop to exit on the next iteration.
   Signal handlers wire SIGINT/SIGTERM to this.
4. Each iteration (:meth:`run_once`) reads ``sync.paused`` from
   ``_metadata``. Paused ⇒ skip the round but keep polling.
   Otherwise ⇒ call the replication stub and record
   ``sync.last_successful_sync``.

Preflight failures
------------------
Any of the four preflight checks (cr-sqlite loadable, NTP drift, peer
reachability, manifest hash computable) failing stops startup with a
clear stderr message and a non-zero exit. The daemon never silently
degrades to "I'm up but not syncing" — either everything is healthy
or the operator knows something is wrong.
"""

from __future__ import annotations

import logging
import signal
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Callable, Optional

import threading

# When run via `python -m scripts.db.sync_daemon` (how the LaunchAgent
# invokes us), `scripts/` is not on sys.path and the `from db.*`
# imports below would fail. Inject it here — matches the pattern in
# scripts/pt.py.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from db.sync_checks import (
    DEFAULT_NTP_HOST,
    manifest_hash,
    ntp_drift_seconds,
    peer_reachable,
)
from db.sync_http import (
    CHANGES_IDX_DB_VERSION,
    CHANGES_IDX_SITE_ID,
    DEFAULT_PORT,
    apply_changes,
    make_server,
    pull_from_peer,
    serve_forever_in_thread,
    set_watermark,
    watermark_for,
)
from db.sync_state import is_paused, record_last_sync


log = logging.getLogger("pt.sync_daemon")


NTP_DRIFT_LIMIT_S = 1.0
DEFAULT_INTERVAL_S = 30.0


@dataclass
class PreflightReport:
    """Outcome of the daemon's startup checks.

    Every field is explicit so the operator can read a single-line
    log message and know which check failed. ``None`` for
    ``ntp_drift_s`` means the sntp probe itself failed (binary
    missing, network down, unparseable output) — treated as a hard
    failure, not "maybe 0 is fine."
    """

    crsqlite_loaded: bool
    ntp_drift_s: Optional[float]
    peer_reachable: bool
    manifest_hash: str

    @property
    def ok(self) -> bool:
        return (
            self.crsqlite_loaded
            and self.ntp_drift_s is not None
            and abs(self.ntp_drift_s) <= NTP_DRIFT_LIMIT_S
            and self.peer_reachable
        )

    def summary(self) -> str:
        drift = (
            f"{self.ntp_drift_s:+.3f}s"
            if self.ntp_drift_s is not None
            else "unavailable"
        )
        return (
            f"crsqlite={'yes' if self.crsqlite_loaded else 'no'} "
            f"ntp_drift={drift} "
            f"peer_reachable={'yes' if self.peer_reachable else 'no'} "
            f"manifest={self.manifest_hash[:12]}"
        )


def preflight(
    conn: sqlite3.Connection,
    peer_host: str,
    ntp_host: str = DEFAULT_NTP_HOST,
) -> PreflightReport:
    """Run the four preflight checks and return a report.

    The connection is expected to already have cr-sqlite loaded (the
    daemon loads it before calling this). We probe
    ``crsql_db_version()`` to confirm — if it raises, cr-sqlite isn't
    available and we report crsqlite_loaded=False so the caller can
    refuse to start.
    """
    try:
        conn.execute("SELECT crsql_db_version()")
        crsqlite_loaded = True
    except sqlite3.OperationalError:
        crsqlite_loaded = False

    drift = ntp_drift_seconds(ntp_host)
    reachable = peer_reachable(peer_host)
    return PreflightReport(
        crsqlite_loaded=crsqlite_loaded,
        ntp_drift_s=drift,
        peer_reachable=reachable,
        manifest_hash=manifest_hash(),
    )


def _get_local_site_hex(conn: sqlite3.Connection) -> str:
    """Return ``hex(crsql_site_id())`` in lowercase.

    Factored out of ``_sync_round`` so tests can monkeypatch a stable
    site id without loading the real cr-sqlite extension.
    """
    site_row = conn.execute("SELECT hex(crsql_site_id())").fetchone()
    if not site_row or not site_row[0]:
        raise RuntimeError(
            "crsql_site_id() returned no value — cr-sqlite is not "
            "fully initialized on this connection"
        )
    return site_row[0].lower()


def _sync_round(
    conn: sqlite3.Connection, peer_host: str, port: int = DEFAULT_PORT
) -> None:
    """Pull the peer's changesets and apply them locally.

    Symmetric protocol — the peer runs the same function with roles
    reversed and pulls from us. That means one round on each machine
    equals one full cross-propagation; no POST path, no coordination
    between halves.

    Sequence:
      1. Get our site id (for ``exclude_site`` so peer doesn't echo
         our rows back) and the current watermark for this peer.
      2. HTTP GET peer's ``/crsql/changes?since=<watermark>&exclude_site=<us>``.
      3. If the batch is empty, nothing changed — return without
         advancing the watermark (there's nothing to advance past).
      4. Apply the rows inside one transaction
         (``INSERT INTO crsql_changes ...``). cr-sqlite's CRDT merge
         runs on each insert; a write of a stale column is a no-op,
         not a data-overwrite. This is why the bootstrap gate in §2.4
         matters — we have to prove that empty-peer doesn't interpret
         as "please delete all rows".
      5. After commit, persist the new watermark = max db_version seen
         so the next round asks for the right slice.
    """
    our_site_hex = _get_local_site_hex(conn)

    # We track the peer's watermark keyed by THEIR site id, not their
    # hostname — hostnames can change, site ids don't. On round 1 we
    # don't know the peer's site id yet; `peer_host` doubles as a
    # hostname-based watermark key for first contact. After round 1
    # we discover the peer's site id from the rows it returned and
    # migrate the watermark key. This keeps the cold-start case
    # simple without losing the site-id invariant afterwards.
    watermark_key = f"host:{peer_host}"
    since = watermark_for(conn, watermark_key)

    rows = pull_from_peer(peer_host, port, since, our_site_hex)
    if not rows:
        log.info("sync round: peer=%s since=%d — no changes", peer_host, since)
        return

    apply_changes(conn, rows)

    # Named-index reads — magic positional integers would silently
    # drift if the crsql_changes tuple shape changes. The CHANGES_IDX_*
    # constants live with the encoder in sync_http so the shape is
    # defined in one place.
    max_version = max(row[CHANGES_IDX_DB_VERSION] for row in rows)
    set_watermark(conn, watermark_key, max_version)

    # Upgrade the watermark key from hostname-based to site-id-based
    # after the first successful batch — peer's site_id is consistent
    # across every row in the batch (we filtered on it server-side).
    # This migration is idempotent and runs cheaply per round.
    peer_site_bytes = rows[0][CHANGES_IDX_SITE_ID]
    if isinstance(peer_site_bytes, (bytes, bytearray)):
        peer_site_hex = bytes(peer_site_bytes).hex().lower()
        if peer_site_hex:
            set_watermark(conn, f"site:{peer_site_hex}", max_version)

    log.info(
        "sync round: peer=%s applied=%d new_watermark=%d",
        peer_host, len(rows), max_version,
    )


# Kept as a public alias so existing tests + external callers don't
# break while the payload is wired in. PR #3c-2 turns the stub into
# the real thing; the name remains `_sync_round_placeholder` for one
# PR cycle so the stack retains a single move per PR.
_sync_round_placeholder = _sync_round


class SyncDaemon:
    """Main-loop process for cr-sqlite replication (scaffolding)."""

    def __init__(
        self,
        db_path: Path,
        peer_host: str,
        interval_seconds: float = DEFAULT_INTERVAL_S,
        crsqlite_path: Optional[Path] = None,
        round_fn: Callable[[sqlite3.Connection, str], None] = _sync_round_placeholder,
        sleep_fn: Callable[[float], None] = time.sleep,
        http_port: int = DEFAULT_PORT,
        http_host: Optional[str] = None,
        serve_http: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.peer_host = peer_host
        self.interval_seconds = interval_seconds
        self.crsqlite_path = (
            Path(crsqlite_path)
            if crsqlite_path is not None
            else Path.home() / ".local/lib/crsqlite/crsqlite.dylib"
        )
        # If the caller accepted the default round_fn (_sync_round_placeholder
        # which is now _sync_round), wrap it to close over http_port so
        # the round function only needs (conn, host) — keeps the Callable
        # shape simple and tests can still pass a stubbed (conn, host) fn.
        if round_fn is _sync_round_placeholder:
            _port = http_port
            def _default_round(c: sqlite3.Connection, h: str) -> None:
                _sync_round(c, h, port=_port)
            round_fn = _default_round
        self._round_fn = round_fn
        self._sleep_fn = sleep_fn
        self._http_port = http_port
        self._http_host = http_host  # None = auto-detect tailnet IP
        self._serve_http = serve_http
        self._stop_requested = False
        self._conn: Optional[sqlite3.Connection] = None
        self._http_server = None  # ThreadingHTTPServer; set in start()
        self._http_thread: Optional[threading.Thread] = None

    # --- lifecycle -----------------------------------------------------

    def stop(self) -> None:
        """Request the main loop to exit on the next iteration."""
        self._stop_requested = True

    def _install_signal_handlers(self) -> None:
        def _handler(signum: int, _frame: Optional[FrameType]) -> None:
            log.info("received signal %d — stopping", signum)
            self.stop()

        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)

    def _open_conn(self) -> sqlite3.Connection:
        """Open the tracker DB with isolation_level=None and cr-sqlite loaded.

        ``isolation_level=None`` so transactions are ours to manage,
        matching the migration runner's pattern and letting
        ``crsql_db_version`` tick on our COMMITs rather than Python's
        implicit ones.
        """
        conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        conn.enable_load_extension(True)
        try:
            conn.load_extension(
                str(self.crsqlite_path), entrypoint="sqlite3_crsqlite_init"
            )
        except sqlite3.OperationalError as err:
            conn.close()
            raise RuntimeError(
                f"cr-sqlite failed to load from {self.crsqlite_path}: {err}. "
                "Daemon cannot start without the extension."
            ) from err
        return conn

    def start(self) -> int:
        """Open DB, run preflight, start HTTP server, then loop. Returns exit code."""
        self._install_signal_handlers()
        try:
            self._conn = self._open_conn()
        except RuntimeError as err:
            log.error("%s", err)
            return 2

        try:
            report = preflight(self._conn, self.peer_host)
            log.info("preflight: %s", report.summary())
            if not report.ok:
                log.error(
                    "preflight failed — refusing to start. "
                    "Fix the failing check(s) above and restart the daemon."
                )
                return 2

            if self._serve_http:
                self._start_http_server()

            while not self._stop_requested:
                try:
                    self.run_once(self._conn)
                except Exception:
                    # A round failure must NOT kill the daemon. Log
                    # and continue — transient network errors are
                    # expected, and the operator can always check
                    # last_successful_sync to see whether rounds are
                    # landing.
                    log.exception("sync round raised; continuing")
                if self._stop_requested:
                    break
                self._sleep_fn(self.interval_seconds)
            return 0
        finally:
            self._stop_http_server()
            if self._conn is not None:
                self._conn.close()

    def _start_http_server(self) -> None:
        """Spin up the pull-endpoint HTTP server on a daemon thread.

        Request threads open their own sqlite connections via the
        factory — the daemon's main connection is thread-affine and
        must not be shared across handlers.
        """
        def _factory() -> sqlite3.Connection:
            c = sqlite3.connect(str(self.db_path), isolation_level=None)
            c.enable_load_extension(True)
            c.load_extension(
                str(self.crsqlite_path), entrypoint="sqlite3_crsqlite_init"
            )
            return c

        self._http_server = make_server(
            conn_factory=_factory,
            port=self._http_port,
            host=self._http_host,
        )
        host, port = self._http_server.server_address[:2]
        log.info("http server listening on %s:%s", host, port)
        self._http_thread = serve_forever_in_thread(self._http_server)

    def _stop_http_server(self) -> None:
        if self._http_server is not None:
            try:
                self._http_server.shutdown()
                self._http_server.server_close()
            except Exception:
                log.exception("error shutting down http server")
            self._http_server = None
        if self._http_thread is not None and self._http_thread.is_alive():
            self._http_thread.join(timeout=5.0)
            self._http_thread = None

    # --- per-round ----------------------------------------------------

    def run_once(self, conn: sqlite3.Connection) -> None:
        """Execute one sync round, honoring pause state.

        Paused ⇒ skip the round but DON'T treat as failure. The
        ``last_successful_sync`` timestamp only advances on real
        rounds so ``pt sync status`` can show an accurate "last
        successful" even during long pauses.
        """
        if is_paused(conn):
            log.debug("paused — skipping round")
            return
        self._round_fn(conn, self.peer_host)
        record_last_sync(conn)


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for ``python -m scripts.db.sync_daemon`` and LaunchAgent."""
    import argparse

    parser = argparse.ArgumentParser(
        description="cr-sqlite sync daemon (Phase 2.1b).",
    )
    parser.add_argument(
        "--db-path",
        required=True,
        type=Path,
        help="Absolute path to tracker.db.",
    )
    parser.add_argument(
        "--peer-host",
        required=True,
        help="Tailnet hostname of the peer (e.g. eriks-mac-mini).",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_INTERVAL_S,
        help=f"Seconds between rounds (default {DEFAULT_INTERVAL_S}).",
    )
    parser.add_argument(
        "--crsqlite-path",
        type=Path,
        default=None,
        help="Override cr-sqlite dylib path.",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port for the pull endpoint (default {DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--http-host",
        default=None,
        help="Bind host for the pull endpoint. Default: tailnet IP.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (DEBUG/INFO/WARNING/ERROR).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    daemon = SyncDaemon(
        db_path=args.db_path,
        peer_host=args.peer_host,
        interval_seconds=args.interval_seconds,
        crsqlite_path=args.crsqlite_path,
        http_port=args.http_port,
        http_host=args.http_host,
    )
    return daemon.start()


if __name__ == "__main__":  # pragma: no cover — entry point
    sys.exit(main())


# Export for the `pt sync resume` block-until-peer-announces logic
# living in pt.py. Kept here so the daemon and CLI agree on how to
# read the announcement table.


def _outstanding_peer_announcements(
    conn: sqlite3.Connection, *, local_site_id: str
) -> list[int]:
    """Return migration versions applied locally but NOT announced by the peer.

    Used by ``pt sync resume`` to decide whether to block (§2.3 step
    6). The table is ``schema_migration_announcements``; each row is
    ``(version, name, machine_id, applied_at)`` keyed by
    ``(version, machine_id)``. A version is "peer-unannounced" when
    we have our own row for it but no row from any OTHER machine_id.

    Returns an empty list when the check can't meaningfully run — for
    example when cr-sqlite hasn't been flipped on the announcement
    table yet (so peer rows can't replicate in), or when the table
    doesn't exist. That's deliberate: before the §2.5 flips, `pt
    sync resume` should never block the operator on a gate it can't
    actually verify.
    """
    try:
        rows = conn.execute(
            "SELECT version FROM schema_migration_announcements "
            "WHERE machine_id = ? "
            "EXCEPT "
            "SELECT version FROM schema_migration_announcements "
            "WHERE machine_id != ?",
            (local_site_id, local_site_id),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]
