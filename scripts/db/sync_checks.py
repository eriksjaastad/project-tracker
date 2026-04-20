"""
Connection hygiene checks for the cr-sqlite sync daemon (Phase 2.1b).

Three independent checks the daemon runs before it starts a sync round,
and that ``pt sync status`` can invoke for on-demand diagnostics:

- ``ntp_drift_seconds()``       — how far this machine's clock is from
                                  Apple time, using a read-only ``sntp``
                                  probe. cr-sqlite's causal bookkeeping
                                  needs sub-second drift; §2.0 pre-req.
- ``peer_reachable(host)``      — is the peer pingable over the Tailscale
                                  mesh? Uses ``tailscale ping`` so we
                                  exercise the real WireGuard path, not
                                  just routing or ICMP.
- ``manifest_hash(conn)``       — a stable fingerprint of this machine's
                                  CRR classification manifest (CRR +
                                  LOCAL_ONLY + CONTROL_PLANE). The
                                  daemon compares its hash against the
                                  peer's before syncing; a mismatch means
                                  one side has a newer ``crr_manifest.py``
                                  and syncing tables unknown to the other
                                  side is a silent-drift disaster.

All three functions are pure and side-effect-free: they never write to
the DB, never mutate system state, never elevate privileges. They shell
out to system binaries that are already on macOS (``sntp``) or that are
installed as part of Phase 2 setup (``tailscale``). On any failure they
return a sentinel — ``None`` for drift, ``False`` for reachability — so
the daemon can decide whether to proceed, pause, or report degraded
status, rather than crashing.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Optional


# sntp's human output varies across macOS versions. Two observed shapes:
#   "2026-04-19 19:45:00.123456 (-0700) -0.004321 +/- 0.023456 time.apple.com 17..."
#   "-11.066506 +/- 0.038576 time.apple.com 2620:..."
# The drift value is always the signed float immediately preceding " +/-",
# regardless of what precedes it — match that pattern directly.
_SNTP_DRIFT_RE = re.compile(
    r"(^|\s)([+-]?\d+(?:\.\d+)?)\s+\+\/-",
    re.MULTILINE,
)

DEFAULT_NTP_HOST = "time.apple.com"
DEFAULT_NTP_TIMEOUT_S = 5.0
DEFAULT_TAILSCALE_PING_TIMEOUT_S = 3.0


def ntp_drift_seconds(
    host: str = DEFAULT_NTP_HOST,
    timeout_s: float = DEFAULT_NTP_TIMEOUT_S,
) -> Optional[float]:
    """Return this machine's clock drift (in seconds) vs ``host``, or ``None``.

    Uses read-only ``sntp <host>`` — the ``-s``/``-S`` set-clock flags
    would require ``sudo`` and we never want the daemon to mutate
    system state implicitly. Returns a signed float (positive ⇒ local
    clock is *ahead* of NTP) or ``None`` on any failure (binary
    missing, network unavailable, unparseable output).
    """
    sntp = shutil.which("sntp")
    if sntp is None:
        return None
    try:
        proc = subprocess.run(
            [sntp, host],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    match = _SNTP_DRIFT_RE.search(proc.stdout or "")
    if match is None:
        return None
    try:
        return float(match.group(2))
    except ValueError:
        return None


def peer_reachable(
    host: str,
    timeout_s: float = DEFAULT_TAILSCALE_PING_TIMEOUT_S,
) -> bool:
    """True when ``tailscale ping`` gets a pong from ``host`` within ``timeout_s``.

    Shells out to the ``tailscale`` CLI rather than bare ICMP so we
    confirm the WireGuard mesh path is live — a ``ping`` might succeed
    over home LAN while the tailnet peer is actually down.
    """
    ts = shutil.which("tailscale") or "/usr/local/bin/tailscale"
    if not Path(ts).exists():
        return False
    try:
        proc = subprocess.run(
            [ts, "ping", "-c", "1", f"--timeout={timeout_s:.1f}s", host],
            capture_output=True,
            text=True,
            timeout=timeout_s + 2.0,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    if proc.returncode != 0:
        return False
    return "pong from" in (proc.stdout or "")


def manifest_hash(conn: Optional[sqlite3.Connection] = None) -> str:
    """Stable SHA-256 hex digest of the current CRR classification manifest.

    The hash covers the three frozensets in ``crr_manifest.py`` —
    ``CRR_TABLES``, ``LOCAL_ONLY_TABLES``, ``CONTROL_PLANE_TABLES`` —
    as sorted JSON. The daemon exchanges this hash with the peer on
    every round; mismatch ⇒ one side's manifest is newer and syncing
    would be syncing the wrong tables. Deterministic across machines
    running the same ``crr_manifest.py`` revision; changes the moment
    anyone adds or reclassifies a table.

    The ``conn`` parameter is accepted for forward-compatibility with a
    future variant that hashes live-DB classifications too, but isn't
    used today — the manifest is a code artifact, not a DB artifact.
    """
    del conn  # currently unused; see docstring
    from db.crr_manifest import (
        CONTROL_PLANE_TABLES,
        CRR_TABLES,
        LOCAL_ONLY_TABLES,
    )

    payload = "|".join(
        [
            "crr:" + ",".join(sorted(CRR_TABLES)),
            "local:" + ",".join(sorted(LOCAL_ONLY_TABLES)),
            "control:" + ",".join(sorted(CONTROL_PLANE_TABLES)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
