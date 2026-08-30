"""Tests for agent-chat/hooks/check_chat.sh — the message delivery filter.

This script had no test coverage, which is how a privacy regression got into
#6772: the no-identity branch was widened from broadcasts-only to unfiltered,
injecting other agents' direct messages into a session that had no address.

These run the real script with a stubbed `curl`, so the filter under test is
the one that actually ships rather than a copy of it.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dataclasses import dataclass

HOOK = Path(__file__).resolve().parent.parent / "agent-chat" / "hooks" / "check_chat.sh"


@dataclass
class HookRun:
    """What the hook injected, and the URL it actually asked the server for."""
    context: str
    url: str

    def __contains__(self, needle):   # `"x" in run` reads as "was x delivered"
        return needle in self.context

    def __eq__(self, other):
        return self.context == other if isinstance(other, str) else NotImplemented

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None, reason="check_chat.sh requires jq"
)


def run_hook(tmp_path, messages, *, identity=None, machine=None, machine_file=None):
    """Execute check_chat.sh against a stubbed API response.

    Returns the additionalContext string the hook would inject, or "" when it
    emits nothing.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    payload = tmp_path / "response.json"
    payload.write_text(json.dumps({"messages": messages}))

    # Stub curl so no network is touched and the response is deterministic.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    url_log = tmp_path / "curl_url.txt"
    curl = bindir / "curl"
    curl.write_text(
        f'#!/usr/bin/env bash\n'
        f'for a in "$@"; do echo "$a" >> {url_log}; done\n'
        f'cat {payload}\n'
    )
    curl.chmod(0o755)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    env["AGENT_CHAT_API_KEY"] = "test-key"
    env["AGENT_CHAT_URL"] = "http://stub.invalid"
    env.pop("AGENT_CHAT_SENDER", None)
    env.pop("AGENT_CHAT_MACHINE", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)

    if identity is not None:
        state = tmp_path / "identity"
        state.mkdir(exist_ok=True)
        (state / "sess.txt").write_text(identity)
        env["AGENT_CHAT_STATE_DIR"] = str(state)
        env["CLAUDE_CODE_SESSION_ID"] = "sess"
    if machine is not None:
        env["AGENT_CHAT_MACHINE"] = machine

    if machine_file is not None:
        state = Path(env.get("AGENT_CHAT_STATE_DIR", tmp_path / "identity"))
        state.mkdir(parents=True, exist_ok=True)
        (state / "machine.txt").write_text(machine_file)
        env["AGENT_CHAT_STATE_DIR"] = str(state)

    result = subprocess.run(
        ["bash", str(HOOK)], capture_output=True, text=True, env=env, timeout=30
    )
    assert result.returncode == 0, f"hook must never fail: {result.stderr}"

    requested_url = url_log.read_text() if url_log.exists() else ""
    context = ""
    if result.stdout.strip():
        try:
            context = json.loads(result.stdout).get(
                "hookSpecificOutput", {}
            ).get("additionalContext", "")
        except json.JSONDecodeError:
            context = ""
    return HookRun(context=context, url=requested_url)


def msg(mid, sender, recipient=None, body="body"):
    return {
        "id": mid,
        "sender": sender,
        "recipient": recipient,
        "body": body,
        "ts": f"2026-08-30T00:00:{mid:02d}Z",
        "priority": "normal",
    }


class TestDirectMessageDelivery:
    """The #6772 bug: every direct message was discarded."""

    def test_dm_addressed_to_us_is_delivered(self, tmp_path):
        out = run_hook(
            tmp_path,
            [msg(1, "ai-memory", "project-tracker", "handoff")],
            identity="project-tracker",
        )
        assert "handoff" in out

    def test_broadcast_is_delivered(self, tmp_path):
        out = run_hook(
            tmp_path, [msg(2, "auxesis-ops", None, "alert")], identity="project-tracker"
        )
        assert "alert" in out

    def test_our_own_message_is_not_echoed_back(self, tmp_path):
        out = run_hook(
            tmp_path,
            [msg(3, "project-tracker", "ai-memory", "mine")],
            identity="project-tracker",
        )
        assert "mine" not in out

    def test_mixed_batch_keeps_only_what_belongs(self, tmp_path):
        out = run_hook(
            tmp_path,
            [
                msg(4, "ai-memory", "project-tracker", "for-me"),
                msg(5, "auxesis-ops", None, "broadcast"),
                msg(6, "project-tracker", "ai-memory", "my-echo"),
            ],
            identity="project-tracker",
        )
        assert "for-me" in out
        assert "broadcast" in out
        assert "my-echo" not in out


class TestNoIdentityIsConservative:
    """Regression guard for the leak introduced mid-#6772.

    A session with no resolved address sends no `for=` filter, so the response
    contains every agent's mail. Showing it unfiltered injects other agents'
    private messages — a wider leak than the silence the card set out to fix.
    """

    def test_other_agents_dms_are_not_shown(self, tmp_path):
        out = run_hook(
            tmp_path,
            [msg(7, "ai-memory", "auxesis", "private-to-someone-else")],
            identity=None,
        )
        assert "private-to-someone-else" not in out

    def test_broadcasts_are_still_shown(self, tmp_path):
        out = run_hook(tmp_path, [msg(8, "auxesis-ops", None, "public")], identity=None)
        assert "public" in out

    def test_failure_is_recorded_not_silent(self, tmp_path):
        run_hook(tmp_path, [msg(9, "auxesis-ops", None, "public")], identity=None)
        drops = tmp_path / "home" / ".claude" / "open-brain" / "agent_chat_drops.log"
        assert drops.exists()
        assert "no_identity" in drops.read_text()


class TestMachineQualifier:
    """`ai-memory@mini` must be REQUESTED, or a qualified DM reaches nobody.

    The server can only return qualified mail if the hook asks for it. The
    previous version of this class asserted only that an unrelated bare message
    was delivered, so it passed with the `for_machine` code deleted entirely —
    a test named after a feature it did not exercise.
    """

    def test_for_machine_is_in_the_request_url(self, tmp_path):
        run = run_hook(
            tmp_path,
            [msg(10, "ai-memory", "project-tracker", "x")],
            identity="project-tracker",
            machine="mini",
        )
        assert "for_machine=mini" in run.url

    def test_machine_is_read_from_the_session_cache(self, tmp_path):
        """Nothing exports AGENT_CHAT_MACHINE, so the cache is the real path.

        SessionStart writes machine.txt; reading only the env var meant
        qualified DMs were never requested under the default configuration.
        """
        run = run_hook(
            tmp_path,
            [msg(11, "ai-memory", "project-tracker", "x")],
            identity="project-tracker",
            machine_file="mini",
        )
        assert "for_machine=mini" in run.url

    def test_env_var_overrides_the_cache(self, tmp_path):
        run = run_hook(
            tmp_path,
            [msg(12, "ai-memory", "project-tracker", "x")],
            identity="project-tracker",
            machine="laptop",
            machine_file="mini",
        )
        assert "for_machine=laptop" in run.url

    def test_no_machine_means_no_param(self, tmp_path):
        """Absent a qualifier the request must stay bare, not send an empty one."""
        run = run_hook(
            tmp_path,
            [msg(13, "ai-memory", "project-tracker", "x")],
            identity="project-tracker",
        )
        assert "for_machine" not in run.url

    def test_bare_address_is_always_requested(self, tmp_path):
        """Bare `for=` must survive, or bare DMs break on the deployed server."""
        run = run_hook(
            tmp_path,
            [msg(14, "ai-memory", "project-tracker", "x")],
            identity="project-tracker",
            machine_file="mini",
        )
        assert "for=project-tracker" in run.url

    def test_qualified_dm_is_delivered_when_the_server_returns_it(self, tmp_path):
        run = run_hook(
            tmp_path,
            [msg(15, "ai-memory", "project-tracker@mini", "qualified-body")],
            identity="project-tracker",
            machine_file="mini",
        )
        assert "qualified-body" in run


class TestNeverBlocksClaude:
    """The hook must exit 0 on every path — it gates every Bash call."""

    def test_empty_message_list(self, tmp_path):
        assert run_hook(tmp_path, [], identity="project-tracker") == ""

    def test_batch_that_filters_to_nothing(self, tmp_path):
        out = run_hook(
            tmp_path, [msg(11, "project-tracker", None, "own")], identity="project-tracker"
        )
        assert out == ""
