#!/usr/bin/env python3
"""Agent Chat cursor files, shared by check_chat.sh and session_identity.py.

Two kinds of cursor live in ~/.claude (#6952, #6994):

  chat_cursor.<slug>            ADDRESS cursor: where this address last polled.
                                Only ever used to seed a NEW session.
  chat_cursor.<slug>.<session>  SESSION cursor: the `since=` one session sends.

#7933: the hook seeded sessions from the address cursor but never advanced it,
so it sat weeks behind and every new session replayed a month of mail. Every
poll now advances both, never backward. Two polls of one address can run at
once (parallel Bash calls, sibling sessions), so a plain rename is not enough:
the read-compare-write happens under a kernel lock, which -- unlike a mkdir
lock -- is released when its holder dies, so a killed poll cannot wedge it.

Advancing the address cursor alone would break #6994: a session that started
before a sibling's poll, but has not yet polled itself, would seed from the
sibling's newer position and never see the DM in between. So SessionStart
freezes the seed into the session cursor (`freeze`), and the hook's own seeding
remains only as the fallback for sessions with no SessionStart hook.

An address with no address cursor yet is NEW, and starts at its session's
start time -- not at the legacy global ~/.claude/chat_cursor, which stopped
moving when cursors went per-address and sits at 2026-08-30. Seeding from it
replayed a month of mail into every new project's first session; it is also
another address's position, which #6952 showed can skip mail this address
could never have seen. The legacy file still serves sessions with no address.

CLI (never prompts, bounded wait, nonzero exit on failure so the hook can log):
  chat_cursor.py advance <ts> <file>...
"""

from __future__ import annotations

import errno
import fcntl
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# A hook must never hold Claude up. The critical section is microseconds; if
# the lock is still busy after this, give up and let the caller log it.
LOCK_WAIT_SECONDS = 2.0
LOCK_NAME = ".chat_cursor.lock"
# A new address starts this far before its session start. Server timestamps
# come from the server's clock; a laptop clock running ahead would otherwise
# skip a DM sent just after the session began. A minute of possible repeats is
# the cheaper failure.
SEED_MARGIN_SECONDS = 60

# Same shapes check_chat.sh's looks_like_cursor accepts: SQLite
# strftime('%Y-%m-%dT%H:%M:%fZ') and Postgres TIMESTAMPTZ .isoformat().
_TS = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?"
    r"(Z|[+-]\d{2}(?::?\d{2})?)?$"
)
_SAFE_SESSION = re.compile(r"^[A-Za-z0-9._-]+$")


def slug(address: str) -> str:
    """Byte-for-byte the same as check_chat.sh's cursor_slug (C locale).

    Truncate to 64 BYTES, then percent-encode everything outside
    [A-Za-z0-9_-]. Injective, and no `/` or `.` can appear in the output.
    """
    out = []
    for b in address.encode("utf-8")[:64]:
        c = chr(b)
        if b < 128 and (c.isalnum() or c in "_-"):
            out.append(c)
        else:
            out.append(f"%{b:02X}")
    return "".join(out)


def parse_ts(value: str) -> tuple[datetime, str] | None:
    """Comparable key for a cursor, or None if it is not one.

    Lexical comparison is wrong across the two server formats (`Z` sorts after
    `+00:00` and `.`), and a naive legacy value carries no offset at all. Both
    servers store UTC, so naive means UTC. The fraction is kept as a padded
    digit string rather than rounded to microseconds, so two distinct
    positions never compare equal and let a cursor slide.
    """
    m = _TS.match(value.strip())
    if not m:
        return None
    y, mo, d, h, mi, s, frac, tz = m.groups()
    try:
        base = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
    except ValueError:  # governance: allow-silent SF002: an out-of-range date is an invalid cursor, and None is the documented "not a position" answer; advance() raises on an invalid new timestamp and the hook logs and reseeds an invalid prior position
        return None
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:4] or 0))
        base -= sign * offset
    return base.replace(tzinfo=timezone.utc), (frac or "").ljust(32, "0")


def now_seed() -> str:
    """Start position for a new address, in the SQLite server's own format."""
    t = datetime.now(timezone.utc) - timedelta(seconds=SEED_MARGIN_SECONDS)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def read_cursor(path: Path) -> str | None:
    """First line of a cursor file if it is a valid position, else None."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            line = fh.readline().strip()
    except FileNotFoundError:  # governance: allow-silent SF002: no cursor yet is the normal state for a new address or session
        return None
    return line if parse_ts(line) else None


def _write(path: Path, value: str, *, clobber: bool) -> bool:
    """Atomically write `value`. With clobber=False an existing file wins.

    The temp name is unique (concurrent writers never share and truncate one
    `.tmp`) and SHORT: a target already near NAME_MAX -- a 64-byte address
    percent-encoded to 192, plus a session UUID, is 241 bytes -- cannot take a
    suffix. Same directory, so the rename and link stay atomic.
    """
    fd, name = tempfile.mkstemp(prefix=".cc.", suffix=".tmp", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(value + "\n")
        if clobber:
            os.replace(tmp, path)
            return True
        try:
            os.link(tmp, path)
            return True
        except FileExistsError:  # governance: allow-silent SF002: an existing cursor is authoritative; not overwriting it is the point of clobber=False
            return False
    finally:
        tmp.unlink(missing_ok=True)


class _Lock:
    """Exclusive flock on ~/.claude/.chat_cursor.lock with a bounded wait."""

    def __init__(self, directory: Path, wait: float = LOCK_WAIT_SECONDS):
        self.path = directory / LOCK_NAME
        self.wait = wait
        self.fd = -1

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + self.wait
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
                    os.close(self.fd)
                    raise
                if time.monotonic() >= deadline:
                    os.close(self.fd)
                    raise TimeoutError(f"cursor lock busy after {self.wait}s") from exc
                time.sleep(0.02)

    def __exit__(self, *_exc):
        os.close(self.fd)  # closing releases the flock


def advance(ts: str, paths: list[Path], *, wait: float = LOCK_WAIT_SECONDS) -> None:
    """Move each cursor forward to `ts`; a cursor already at or past it stays.

    An existing file that is not a valid position is replaced -- staying stuck
    on garbage would pin the address forever. Raises on any failure, and the
    first failure stops the rest: callers pass the ADDRESS cursor first, so a
    failure can never leave a session ahead of its address. That order matters
    because a session's next poll asks `since=` its own cursor -- once the
    session has moved, nothing would ever bring the address up to it.
    """
    new = parse_ts(ts)
    if new is None:
        raise ValueError(f"not a cursor timestamp: {ts!r}")
    if not paths:
        return
    with _Lock(paths[0].parent, wait):
        for path in paths:
            current = parse_ts(read_cursor(path) or "")
            if current is not None and current >= new:
                continue
            _write(path, ts.strip(), clobber=True)


def freeze(address: str, session_id: str, claude_dir: Path | None = None) -> str | None:
    """Seed this session's cursor at SessionStart. Returns the seed, or None.

    The address cursor if it holds a valid position, else now (a new
    address). Never the legacy global cursor. Same rule as the hook's
    first-poll fallback. An existing session cursor (resume, compact) is never
    touched. Session ids that could not appear verbatim in the hook's
    filename are skipped -- the hook then seeds on first poll as before.
    """
    if not address or not session_id or not _SAFE_SESSION.match(session_id):
        return None
    base = claude_dir or Path.home() / ".claude"
    key = slug(address)
    target = base / f"chat_cursor.{key}.{session_id}"
    if target.exists():
        return None
    # Cursor files are only ever replaced by rename, so this read needs no lock.
    seed = read_cursor(base / f"chat_cursor.{key}") or now_seed()
    return seed if _write(target, seed, clobber=False) else None


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "advance":
        try:
            advance(argv[1], [Path(p) for p in argv[2:]])
        except Exception as exc:  # noqa: BLE001 - reported to the hook's drop log
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        return 0
    print("usage: chat_cursor.py advance <ts> <file>...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
