"""Tests for agent-chat server message matching.

Two defects live here. `ORDER BY ts ASC LIMIT n` returned the OLDEST n, which
froze every client's default view on the first messages ever sent. And exact
recipient matching meant a DM to `ai-memory@mini` was stored but matched
nobody — the same silent-non-delivery this card exists to remove.
"""

import importlib.util
from pathlib import Path

import pytest

# Load by file path, NOT via sys.path: agent-chat/server/db.py would otherwise
# shadow the project's own `db` package that scripts/pt.py imports.
_DB_PATH = Path(__file__).resolve().parent.parent / "agent-chat" / "server" / "db.py"
_spec = importlib.util.spec_from_file_location("agent_chat_server_db", _DB_PATH)
chatdb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chatdb)


@pytest.fixture
def conn(tmp_path):
    path = str(tmp_path / "chat.db")
    chatdb.init_db(path)
    with chatdb.get_connection(path) as c:
        yield c


def bodies(rows):
    return [r["body"] for r in rows]


class TestRecipientMatching:
    def _seed(self, conn):
        for body, rcpt in [
            ("bare", "ai-memory"),
            ("qualified", "ai-memory@mini"),
            ("other-machine", "ai-memory@laptop"),
            ("someone-else", "project-tracker"),
            ("broadcast", None),
        ]:
            chatdb.insert_message(conn, sender="a", body=body, recipient=rcpt)

    def test_bare_address_gets_its_mail_and_broadcasts(self, conn):
        self._seed(conn)
        got = bodies(chatdb.query_messages(conn, for_recipient="ai-memory"))
        assert "bare" in got and "broadcast" in got

    def test_bare_address_does_not_receive_another_agents_mail(self, conn):
        self._seed(conn)
        assert "someone-else" not in bodies(
            chatdb.query_messages(conn, for_recipient="ai-memory")
        )

    def test_qualified_dm_reaches_the_machine_it_names(self, conn):
        """Without this, `--to ai-memory@mini` is stored and matches nobody."""
        self._seed(conn)
        got = bodies(chatdb.query_messages(conn, for_recipient="ai-memory", for_machine="mini"))
        assert "qualified" in got

    def test_qualified_dm_does_not_reach_a_different_machine(self, conn):
        self._seed(conn)
        got = bodies(chatdb.query_messages(conn, for_recipient="ai-memory", for_machine="mini"))
        assert "other-machine" not in got

    def test_unqualified_session_does_not_absorb_qualified_mail(self, conn):
        """A laptop FM must not swallow mail addressed specifically to the Mini."""
        self._seed(conn)
        got = bodies(chatdb.query_messages(conn, for_recipient="ai-memory"))
        assert "qualified" not in got


class TestOrdering:
    def _seed(self, conn, n=5):
        for i in range(1, n + 1):
            chatdb.insert_message(conn, sender="a", body=f"m{i}", recipient=None)

    def test_default_returns_oldest_preserving_legacy_behaviour(self, conn):
        self._seed(conn)
        assert bodies(chatdb.query_messages(conn, limit=2)) == ["m1", "m2"]

    def test_newest_first_selects_the_latest_rows(self, conn):
        """The fix: ordering decides WHICH rows the limit takes, not just order."""
        self._seed(conn)
        got = bodies(chatdb.query_messages(conn, limit=2, newest_first=True))
        assert set(got) == {"m4", "m5"}
