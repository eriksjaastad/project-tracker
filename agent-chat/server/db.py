"""
Agent Chat database layer.

PostgreSQL via psycopg2 (Cloud Run) or SQLite (local dev).
Same dual-backend pattern as the cost tracker.
"""

import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sender TEXT NOT NULL,
    recipient TEXT,
    reply_to INTEGER REFERENCES messages(id),
    body TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',
    metadata JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient);
CREATE INDEX IF NOT EXISTS idx_messages_reply_to ON messages(reply_to);
"""

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    sender TEXT NOT NULL,
    recipient TEXT,
    reply_to INTEGER REFERENCES messages(id),
    body TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',
    metadata TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient);
CREATE INDEX IF NOT EXISTS idx_messages_reply_to ON messages(reply_to);
"""


class DatabaseConfigError(RuntimeError):
    """No durable database is configured and nobody opted into the local one.

    Raised instead of quietly falling back to an on-disk SQLite file. In Cloud
    Run that file lives on an ephemeral container filesystem, so the fallback
    produced a service that starts, passes /health, accepts writes and returns
    200s while every message vanishes with the container. The symptom is the
    ABSENCE of messages, which is invisible by construction -- agents simply
    stop receiving DMs and nothing reports why.
    """


def _get_database_url() -> Optional[str]:
    return os.environ.get("AGENT_CHAT_DATABASE_URL")


def _use_postgres() -> bool:
    return HAS_PSYCOPG2 and _get_database_url() is not None


def _sqlite_fallback_allowed() -> bool:
    """True only for an affirmative opt-in.

    Deliberately not `bool(os.environ.get(...))`: treating any non-empty value
    as consent would make `AGENT_CHAT_ALLOW_SQLITE=0` mean yes, which is the
    kind of guard that reads as protection and isn't one.
    """
    return os.environ.get("AGENT_CHAT_ALLOW_SQLITE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def describe_backend() -> str:
    """Which store this process is actually using: 'postgres' or 'sqlite'.

    Surfaced on /health for the same reason `version` is: a durable-storage
    failure here is invisible from the outside, because the service answers
    200 either way. Reports the kind only -- never the URL or credentials.
    """
    return "postgres" if _use_postgres() else "sqlite"


def _fallback_sqlite_path() -> str:
    """Path of the local dev database. Separate function so tests can redirect it."""
    from pathlib import Path

    return str(Path(__file__).parent.parent / "chat_dev.db")


@contextmanager
def get_connection(sqlite_path: Optional[str] = None):
    if sqlite_path:
        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
        finally:
            conn.close()
    elif _use_postgres():
        conn = psycopg2.connect(_get_database_url())
        try:
            yield conn
        finally:
            conn.close()
    else:
        url = _get_database_url()
        if url is not None and not HAS_PSYCOPG2:
            # A configured URL we cannot honour is a broken image, not a reason
            # to downgrade storage. This was the nastier half of the bug: the
            # URL was right there and the old code ignored it.
            raise DatabaseConfigError(
                "AGENT_CHAT_DATABASE_URL is set but psycopg2 is not importable, so the "
                "Postgres backend cannot be used. Refusing to fall back to a local "
                "SQLite file, which is ephemeral in Cloud Run and would silently drop "
                "every message. Install psycopg2-binary in the image."
            )
        if url is None and not _sqlite_fallback_allowed():
            raise DatabaseConfigError(
                "AGENT_CHAT_DATABASE_URL is not set. Refusing to fall back to a local "
                "SQLite file: in Cloud Run that filesystem is ephemeral, so the service "
                "would start, pass /health, accept writes and return 200s while every "
                "message vanished with the container. "
                "Set AGENT_CHAT_DATABASE_URL (Doppler project 'agent-chat', config "
                "'prd'), or set AGENT_CHAT_ALLOW_SQLITE=1 to deliberately use the local "
                "development database."
            )
        db_path = _fallback_sqlite_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
        finally:
            conn.close()


def init_db(sqlite_path: Optional[str] = None) -> None:
    with get_connection(sqlite_path) as conn:
        if _use_postgres() and not sqlite_path:
            cursor = conn.cursor()
            for statement in PG_SCHEMA.split(";"):
                statement = statement.strip()
                if statement:
                    try:
                        cursor.execute(statement)
                        conn.commit()
                    except Exception as e:
                        logger.warning("Schema statement failed (rolled back): %s — %s", statement[:80], e)
                        conn.rollback()
            # Migrations: add columns that may not exist on older schemas
            for migration in [
                "ALTER TABLE messages ADD COLUMN IF NOT EXISTS recipient TEXT",
                "ALTER TABLE messages ADD COLUMN IF NOT EXISTS reply_to INTEGER REFERENCES messages(id)",
                "CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient)",
                "CREATE INDEX IF NOT EXISTS idx_messages_reply_to ON messages(reply_to)",
            ]:
                try:
                    cursor.execute(migration)
                    conn.commit()
                except Exception as e:
                    logger.warning("Migration failed (rolled back): %s — %s", migration[:80], e)
                    conn.rollback()
        else:
            conn.executescript(SQLITE_SCHEMA)


def _is_sqlite(conn) -> bool:
    return isinstance(conn, sqlite3.Connection)


def _p(conn) -> str:
    return "?" if _is_sqlite(conn) else "%s"


def insert_message(conn, *, sender: str, body: str, recipient: Optional[str] = None,
                   reply_to: Optional[int] = None,
                   priority: str = "normal", metadata: str = "{}") -> dict:
    p = _p(conn)
    if _is_sqlite(conn):
        cursor = conn.execute(
            f"INSERT INTO messages (sender, recipient, reply_to, body, priority, metadata) VALUES ({p}, {p}, {p}, {p}, {p}, {p})",
            (sender, recipient, reply_to, body, priority, metadata),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    else:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            f"INSERT INTO messages (sender, recipient, reply_to, body, priority, metadata) VALUES ({p}, {p}, {p}, {p}, {p}, {p}::jsonb) RETURNING *",
            (sender, recipient, reply_to, body, priority, metadata),
        )
        row = cursor.fetchone()
        conn.commit()
        return dict(row)


def query_messages(conn, *, since: Optional[str] = None,
                   sender: Optional[str] = None, for_recipient: Optional[str] = None,
                   limit: int = 50, newest_first: bool = False,
                   for_machine: Optional[str] = None) -> list[dict]:
    """Query messages.

    `newest_first` controls WHICH rows the LIMIT selects, not just their order:
    ascending returns the OLDEST `limit` rows, which is why the default client
    view was frozen on the first messages ever sent while newer ones existed.
    Callers wanting "the latest N" must pass newest_first=True.
    """
    p = _p(conn)
    clauses = []
    params = []

    if since:
        clauses.append(f"ts > {p}")
        params.append(since)
    if sender:
        clauses.append(f"sender = {p}")
        params.append(sender)
    if for_recipient:
        # Broadcasts (recipient IS NULL) + mail addressed to this agent.
        # An agent answers to its bare project address AND, when it declares a
        # machine, to `project@machine` — Erik's ruling 2026-08-30: project
        # address by default, optional qualifier when two machines share a
        # project. Without this branch a DM to `ai-memory@mini` is stored but
        # matches nobody, which is the silent-non-delivery bug all over again.
        if for_machine:
            clauses.append(f"(recipient IS NULL OR recipient = {p} OR recipient = {p})")
            params.append(for_recipient)
            params.append(f"{for_recipient}@{for_machine}")
        else:
            clauses.append(f"(recipient IS NULL OR recipient = {p})")
            params.append(for_recipient)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    direction = "DESC" if newest_first else "ASC"
    sql = f"SELECT * FROM messages {where} ORDER BY ts {direction} LIMIT {p}"
    params.append(limit)

    if _is_sqlite(conn):
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    else:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
