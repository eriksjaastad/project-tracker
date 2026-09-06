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
import tempfile
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


def run_hook(
    tmp_path,
    messages,
    *,
    identity=None,
    machine=None,
    machine_file=None,
    home=None,
    clear_throttle=True,
):
    """Execute check_chat.sh against a stubbed API response.

    Returns the additionalContext string the hook would inject, or "" when it
    emits nothing.

    `home` lets a test poll twice from the same HOME — that is the only way to
    exercise cursor state, which is what several sessions on one laptop share.
    Each call still gets its own stub dir, so the recorded URL belongs to that
    poll alone. The 30s throttle would otherwise suppress the second poll, so
    it is reset unless a test is specifically asserting on it.
    """
    if home is None:
        home = tmp_path / "home"
    home = Path(home)
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    if clear_throttle:
        throttle = home / ".claude" / "chat_throttle"
        if throttle.exists():
            throttle.unlink()

    rundir = Path(tempfile.mkdtemp(dir=tmp_path))
    payload = rundir / "response.json"
    payload.write_text(json.dumps({"messages": messages}))

    # Stub curl so no network is touched and the response is deterministic.
    bindir = rundir / "bin"
    bindir.mkdir()
    url_log = rundir / "curl_url.txt"
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
        state = rundir / "identity"
        state.mkdir(exist_ok=True)
        (state / "sess.txt").write_text(identity)
        env["AGENT_CHAT_STATE_DIR"] = str(state)
        env["CLAUDE_CODE_SESSION_ID"] = "sess"
    if machine is not None:
        env["AGENT_CHAT_MACHINE"] = machine

    if machine_file is not None:
        state = Path(env.get("AGENT_CHAT_STATE_DIR", rundir / "identity"))
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


def cursors(home):
    """Cursor files that exist under a HOME, by name."""
    return sorted(p.name for p in (Path(home) / ".claude").glob("chat_cursor*"))


class TestPerAddressCursor:
    """#6952: one cursor per address, because one response per address.

    Several floor managers run on one laptop at once. The request is scoped
    `?for=$SENDER`, so a single shared cursor let session A mark as seen mail
    that A's own poll could never have returned — mail addressed to B. It
    happened: the shared cursor sat at the timestamp of a DM to `ai-memory`,
    parked there by a `for=project-tracker` poll.
    """

    def test_one_sessions_poll_does_not_advance_anothers(self, tmp_path):
        home = tmp_path / "shared-home"
        alpha = run_hook(
            tmp_path, [msg(20, "ai-memory", "alpha", "for-alpha")],
            identity="alpha", home=home,
        )
        assert "for-alpha" in alpha

        beta = run_hook(
            tmp_path, [msg(21, "ai-memory", "beta", "for-beta")],
            identity="beta", home=home,
        )
        # The core bug: alpha's advance must not become beta's floor.
        assert "since=" not in beta.url
        assert "for-beta" in beta

        assert cursors(home) == ["chat_cursor.alpha", "chat_cursor.beta"]
        alpha_file = home / ".claude" / "chat_cursor.alpha"
        assert alpha_file.read_text().strip() == "2026-08-30T00:00:20Z"

    def test_an_address_does_advance_its_own_cursor(self, tmp_path):
        home = tmp_path / "shared-home"
        run_hook(
            tmp_path, [msg(22, "ai-memory", "alpha", "first")],
            identity="alpha", home=home,
        )
        second = run_hook(
            tmp_path, [msg(23, "ai-memory", "alpha", "second")],
            identity="alpha", home=home,
        )
        assert "since=2026-08-30T00%3A00%3A22Z" in second.url

    def test_legacy_global_cursor_seeds_the_per_address_file(self, tmp_path):
        """Without the seed, the first per-address poll replays the whole board."""
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor").write_text("2026-08-30T17:36:50\n")

        run = run_hook(
            tmp_path, [msg(24, "ai-memory", "alpha", "x")],
            identity="alpha", home=home,
        )
        assert "since=2026-08-30T17%3A36%3A50" in run.url
        assert (home / ".claude" / "chat_cursor.alpha").exists()

    def test_the_legacy_cursor_seeds_only_once(self, tmp_path):
        """After the first poll the per-address file owns the position.

        A re-seed on every poll would drag the address backwards (or forwards)
        to whatever some other session last wrote globally — the original bug
        wearing a migration's clothes.
        """
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        legacy = home / ".claude" / "chat_cursor"
        legacy.write_text("2026-08-30T17:36:50")

        run_hook(
            tmp_path, [msg(25, "ai-memory", "alpha", "x")],
            identity="alpha", home=home,
        )
        legacy.write_text("2026-09-01T00:00:00")
        second = run_hook(
            tmp_path, [msg(26, "ai-memory", "alpha", "y")],
            identity="alpha", home=home,
        )
        assert "since=2026-08-30T00%3A00%3A25Z" in second.url
        assert "2026-09-01" not in second.url

    def test_at_qualified_address_produces_a_safe_filename(self, tmp_path):
        """`project-tracker@laptop` is a normal address, not a path."""
        home = tmp_path / "home"
        run = run_hook(
            tmp_path, [msg(27, "ai-memory", "project-tracker@laptop", "x")],
            identity="project-tracker@laptop", home=home,
        )
        assert "x" in run
        assert cursors(home) == ["chat_cursor.project-tracker%40laptop"]

    def test_distinct_addresses_cannot_collide(self, tmp_path):
        """Folding unsafe characters to `_` re-creates this card's own bug.

        `a/b` and `a_b` are different addresses. If they sanitize to one
        filename they share a position, and one steals the other's mail —
        the shared-cursor race again, just smaller.
        """
        home = tmp_path / "shared-home"
        first = run_hook(
            tmp_path, [msg(32, "ai-memory", "a/b", "slash")],
            identity="a/b", home=home,
        )
        assert "slash" in first

        second = run_hook(
            tmp_path, [msg(33, "ai-memory", "a_b", "under")],
            identity="a_b", home=home,
        )
        assert "since=" not in second.url
        assert "under" in second

        assert cursors(home) == ["chat_cursor.a%2Fb", "chat_cursor.a_b"]
        assert (home / ".claude" / "chat_cursor.a%2Fb").read_text().strip() == (
            "2026-08-30T00:00:32Z"
        )

    def test_an_empty_legacy_cursor_is_not_taken_as_a_seed(self, tmp_path):
        """A 0-byte legacy file is not a position — a stray `touch` makes one.

        Seeding from it wrote an empty cursor, and the next poll went out with
        no `since` at all: the unbounded replay the migration exists to stop.
        """
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor").write_text("")

        run = run_hook(tmp_path, [], identity="emptytest", home=home)
        assert "since=" not in run.url
        assert cursors(home) == ["chat_cursor"]  # nothing seeded

    def test_a_legacy_cursor_with_trailing_content_is_rejected(self, tmp_path):
        """Validating a prefix is not validating a line.

        `2026-08-30T17:36:50 garbage` starts with a real timestamp. An
        unanchored pattern passed it, and a strip that deleted interior
        whitespace then collapsed it to `2026-08-30T17:36:50garbage` — a valid
        string manufactured out of an invalid line, sent verbatim as `since=`
        on the next poll. The line must be rejected, not repaired.
        """
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor").write_text("2026-08-30T17:36:50 garbage\n")

        run = run_hook(
            tmp_path, [msg(35, "ai-memory", "trailing", "x")],
            identity="trailing", home=home,
        )
        assert "since=" not in run.url
        assert "garbage" not in run.url
        assert "2026-08-30T17%3A36%3A50" not in run.url

    @pytest.mark.parametrize(
        "stored,encoded",
        [
            # SQLite: strftime('%Y-%m-%dT%H:%M:%fZ') — see agent-chat/server/db.py
            ("2026-08-30T17:36:50.123Z", "2026-08-30T17%3A36%3A50.123Z"),
            # Postgres TIMESTAMPTZ through .isoformat()
            ("2026-08-30T17:36:50.123456+00:00",
             "2026-08-30T17%3A36%3A50.123456%2B00%3A00"),
            ("2026-08-30T17:36:50Z", "2026-08-30T17%3A36%3A50Z"),
        ],
    )
    def test_the_real_timestamp_shapes_still_seed(self, tmp_path, stored, encoded):
        """Anchoring must not reject the formats the server actually emits.

        Too strict is not safe here: every address would start clean and the
        migration would stop migrating anything.
        """
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor").write_text(stored + "\n")

        run = run_hook(
            tmp_path, [msg(36, "ai-memory", "shapes", "x")],
            identity="shapes", home=home,
        )
        assert f"since={encoded}" in run.url

    def test_surrounding_whitespace_does_not_stop_a_valid_seed(self, tmp_path):
        """Trimming the ends is legitimate; only interior edits are not."""
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor").write_text("  2026-08-30T17:36:50Z  \r\n")

        run = run_hook(
            tmp_path, [msg(37, "ai-memory", "padded", "x")],
            identity="padded", home=home,
        )
        assert "since=2026-08-30T17%3A36%3A50Z" in run.url

    def test_a_corrupt_legacy_cursor_is_not_taken_as_a_seed(self, tmp_path):
        """`since=<garbage>` reaches the API and may return nothing, forever.

        Starting this address clean is the honest failure; migrating junk
        forward turns a delivery bug into a silent one.
        """
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor").write_text("not-a-timestamp\n")

        run = run_hook(
            tmp_path, [msg(34, "ai-memory", "corrupt", "x")],
            identity="corrupt", home=home,
        )
        assert "since=" not in run.url
        assert "not-a-timestamp" not in run.url
        # The poll's own result still lands, so the address is not stuck.
        assert (home / ".claude" / "chat_cursor.corrupt").read_text().strip() == (
            "2026-08-30T00:00:34Z"
        )

    def test_a_separator_in_the_address_cannot_escape_the_claude_dir(self, tmp_path):
        """Defense in depth: a mis-derived address must not write outside ~/.claude."""
        home = tmp_path / "home"
        run_hook(
            tmp_path, [msg(28, "ai-memory", None, "x")],
            identity="../../pwned", home=home,
        )
        written = cursors(home)
        assert len(written) == 1
        assert "/" not in written[0] and ".." not in written[0]
        # The only file anywhere named for that address is the one inside .claude.
        assert list(tmp_path.rglob("*pwned*")) == [home / ".claude" / written[0]]

    def test_a_session_with_no_address_keeps_the_global_cursor(self, tmp_path):
        """No address means no `for=` filter, so the global cursor still fits."""
        home = tmp_path / "home"
        run_hook(tmp_path, [msg(29, "auxesis-ops", None, "public")],
                 identity=None, home=home)
        assert cursors(home) == ["chat_cursor"]

    def test_the_throttle_still_suppresses_a_second_poll(self, tmp_path):
        """Per-address cursors must not cost the 30s throttle."""
        home = tmp_path / "home"
        run_hook(tmp_path, [msg(30, "ai-memory", "alpha", "first")],
                 identity="alpha", home=home)
        second = run_hook(
            tmp_path, [msg(31, "ai-memory", "alpha", "second")],
            identity="alpha", home=home, clear_throttle=False,
        )
        assert second == ""
        assert second.url == ""
