"""Tests for pt message subcommands (Agent Chat integration)."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

# Import the CLI and helpers
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import pt
from pt import cli, _load_chat_config, _format_message_line


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_env_file(tmp_path):
    """Create a fake agent-chat.env config file."""
    env_file = tmp_path / "agent-chat.env"
    env_file.write_text(
        "AGENT_CHAT_URL=https://fake-chat.example.com\n"
        "AGENT_CHAT_API_KEY=test-key-123\n"
        "AGENT_CHAT_SENDER=test-agent\n"
    )
    return env_file


class TestLoadChatConfig:
    def test_loads_from_env_file(self, fake_env_file):
        with patch.object(Path, "home", return_value=fake_env_file.parent.parent):
            # Create the expected path structure
            claude_dir = fake_env_file.parent.parent / ".claude"
            claude_dir.mkdir(exist_ok=True)
            target = claude_dir / "agent-chat.env"
            target.write_text(fake_env_file.read_text())

            config = _load_chat_config()
            assert config["url"] == "https://fake-chat.example.com"
            assert config["key"] == "test-key-123"
            assert config["sender"] == "test-agent"

    def test_raises_without_config(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path), \
             patch.dict(os.environ, {}, clear=True):
            with pytest.raises(Exception, match="Agent Chat not configured"):
                _load_chat_config()

    def test_env_vars_work_as_fallback(self, tmp_path):
        env = {
            "AGENT_CHAT_URL": "https://env-chat.example.com",
            "AGENT_CHAT_API_KEY": "env-key",
            "AGENT_CHAT_SENDER": "env-sender",
        }
        with patch.object(Path, "home", return_value=tmp_path), \
             patch.dict(os.environ, env, clear=True):
            config = _load_chat_config()
            assert config["url"] == "https://env-chat.example.com"
            assert config["key"] == "env-key"


class TestFormatMessageLine:
    def test_basic_message(self):
        msg = {
            "id": 1,
            "ts": "2026-04-03T10:00:00Z",
            "sender": "erik",
            "recipient": None,
            "priority": "normal",
            "body": "Hello world",
            "reply_to": None,
        }
        line = _format_message_line(msg)
        assert "#1" in line
        assert "erik" in line
        assert "Hello world" in line
        assert "normal" in line

    def test_directed_message(self):
        msg = {
            "id": 5,
            "ts": "2026-04-03T10:00:00Z",
            "sender": "erik",
            "recipient": "mini-claude",
            "priority": "high",
            "body": "Check this",
            "reply_to": None,
        }
        line = _format_message_line(msg)
        assert "erik -> mini-claude" in line
        assert "high" in line

    def test_reply_message(self):
        msg = {
            "id": 10,
            "ts": "2026-04-03T10:00:00Z",
            "sender": "claude-architect",
            "recipient": None,
            "priority": "normal",
            "body": "Got it",
            "reply_to": 5,
        }
        line = _format_message_line(msg)
        assert "(reply to #5)" in line

    def test_body_truncation(self):
        msg = {
            "id": 1,
            "ts": "2026-04-03T10:00:00Z",
            "sender": "erik",
            "recipient": None,
            "priority": "normal",
            "body": "A" * 200,
            "reply_to": None,
        }
        line = _format_message_line(msg)
        # Body should be truncated to 80 chars
        assert len(line.split("|")[-1].strip()) <= 80


class TestMessageList:
    def test_list_json_output(self, runner):
        mock_response = {
            "messages": [
                {"id": 1, "ts": "2026-04-03T10:00:00Z", "sender": "erik",
                 "recipient": None, "body": "test", "priority": "normal", "reply_to": None}
            ]
        }
        with patch("pt._load_chat_config", return_value={"url": "http://x", "key": "k", "sender": "s"}), \
             patch("pt._chat_api_request", return_value=mock_response):
            result = runner.invoke(cli, ["message", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["messages"][0]["sender"] == "erik"

    def test_list_plain_output(self, runner):
        mock_response = {
            "messages": [
                {"id": 1, "ts": "2026-04-03T10:00:00Z", "sender": "erik",
                 "recipient": None, "body": "Hello", "priority": "normal", "reply_to": None}
            ]
        }
        with patch("pt._load_chat_config", return_value={"url": "http://x", "key": "k", "sender": "s"}), \
             patch("pt._chat_api_request", return_value=mock_response):
            result = runner.invoke(cli, ["message", "list"])
            assert result.exit_code == 0
            assert "#1" in result.output
            assert "erik" in result.output

    def test_list_empty(self, runner):
        with patch("pt._load_chat_config", return_value={"url": "http://x", "key": "k", "sender": "s"}), \
             patch("pt._chat_api_request", return_value={"messages": []}):
            result = runner.invoke(cli, ["message", "list"])
            assert "No messages found" in result.output


@pytest.fixture(autouse=True)
def isolate_chat_identity(tmp_path, monkeypatch):
    """Keep chat tests off the real machine's session identity.

    `pt message` resolves its sender from the session identity written at
    SessionStart. Without isolation these tests read the identity of whatever
    session is running them, so they pass on one machine and fail on another.
    """
    monkeypatch.setenv("AGENT_CHAT_STATE_DIR", str(tmp_path / "identity"))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.delenv("AGENT_CHAT_SENDER", raising=False)
    # Also keep them off the real kanban DB, which recipient validation reads.
    # Empty set means "cannot verify", so sends are not blocked by isolation.
    monkeypatch.setattr(pt, "_known_chat_addresses", lambda: set())


class TestMessageSend:
    def test_send_basic(self, runner):
        with patch("pt._load_chat_config", return_value={"url": "http://x", "key": "k", "sender": "test-agent"}), \
             patch("pt._chat_api_request", return_value={"id": 42}) as mock_req:
            result = runner.invoke(cli, ["message", "send", "Hello world"])
            assert result.exit_code == 0
            assert "Sent #42" in result.output
            call_data = mock_req.call_args[1]["data"]
            assert call_data["sender"] == "test-agent"
            assert call_data["body"] == "Hello world"

    def test_send_with_recipient(self, runner):
        with patch("pt._load_chat_config", return_value={"url": "http://x", "key": "k", "sender": "test-agent"}), \
             patch("pt._chat_api_request", return_value={"id": 43}) as mock_req:
            result = runner.invoke(cli, ["message", "send", "Check this", "--to", "mini-claude"])
            assert result.exit_code == 0
            call_data = mock_req.call_args[1]["data"]
            assert call_data["to"] == "mini-claude"

    def test_send_with_priority_and_reply(self, runner):
        with patch("pt._load_chat_config", return_value={"url": "http://x", "key": "k", "sender": "test-agent"}), \
             patch("pt._chat_api_request", return_value={"id": 44}) as mock_req:
            result = runner.invoke(cli, ["message", "send", "Ack", "--priority", "high", "--reply-to", "10"])
            assert result.exit_code == 0
            call_data = mock_req.call_args[1]["data"]
            assert call_data["priority"] == "high"
            assert call_data["reply_to"] == 10

    def test_send_json_output(self, runner):
        with patch("pt._load_chat_config", return_value={"url": "http://x", "key": "k", "sender": "test-agent"}), \
             patch("pt._chat_api_request", return_value={"id": 45, "ts": "2026-04-03T10:00:00Z"}):
            result = runner.invoke(cli, ["message", "send", "Hello", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["id"] == 45


class TestInboxSemantics:
    """#6772 — list defaults to your inbox, newest first.

    The old default returned the OLDEST N messages across the whole board, so
    the view was permanently frozen on 2026-04-02 while #91 arrived in August.
    """

    def _identity(self, tmp_path, monkeypatch, address):
        state = tmp_path / "identity"
        state.mkdir(parents=True, exist_ok=True)
        (state / "sess.txt").write_text(address)
        monkeypatch.setenv("AGENT_CHAT_STATE_DIR", str(state))
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess")

    def test_defaults_to_own_inbox(self, runner, tmp_path, monkeypatch):
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._chat_api_request", return_value={"messages": [], "order": "desc"}) as req:
            runner.invoke(cli, ["message", "list"])

        assert req.call_args[1]["params"]["for"] == "project-tracker"

    def test_all_flag_shows_whole_board(self, runner, tmp_path, monkeypatch):
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._chat_api_request", return_value={"messages": [], "order": "desc"}) as req:
            runner.invoke(cli, ["message", "list", "--all"])

        assert "for" not in req.call_args[1]["params"]

    def test_requests_newest_rows_from_server(self, runner, tmp_path, monkeypatch):
        """order=desc selects WHICH rows the limit takes, not just their order."""
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._chat_api_request", return_value={"messages": [], "order": "desc"}) as req:
            runner.invoke(cli, ["message", "list"])

        assert req.call_args[1]["params"]["order"] == "desc"

    def test_displays_newest_first(self, runner, tmp_path, monkeypatch):
        self._identity(tmp_path, monkeypatch, "project-tracker")
        msgs = [
            {"id": 1, "sender": "a", "body": "old", "ts": "2026-04-02T00:00:00Z", "priority": "normal"},
            {"id": 91, "sender": "b", "body": "new", "ts": "2026-08-30T00:00:00Z", "priority": "normal"},
        ]
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._chat_api_request", return_value={"messages": msgs, "order": "desc"}):
            result = runner.invoke(cli, ["message", "list"])

        assert result.output.index("#91") < result.output.index("#1")

    def test_oldest_first_flag_restores_chronological(self, runner, tmp_path, monkeypatch):
        self._identity(tmp_path, monkeypatch, "project-tracker")
        msgs = [
            {"id": 1, "sender": "a", "body": "old", "ts": "2026-04-02T00:00:00Z", "priority": "normal"},
            {"id": 91, "sender": "b", "body": "new", "ts": "2026-08-30T00:00:00Z", "priority": "normal"},
        ]
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._chat_api_request", return_value={"messages": msgs, "order": "desc"}):
            result = runner.invoke(cli, ["message", "list", "--oldest-first"])

        assert result.output.index("#1") < result.output.index("#91")

    def test_recovers_when_server_ignores_order(self, runner, tmp_path, monkeypatch):
        """The deployed server predates `order`; the client must still be right.

        An old deployment returns the oldest page and no `order` key. Reversing
        that page would reorder the WRONG rows, so the client refetches wider
        and takes the tail.
        """
        self._identity(tmp_path, monkeypatch, "project-tracker")
        oldest_page = [
            {"id": i, "sender": "a", "body": "x", "ts": f"2026-04-0{i}T00:00:00Z", "priority": "normal"}
            for i in (1, 2)
        ]
        wide = oldest_page + [
            {"id": 90, "sender": "b", "body": "y", "ts": "2026-08-29T00:00:00Z", "priority": "normal"},
            {"id": 91, "sender": "b", "body": "z", "ts": "2026-08-30T00:00:00Z", "priority": "normal"},
        ]
        responses = [{"messages": oldest_page}, {"messages": wide}]
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._chat_api_request", side_effect=responses):
            result = runner.invoke(cli, ["message", "list", "--limit", "2"])

        # Shows the newest two, not the oldest two.
        assert "#91" in result.output and "#90" in result.output
        assert "#1" not in result.output


class TestSelfSendGuard:
    """Sending to your own address used to succeed silently and go nowhere."""

    def _identity(self, tmp_path, monkeypatch, address):
        state = tmp_path / "identity"
        state.mkdir(parents=True, exist_ok=True)
        (state / "sess.txt").write_text(address)
        monkeypatch.setenv("AGENT_CHAT_STATE_DIR", str(state))
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess")

    def test_send_to_self_is_refused(self, runner, tmp_path, monkeypatch):
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._chat_api_request", return_value={"id": 1}) as req:
            result = runner.invoke(cli, ["message", "send", "hi", "--to", "project-tracker"])

        assert result.exit_code != 0
        assert "own address" in result.output
        req.assert_not_called()

    def test_send_to_peer_is_allowed(self, runner, tmp_path, monkeypatch):
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._chat_api_request", return_value={"id": 1}) as req:
            result = runner.invoke(cli, ["message", "send", "hi", "--to", "ai-memory"])

        assert result.exit_code == 0
        assert req.call_args[1]["data"]["sender"] == "project-tracker"

    def test_session_identity_beats_machine_global_config(self, runner, tmp_path, monkeypatch):
        """The whole point: six FMs on one machine must not share a sender."""
        self._identity(tmp_path, monkeypatch, "ai-memory")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "claude-architect"}), \
             patch("pt._chat_api_request", return_value={"id": 1}) as req:
            runner.invoke(cli, ["message", "send", "hi"])

        assert req.call_args[1]["data"]["sender"] == "ai-memory"


class TestUnknownAddressGuard:
    """An unknown address is accepted by the server and delivered to nobody.

    This is how message #91 was lost on 2026-08-30: addressed to a name no
    session listened on, reported as "Sent". Delivery is the point of this
    card, so a send that cannot arrive must not report success.
    """

    def _identity(self, tmp_path, monkeypatch, address):
        state = tmp_path / "identity"
        state.mkdir(parents=True, exist_ok=True)
        (state / "sess.txt").write_text(address)
        monkeypatch.setenv("AGENT_CHAT_STATE_DIR", str(state))
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess")

    def test_unknown_address_is_refused(self, runner, tmp_path, monkeypatch):
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._known_chat_addresses", return_value={"project-tracker", "ai-memory"}), \
             patch("pt._chat_api_request", return_value={"id": 1}) as req:
            result = runner.invoke(cli, ["message", "send", "hi", "--to", "no-such-project"])

        assert result.exit_code != 0
        assert "delivered to nobody" in result.output
        req.assert_not_called()

    def test_typo_gets_a_suggestion(self, runner, tmp_path, monkeypatch):
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._known_chat_addresses", return_value={"project-tracker", "ai-memory"}), \
             patch("pt._chat_api_request", return_value={"id": 1}):
            result = runner.invoke(cli, ["message", "send", "hi", "--to", "ai-memry"])

        assert "ai-memory" in result.output

    def test_known_address_sends(self, runner, tmp_path, monkeypatch):
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._known_chat_addresses", return_value={"project-tracker", "ai-memory"}), \
             patch("pt._chat_api_request", return_value={"id": 1}) as req:
            result = runner.invoke(cli, ["message", "send", "hi", "--to", "ai-memory"])

        assert result.exit_code == 0
        req.assert_called_once()

    def test_machine_qualified_address_validates_on_project(self, runner, tmp_path, monkeypatch):
        """`ai-memory@mini` is valid because `ai-memory` is a known project."""
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._known_chat_addresses", return_value={"project-tracker", "ai-memory"}), \
             patch("pt._chat_api_request", return_value={"id": 1}) as req:
            result = runner.invoke(cli, ["message", "send", "hi", "--to", "ai-memory@mini"])

        assert result.exit_code == 0
        req.assert_called_once()

    def test_force_overrides(self, runner, tmp_path, monkeypatch):
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._known_chat_addresses", return_value={"project-tracker"}), \
             patch("pt._chat_api_request", return_value={"id": 1}) as req:
            result = runner.invoke(cli, ["message", "send", "hi", "--to", "odd-name", "--force"])

        assert result.exit_code == 0
        req.assert_called_once()

    def test_unavailable_project_list_does_not_block(self, runner, tmp_path, monkeypatch):
        """A DB hiccup must mean 'cannot verify', never 'invalid'."""
        self._identity(tmp_path, monkeypatch, "project-tracker")
        with patch("pt._load_chat_config", return_value={"url": "u", "key": "k", "sender": "cfg"}), \
             patch("pt._known_chat_addresses", return_value=set()), \
             patch("pt._chat_api_request", return_value={"id": 1}) as req:
            result = runner.invoke(cli, ["message", "send", "hi", "--to", "anything"])

        assert result.exit_code == 0
        req.assert_called_once()
