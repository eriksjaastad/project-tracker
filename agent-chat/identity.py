"""Agent Chat identity resolution.

Erik's ruling 2026-08-30 separates two axes that were previously conflated:

  ADDRESS = project name. What you type in `--to`. Stable, human-legible,
            survives session death.
  BINDING  = session. How an agent learns its OWN address: resolved once at
            session launch and frozen for the session's life.

Project addressing without session binding is the cwd bug: an agent that
re-derives its address from the current directory becomes a different agent
every time it cd's. A project-tracker session that reads ~/projects/ai-memory
would start claiming to be ai-memory. So resolution happens exactly once, in
the SessionStart hook, and every consumer afterwards only ever reads the
stored answer.

The address is derived from the project NAME, never the path. Layouts diverge
between machines (the laptop uses the ~/projects/_tools/ underscore
convention, the Mini does not; auxesis sits at a different depth there), so a
path-derived identity works on one machine and breaks when the Mini rejoins.

Machine qualifier is email-style and optional: `ai-memory@mini` addresses one
specific floor manager when two machines work the same project. A bare
`ai-memory` reaches whoever is on it. Qualify only when it matters.

Agent qualifier (#7146) disambiguates concurrent agents in the SAME directory:
`ai-memory+hermes` vs bare `ai-memory`. Set `AGENT_CHAT_AGENT` (a short slug:
letters, digits, `.`, `_`, `-`) at session launch. Legacy sessions that omit it
keep the bare project address, so the existing corpus still delivers. When two
agents launch at `~/projects` without `AGENT_CHAT_AGENT`, both still resolve to
`claude-architect` — that collision is the bug this env var exists to prevent;
set e.g. `AGENT_CHAT_AGENT=codex` / `claude` so addresses become
`claude-architect+codex` and `claude-architect+claude`.
"""

from __future__ import annotations

import os
import re
import socket
from pathlib import Path

# Markers that identify a project root, in priority order. .git first because
# it is the strongest signal; CLAUDE.md covers project dirs that are not
# repositories.
PROJECT_ROOT_MARKERS = (".git", "CLAUDE.md")

# The ~/projects root is not a project — it is the Architect's own directory,
# and the legacy corpus already uses this address for it.
ARCHITECT_ADDRESS = "claude-architect"

# Reserved for the human. No agent may resolve to it.
HUMAN_ADDRESS = "erik"

# Addresses are used in URLs and jq comparisons; keep them boring.
# Local part may include a single `+agent` qualifier (#7146).
_VALID_ADDRESS = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_VALID_AGENT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def projects_root() -> Path:
    """Root directory containing all projects."""
    return Path(os.environ.get("PROJECTS_ROOT", str(Path.home() / "projects")))


def state_dir() -> Path:
    """Where resolved session identities are stored."""
    override = os.environ.get("AGENT_CHAT_STATE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "state" / "agent_chat" / "identity"


def machine_name() -> str:
    """Short name for this machine, used as the optional @qualifier.

    Derived from the hostname rather than configured, so a new machine works
    without setup. `Eriks-Mac-mini.local` -> `mini`.
    """
    override = os.environ.get("AGENT_CHAT_MACHINE")
    if override:
        return override.strip().lower()

    host = socket.gethostname().split(".")[0].lower()
    if "mini" in host:
        return "mini"
    if "macbook" in host or "laptop" in host:
        return "laptop"
    # Unknown machine: use the hostname itself rather than guessing, so the
    # qualifier is still unique and debuggable.
    return re.sub(r"[^a-z0-9-]", "-", host) or "unknown"


def agent_name() -> str | None:
    """Optional agent slug from AGENT_CHAT_AGENT (or AGENT_CHAT_AGENT_NAME).

    Empty/unset means legacy bare project addressing. Invalid values are ignored
    rather than poisoning the address.
    """
    raw = (
        os.environ.get("AGENT_CHAT_AGENT")
        or os.environ.get("AGENT_CHAT_AGENT_NAME")
        or ""
    ).strip().lower()
    if not raw:
        return None
    if not _VALID_AGENT.match(raw):
        return None
    if raw == HUMAN_ADDRESS:
        return None
    return raw


def with_agent(project: str, agent: str | None = None) -> str:
    """Attach an agent qualifier: `ai-memory` + `hermes` -> `ai-memory+hermes`."""
    if not agent:
        return project
    return f"{project}+{agent}"


def split_local(local: str) -> tuple[str, str | None]:
    """Split `ai-memory+hermes` into ("ai-memory", "hermes")."""
    if "+" in local:
        project, _, agent = local.partition("+")
        return project, (agent or None)
    return local, None


def find_project_root(start: Path) -> Path | None:
    """Walk up from `start` looking for a project root marker.

    Returns None when `start` is not inside a project — the caller decides
    what that means rather than getting a silently wrong answer.
    """
    try:
        current = Path(start).resolve()
    except (OSError, RuntimeError):
        return None

    root = projects_root()
    try:
        root = root.resolve()
    except (OSError, RuntimeError):
        pass

    for candidate in (current, *current.parents):
        # The projects root itself is the Architect's directory, not a project.
        if candidate == root:
            return candidate
        for marker in PROJECT_ROOT_MARKERS:
            if (candidate / marker).exists():
                return candidate
        # Never walk above the projects root.
        if candidate == candidate.parent:
            break
    return None


def project_name_for(cwd: str | Path) -> str | None:
    """Resolve the project NAME for a directory, or None if outside a project.

    Only the basename of the project root is used. The path that led there is
    deliberately discarded — that is what keeps this stable across machines
    with different layouts.
    """
    project_root = find_project_root(Path(cwd))
    if project_root is None:
        return None

    try:
        root = projects_root().resolve()
    except (OSError, RuntimeError):
        root = projects_root()

    if project_root == root:
        return ARCHITECT_ADDRESS

    name = project_root.name
    if not name or not _VALID_ADDRESS.match(name):
        return None
    if name == HUMAN_ADDRESS:
        # Reserved. An agent in a directory named `erik` must not be able to
        # impersonate the human address.
        return None
    return name


def qualify(address: str, machine: str | None = None) -> str:
    """Attach a machine qualifier: `ai-memory` + `mini` -> `ai-memory@mini`."""
    if not machine:
        return address
    return f"{address}@{machine}"


def split_address(address: str) -> tuple[str, str | None]:
    """Split `ai-memory+hermes@mini` into ("ai-memory+hermes", "mini").

    The local part may itself contain a `+agent` qualifier; use `split_local`
    to peel that off. A bare `ai-memory` returns ("ai-memory", None), meaning
    "whoever bound that bare project address", which is the default and the
    common case.
    """
    if "@" in address:
        local, _, machine = address.partition("@")
        return local, (machine or None)
    return address, None


def machine_path() -> Path:
    """Where this machine's qualifier is cached.

    Machine-global, not per-session. check_chat.sh reads this at poll time so
    it can request `for_machine=` without spawning Python on the hot path —
    the hook runs before every Bash call and has a hard latency budget.
    """
    return state_dir() / "machine.txt"


def write_machine(machine: str | None = None) -> Path:
    """Cache this machine's qualifier for the shell hook to read."""
    value = machine or machine_name()
    path = machine_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(value + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def identity_path(session_id: str) -> Path:
    """Path of the stored identity for one session."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", session_id or "")
    return state_dir() / f"{safe}.txt"


def write_identity(session_id: str, address: str) -> Path:
    """Persist a session's resolved address. Written once, at session start."""
    path = identity_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(address + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def read_identity(session_id: str | None = None) -> str | None:
    """Read this session's frozen address.

    Falls back to AGENT_CHAT_SENDER so sessions that started before identity
    binding existed keep working — but never re-derives from the current
    directory, which is the bug this module exists to prevent.
    """
    if session_id is None:
        session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")

    if session_id:
        try:
            value = identity_path(session_id).read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            pass

    fallback = os.environ.get("AGENT_CHAT_SENDER", "").strip()
    if not fallback:
        return None
    # The reservation has to hold here too. Enforcing it only in
    # project_name_for() left AGENT_CHAT_SENDER=erik as an unguarded way for an
    # agent to speak as the human — and the env fallback is the path every
    # session uses before hooks are installed.
    local = fallback.split("@", 1)[0]
    project, _agent = split_local(local)
    if project == HUMAN_ADDRESS:
        return None
    return fallback


def resolve_for_session(session_id: str, cwd: str | Path) -> str | None:
    """Resolve and freeze a session's address. Idempotent per session.

    Called once from the SessionStart hook. If an identity already exists for
    this session it is returned unchanged — re-resolving would reintroduce the
    drift this is meant to prevent.
    """
    existing = None
    try:
        existing = identity_path(session_id).read_text(encoding="utf-8").strip()
    except OSError:
        pass
    if existing:
        return existing

    name = project_name_for(cwd)
    if name is None:
        return None
    address = with_agent(name, agent_name())
    write_identity(session_id, address)
    return address
