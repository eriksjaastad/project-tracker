"""Tests for pt hygiene --json portfolio hygiene state command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pt import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path) -> None:
    """Initialise a bare-minimum git repo with one tracked file and a commit."""
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(path), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path), check=True, capture_output=True,
    )
    # Tracked file + initial commit so the repo is non-empty
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(path), check=True, capture_output=True,
    )


def _invoke(portfolio_root: Path, args: list[str]):
    """Run a pt CLI invocation with PROJECTS_ROOT overridden to portfolio_root."""
    runner = CliRunner()
    return runner.invoke(
        cli,
        args,
        env={
            "PROJECTS_ROOT": str(portfolio_root),
            "PT_SUPPRESS_MIGRATION_WARNING": "1",
            "PT_NO_BANNER": "1",
            # Keep DB operations from touching the real DB
            "PT_DB_PATH": str(portfolio_root / "tracker.db"),
        },
        catch_exceptions=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_clean_portfolio_exit_0_and_schema(tmp_path: Path) -> None:
    """A clean single-repo portfolio exits 0 with stable schema keys."""
    repo = tmp_path / "my-project"
    repo.mkdir()
    _init_git_repo(repo)

    result = _invoke(tmp_path, ["hygiene", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    # Schema stability
    assert payload["schema_version"] == "pt.hygiene.v1"
    assert payload["ok"] is True
    assert payload["command"] == "hygiene"
    assert "scanned_at" in payload
    assert "projects_root" in payload
    assert payload["summary"]["total_repos"] == 1
    assert payload["summary"]["clean_repos"] == 1
    assert payload["summary"]["repos_with_findings"] == 0

    # Result entry shape
    repo_result = payload["results"][0]
    assert repo_result["project"] == "my-project"
    assert repo_result["clean"] is True
    findings = repo_result["findings"]
    for key in (
        "dirty_tree",
        "local_only_branches",
        "branches_ahead_of_remote",
        "stashes",
        "open_pr_drift",
        "stale_progress_md",
    ):
        assert key in findings, f"missing finding key: {key}"
    assert findings["dirty_tree"]["present"] is False
    assert findings["dirty_tree"]["files"] == []
    assert findings["stashes"]["present"] is False
    assert findings["stashes"]["count"] == 0


def test_dirty_tree_finding_excludes_progress_md(tmp_path: Path) -> None:
    """A dirty tree is detected but PROGRESS.md modifications are excluded."""
    repo = tmp_path / "dirty-project"
    repo.mkdir()
    _init_git_repo(repo)

    # Modify tracked file (should be detected)
    (repo / "README.md").write_text("changed\n")

    # Add PROGRESS.md as a new untracked file (should NOT count)
    (repo / "PROGRESS.md").write_text("some progress\n")

    result = _invoke(tmp_path, ["hygiene", "--json"])

    assert result.exit_code == 6, result.output  # EXIT_HYGIENE_FINDING
    payload = json.loads(result.output)
    assert payload["ok"] is False

    repo_result = payload["results"][0]
    assert repo_result["clean"] is False
    dirty = repo_result["findings"]["dirty_tree"]
    assert dirty["present"] is True
    assert "PROGRESS.md" not in dirty["files"]
    assert any("README.md" in f for f in dirty["files"])


def test_progress_md_alone_does_not_trip_dirty_tree(tmp_path: Path) -> None:
    """PROGRESS.md-only dirtiness is NOT reported in dirty_tree."""
    repo = tmp_path / "progress-only-project"
    repo.mkdir()
    _init_git_repo(repo)

    # Only PROGRESS.md is dirty (this is the documented always-dirty file)
    (repo / "PROGRESS.md").write_text("session notes\n")

    result = _invoke(tmp_path, ["hygiene", "--json"])

    payload = json.loads(result.output)
    repo_result = payload["results"][0]
    dirty = repo_result["findings"]["dirty_tree"]
    assert dirty["present"] is False
    assert "PROGRESS.md" not in dirty["files"]


def test_local_only_branch_finding(tmp_path: Path) -> None:
    """A local branch with no upstream is reported."""
    repo = tmp_path / "branchy-project"
    repo.mkdir()
    _init_git_repo(repo)

    # Create a local branch with no remote
    subprocess.run(
        ["git", "checkout", "-b", "feat/orphan"],
        cwd=str(repo), check=True, capture_output=True,
    )
    # Switch back so HEAD is on main
    subprocess.run(
        ["git", "checkout", "main"],
        cwd=str(repo), check=True, capture_output=True,
    )

    result = _invoke(tmp_path, ["hygiene", "--json"])

    payload = json.loads(result.output)
    repo_result = payload["results"][0]
    local_only = repo_result["findings"]["local_only_branches"]
    assert local_only["present"] is True
    assert "feat/orphan" in local_only["branches"]
    # main itself should NOT appear
    assert "main" not in local_only["branches"]


def test_stash_finding(tmp_path: Path) -> None:
    """A stash is reported."""
    repo = tmp_path / "stashy-project"
    repo.mkdir()
    _init_git_repo(repo)

    # Create a stash
    (repo / "README.md").write_text("stashed change\n")
    subprocess.run(
        ["git", "stash", "push", "-m", "wip"],
        cwd=str(repo), check=True, capture_output=True,
    )

    result = _invoke(tmp_path, ["hygiene", "--json"])

    payload = json.loads(result.output)
    repo_result = payload["results"][0]
    stashes = repo_result["findings"]["stashes"]
    assert stashes["present"] is True
    assert stashes["count"] >= 1


def test_project_filter_narrows_to_one_repo(tmp_path: Path) -> None:
    """--project NAME scans only that repo."""
    for name in ("alpha", "beta", "gamma"):
        repo = tmp_path / name
        repo.mkdir()
        _init_git_repo(repo)

    result = _invoke(tmp_path, ["hygiene", "--json", "--project", "beta"])

    payload = json.loads(result.output)
    assert payload["summary"]["total_repos"] == 1
    assert payload["results"][0]["project"] == "beta"


def test_project_filter_invalid_name_exits_2(tmp_path: Path) -> None:
    """--project with a nonexistent name exits 2 (validation error)."""
    repo = tmp_path / "real-repo"
    repo.mkdir()
    _init_git_repo(repo)

    result = _invoke(tmp_path, ["hygiene", "--json", "--project", "does-not-exist"])

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["class"] == "validation"


def test_quiet_flag_hides_clean_repos(tmp_path: Path) -> None:
    """--quiet suppresses clean repos in human output (non-JSON mode)."""
    repo_clean = tmp_path / "clean-repo"
    repo_clean.mkdir()
    _init_git_repo(repo_clean)

    repo_dirty = tmp_path / "dirty-repo"
    repo_dirty.mkdir()
    _init_git_repo(repo_dirty)
    (repo_dirty / "README.md").write_text("dirty\n")

    result = _invoke(tmp_path, ["hygiene", "--quiet"])

    # Should see the dirty repo but not the clean one in output
    assert "dirty-repo" in result.output
    assert "clean-repo" not in result.output


def test_json_schema_all_keys_present(tmp_path: Path) -> None:
    """Every documented key in the pt.hygiene.v1 schema must be present."""
    repo = tmp_path / "schema-test"
    repo.mkdir()
    _init_git_repo(repo)

    result = _invoke(tmp_path, ["hygiene", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)

    # Top-level envelope
    required_top = {"schema_version", "ok", "command", "scanned_at", "projects_root", "summary", "results"}
    assert required_top <= set(payload.keys())

    # Summary
    required_summary = {"total_repos", "clean_repos", "repos_with_findings"}
    assert required_summary <= set(payload["summary"].keys())

    # Per-repo entry
    entry = payload["results"][0]
    required_entry = {"project", "path", "clean", "findings"}
    assert required_entry <= set(entry.keys())

    # Findings keys
    required_findings = {
        "dirty_tree",
        "local_only_branches",
        "branches_ahead_of_remote",
        "stashes",
        "open_pr_drift",
        "stale_progress_md",
    }
    assert required_findings <= set(entry["findings"].keys())

    # Nested shapes
    assert "present" in entry["findings"]["dirty_tree"]
    assert "files" in entry["findings"]["dirty_tree"]
    assert "present" in entry["findings"]["stashes"]
    assert "count" in entry["findings"]["stashes"]
    assert "present" in entry["findings"]["local_only_branches"]
    assert "branches" in entry["findings"]["local_only_branches"]
    assert "present" in entry["findings"]["branches_ahead_of_remote"]
    assert "branches" in entry["findings"]["branches_ahead_of_remote"]
    assert "present" in entry["findings"]["stale_progress_md"]
