"""Tests for Agent Chat identity resolution (#6772).

Agent Chat silently dropped every direct message from 2026-07-23 to
2026-08-30. Two causes, and these tests cover the identity half:

  - Every agent on a machine shared AGENT_CHAT_SENDER=claude-architect, so
    `--to claude-architect` sent to itself and DMs could not address a
    specific floor manager.
  - A cwd-derived address would have replaced that bug with a worse one: an
    agent that cd's into a peer's repo would assume the peer's identity.

Erik's ruling: ADDRESS = project name, BINDING = session (resolved once at
launch, frozen for the session's life).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent-chat"))

import identity  # noqa: E402


@pytest.fixture
def projects(tmp_path, monkeypatch):
    """A fake ~/projects with two project dirs and a non-project dir."""
    root = tmp_path / "projects"
    (root / "project-tracker").mkdir(parents=True)
    (root / "project-tracker" / ".git").mkdir()
    (root / "ai-memory").mkdir()
    (root / "ai-memory" / ".git").mkdir()
    (root / "notes-no-marker").mkdir()
    monkeypatch.setenv("PROJECTS_ROOT", str(root))
    monkeypatch.setenv("AGENT_CHAT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("AGENT_CHAT_SENDER", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    return root


class TestProjectNameResolution:
    """Address comes from the project NAME, never the path."""

    def test_project_root_resolves_to_its_name(self, projects):
        assert identity.project_name_for(projects / "ai-memory") == "ai-memory"

    def test_subdirectory_resolves_to_the_project_not_the_subdir(self, projects):
        """cwd deep inside a project still yields the project address."""
        deep = projects / "project-tracker" / "dashboard" / "frontend" / "src"
        deep.mkdir(parents=True)
        assert identity.project_name_for(deep) == "project-tracker"

    def test_projects_root_is_the_architect(self, projects):
        assert identity.project_name_for(projects) == identity.ARCHITECT_ADDRESS

    def test_outside_any_project_returns_none(self, projects, tmp_path):
        """No address is better than a wrong one."""
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        assert identity.project_name_for(outside) is None

    def test_path_layout_does_not_affect_the_address(self, tmp_path, monkeypatch):
        """The Mini nests projects differently; the address must not care."""
        alt = tmp_path / "different" / "layout"
        (alt / "ai-memory" / ".git").mkdir(parents=True)
        monkeypatch.setenv("PROJECTS_ROOT", str(alt))
        assert identity.project_name_for(alt / "ai-memory") == "ai-memory"

    def test_human_address_is_reserved(self, projects):
        """An agent must not be able to resolve to Erik's address."""
        (projects / "erik" / ".git").mkdir(parents=True)
        assert identity.project_name_for(projects / "erik") is None

    def test_claude_md_marks_a_project_without_git(self, projects):
        proj = projects / "no-git-project"
        proj.mkdir()
        (proj / "CLAUDE.md").write_text("# project")
        assert identity.project_name_for(proj) == "no-git-project"


class TestSessionBinding:
    """Resolved once at launch, then frozen — this is the cwd-bug guard."""

    def test_resolve_writes_and_returns_address(self, projects):
        addr = identity.resolve_for_session("sess-1", projects / "ai-memory")
        assert addr == "ai-memory"
        assert identity.read_identity("sess-1") == "ai-memory"

    def test_identity_is_frozen_against_directory_changes(self, projects):
        """The core regression: cd'ing into a peer repo must not re-address us.

        This is exactly what happened in the 2026-08-30 session — a
        project-tracker agent read ~/projects/ai-memory repeatedly.
        """
        identity.resolve_for_session("sess-2", projects / "project-tracker")

        # Later in the same session, working inside another project.
        again = identity.resolve_for_session("sess-2", projects / "ai-memory")

        assert again == "project-tracker"
        assert identity.read_identity("sess-2") == "project-tracker"

    def test_sessions_are_independent(self, projects):
        identity.resolve_for_session("sess-a", projects / "project-tracker")
        identity.resolve_for_session("sess-b", projects / "ai-memory")

        assert identity.read_identity("sess-a") == "project-tracker"
        assert identity.read_identity("sess-b") == "ai-memory"

    def test_two_sessions_in_one_project_share_an_address(self, projects):
        """Erik's ruling: project mailbox semantics, both receive."""
        identity.resolve_for_session("sess-x", projects / "ai-memory")
        identity.resolve_for_session("sess-y", projects / "ai-memory")

        assert identity.read_identity("sess-x") == identity.read_identity("sess-y")

    def test_outside_a_project_stores_nothing(self, projects, tmp_path):
        outside = tmp_path / "nowhere"
        outside.mkdir()
        assert identity.resolve_for_session("sess-3", outside) is None
        assert identity.read_identity("sess-3") is None

    def test_falls_back_to_env_for_pre_existing_sessions(self, projects, monkeypatch):
        """Sessions started before identity binding shipped keep working."""
        monkeypatch.setenv("AGENT_CHAT_SENDER", "claude-architect")
        assert identity.read_identity("unknown-session") == "claude-architect"

    def test_reads_session_id_from_environment(self, projects, monkeypatch):
        """`pt message` has no hook payload — it reads CLAUDE_CODE_SESSION_ID."""
        identity.resolve_for_session("sess-env", projects / "ai-memory")
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-env")
        assert identity.read_identity() == "ai-memory"

    def test_session_id_with_path_characters_is_sanitised(self, projects):
        """A session id must never escape the state directory."""
        identity.resolve_for_session("../../etc/passwd", projects / "ai-memory")
        written = identity.identity_path("../../etc/passwd")
        assert written.parent == identity.state_dir()


class TestMachineQualifier:
    """`ai-memory@mini` addresses one machine; bare `ai-memory` addresses the project."""

    def test_qualify_appends_machine(self):
        assert identity.qualify("ai-memory", "mini") == "ai-memory@mini"

    def test_qualify_without_machine_is_bare(self):
        assert identity.qualify("ai-memory", None) == "ai-memory"

    def test_split_qualified_address(self):
        assert identity.split_address("ai-memory@mini") == ("ai-memory", "mini")

    def test_split_bare_address_means_any_machine(self):
        assert identity.split_address("ai-memory") == ("ai-memory", None)

    def test_machine_name_is_overridable(self, monkeypatch):
        monkeypatch.setenv("AGENT_CHAT_MACHINE", "MINI")
        assert identity.machine_name() == "mini"

    def test_machine_name_derived_from_hostname(self, monkeypatch):
        monkeypatch.delenv("AGENT_CHAT_MACHINE", raising=False)
        monkeypatch.setattr(identity.socket, "gethostname", lambda: "Eriks-Mac-mini.local")
        assert identity.machine_name() == "mini"

    def test_unknown_hostname_still_yields_a_usable_qualifier(self, monkeypatch):
        monkeypatch.delenv("AGENT_CHAT_MACHINE", raising=False)
        monkeypatch.setattr(identity.socket, "gethostname", lambda: "Some Box.local")
        name = identity.machine_name()
        assert name and " " not in name


class TestLegacyCorpusMapping:
    """Erik: existing addresses must map onto the new scheme, not break."""

    def test_existing_addresses_split_cleanly(self):
        for addr in ("ai-memory", "project-tracker", "claude-architect"):
            project, machine = identity.split_address(addr)
            assert project == addr and machine is None

    def test_mini_claude_becomes_machine_qualified(self):
        project, machine = identity.split_address("auxesis@mini")
        assert (project, machine) == ("auxesis", "mini")
