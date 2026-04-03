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
