"""Agent Chat must refuse to run on a database that silently loses messages.

`get_connection()` used to fall through to a local `chat_dev.db` whenever
`AGENT_CHAT_DATABASE_URL` was absent. In Cloud Run the container filesystem is
ephemeral, so that produced a service which starts, passes /health, accepts
writes and returns 200s while every message vanishes with the container. No
error, no log line, no alert -- and because the symptom is the ABSENCE of
messages, nobody notices until someone asks why an agent stopped replying.

Portfolio rule (root CLAUDE.md): a missing secret must crash the app, not
silently stub it. These tests pin that behaviour.
"""

import importlib.util
from pathlib import Path

import pytest

# Load by file path, NOT via sys.path: agent-chat/server/db.py would otherwise
# shadow the project's own `db` package that scripts/pt.py imports.
_DB_PATH = Path(__file__).resolve().parent.parent / "agent-chat" / "server" / "db.py"
_spec = importlib.util.spec_from_file_location("agent_chat_db_config", _DB_PATH)
chatdb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chatdb)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Every test states its own config; never inherit the developer's shell."""
    monkeypatch.delenv("AGENT_CHAT_DATABASE_URL", raising=False)
    monkeypatch.delenv("AGENT_CHAT_ALLOW_SQLITE", raising=False)


def test_missing_database_url_raises_instead_of_silently_using_local_sqlite():
    """The Cloud Run failure mode: env var lost, service happily writes to /tmp."""
    with pytest.raises(chatdb.DatabaseConfigError) as exc:
        with chatdb.get_connection():
            pass
    msg = str(exc.value)
    assert "AGENT_CHAT_DATABASE_URL" in msg, "error must name the missing variable"
    assert "AGENT_CHAT_ALLOW_SQLITE" in msg, "error must name the local-dev opt-in"


def test_database_url_set_but_driver_missing_raises(monkeypatch):
    """A configured URL we cannot honour is a broken deploy, not a reason to downgrade.

    This was the nastier half: the URL is right there and the old code ignored
    it, falling back to ephemeral SQLite because psycopg2 failed to import.
    """
    monkeypatch.setenv("AGENT_CHAT_DATABASE_URL", "postgresql://example/db")
    monkeypatch.setattr(chatdb, "HAS_PSYCOPG2", False)
    with pytest.raises(chatdb.DatabaseConfigError) as exc:
        with chatdb.get_connection():
            pass
    assert "psycopg2" in str(exc.value)


def test_explicit_sqlite_path_still_works(tmp_path):
    """Passing a path is an explicit choice -- tests and local tools rely on it."""
    path = str(tmp_path / "chat.db")
    chatdb.init_db(path)
    with chatdb.get_connection(path) as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_local_dev_opt_in_allows_sqlite_fallback(monkeypatch, tmp_path):
    """Local dev keeps working, but only by saying so out loud."""
    monkeypatch.setenv("AGENT_CHAT_ALLOW_SQLITE", "1")
    monkeypatch.setattr(chatdb, "_fallback_sqlite_path", lambda: str(tmp_path / "dev.db"))
    with chatdb.get_connection() as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


@pytest.mark.parametrize("value", ["0", "false", "no", "", "  "])
def test_opt_in_must_be_affirmative(monkeypatch, value):
    """A guard that treats any non-empty value as consent is not a guard."""
    monkeypatch.setenv("AGENT_CHAT_ALLOW_SQLITE", value)
    with pytest.raises(chatdb.DatabaseConfigError):
        with chatdb.get_connection():
            pass


def test_describe_backend_reports_sqlite_when_no_postgres():
    """/health must be able to say which store it is actually on.

    A durable-storage failure answers 200 exactly like a healthy service, so
    "which backend?" has to be answerable with a plain curl -- the same
    argument that put `version` on this endpoint.
    """
    assert chatdb.describe_backend() == "sqlite"


def test_describe_backend_reports_postgres_when_configured(monkeypatch):
    monkeypatch.setenv("AGENT_CHAT_DATABASE_URL", "postgresql://example/db")
    monkeypatch.setattr(chatdb, "HAS_PSYCOPG2", True)
    assert chatdb.describe_backend() == "postgres"


def test_describe_backend_never_leaks_the_url(monkeypatch):
    """Kind only. The URL carries credentials and /health is unauthenticated."""
    monkeypatch.setenv("AGENT_CHAT_DATABASE_URL", "postgresql://user:secret@host/db")
    monkeypatch.setattr(chatdb, "HAS_PSYCOPG2", True)
    reported = chatdb.describe_backend()
    assert "secret" not in reported and "host" not in reported
    assert reported == "postgres"
