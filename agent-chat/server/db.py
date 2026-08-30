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


def _get_database_url() -> Optional[str]:
    return os.environ.get("AGENT_CHAT_DATABASE_URL")


def _use_postgres() -> bool:
    return HAS_PSYCOPG2 and _get_database_url() is not None


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
        from pathlib import Path
        db_path = str(Path(__file__).parent.parent / "chat_dev.db")
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
