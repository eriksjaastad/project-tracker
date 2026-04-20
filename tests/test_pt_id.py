"""Tests for scripts/db/pt_id.py — the 63-bit client-side ID generator.

Covers:
- Bit-layout correctness (decompose ∘ next_id == identity for the
  fields we can observe).
- Monotonicity within a process.
- Counter reset across ms boundaries.
- Counter overflow busy-waits rather than colliding.
- Cross-machine: two generators with distinct machine_ids never collide
  even when firing in the same ms.
- Invalid machine_id rejection (0 / _MID_MAX are accepted; anything
  outside raises).
- Clock-regression handling preserves monotonicity with a WARNING.
- Pre-epoch clock rejection.
- 41-bit timestamp overflow rejection (future-proofing).
- load_machine_id priority: explicit _metadata > crsql_site_id hash > 0.
- Default-zero warning logs once per process.
- Singleton reuse across get_generator() calls.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db import pt_id  # noqa: E402
from db.pt_id import (  # noqa: E402
    PT_ID_EPOCH_MS,
    PtIdGenerator,
    _CTR_MAX,
    _MID_MAX,
    _MID_SHIFT,
    _TS_MAX,
    _TS_SHIFT,
    get_generator,
    load_machine_id,
    next_id,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def _reset():
    """Every test starts with a fresh singleton + fresh warning state."""
    reset_for_testing()
    yield
    reset_for_testing()


# ---------------------------------------------------------------------
# PtIdGenerator — construction + boundary machine_id
# ---------------------------------------------------------------------


def test_generator_rejects_negative_machine_id():
    with pytest.raises(ValueError, match="out of range"):
        PtIdGenerator(-1)


def test_generator_rejects_machine_id_above_max():
    with pytest.raises(ValueError, match="out of range"):
        PtIdGenerator(_MID_MAX + 1)


def test_generator_accepts_boundary_machine_ids():
    """0 and the maximum (1023) are valid — exclusive-upper-bound bug guard."""
    assert PtIdGenerator(0).machine_id == 0
    assert PtIdGenerator(_MID_MAX).machine_id == _MID_MAX


# ---------------------------------------------------------------------
# Monotonicity within a process
# ---------------------------------------------------------------------


def test_ids_strictly_increase_within_process():
    """Successive IDs must be strictly > previous. If this test fails,
    CRR uniqueness is compromised even within a single process —
    concurrent writes within the same ms would collide."""
    g = PtIdGenerator(machine_id=1)
    ids = [g.next_id() for _ in range(500)]
    assert all(a < b for a, b in zip(ids, ids[1:])), (
        "IDs must be strictly increasing; found a non-strict pair"
    )


def test_ids_fit_signed_int64_even_at_max_fields():
    """SQLite's signed INTEGER max is 2^63 - 1. All 63-bit IDs must fit."""
    # Simulate the worst case: max timestamp, max machine_id, max counter.
    max_id = (_TS_MAX << _TS_SHIFT) | (_MID_MAX << _MID_SHIFT) | _CTR_MAX
    assert max_id < (1 << 63), "packed ID must fit signed INT64"
    assert max_id > 0


# ---------------------------------------------------------------------
# Bit-layout correctness via decompose
# ---------------------------------------------------------------------


def test_decompose_roundtrip_preserves_machine_id():
    g = PtIdGenerator(machine_id=42)
    pt = g.next_id()
    _ts, mid, _ctr = g.decompose(pt)
    assert mid == 42


def test_decompose_counter_is_zero_for_first_id_in_new_ms():
    g = PtIdGenerator(machine_id=1)
    pt = g.next_id()
    _ts, _mid, ctr = g.decompose(pt)
    assert ctr == 0


def test_decompose_counter_increments_within_same_ms():
    """Pin the within-ms counter increment: two successive IDs in the
    same ms must have ctr values 0, 1, 2, ..."""
    g = PtIdGenerator(machine_id=1)
    # Freeze time so both calls land in the same ms.
    frozen_ms = int(time.time() * 1000) - PT_ID_EPOCH_MS + 100
    with patch("db.pt_id.time.time", return_value=(frozen_ms + PT_ID_EPOCH_MS) / 1000.0):
        id_a = g.next_id()
        id_b = g.next_id()
        id_c = g.next_id()
    _, _, ctr_a = g.decompose(id_a)
    _, _, ctr_b = g.decompose(id_b)
    _, _, ctr_c = g.decompose(id_c)
    assert ctr_a == 0
    assert ctr_b == 1
    assert ctr_c == 2


def test_counter_resets_when_ms_advances():
    """When wall-clock ms advances between two calls, the counter
    resets to 0 — the ms bits carry the uniqueness, so ctr can recycle."""
    g = PtIdGenerator(machine_id=1)
    base_ms = int(time.time() * 1000) - PT_ID_EPOCH_MS + 1000
    with patch("db.pt_id.time.time", return_value=(base_ms + PT_ID_EPOCH_MS) / 1000.0):
        g.next_id()
        g.next_id()  # ctr now at 1
    # Advance the simulated clock by 2ms and call again.
    with patch("db.pt_id.time.time", return_value=(base_ms + 2 + PT_ID_EPOCH_MS) / 1000.0):
        new_id = g.next_id()
    _, _, ctr = g.decompose(new_id)
    assert ctr == 0, "counter must reset when ms advances"


# ---------------------------------------------------------------------
# Counter overflow
# ---------------------------------------------------------------------


def test_counter_overflow_advances_to_next_ms_instead_of_colliding():
    """The 12-bit counter saturates at 4095. The 4097th ID in one ms
    must NOT wrap back to 0 in the same ms (that would collide with
    the 1st ID). Instead we wait for next ms."""
    g = PtIdGenerator(machine_id=7)
    # Force the pre-overflow state: counter at max in some ms that's
    # already elapsed (so the wall-clock read advances past it).
    past_ms = int(time.time() * 1000) - PT_ID_EPOCH_MS - 10
    g._last_ms = past_ms
    g._counter = _CTR_MAX  # 4095

    new_id = g.next_id()
    ts, _mid, ctr = g.decompose(new_id)
    assert ts > past_ms, (
        f"after overflow, timestamp ({ts}) must advance past "
        f"saturated-ms ({past_ms})"
    )
    assert ctr == 0, "after overflow-and-advance, counter should reset"


# ---------------------------------------------------------------------
# Cross-machine: distinct machine_ids cannot collide
# ---------------------------------------------------------------------


def test_two_generators_with_distinct_machine_ids_never_collide():
    """Same-ms IDs from two generators with different machine_ids must
    differ at the machine-id bits — so the full 63-bit values differ.
    This is the core correctness claim of #6044's fix."""
    g_a = PtIdGenerator(machine_id=5)
    g_b = PtIdGenerator(machine_id=6)
    frozen_ms = int(time.time() * 1000) - PT_ID_EPOCH_MS + 100
    frozen_time = (frozen_ms + PT_ID_EPOCH_MS) / 1000.0
    with patch("db.pt_id.time.time", return_value=frozen_time):
        # Each generator fires 100 IDs within the same ms.
        ids_a = {g_a.next_id() for _ in range(100)}
        ids_b = {g_b.next_id() for _ in range(100)}
    assert len(ids_a) == 100
    assert len(ids_b) == 100
    assert ids_a.isdisjoint(ids_b), (
        "IDs from machines with different machine_ids must never collide"
    )


# ---------------------------------------------------------------------
# Clock handling — pre-epoch, overflow, backward movement
# ---------------------------------------------------------------------


def test_generator_rejects_pre_epoch_clock():
    """If system clock is before PT_ID_EPOCH_MS, refuse to generate.
    An ID from a pre-epoch clock would have a negative timestamp bit,
    which overlaps the sign bit and produces invalid values."""
    g = PtIdGenerator(machine_id=1)
    pre_epoch_time = (PT_ID_EPOCH_MS / 1000.0) - 1.0
    with patch("db.pt_id.time.time", return_value=pre_epoch_time):
        with pytest.raises(RuntimeError, match="before PT_ID_EPOCH_MS"):
            g.next_id()


def test_generator_rejects_post_41bit_overflow_clock():
    """Year-2095 problem: ms since epoch exceeds 41 bits. Don't silently
    truncate — raise so the operator knows to rotate the layout."""
    g = PtIdGenerator(machine_id=1)
    overflow_ms = PT_ID_EPOCH_MS + _TS_MAX + 1
    with patch("db.pt_id.time.time", return_value=overflow_ms / 1000.0):
        with pytest.raises(RuntimeError, match="exceeds 41-bit budget"):
            g.next_id()


def test_clock_regression_preserves_monotonicity_with_warning(caplog):
    """If the clock moves backward (NTP step, hibernate drift), IDs
    must remain strictly monotonic. We stay at last_ms and increment
    counter; a WARNING signals the anomaly."""
    g = PtIdGenerator(machine_id=1)

    # First call establishes a high-water ms.
    high_water_ms = int(time.time() * 1000) - PT_ID_EPOCH_MS + 5000
    with patch("db.pt_id.time.time", return_value=(high_water_ms + PT_ID_EPOCH_MS) / 1000.0):
        id_before = g.next_id()

    # Second call simulates a 2-second backward clock step.
    regressed_ms = high_water_ms - 2000
    caplog.set_level(logging.WARNING, logger="pt.id")
    with patch("db.pt_id.time.time", return_value=(regressed_ms + PT_ID_EPOCH_MS) / 1000.0):
        id_after = g.next_id()

    assert id_after > id_before, "monotonicity must survive clock regression"
    assert any(
        "clock moved backward" in rec.message for rec in caplog.records
    ), "clock-regression path must log a WARNING"


# ---------------------------------------------------------------------
# load_machine_id — priority resolution
# ---------------------------------------------------------------------


def test_load_machine_id_defaults_to_zero_when_db_path_none(caplog):
    caplog.set_level(logging.WARNING, logger="pt.id")
    assert load_machine_id(None) == 0
    assert any("machine_id=0" in rec.message for rec in caplog.records)


def test_load_machine_id_defaults_to_zero_when_db_missing(tmp_path):
    missing = tmp_path / "does-not-exist.db"
    assert load_machine_id(missing) == 0


def test_load_machine_id_reads_explicit_metadata_config(tmp_path):
    """Operator-set _metadata['pt.machine_id'] wins over site_id hashing."""
    db = tmp_path / "explicit.db"
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE _metadata (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO _metadata (key, value, created_at) VALUES (?, ?, ?)",
        ("pt.machine_id", "42", "2026-04-20T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()
    assert load_machine_id(db) == 42


def test_load_machine_id_rejects_out_of_range_metadata(tmp_path):
    db = tmp_path / "bad.db"
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE _metadata (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO _metadata (key, value, created_at) VALUES (?, ?, ?)",
        ("pt.machine_id", "9999", "2026-04-20T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()
    with pytest.raises(ValueError, match="out of range"):
        load_machine_id(db)


def test_load_machine_id_falls_back_when_metadata_table_missing(tmp_path, monkeypatch):
    """_metadata may not exist on a bare-new DB; that's not an error,
    we just move on to the next resolution step. On a machine without
    cr-sqlite, that means default-zero."""
    db = tmp_path / "bare.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE anything_else (id INTEGER)")
    conn.commit()
    conn.close()
    # Simulate a machine without cr-sqlite installed.
    monkeypatch.setattr(pt_id, "_CRSQLITE_DYLIB", Path("/nonexistent/crsqlite.dylib"))
    assert load_machine_id(db) == 0


def test_load_machine_id_hashes_site_id_when_metadata_missing_but_crsqlite_present(tmp_path):
    """On a machine WITH cr-sqlite installed, the fallback path goes to
    hash(crsql_site_id()) not default-zero. This is the auto-config
    behavior — fresh DB creates a new site_id the moment cr-sqlite
    loads, and we derive a 10-bit machine_id from it.

    Skipped if cr-sqlite isn't installed on the test host — the test
    above (`..._falls_back_when_metadata_table_missing`) covers the
    no-cr-sqlite path explicitly."""
    crsqlite = Path.home() / ".local/lib/crsqlite/crsqlite.dylib"
    if not crsqlite.exists():
        pytest.skip("cr-sqlite dylib not present; auto-derivation path not testable here")

    db = tmp_path / "with_crsqlite.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE anything_else (id INTEGER)")
    conn.commit()
    conn.close()
    mid = load_machine_id(db)
    assert 0 <= mid <= _MID_MAX, f"derived machine_id {mid} out of 10-bit range"


# ---------------------------------------------------------------------
# One-time warning semantics
# ---------------------------------------------------------------------


def test_default_zero_warning_fires_only_once_per_process(caplog):
    caplog.set_level(logging.WARNING, logger="pt.id")
    load_machine_id(None)
    load_machine_id(None)
    load_machine_id(None)
    warnings = [
        rec for rec in caplog.records
        if "defaulting machine_id=0" in rec.message
    ]
    assert len(warnings) == 1, (
        f"default-zero warning should fire once, fired {len(warnings)} times"
    )


# ---------------------------------------------------------------------
# Singleton semantics
# ---------------------------------------------------------------------


def test_get_generator_returns_same_instance_across_calls():
    g1 = get_generator(None)
    g2 = get_generator(None)
    g3 = get_generator(None)
    assert g1 is g2 is g3


def test_next_id_uses_singleton_consistently():
    """next_id() is sugar over get_generator().next_id(); successive
    calls must be strictly increasing (proves they hit one generator)."""
    ids = [next_id(None) for _ in range(50)]
    assert all(a < b for a, b in zip(ids, ids[1:]))


def test_reset_for_testing_clears_singleton():
    g1 = get_generator(None)
    reset_for_testing()
    g2 = get_generator(None)
    assert g1 is not g2, "reset_for_testing must produce a fresh singleton"
