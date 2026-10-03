"""Tests for agent-chat/hooks/check_chat.sh — the message delivery filter.

This script had no test coverage, which is how a privacy regression got into
#6772: the no-identity branch was widened from broadcasts-only to unfiltered,
injecting other agents' direct messages into a session that had no address.

These run the real script with a stubbed `curl`, so the filter under test is
the one that actually ships rather than a copy of it.
"""

import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dataclasses import dataclass

AGENT_CHAT = Path(__file__).resolve().parent.parent / "agent-chat"
HOOK = AGENT_CHAT / "hooks" / "check_chat.sh"
SESSION_HOOK = AGENT_CHAT / "hooks" / "session_identity.py"
sys.path.insert(0, str(AGENT_CHAT))
import chat_cursor  # noqa: E402

# A stub server that honours the request the hook actually sends: `since`
# (strictly later, compared as instants like the server's TIMESTAMPTZ column),
# `for`/`for_machine` and `limit`, oldest first. Returning the whole payload
# regardless let a session look like it received mail its URL had skipped.
STUB_SERVER = r"""
import json, os, sys, urllib.parse
from datetime import datetime, timezone
log, payload = sys.argv[1], sys.argv[2]
args = sys.argv[3:]
with open(log, "a") as fh:
    fh.write("\n".join(args) + "\n")
url = next(a for a in args if a.startswith("http"))
q = {k: v[-1] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
def instant(ts):
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
msgs = json.load(open(payload))["messages"]
if "since" in q and not os.environ.get("STUB_IGNORE_SINCE"):
    msgs = [m for m in msgs if instant(m["ts"]) > instant(q["since"])]
if "for" in q:
    mine = {q["for"]} | ({q["for"] + "@" + q["for_machine"]} if "for_machine" in q else set())
    msgs = [m for m in msgs if m["recipient"] in (None, "") or m["recipient"] in mine]
msgs.sort(key=lambda m: instant(m["ts"]))
print(json.dumps({"messages": msgs[: int(q.get("limit", 50))]}))
"""


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
    session="sess",
    sender_env=None,
    stale_response=False,
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
        # The throttle is per-cursor since #6994 (chat_throttle.<addr>.<session>),
        # so clearing the single legacy path is no longer enough — a second poll
        # would be silently suppressed and the test would see an empty URL.
        for throttle in (home / ".claude").glob("chat_throttle*"):
            throttle.unlink()

    rundir = Path(tempfile.mkdtemp(dir=tmp_path))
    payload = rundir / "response.json"
    payload.write_text(json.dumps({"messages": messages}))

    # Stub curl so no network is touched and the response is deterministic.
    bindir = rundir / "bin"
    bindir.mkdir()
    url_log = rundir / "curl_url.txt"
    curl = bindir / "curl"
    server = rundir / "server.py"
    server.write_text(STUB_SERVER)
    curl.write_text(
        f'#!/usr/bin/env bash\n'
        f'exec "{sys.executable}" "{server}" "{url_log}" "{payload}" "$@"\n'
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
        (state / f"{session}.txt").write_text(identity)
        env["AGENT_CHAT_STATE_DIR"] = str(state)
        # `session` distinguishes two sessions of the SAME project on one box —
        # the case #6994 is about. Defaults to "sess" so existing tests are
        # unaffected.
        env["CLAUDE_CODE_SESSION_ID"] = session
    if machine is not None:
        env["AGENT_CHAT_MACHINE"] = machine
    if stale_response:
        # A response computed before a sibling poll moved the cursor, landing
        # after it: the server answers an older `since` than the file now holds.
        env["STUB_IGNORE_SINCE"] = "1"
    if sender_env is not None:
        # A session that predates identity binding: an address, no SESSION_ID.
        env["AGENT_CHAT_SENDER"] = sender_env

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


def ts(sec):
    """A message time later than any start-of-session seed the hook can write.

    A new address now starts at its session start (#7933), and the stub server
    honours `since`, so mail in tests has to be newer than "now" to arrive.
    """
    return f"2099-08-30T00:00:{sec:02d}Z"


def enc(value):
    return value.replace(":", "%3A").replace("+", "%2B")


def msg(mid, sender, recipient=None, body="body", at=None):
    return {
        "id": mid,
        "sender": sender,
        "recipient": recipient,
        "body": body,
        "ts": at or ts(mid),
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


def cursor(home, name):
    return (Path(home) / ".claude" / name).read_text().strip()


def since_of(run):
    """The `since` the hook actually sent, decoded, or None."""
    url = next(line for line in run.url.splitlines() if line.startswith("http"))
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("since", [None])[-1]


def assert_session_start(value):
    """A start-of-session seed: now, less the 60s clock-skew margin."""
    when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    assert now - timedelta(seconds=120) <= when <= now, value


def drops(home):
    log = Path(home) / ".claude" / "open-brain" / "agent_chat_drops.log"
    return log.read_text() if log.exists() else ""


@contextlib.contextmanager
def held_lock(home):
    """Hold the cursor helper's lock, as a stuck sibling poll would."""
    fd = os.open(Path(home) / ".claude" / chat_cursor.LOCK_NAME, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def start_session(tmp_path, home, project, session):
    """Run the real SessionStart hook for `project` with HOME=home."""
    projects = tmp_path / "projects"
    (projects / project).mkdir(parents=True, exist_ok=True)
    (projects / project / "CLAUDE.md").write_text("x")
    env = dict(os.environ)
    for var in ("AGENT_CHAT_AGENT", "AGENT_CHAT_SENDER", "CLAUDE_CODE_SESSION_ID"):
        env.pop(var, None)
    env.update(
        HOME=str(home),
        PROJECTS_ROOT=str(projects),
        AGENT_CHAT_STATE_DIR=str(tmp_path / f"state-{session}"),
        AGENT_CHAT_MACHINE="laptop",
    )
    (Path(home) / ".claude").mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, str(SESSION_HOOK)],
        input=json.dumps({"session_id": session, "cwd": str(projects / project)}),
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert result.returncode == 0, result.stderr


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
        assert_session_start(since_of(beta))
        assert "for-beta" in beta

        assert cursors(home) == [
            "chat_cursor.alpha", "chat_cursor.alpha.sess",
            "chat_cursor.beta", "chat_cursor.beta.sess",
        ]
        assert cursor(home, "chat_cursor.alpha.sess") == ts(20)

    def test_an_address_does_advance_its_own_cursor(self, tmp_path):
        home = tmp_path / "shared-home"
        run_hook(
            tmp_path, [msg(22, "ai-memory", "alpha", "first")],
            identity="alpha", home=home,
        )
        second = run_hook(
            tmp_path, [msg(22, "ai-memory", "alpha", "first"),
                       msg(23, "ai-memory", "alpha", "second")],
            identity="alpha", home=home,
        )
        assert f"since={enc(ts(22))}" in second.url
        assert "second" in second and "first" not in second

    def test_at_qualified_address_produces_a_safe_filename(self, tmp_path):
        """`project-tracker@laptop` is a normal address, not a path."""
        home = tmp_path / "home"
        run = run_hook(
            tmp_path, [msg(27, "ai-memory", "project-tracker@laptop", "x")],
            identity="project-tracker@laptop", home=home,
        )
        assert "x" in run
        assert cursors(home) == [
            "chat_cursor.project-tracker%40laptop",
            "chat_cursor.project-tracker%40laptop.sess",
        ]

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
        assert_session_start(since_of(second))
        assert "under" in second

        assert cursors(home) == [
            "chat_cursor.a%2Fb", "chat_cursor.a%2Fb.sess",
            "chat_cursor.a_b", "chat_cursor.a_b.sess",
        ]
        assert cursor(home, "chat_cursor.a%2Fb") == ts(32)

    @pytest.mark.parametrize(
        "stored",
        [
            # SQLite: strftime('%Y-%m-%dT%H:%M:%fZ') — see agent-chat/server/db.py
            "2026-08-30T17:36:50.123Z",
            # Postgres TIMESTAMPTZ through .isoformat()
            "2026-08-30T17:36:50.123456+00:00",
            "2026-08-30T17:36:50Z",
        ],
    )
    def test_the_real_timestamp_shapes_seed_from_the_address(self, tmp_path, stored):
        """Validation must accept every format the server actually emits.

        Too strict is not safe: every session would start at "now" and drop
        whatever reached its address since the last poll.
        """
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor.shapes").write_text(stored + "\n")

        run = run_hook(
            tmp_path, [msg(36, "ai-memory", "shapes", "x")],
            identity="shapes", home=home,
        )
        assert f"since={enc(stored)}" in run.url

    def test_surrounding_whitespace_does_not_stop_a_valid_seed(self, tmp_path):
        """Trimming the ends is legitimate; only interior edits are not."""
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor.padded").write_text("  2026-08-30T17:36:50Z  \r\n")

        run = run_hook(
            tmp_path, [msg(37, "ai-memory", "padded", "x")],
            identity="padded", home=home,
        )
        assert "since=2026-08-30T17%3A36%3A50Z" in run.url

    @pytest.mark.parametrize(
        "stored",
        [
            "",  # a stray `touch`
            "not-a-timestamp\n",
            # Validating a prefix is not validating a line: an unanchored
            # pattern passed this, and a strip of interior whitespace then
            # manufactured `...50garbage` and sent it as `since=`.
            "2026-08-30T17:36:50 garbage\n",
        ],
    )
    def test_an_invalid_address_seed_is_not_taken(self, tmp_path, stored):
        """A non-position is rejected, logged, and the session starts now.

        Not "no since": that replays the whole archive. Not repaired: an edited
        line is a position this API never issued.
        """
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor.corrupt").write_text(stored)

        run = run_hook(
            tmp_path, [msg(34, "ai-memory", "corrupt", "x")],
            identity="corrupt", home=home,
        )
        assert_session_start(since_of(run))
        assert "garbage" not in run.url and "not-a-timestamp" not in run.url
        if stored:
            assert "invalid_address_seed" in drops(home)
        # The poll's own result lands, so neither cursor is stuck on junk.
        assert cursor(home, "chat_cursor.corrupt.sess") == ts(34)
        assert cursor(home, "chat_cursor.corrupt") == ts(34)

    def test_a_separator_in_the_address_cannot_escape_the_claude_dir(self, tmp_path):
        """Defense in depth: a mis-derived address must not write outside ~/.claude."""
        home = tmp_path / "home"
        run_hook(
            tmp_path, [msg(28, "ai-memory", None, "x")],
            identity="../../pwned", home=home,
        )
        written = cursors(home)
        assert len(written) == 2  # address + session
        assert all("/" not in w and ".." not in w for w in written)
        # Every file anywhere named for that address (cursors and throttle)
        # must sit directly inside .claude with the separators escaped.
        escaped = sorted(tmp_path.rglob("*pwned*"))
        assert escaped, "expected the address-derived files to exist"
        for path in escaped:
            assert path.parent == home / ".claude", f"{path} escaped ~/.claude"
            assert "/" not in path.name and ".." not in path.name

    def test_one_sessions_throttle_does_not_suppress_another(self, tmp_path):
        """The throttle was machine-global, so one poll muted the whole box for 30s."""
        home = tmp_path / "shared-home"
        run_hook(tmp_path, [msg(41, "ai-memory", "project-tracker", "a")],
                 identity="project-tracker", home=home, session="sess-a")
        # Do NOT clear throttles: sess-b must be unaffected by sess-a's poll.
        out = run_hook(tmp_path, [msg(42, "ai-memory", "project-tracker", "b-body")],
                       identity="project-tracker", home=home, session="sess-b",
                       clear_throttle=False)
        assert "b-body" in out, "sess-b was throttled by sess-a's poll"

    def test_a_session_with_no_address_keeps_the_global_cursor(self, tmp_path):
        """No address means no `for=` filter, so the global cursor still fits.

        It is the legacy file's only remaining reader, and it still both reads
        and advances it.
        """
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor").write_text(ts(28) + "\n")
        run = run_hook(tmp_path, [msg(28, "x", None, "old"), msg(29, "auxesis-ops", None, "public")],
                       identity=None, home=home)
        assert since_of(run) == ts(28)
        assert "public" in run and "old" not in run
        assert cursors(home) == ["chat_cursor"]
        assert cursor(home, "chat_cursor") == ts(29)

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


AUGUST = [
    msg(1, "ai-memory", "project-tracker", "august-dm", at="2026-08-30T17:40:00Z"),
    msg(2, "auxesis-ops", None, "august-broadcast", at="2026-09-15T00:00:00Z"),
]


class TestLegacyCursorIsRetired:
    """Erik, #7933: a NEW address must not seed from ~/.claude/chat_cursor.

    That file stopped moving when cursors went per-address and sits at
    2026-08-30, so a project's first session replayed a month of mail. It is
    also another address's position, which #6952 showed can skip mail. A new
    address starts at its session start instead.
    """

    def _legacy(self, home):
        (home / ".claude").mkdir(parents=True, exist_ok=True)
        legacy = home / ".claude" / "chat_cursor"
        legacy.write_text("2026-08-30T17:36:50\n")
        return legacy

    def test_session_start_does_not_replay_august(self, tmp_path):
        home = tmp_path / "home"
        legacy = self._legacy(home)
        start_session(tmp_path, home, "project-tracker", "s1")
        assert_session_start(cursor(home, "chat_cursor.project-tracker.s1"))

        first = run_hook(tmp_path, AUGUST, identity="project-tracker",
                         home=home, session="s1")
        assert "august" not in first.context
        assert_session_start(since_of(first))

        new = run_hook(tmp_path, [*AUGUST, msg(50, "ai-memory", "project-tracker", "fresh-dm")],
                       identity="project-tracker", home=home, session="s1")
        assert "fresh-dm" in new and "august" not in new.context
        assert cursor(home, "chat_cursor.project-tracker") == ts(50)
        assert legacy.read_text() == "2026-08-30T17:36:50\n"  # untouched

    def test_first_poll_without_session_start_does_not_replay_august(self, tmp_path):
        """Sessions with no SessionStart hook take the same rule at first poll."""
        home = tmp_path / "home"
        self._legacy(home)
        run = run_hook(tmp_path, AUGUST, identity="project-tracker", home=home)
        assert "august" not in run.context
        assert_session_start(since_of(run))
        assert "2026-08-30" not in run.url

    def test_a_session_without_session_id_starts_now_too(self, tmp_path):
        """Pre-identity sessions use the address cursor directly; same rule."""
        home = tmp_path / "home"
        self._legacy(home)
        first = run_hook(tmp_path, AUGUST, sender_env="project-tracker", home=home)
        assert "august" not in first.context
        assert_session_start(since_of(first))
        second = run_hook(tmp_path, [*AUGUST, msg(51, "a", "project-tracker", "new-one")],
                          sender_env="project-tracker", home=home)
        assert "new-one" in second
        assert cursors(home) == ["chat_cursor", "chat_cursor.project-tracker"]
        assert cursor(home, "chat_cursor.project-tracker") == ts(51)

    def test_an_existing_address_position_is_kept(self, tmp_path):
        """Only NEW addresses start now; a real address cursor is still the seed."""
        home = tmp_path / "home"
        self._legacy(home)
        (home / ".claude" / "chat_cursor.project-tracker").write_text("2026-09-14T00:00:00Z\n")
        start_session(tmp_path, home, "project-tracker", "s1")
        assert cursor(home, "chat_cursor.project-tracker.s1") == "2026-09-14T00:00:00Z"

        run = run_hook(tmp_path, AUGUST, identity="project-tracker", home=home, session="s1")
        assert "since=2026-09-14T00%3A00%3A00Z" in run.url
        assert "august-broadcast" in run and "august-dm" not in run.context


class TestAddressCursorAdvances:
    """#7933: polls advance chat_cursor.<address>, the seed for new sessions.

    Only the session file used to be written, so the architect's address cursor
    sat at 2026-08-30 while its sessions read into October and each new session
    replayed a month of mail.
    """

    def test_a_new_session_starts_at_the_last_poll_position(self, tmp_path):
        home = tmp_path / "home"
        run_hook(tmp_path, [msg(10, "a", "alpha", "already-read")], identity="alpha",
                 home=home, session="old")
        assert cursor(home, "chat_cursor.alpha") == ts(10)

        start_session(tmp_path, home, "alpha", "new")
        run = run_hook(tmp_path, [msg(10, "a", "alpha", "already-read"),
                                  msg(11, "a", "alpha", "unread")],
                       identity="alpha", home=home, session="new")
        assert f"since={enc(ts(10))}" in run.url
        assert "unread" in run and "already-read" not in run

    def test_the_address_cursor_never_moves_backward(self, tmp_path):
        """A session behind its sibling must not drag the shared seed back."""
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor.alpha").write_text(ts(59) + "\n")
        (home / ".claude" / "chat_cursor.alpha.slow").write_text(ts(10) + "\n")
        run = run_hook(tmp_path, [msg(20, "a", "alpha", "late")], identity="alpha",
                       home=home, session="slow")
        assert "late" in run
        assert cursor(home, "chat_cursor.alpha.slow") == ts(20)
        assert cursor(home, "chat_cursor.alpha") == ts(59)

    def test_our_own_echoes_still_advance_both_cursors(self, tmp_path):
        """A page of only our own messages must not pin the cursor.

        With limit=20, twenty echoes would otherwise hide all newer mail.
        """
        home = tmp_path / "home"
        run = run_hook(tmp_path, [msg(59, "alpha", None, "mine")], identity="alpha", home=home)
        assert run == ""
        assert cursor(home, "chat_cursor.alpha.sess") == ts(59)
        assert cursor(home, "chat_cursor.alpha") == ts(59)

    def test_concurrent_sessions_of_one_project_both_receive_the_dm(self, tmp_path):
        """#6994 with the address cursor now advancing.

        Both sessions are open before either polls. A polls, takes the DM and
        advances the address cursor. B has not polled yet; if B seeded at its
        first poll it would start past the DM. Its seed was frozen at
        SessionStart, so it still gets it.
        """
        home = tmp_path / "shared-home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor.project-tracker").write_text(ts(1) + "\n")
        start_session(tmp_path, home, "project-tracker", "sess-a")
        start_session(tmp_path, home, "project-tracker", "sess-b")

        dm = [msg(40, "ai-memory", "project-tracker", "for-both")]
        first = run_hook(tmp_path, dm, identity="project-tracker", home=home, session="sess-a")
        assert cursor(home, "chat_cursor.project-tracker") == ts(40)
        second = run_hook(tmp_path, dm, identity="project-tracker", home=home, session="sess-b")

        assert "for-both" in first
        assert "for-both" in second, "sess-b skipped the DM its sibling consumed"
        assert f"since={enc(ts(1))}" in second.url

    def test_session_start_never_rewrites_an_existing_session_cursor(self, tmp_path):
        """SessionStart fires again on resume/compact; the position must survive."""
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor.alpha").write_text(ts(30) + "\n")
        (home / ".claude" / "chat_cursor.alpha.s1").write_text(ts(5) + "\n")
        start_session(tmp_path, home, "alpha", "s1")
        assert cursor(home, "chat_cursor.alpha.s1") == ts(5)

    def test_the_python_and_bash_slugs_name_the_same_file(self, tmp_path):
        """SessionStart writes the file the hook later reads, or freezing is moot."""
        home = tmp_path / "home"
        claude = home / ".claude"
        claude.mkdir(parents=True)
        address = "a/b@x+%é"
        (claude / f"chat_cursor.{chat_cursor.slug(address)}").write_text(ts(5) + "\n")
        assert chat_cursor.freeze(address, "s1", claude) == ts(5)
        # If the hook missed the frozen file it would seed from this instead.
        (claude / f"chat_cursor.{chat_cursor.slug(address)}").write_text(ts(9) + "\n")
        run = run_hook(tmp_path, [], identity=address, home=home, session="s1")
        assert since_of(run) == ts(5)

    def test_a_held_lock_cannot_block_the_hook_or_move_any_cursor(self, tmp_path):
        """Bounded wait, logged, mail still shown -- and NO unlocked write.

        The position stays put for a retry; the duplicate on the next poll is
        the price, and the retry then advances both cursors.
        """
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        for name in ("chat_cursor.alpha", "chat_cursor.alpha.sess"):
            (home / ".claude" / name).write_text(ts(1) + "\n")
        batch = [msg(7, "a", "alpha", "through")]
        with held_lock(home):
            began = time.monotonic()
            run = run_hook(tmp_path, batch, identity="alpha", home=home)
            assert time.monotonic() - began < 15
        assert "through" in run
        assert "cursor_advance_failed" in drops(home)
        assert cursor(home, "chat_cursor.alpha.sess") == ts(1)
        assert cursor(home, "chat_cursor.alpha") == ts(1)

        retry = run_hook(tmp_path, batch, identity="alpha", home=home)
        assert "through" in retry
        assert cursor(home, "chat_cursor.alpha.sess") == ts(7)
        assert cursor(home, "chat_cursor.alpha") == ts(7)

    @pytest.mark.parametrize("locked", [True, False])
    def test_without_a_session_id_a_late_poll_cannot_drag_the_address_back(
        self, tmp_path, locked
    ):
        """No session id: the session cursor IS the address cursor.

        A poll whose response predates a sibling's advance must neither write
        its older position under the lock nor around it when the lock is busy.
        """
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "chat_cursor.alpha").write_text(ts(59) + "\n")
        batch = [msg(20, "a", "alpha", "inflight")]
        with held_lock(home) if locked else contextlib.nullcontext():
            run = run_hook(tmp_path, batch, sender_env="alpha", home=home,
                           stale_response=True)
        assert "inflight" in run
        assert cursor(home, "chat_cursor.alpha") == ts(59)

    def test_an_address_write_failure_leaves_the_session_behind_it(self, tmp_path):
        """Address first: a failed address write must not strand the address.

        Had the session moved anyway, its next poll would ask past this batch
        and nothing would ever carry the address up to it.
        """
        home = tmp_path / "home"
        claude = home / ".claude"
        claude.mkdir(parents=True)
        (claude / "chat_cursor.alpha").mkdir()  # unreadable as a cursor
        (claude / "chat_cursor.alpha.sess").write_text(ts(1) + "\n")
        batch = [msg(8, "a", "alpha", "kept")]

        run = run_hook(tmp_path, batch, identity="alpha", home=home)
        assert "kept" in run
        assert "cursor_advance_failed" in drops(home)
        assert cursor(home, "chat_cursor.alpha.sess") == ts(1)

        (claude / "chat_cursor.alpha").rename(tmp_path / "set-aside")
        retry = run_hook(tmp_path, batch, identity="alpha", home=home)
        assert "kept" in retry
        assert cursor(home, "chat_cursor.alpha") == ts(8)
        assert cursor(home, "chat_cursor.alpha.sess") == ts(8)


class TestCursorHelper:
    """agent-chat/chat_cursor.py: ordering and concurrency of advance()."""

    @pytest.mark.parametrize(
        "current,new,expected",
        [
            # Lexically `59Z` sorts after `59.5+00:00`; as instants it is earlier.
            ("2099-08-30T00:00:59.5+00:00", "2099-08-30T00:00:59Z", "2099-08-30T00:00:59.5+00:00"),
            # Lexically `T01` sorts after `T00`; +02:00 makes it 23:00 the day before.
            ("2099-08-30T01:00:00+02:00", "2099-08-30T00:00:10Z", "2099-08-30T00:00:10Z"),
            # Naive legacy values are UTC, as both servers store.
            ("2099-08-30T00:00:10", "2099-08-30T00:00:10.000001Z", "2099-08-30T00:00:10.000001Z"),
            # Beyond microseconds is still compared, not rounded into a tie.
            ("2099-08-30T00:00:10.1234567Z", "2099-08-30T00:00:10.1234568Z",
             "2099-08-30T00:00:10.1234568Z"),
            ("garbage", "2099-08-30T00:00:10Z", "2099-08-30T00:00:10Z"),
        ],
    )
    def test_ordering_is_by_instant(self, tmp_path, current, new, expected):
        path = tmp_path / "chat_cursor.x"
        path.write_text(current + "\n")
        chat_cursor.advance(new, [path])
        assert path.read_text().strip() == expected

    def test_an_invalid_new_timestamp_is_refused(self, tmp_path):
        path = tmp_path / "chat_cursor.x"
        path.write_text(ts(1) + "\n")
        with pytest.raises(ValueError):
            chat_cursor.advance("tomorrow", [path])
        assert path.read_text().strip() == ts(1)

    def test_concurrent_advances_end_at_the_maximum(self, tmp_path):
        path = tmp_path / "chat_cursor.x"
        stamps = [ts(s) for s in (7, 42, 3, 58, 19, 33, 11, 50, 2, 26, 45, 9)]
        procs = [
            subprocess.Popen([sys.executable, str(AGENT_CHAT / "chat_cursor.py"),
                              "advance", stamp, str(path)])
            for stamp in stamps
        ]
        assert all(p.wait(timeout=30) == 0 for p in procs)
        assert path.read_text().strip() == ts(58)
        assert not [p for p in tmp_path.iterdir() if ".tmp" in p.name]

    def test_names_at_the_slug_bound_stay_within_name_max(self, tmp_path):
        """64 encoded bytes (192-char slug) + a UUID session is a 241-byte name.

        Legal, but only if temp files do not append to it: a `<name>.tmp.<pid>
        .<ns>` temp crossed NAME_MAX and failed freeze and advance outright.
        """
        home = tmp_path / "home"
        claude = home / ".claude"
        claude.mkdir(parents=True)
        address = "@" * 64
        session = "0f0e7c0e-5a4b-4c3d-9e2f-1a2b3c4d5e6f"
        address_file = claude / f"chat_cursor.{chat_cursor.slug(address)}"
        session_file = claude / f"chat_cursor.{chat_cursor.slug(address)}.{session}"
        assert len(session_file.name) == 241

        assert_session_start(chat_cursor.freeze(address, session, claude))
        chat_cursor.advance(ts(5), [address_file, session_file])
        assert cursor(home, address_file.name) == ts(5)
        assert cursor(home, session_file.name) == ts(5)

        run = run_hook(tmp_path, [msg(6, "a", None, "bounded")], identity=address,
                       home=home, session=session)
        assert since_of(run) == ts(5) and "bounded" in run
        assert cursor(home, session_file.name) == ts(6)
        assert cursor(home, address_file.name) == ts(6)
        assert "cursor_advance_failed" not in drops(home)
        assert not [p for p in claude.iterdir() if ".tmp" in p.name]

    def test_lock_wait_is_bounded(self, tmp_path):
        fd = os.open(tmp_path / chat_cursor.LOCK_NAME, os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            began = time.monotonic()
            with pytest.raises(TimeoutError):
                chat_cursor.advance(ts(1), [tmp_path / "chat_cursor.x"], wait=0.2)
            assert time.monotonic() - began < 2
        finally:
            os.close(fd)
