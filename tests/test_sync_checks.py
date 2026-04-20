"""Tests for scripts/db/sync_checks.py — preflight hygiene primitives.

The three checks are pure wrappers around (1) ``sntp``, (2)
``tailscale ping``, and (3) the in-process ``crr_manifest`` module.
Tests mock the shell-outs (subprocess) so they can exercise the
"binary missing", "timeout", "unparseable output" branches without
depending on the host's actual network or NTP state.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.sync_checks import (  # noqa: E402
    manifest_hash,
    ntp_drift_seconds,
    peer_reachable,
)


# ---------------------------------------------------------------------
# ntp_drift_seconds
# ---------------------------------------------------------------------


_SAMPLE_SNTP_OUTPUT_NEG = (
    "2026-04-19 19:45:00.123456 (-0700) -0.004321 +/- 0.023456 "
    "time.apple.com 17.253.84.253\n"
)
_SAMPLE_SNTP_OUTPUT_POS = (
    "2026-04-19 19:45:00.123456 (-0700) +13.480000 +/- 0.045000 "
    "time.apple.com 17.253.84.253\n"
)


def _mock_run(stdout: str = "", returncode: int = 0, raise_: Exception | None = None):
    def _inner(*_a, **_kw):
        if raise_:
            raise raise_
        return subprocess.CompletedProcess(
            args=["sntp"], returncode=returncode, stdout=stdout, stderr=""
        )
    return _inner


def test_ntp_drift_parses_negative_drift():
    with patch("db.sync_checks.shutil.which", return_value="/usr/bin/sntp"), \
         patch("db.sync_checks.subprocess.run", _mock_run(_SAMPLE_SNTP_OUTPUT_NEG)):
        assert ntp_drift_seconds() == pytest.approx(-0.004321)


def test_ntp_drift_parses_positive_drift_matching_mini_report():
    """The Mini's clock was reported at +13.48s against Apple time
    during Phase 2 setup. Pin that the parser handles large positive
    values (not just sub-second ones)."""
    with patch("db.sync_checks.shutil.which", return_value="/usr/bin/sntp"), \
         patch("db.sync_checks.subprocess.run", _mock_run(_SAMPLE_SNTP_OUTPUT_POS)):
        assert ntp_drift_seconds() == pytest.approx(13.48)


def test_ntp_drift_returns_none_when_binary_missing():
    with patch("db.sync_checks.shutil.which", return_value=None):
        assert ntp_drift_seconds() is None


def test_ntp_drift_returns_none_on_timeout():
    with patch("db.sync_checks.shutil.which", return_value="/usr/bin/sntp"), \
         patch("db.sync_checks.subprocess.run",
               _mock_run(raise_=subprocess.TimeoutExpired("sntp", 5))):
        assert ntp_drift_seconds() is None


def test_ntp_drift_returns_none_on_nonzero_exit():
    with patch("db.sync_checks.shutil.which", return_value="/usr/bin/sntp"), \
         patch("db.sync_checks.subprocess.run",
               _mock_run(stdout="", returncode=1)):
        assert ntp_drift_seconds() is None


def test_ntp_drift_returns_none_on_unparseable_output():
    with patch("db.sync_checks.shutil.which", return_value="/usr/bin/sntp"), \
         patch("db.sync_checks.subprocess.run",
               _mock_run(stdout="garbage output with no drift info")):
        assert ntp_drift_seconds() is None


# ---------------------------------------------------------------------
# peer_reachable
# ---------------------------------------------------------------------


def test_peer_reachable_true_on_pong():
    pong = "pong from eriks-mac-mini (100.68.223.79) via 192.168.1.207:41641 in 6ms\n"
    with patch("db.sync_checks.shutil.which", return_value="/usr/local/bin/tailscale"), \
         patch("db.sync_checks.Path.exists", return_value=True), \
         patch("db.sync_checks.subprocess.run", _mock_run(pong)):
        assert peer_reachable("eriks-mac-mini") is True


def test_peer_reachable_false_when_binary_missing():
    with patch("db.sync_checks.shutil.which", return_value=None), \
         patch("db.sync_checks.Path.exists", return_value=False):
        assert peer_reachable("eriks-mac-mini") is False


def test_peer_reachable_false_on_timeout():
    with patch("db.sync_checks.shutil.which", return_value="/usr/local/bin/tailscale"), \
         patch("db.sync_checks.Path.exists", return_value=True), \
         patch("db.sync_checks.subprocess.run",
               _mock_run(raise_=subprocess.TimeoutExpired("tailscale", 5))):
        assert peer_reachable("eriks-mac-mini") is False


def test_peer_reachable_false_on_no_pong_in_output():
    """tailscale ping can return 0 even on failure under some versions —
    presence of 'pong from' is the authoritative signal."""
    with patch("db.sync_checks.shutil.which", return_value="/usr/local/bin/tailscale"), \
         patch("db.sync_checks.Path.exists", return_value=True), \
         patch("db.sync_checks.subprocess.run", _mock_run("pinging...\n", returncode=0)):
        assert peer_reachable("eriks-mac-mini") is False


def test_peer_reachable_false_on_nonzero_return():
    with patch("db.sync_checks.shutil.which", return_value="/usr/local/bin/tailscale"), \
         patch("db.sync_checks.Path.exists", return_value=True), \
         patch("db.sync_checks.subprocess.run", _mock_run("", returncode=1)):
        assert peer_reachable("eriks-mac-mini") is False


# ---------------------------------------------------------------------
# manifest_hash
# ---------------------------------------------------------------------


def test_manifest_hash_is_deterministic():
    """Two calls with no changes in between produce identical hashes —
    the daemon compares this value across machines on every round and
    a non-deterministic hash would fire false positives."""
    assert manifest_hash() == manifest_hash()


def test_manifest_hash_length_is_sha256_hex():
    h = manifest_hash()
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_manifest_hash_changes_when_crr_set_changes(monkeypatch):
    """A manifest change (someone added a table to CRR_TABLES) must
    invalidate the hash — otherwise peers with divergent manifests
    would sync tables one side doesn't know about."""
    baseline = manifest_hash()
    monkeypatch.setattr(
        "db.crr_manifest.CRR_TABLES",
        frozenset({"tasks", "ideas", "task_history", "task_attachments",
                   "projects", "project_info", "ai_agents",
                   "service_dependencies", "calendar_events",
                   "calendar_event_tasks", "brand_new_table"}),
    )
    assert manifest_hash() != baseline


def test_manifest_hash_changes_when_local_only_set_changes(monkeypatch):
    baseline = manifest_hash()
    monkeypatch.setattr(
        "db.crr_manifest.LOCAL_ONLY_TABLES",
        frozenset({"schema_migrations"}),  # smaller than real set
    )
    assert manifest_hash() != baseline


def test_manifest_hash_is_order_independent(monkeypatch):
    """Frozensets have no order but JSON encoding must sort — two
    machines with differently-constructed but identically-contented
    frozensets must produce the same hash."""
    baseline = manifest_hash()
    # Reassign to a re-constructed frozenset (same members, new internal order).
    from db import crr_manifest as mod
    shuffled = frozenset(reversed(list(mod.CRR_TABLES)))
    monkeypatch.setattr("db.crr_manifest.CRR_TABLES", shuffled)
    assert manifest_hash() == baseline
