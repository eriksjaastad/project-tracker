"""Client-side unique ID generator for CRR tables (pt #6044).

Background
----------
cr-sqlite rejects ``AUTOINCREMENT`` on CRR-classified tables because two
nodes would assign unrelated rows the same PK under concurrent inserts
(validated empirically 2026-04-20: two sites each auto-generated ``id=3``
for different new rows; sync merged them as the same row, one machine's
content silently overwrote the other's). A plain ``INTEGER PRIMARY KEY``
without ``AUTOINCREMENT`` passes cr-sqlite's validator, but SQLite will
still auto-generate rowid values for NULL/omitted id columns — same
collision hazard, just invisible to cr-sqlite's static check.

This module produces 63-bit integer IDs at application insert time that
are collision-free across machines PROVIDED each machine has a distinct
10-bit ``machine_id``. The IDs fit SQLite's signed ``INTEGER`` type
(2^63 - 1) and slot into existing ``INTEGER PRIMARY KEY`` columns with
no schema changes beyond dropping ``AUTOINCREMENT``.

Bit layout (Snowflake-style, 63 bits total)
-------------------------------------------

    bit 62                    22 12          0
     [  timestamp_ms (41)  ][ mid(10) ][ ctr(12) ]
     MSB                                      LSB

- ``timestamp_ms`` (41 bits): milliseconds since ``PT_ID_EPOCH_MS``
  (2026-01-01T00:00:00Z). Rolls over in ~69 years (year 2095).
- ``machine_id`` (10 bits): 0..1023. Identifies the originating
  machine. Must be distinct across all machines in the sync group.
- ``counter`` (12 bits): monotonic counter within each millisecond,
  resets at each new ms. Overflow (4096 IDs in one ms on one machine)
  causes a busy-wait to the next ms — a nominal signal of an anomalous
  burst rate, not a realistic path.

Why 41/10/12 over TodoMVC's 32/16/16:
- ms instead of s timestamp: eliminates "same-second" collisions across
  fast process restarts and sub-second bursts.
- 10-bit ``machine_id``: 1024 machines is plenty for a personal
  multi-device setup (laptop + Mini + phone + iPad + future) while
  leaving bits for timestamp resolution.
- 12-bit counter: 4096/ms = 4M/s per machine, far above any burst
  scenario (agent-driven card factory, task_history on migration).

Machine ID assignment
---------------------

Two strategies, priority order:

1. **Explicit config (preferred)** — set the ``pt.machine_id`` key in
   ``_metadata`` table to a value in ``0..1023``. Operator assigns
   known IDs (laptop=0, mini=1, etc.) so cross-machine collisions
   are impossible by construction. Recommended once the sync group
   grows past 2 machines.
2. **Hash of ``crsql_site_id()`` (fallback)** — if cr-sqlite is
   loaded and no explicit config is set, hash the site_id's low
   bytes to 10 bits. Auto-configuration path. Birthday-paradox
   collision probability (exact formula: ``1 - prod(1 - k/1024)``
   for k in 1..N-1, bucket count 1024):
        P(collision | 2 machines)  ≈ 0.098%
        P(collision | 5 machines)  ≈ 0.97%
        P(collision | 10 machines) ≈ 4.3%
   For 2 machines, effectively safe but NOT zero. Logs a WARNING
   recommending explicit config once ≥3 machines are detected.

If cr-sqlite is not loaded (fresh checkout, tests, CLI subcommands
that don't hit sync), ``machine_id`` defaults to ``0`` with a WARNING
logged once per process. This keeps fresh/test environments working
but would cause collisions if two unconfigured machines later joined
a sync group. The warning is the explicit signal to configure.

Monotonicity guarantees
-----------------------

- **Within a process:** IDs are strictly increasing. Time advances or
  counter increments; never the reverse.
- **Clock moves backward:** If the wall clock regresses (NTP step,
  laptop hibernation drift), ``next_id`` continues using the last
  observed ms and increments counter. If counter exhausts (rare), it
  advances last_ms by 1 and resets counter. This preserves
  monotonicity at the cost of ID space ahead of wall clock — a mild
  future-dating that resolves when real time catches up.
- **Across process restarts:** no guarantee of strict monotonicity
  across boundaries — IDs can repeat if the clock hasn't advanced and
  machine_id is the same. In practice: clock almost always advances
  between restarts. For strict cross-process monotonicity a persisted
  high-water mark would be required; we don't build that here because
  (a) CRR correctness doesn't need it (machine_id already prevents
  collisions) and (b) it adds IO per insert.

Collision analysis
------------------

**Distinct machine_ids:** two machines with different ``machine_id``
values generating IDs in the same ms CANNOT collide — their mid bits
differ, so the full 63-bit IDs differ.

**Same machine_id (misconfigured):** two machines sharing a
``machine_id`` WILL collide if they issue IDs with the same counter
value in the same ms. With per-machine monotonic counters starting at
0, a fresh startup on both machines at the same ms produces ID
collisions immediately. This is why ``check_machine_id_conflict()``
should be called at daemon startup if enhanced safety is needed
(future work; tracked separately if the need arises).

**Usage**::

    from db.pt_id import next_id
    from db.schema import get_db_path

    new_id = next_id(db_path=get_db_path())
    conn.execute(
        "INSERT INTO tasks (id, title, ...) VALUES (?, ?, ...)",
        (new_id, title, ...),
    )

The generator is a process-wide thread-safe singleton. First call
performs ``machine_id`` resolution; subsequent calls reuse it.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("pt.id")

# 2026-01-01T00:00:00Z in ms since Unix epoch. Verify with:
#   python3 -c "import datetime; print(datetime.datetime.fromtimestamp(1767225600, tz=datetime.timezone.utc))"
# Chosen as a recent epoch to maximize future timestamp runway (~69 years
# from this epoch, so 41-bit timestamp rollover hits around year 2095).
# Changing this is a BREAKING change — all new IDs shift relative to old ones.
PT_ID_EPOCH_MS = 1767225600000

# Bit widths. Total = 63 so signed SQLite INTEGER (2^63 - 1) fits.
_TS_BITS = 41
_MID_BITS = 10
_CTR_BITS = 12
assert _TS_BITS + _MID_BITS + _CTR_BITS == 63

_MID_MAX = (1 << _MID_BITS) - 1     # 1023
_CTR_MAX = (1 << _CTR_BITS) - 1     # 4095
_TS_MAX = (1 << _TS_BITS) - 1       # ~2.2e12 ms ≈ 69 years past epoch

_MID_SHIFT = _CTR_BITS              # 12
_TS_SHIFT = _CTR_BITS + _MID_BITS   # 22


class PtIdGenerator:
    """Thread-safe 63-bit ID generator. One instance per process."""

    def __init__(self, machine_id: int) -> None:
        if not (0 <= machine_id <= _MID_MAX):
            raise ValueError(
                f"machine_id {machine_id} out of range 0..{_MID_MAX}"
            )
        self._machine_id = machine_id
        self._lock = threading.Lock()
        self._last_ms = 0
        self._counter = -1  # incremented to 0 on first id in a new ms

    @property
    def machine_id(self) -> int:
        return self._machine_id

    def next_id(self) -> int:
        """Return the next 63-bit ID. Thread-safe."""
        with self._lock:
            now_ms = int(time.time() * 1000) - PT_ID_EPOCH_MS
            if now_ms < 0:
                raise RuntimeError(
                    "system clock is before PT_ID_EPOCH_MS "
                    f"(2026-01-01T00:00:00Z); refusing to generate IDs "
                    f"(got offset {now_ms} ms)"
                )
            if now_ms > _TS_MAX:
                raise RuntimeError(
                    f"epoch-relative ms {now_ms} exceeds 41-bit budget "
                    f"(max {_TS_MAX}); pt_id layout needs rotation "
                    "(expected ~year 2095)"
                )

            if now_ms > self._last_ms:
                self._last_ms = now_ms
                self._counter = 0
            elif now_ms == self._last_ms:
                self._counter += 1
                if self._counter > _CTR_MAX:
                    # 4096 IDs in one ms — wait for next ms rather than
                    # collide. Busy-wait is acceptable: this path is
                    # vanishingly rare (4M IDs/s per machine sustained).
                    nxt = int(time.time() * 1000) - PT_ID_EPOCH_MS
                    while nxt == self._last_ms:
                        nxt = int(time.time() * 1000) - PT_ID_EPOCH_MS
                    self._last_ms = nxt
                    self._counter = 0
            else:
                # Clock moved backward. Preserve monotonicity by staying
                # at last_ms and incrementing counter. Log — this is
                # unusual (NTP step, hibernate drift).
                self._counter += 1
                if self._counter > _CTR_MAX:
                    self._last_ms += 1
                    self._counter = 0
                log.warning(
                    "pt_id: clock moved backward (wall=%d, last=%d); "
                    "continuing at last_ms+counter=%d+%d",
                    now_ms, self._last_ms, self._last_ms, self._counter,
                )

            return (
                (self._last_ms << _TS_SHIFT)
                | (self._machine_id << _MID_SHIFT)
                | self._counter
            )

    def decompose(self, pt_id: int) -> tuple[int, int, int]:
        """Return ``(timestamp_ms_since_epoch, machine_id, counter)``.

        Inverse of ``next_id``'s bit-packing. Useful for debugging and
        tests; not a hot-path function.
        """
        ctr = pt_id & _CTR_MAX
        mid = (pt_id >> _MID_SHIFT) & _MID_MAX
        ts = (pt_id >> _TS_SHIFT) & _TS_MAX
        return ts, mid, ctr


# ---------------------------------------------------------------------
# Machine-ID resolution
# ---------------------------------------------------------------------

_CRSQLITE_DYLIB = Path.home() / ".local/lib/crsqlite/crsqlite.dylib"
_default_zero_warned = False


def _warn_default_zero(reason: str) -> int:
    """Log the default-zero warning at most once per process."""
    global _default_zero_warned
    if not _default_zero_warned:
        log.warning(
            "pt_id: %s; defaulting machine_id=0. Safe for fresh "
            "checkouts and test environments; UNSAFE if two "
            "unconfigured machines ever join a sync group. Set "
            "_metadata['pt.machine_id'] explicitly before enabling sync.",
            reason,
        )
        _default_zero_warned = True
    return 0


def load_machine_id(db_path: Optional[Path]) -> int:
    """Resolve this process's ``machine_id``.

    Priority:
      1. ``_metadata['pt.machine_id']`` explicit config (operator-set).
      2. Hash of ``crsql_site_id()`` low bytes (auto; warns for ≥3
         machines due to birthday-paradox).
      3. Default 0 with a one-time warning (fresh checkouts, tests,
         paths where cr-sqlite isn't loaded).

    Caller should hold the resulting int for the process lifetime —
    the resolved value is stable across the process (site_id is
    fixed; operator config doesn't change mid-run).
    """
    if db_path is None:
        return _warn_default_zero("no db_path provided")

    if not db_path.exists():
        return _warn_default_zero(f"db does not exist at {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        # 1. Explicit config wins.
        try:
            row = conn.execute(
                "SELECT value FROM _metadata WHERE key = 'pt.machine_id'"
            ).fetchone()
        except sqlite3.OperationalError:
            # _metadata table may not exist yet on a bare-new DB.
            row = None

        if row is not None:
            try:
                mid = int(row[0])
            except (TypeError, ValueError):
                raise ValueError(
                    f"_metadata['pt.machine_id'] must be an int, "
                    f"got {row[0]!r}"
                )
            if not (0 <= mid <= _MID_MAX):
                raise ValueError(
                    f"_metadata['pt.machine_id']={mid} out of range "
                    f"0..{_MID_MAX}"
                )
            log.info(
                "pt_id: machine_id=%d from _metadata explicit config",
                mid,
            )
            return mid

        # 2. Derive from crsql_site_id if cr-sqlite can load.
        if _CRSQLITE_DYLIB.exists():
            try:
                conn.enable_load_extension(True)
                conn.load_extension(
                    str(_CRSQLITE_DYLIB),
                    entrypoint="sqlite3_crsqlite_init",
                )
                site_hex = conn.execute(
                    "SELECT hex(crsql_site_id())"
                ).fetchone()[0]
                # Hash the full 16-byte site_id deterministically to
                # low 10 bits. SHA-256 gives a better distribution than
                # just taking low bytes — site_ids are UUID-v4 random
                # so low bytes are random too, but this keeps the
                # derivation obviously deterministic and testable.
                digest = hashlib.sha256(bytes.fromhex(site_hex)).digest()
                mid = ((digest[0] << 8) | digest[1]) & _MID_MAX
                log.warning(
                    "pt_id: machine_id=%d derived from hash(crsql_site_id). "
                    "For ≥3 machines, set _metadata['pt.machine_id'] "
                    "explicitly to avoid 1-in-1024 birthday collisions.",
                    mid,
                )
                return mid
            except sqlite3.OperationalError as err:
                log.info(
                    "pt_id: cr-sqlite load failed (%s); falling through to default",
                    err,
                )

        return _warn_default_zero(
            "cr-sqlite not loaded and no _metadata['pt.machine_id']"
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------

_singleton: Optional[PtIdGenerator] = None
_singleton_lock = threading.Lock()


def get_generator(db_path: Optional[Path] = None) -> PtIdGenerator:
    """Return the process-wide ``PtIdGenerator`` singleton.

    First call resolves ``machine_id`` via ``load_machine_id(db_path)``
    and instantiates; subsequent calls return the same instance and
    ignore ``db_path``. Thread-safe.
    """
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            mid = load_machine_id(db_path)
            _singleton = PtIdGenerator(mid)
        return _singleton


def next_id(db_path: Optional[Path] = None) -> int:
    """Convenience: get next ID from the process singleton.

    Suitable for one-liner INSERT paths::

        conn.execute(
            "INSERT INTO tasks (id, title, ...) VALUES (?, ?, ...)",
            (next_id(), title, ...),
        )
    """
    return get_generator(db_path).next_id()


def reset_for_testing() -> None:
    """Clear the process singleton and the one-time warning flag.

    Tests only. Guarded by ``pytest in sys.modules`` to prevent
    accidental production use — resetting mid-run could produce IDs
    under a different ``machine_id`` if the operator changed
    ``_metadata['pt.machine_id']`` between calls, which is exactly
    the identity drift this module is designed to prevent.
    """
    if "pytest" not in sys.modules:
        raise RuntimeError(
            "reset_for_testing() called outside a pytest run; refusing. "
            "Resetting the singleton mid-process can produce IDs under "
            "different machine_ids, which is the exact identity drift "
            "this module prevents."
        )
    global _singleton, _default_zero_warned
    with _singleton_lock:
        _singleton = None
        _default_zero_warned = False
