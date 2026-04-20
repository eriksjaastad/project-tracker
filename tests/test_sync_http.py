"""Tests for scripts/db/sync_http.py — the cr-sqlite changeset transport.

Two layers covered here:

- Encoding (``row_to_json`` / ``json_to_row``) — every type of value
  cr-sqlite can put in the ``val`` column plus the two BLOB columns
  (``pk``, ``site_id``). Round-trip symmetry is the contract.
- End-to-end: spin up ``make_server`` against an in-memory sqlite DB
  pre-populated with ``crsql_changes`` rows (via a mock cr-sqlite —
  we don't need the real extension to test the transport), and call
  ``pull_from_peer`` against it. Verifies URL shape, query filtering,
  NDJSON streaming, error paths.

Watermark round-trip tests sit alongside, since they share the same
``_metadata`` key namespace.
"""

from __future__ import annotations

import json
import socket
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.sync_http import (  # noqa: E402
    apply_changes,
    iter_changes_for_peer,
    json_to_row,
    make_server,
    pull_from_peer,
    row_to_json,
    serve_forever_in_thread,
    set_watermark,
    watermark_for,
)


# ---------------------------------------------------------------------
# Encoding round-trip
# ---------------------------------------------------------------------


def test_row_encode_decode_round_trip_text_val():
    original = (
        "t",
        b"\x01\t\x01",
        "note",
        "hello",
        1, 5,
        b"\x6a\x91\x35\x9e" * 4,  # 16-byte site_id
        1, 0,
    )
    decoded = json_to_row(row_to_json(original))
    assert decoded == original


def test_row_encode_decode_round_trip_int_val():
    original = ("t", b"\x01", "age", 42, 1, 2, b"\x00" * 16, 1, 0)
    assert json_to_row(row_to_json(original)) == original


def test_row_encode_decode_round_trip_null_val():
    original = ("t", b"\x01", "note", None, 1, 2, b"\x00" * 16, 1, 0)
    assert json_to_row(row_to_json(original)) == original


def test_row_encode_decode_round_trip_float_val():
    original = ("t", b"\x01", "score", 3.14, 1, 2, b"\x00" * 16, 1, 0)
    assert json_to_row(row_to_json(original)) == original


def test_row_encode_decode_round_trip_blob_val():
    """Binary val column (e.g. a stored hash) must round-trip via b64."""
    original = ("t", b"\x01", "hash", b"\xde\xad\xbe\xef", 1, 2, b"\x00" * 16, 1, 0)
    decoded = json_to_row(row_to_json(original))
    assert decoded[3] == b"\xde\xad\xbe\xef"


def test_wire_format_is_single_line_json_no_embedded_newlines():
    """NDJSON requires one record per line — the encoder must not
    produce multi-line output, even for long BLOB columns."""
    payload = row_to_json(
        ("t", b"\x00" * 50, "note", "x" * 1000, 1, 2, b"\x00" * 16, 1, 0)
    )
    assert "\n" not in payload
    # And it must parse.
    json.loads(payload)


def test_json_to_row_raises_on_missing_keys():
    with pytest.raises(KeyError):
        json_to_row('{"table": "t"}')  # missing everything else


# ---------------------------------------------------------------------
# iter_changes_for_peer — SQL correctness
# ---------------------------------------------------------------------


def _fake_crsql_changes_db(tmp_path: Path) -> sqlite3.Connection:
    """Build an in-memory DB mimicking cr-sqlite's crsql_changes shape.

    Tests don't need the actual extension to exercise the transport
    code — the SQL-level query against a same-shaped table is enough,
    and this keeps the test suite runnable on machines without cr-sqlite
    (e.g. CI until we install it there).
    """
    conn = sqlite3.connect(tmp_path / "fake.db", isolation_level=None)
    conn.execute(
        'CREATE TABLE crsql_changes ('
        '"table" TEXT, pk BLOB, cid TEXT, val, '
        'col_version INTEGER, db_version INTEGER, '
        'site_id BLOB, cl INTEGER, seq INTEGER)'
    )
    return conn


def test_iter_changes_filters_by_db_version(tmp_path: Path):
    conn = _fake_crsql_changes_db(tmp_path)
    for ver in range(1, 6):
        conn.execute(
            "INSERT INTO crsql_changes VALUES "
            "('t', ?, 'note', 'v', 1, ?, ?, 1, 0)",
            (bytes([ver]), ver, b"\x11" * 16),
        )
    rows = list(iter_changes_for_peer(conn, since=2, exclude_site_hex="00" * 16))
    versions = [r[5] for r in rows]
    assert versions == [3, 4, 5]


def test_iter_changes_filters_out_excluded_site(tmp_path: Path):
    """The peer's site_id must never appear in what we send them —
    that would echo their own writes back as if we'd authored them."""
    conn = _fake_crsql_changes_db(tmp_path)
    our_site = b"\xaa" * 16
    peer_site = b"\xbb" * 16
    conn.execute(
        "INSERT INTO crsql_changes VALUES "
        "('t', ?, 'note', 'ours', 1, 1, ?, 1, 0)", (b"\x01", our_site))
    conn.execute(
        "INSERT INTO crsql_changes VALUES "
        "('t', ?, 'note', 'theirs', 1, 2, ?, 1, 0)", (b"\x02", peer_site))
    rows = list(iter_changes_for_peer(
        conn, since=0, exclude_site_hex=peer_site.hex()
    ))
    # Only our row comes back — their own row is filtered out.
    assert len(rows) == 1
    assert rows[0][3] == "ours"


def test_iter_changes_rejects_non_hex_site(tmp_path: Path):
    conn = _fake_crsql_changes_db(tmp_path)
    with pytest.raises(ValueError, match="hex"):
        list(iter_changes_for_peer(conn, since=0, exclude_site_hex="not-hex"))


# ---------------------------------------------------------------------
# End-to-end HTTP round-trip
# ---------------------------------------------------------------------


def _pick_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_pull_from_peer_returns_rows_end_to_end(tmp_path: Path):
    """Spin up the real server on localhost, GET it from the real
    client, verify what comes back matches what went in."""
    server_db = _fake_crsql_changes_db(tmp_path)
    server_db.execute(
        "INSERT INTO crsql_changes VALUES "
        "('t', ?, 'note', 'from peer', 1, 1, ?, 1, 0)",
        (b"\x01\x02", b"\xbb" * 16),
    )

    def _factory():
        return sqlite3.connect(tmp_path / "fake.db")

    port = _pick_free_port()
    server = make_server(conn_factory=_factory, port=port, host="127.0.0.1")
    thread = serve_forever_in_thread(server)
    try:
        rows = pull_from_peer(
            peer_host="127.0.0.1",
            port=port,
            since=0,
            exclude_site_hex="aa" * 16,  # not the server's site
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert len(rows) == 1
    assert rows[0][0] == "t"
    assert rows[0][3] == "from peer"
    # The blob columns round-tripped.
    assert rows[0][1] == b"\x01\x02"
    assert rows[0][6] == b"\xbb" * 16


def test_pull_from_peer_empty_batch_is_empty_list(tmp_path: Path):
    server_db = _fake_crsql_changes_db(tmp_path)
    server_db.execute(
        "INSERT INTO crsql_changes VALUES "
        "('t', ?, 'note', 'old', 1, 1, ?, 1, 0)",
        (b"\x01", b"\xbb" * 16),
    )

    def _factory():
        return sqlite3.connect(tmp_path / "fake.db")

    port = _pick_free_port()
    server = make_server(conn_factory=_factory, port=port, host="127.0.0.1")
    thread = serve_forever_in_thread(server)
    try:
        rows = pull_from_peer(
            peer_host="127.0.0.1", port=port, since=1,  # past the row
            exclude_site_hex="aa" * 16,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert rows == []


def test_server_rejects_missing_query_params(tmp_path: Path):
    def _factory():
        conn = sqlite3.connect(":memory:")
        return conn

    port = _pick_free_port()
    server = make_server(conn_factory=_factory, port=port, host="127.0.0.1")
    thread = serve_forever_in_thread(server)
    try:
        import urllib.request, urllib.error
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/crsql/changes"  # no query string
        )
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(req, timeout=2)
        assert ei.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_404s_on_wrong_path(tmp_path: Path):
    def _factory():
        return sqlite3.connect(":memory:")

    port = _pick_free_port()
    server = make_server(conn_factory=_factory, port=port, host="127.0.0.1")
    thread = serve_forever_in_thread(server)
    try:
        import urllib.request, urllib.error
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/nope", timeout=2
            )
        assert ei.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------
# apply_changes transaction behavior
# ---------------------------------------------------------------------


def test_apply_changes_empty_list_is_noop(tmp_path: Path):
    conn = _fake_crsql_changes_db(tmp_path)
    assert apply_changes(conn, []) == 0


def test_apply_changes_writes_rows_to_crsql_changes(tmp_path: Path):
    conn = _fake_crsql_changes_db(tmp_path)
    rows = [
        ("t", b"\x01", "note", "a", 1, 1, b"\xbb" * 16, 1, 0),
        ("t", b"\x02", "note", "b", 1, 2, b"\xbb" * 16, 1, 0),
    ]
    assert apply_changes(conn, rows) == 2
    count = conn.execute("SELECT COUNT(*) FROM crsql_changes").fetchone()[0]
    assert count == 2


def test_apply_changes_rolls_back_on_failure(tmp_path: Path):
    """If one row in the batch fails, the whole batch is discarded —
    no partial writes. Re-pulling will retry the full batch."""
    conn = _fake_crsql_changes_db(tmp_path)
    # Replace with a shape that enforces a check we can violate. Use
    # `cid` for the check so we don't have to escape the `table`
    # reserved word inside the constraint expression.
    conn.execute("DROP TABLE crsql_changes")
    conn.execute(
        'CREATE TABLE crsql_changes ('
        '"table" TEXT, pk BLOB, cid TEXT CHECK (cid != "forbidden"), '
        'val, col_version INTEGER, db_version INTEGER, '
        'site_id BLOB, cl INTEGER, seq INTEGER)'
    )

    rows = [
        ("t", b"\x01", "ok",        "a", 1, 1, b"\x00" * 16, 1, 0),
        ("t", b"\x02", "forbidden", "b", 1, 2, b"\x00" * 16, 1, 0),
    ]
    with pytest.raises(sqlite3.IntegrityError):
        apply_changes(conn, rows)
    # Neither row committed.
    count = conn.execute("SELECT COUNT(*) FROM crsql_changes").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------
# Watermark persistence
# ---------------------------------------------------------------------


def _metadata_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "m.db", isolation_level=None)
    conn.execute(
        "CREATE TABLE _metadata ("
        "key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    return conn


def test_watermark_defaults_to_zero(tmp_path: Path):
    conn = _metadata_db(tmp_path)
    assert watermark_for(conn, "peer-a") == 0


def test_watermark_returns_zero_when_metadata_missing():
    conn = sqlite3.connect(":memory:")
    assert watermark_for(conn, "peer-a") == 0


def test_watermark_round_trip(tmp_path: Path):
    conn = _metadata_db(tmp_path)
    set_watermark(conn, "peer-a", 42)
    assert watermark_for(conn, "peer-a") == 42


def test_watermark_is_peer_specific(tmp_path: Path):
    conn = _metadata_db(tmp_path)
    set_watermark(conn, "peer-a", 10)
    set_watermark(conn, "peer-b", 20)
    assert watermark_for(conn, "peer-a") == 10
    assert watermark_for(conn, "peer-b") == 20


def test_watermark_is_case_insensitive_on_site_hex(tmp_path: Path):
    """Site hex is sometimes upper, sometimes lower depending on source
    (hex() is uppercase, our code lowercases). The watermark must be
    keyed consistently so we don't track the same peer twice."""
    conn = _metadata_db(tmp_path)
    set_watermark(conn, "ABCDEF", 5)
    assert watermark_for(conn, "abcdef") == 5


def test_watermark_handles_corrupt_value(tmp_path: Path):
    conn = _metadata_db(tmp_path)
    conn.execute(
        "INSERT INTO _metadata (key, value, created_at) "
        "VALUES ('sync.peer_watermark.abc', 'not-an-int', '2026-04-19')"
    )
    # Defaults to 0 rather than crashing — a corrupt watermark shouldn't
    # brick the daemon loop.
    assert watermark_for(conn, "abc") == 0


# ---------------------------------------------------------------------
# _sync_round — the daemon's per-round function
# ---------------------------------------------------------------------


def _sync_round_fixture(tmp_path: Path):
    """Build a fixture: server DB with 2 fake changeset rows on a
    populated 'peer' site; client DB with _metadata + crsql_changes
    shape ready to receive. Returns (client_conn, port, thread, srv).
    Caller is responsible for ``srv.shutdown()`` + thread.join."""
    # Server side — populated "peer".
    server_db_path = tmp_path / "server.db"
    s = sqlite3.connect(server_db_path, isolation_level=None)
    s.execute(
        'CREATE TABLE crsql_changes ('
        '"table" TEXT, pk BLOB, cid TEXT, val, '
        'col_version INTEGER, db_version INTEGER, '
        'site_id BLOB, cl INTEGER, seq INTEGER)'
    )
    peer_site = b"\xbb" * 16
    s.execute(
        'INSERT INTO crsql_changes VALUES '
        "('t', ?, 'note', 'row1', 1, 7, ?, 1, 0)",
        (b"\x01", peer_site),
    )
    s.execute(
        'INSERT INTO crsql_changes VALUES '
        "('t', ?, 'note', 'row2', 1, 9, ?, 1, 0)",
        (b"\x02", peer_site),
    )
    s.close()

    # Client side — empty _metadata + empty crsql_changes.
    client_db_path = tmp_path / "client.db"
    c = sqlite3.connect(client_db_path, isolation_level=None)
    c.execute(
        "CREATE TABLE _metadata (key TEXT PRIMARY KEY, "
        "value TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    c.execute(
        'CREATE TABLE crsql_changes ('
        '"table" TEXT, pk BLOB, cid TEXT, val, '
        'col_version INTEGER, db_version INTEGER, '
        'site_id BLOB, cl INTEGER, seq INTEGER)'
    )

    port = _pick_free_port()
    srv = make_server(
        conn_factory=lambda: sqlite3.connect(server_db_path),
        port=port,
        host="127.0.0.1",
    )
    thread = serve_forever_in_thread(srv)
    return c, port, thread, srv


def test_sync_round_writes_host_and_site_watermarks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """After a non-empty round both the host: and site: keys are
    written to _metadata. Pins the migration path — previously untested."""
    from db import sync_daemon

    monkeypatch.setattr(
        sync_daemon, "_get_local_site_hex", lambda conn: "aa" * 16
    )

    c, port, thread, srv = _sync_round_fixture(tmp_path)
    try:
        sync_daemon._sync_round(c, peer_host="127.0.0.1", port=port)
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)
        c.close()

    # Reopen to verify watermark persistence.
    c = sqlite3.connect(tmp_path / "client.db")
    kv = dict(c.execute(
        "SELECT key, value FROM _metadata WHERE key LIKE 'sync.peer_watermark.%'"
    ).fetchall())
    c.close()

    assert "sync.peer_watermark.host:127.0.0.1" in kv
    assert "sync.peer_watermark.site:" + "bb" * 16 in kv
    assert kv["sync.peer_watermark.host:127.0.0.1"] == "9"
    assert kv["sync.peer_watermark.site:" + "bb" * 16] == "9"


def test_sync_round_empty_batch_does_not_advance_watermark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """If the peer has no new rows (since >= max db_version), the
    watermark stays put — re-pulling with the same since is the
    correct next-round behavior."""
    from db import sync_daemon

    monkeypatch.setattr(
        sync_daemon, "_get_local_site_hex", lambda conn: "aa" * 16
    )

    c, port, thread, srv = _sync_round_fixture(tmp_path)
    try:
        # Pre-seed the watermark past the server's max db_version (9).
        set_watermark(c, "host:127.0.0.1", 99)
        sync_daemon._sync_round(c, peer_host="127.0.0.1", port=port)
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)

    # Watermark unchanged, client's crsql_changes still empty.
    assert watermark_for(c, "host:127.0.0.1") == 99
    applied_count = c.execute(
        "SELECT COUNT(*) FROM crsql_changes"
    ).fetchone()[0]
    assert applied_count == 0
    c.close()


def test_sync_round_applies_peer_rows_to_local_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """After a non-empty round the client's crsql_changes table
    contains the peer's rows — the ⛔ §2.4 bootstrap gate semantic
    (empty peer RECEIVES, populated peer UNCHANGED) at the
    transport layer."""
    from db import sync_daemon

    monkeypatch.setattr(
        sync_daemon, "_get_local_site_hex", lambda conn: "aa" * 16
    )

    c, port, thread, srv = _sync_round_fixture(tmp_path)
    try:
        sync_daemon._sync_round(c, peer_host="127.0.0.1", port=port)
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)

    applied = c.execute(
        'SELECT val, db_version FROM crsql_changes ORDER BY db_version'
    ).fetchall()
    c.close()
    assert applied == [("row1", 7), ("row2", 9)]


def test_get_local_site_hex_raises_when_site_id_missing():
    """If crsql_site_id() returns None (extension not loaded), the
    helper must raise — continuing would pass NULL/"" to the peer's
    exclude_site param and the peer would echo our own rows back."""
    from db.sync_daemon import _get_local_site_hex

    class _NoSite:
        def execute(self, _sql):
            class _R:
                def fetchone(_self):
                    return None
            return _R()

    with pytest.raises(RuntimeError, match="crsql_site_id"):
        _get_local_site_hex(_NoSite())  # type: ignore[arg-type]
