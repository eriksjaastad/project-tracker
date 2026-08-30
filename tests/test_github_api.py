"""Tests for GitHub API integration in the dashboard.

Covers:
- _gh_json: subprocess execution, error handling, timeouts
- _get_tracked_repo_names: project filtering, github-repos expansion
- _fetch_github_data: data assembly and structure
- /api/github endpoint: caching behavior, response structure
"""

import sys
import os
import asyncio
import subprocess
import warnings
from datetime import datetime
from unittest.mock import patch, MagicMock
from time import time as _time


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def as_gh_call(fn):
    """Adapt a data-returning mock to _gh_call's (data, failure_kind) contract.

    _fetch_github_data calls _gh_call, which reports WHY a call failed so a
    missing repo can be told apart from a broken fetch. Mocks stay written in
    terms of returned data; returning None means GH_ERROR, and a mock can return an
    explicit (data, kind) tuple when it needs to simulate GH_NOT_FOUND.
    """
    from dashboard.app import GH_OK, GH_ERROR

    def wrapper(args, timeout=30):
        result = fn(args, timeout)
        if isinstance(result, tuple):
            return result
        return (result, GH_OK if result is not None else GH_ERROR)

    return wrapper


class TestGhJson:
    """Tests for _gh_json — runs gh CLI commands and returns parsed JSON."""

    def test_successful_command(self):
        """_gh_json returns parsed JSON on success."""
        from dashboard.app import _gh_json
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"login": "testuser"}'

        with patch("dashboard.app.subprocess.run", return_value=mock_result) as mock_run:
            result = _gh_json(["api", "/user"])

        assert result == {"login": "testuser"}
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0][-2:] == ["api", "/user"]
        assert call_args[1]["capture_output"] is True
        assert call_args[1]["text"] is True
        assert call_args[1]["timeout"] == 30

    def test_custom_timeout(self):
        """_gh_json passes custom timeout to subprocess."""
        from dashboard.app import _gh_json
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[]"

        with patch("dashboard.app.subprocess.run", return_value=mock_result) as mock_run:
            _gh_json(["pr", "list"], timeout=15)

        assert mock_run.call_args[1]["timeout"] == 15

    def test_failed_command_returns_none(self):
        """_gh_json returns None when gh exits non-zero."""
        from dashboard.app import _gh_json
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "not authenticated"

        with patch("dashboard.app.subprocess.run", return_value=mock_result):
            result = _gh_json(["api", "/user"])

        assert result is None

    def test_timeout_returns_none(self):
        """_gh_json returns None on subprocess timeout."""
        from dashboard.app import _gh_json

        with patch("dashboard.app.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30)):
            result = _gh_json(["api", "/user"])

        assert result is None

    def test_non_json_output_returns_none(self):
        """_gh_json returns None when stdout is not valid JSON."""
        from dashboard.app import _gh_json
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "This is not JSON at all"

        with patch("dashboard.app.subprocess.run", return_value=mock_result):
            result = _gh_json(["api", "/user"])

        assert result is None

    def test_missing_gh_binary_returns_none(self):
        """_gh_json returns None when gh CLI is not found."""
        from dashboard.app import _gh_json

        with patch("dashboard.app.subprocess.run", side_effect=FileNotFoundError()):
            result = _gh_json(["api", "/user"])

        assert result is None

    def test_empty_stdout_returns_none(self):
        """_gh_json returns None when stdout is empty/whitespace."""
        from dashboard.app import _gh_json
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "   "

        with patch("dashboard.app.subprocess.run", return_value=mock_result):
            result = _gh_json(["api", "/user"])

        assert result is None

    def test_returns_list(self):
        """_gh_json can return a list, not just a dict."""
        from dashboard.app import _gh_json
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '[{"name": "repo1"}, {"name": "repo2"}]'

        with patch("dashboard.app.subprocess.run", return_value=mock_result):
            result = _gh_json(["pr", "list", "--json", "name"])

        assert isinstance(result, list)
        assert len(result) == 2


class TestGetTrackedRepoNames:
    """Tests for _get_tracked_repo_names — filters projects from kanban DB."""

    def test_returns_sorted_project_names(self):
        """Returns sorted list of project IDs, excluding internal prefixes."""
        from dashboard.app import _get_tracked_repo_names

        mock_projects = [
            {"id": "project-tracker"},
            {"id": "trading-copilot"},
            {"id": "ai-journal"},
        ]

        with patch("dashboard.app.DatabaseManager") as MockDB:
            mock_db = MagicMock()
            mock_db.get_all_projects.return_value = mock_projects
            MockDB.return_value = mock_db

            result = _get_tracked_repo_names()

        assert result == ["ai-journal", "project-tracker", "trading-copilot"]

    def test_filters_underscore_prefixed_projects(self):
        """Projects starting with _ or __ are excluded."""
        from dashboard.app import _get_tracked_repo_names

        mock_projects = [
            {"id": "_tools"},
            {"id": "__knowledge"},
            {"id": "_collaboration"},
            {"id": "real-project"},
        ]

        with patch("dashboard.app.DatabaseManager") as MockDB:
            mock_db = MagicMock()
            mock_db.get_all_projects.return_value = mock_projects
            MockDB.return_value = mock_db

            result = _get_tracked_repo_names()

        assert result == ["real-project"]
        assert "_tools" not in result
        assert "__knowledge" not in result

    def test_github_repos_expands_children(self, tmp_path):
        """github-repos project is replaced by its child directories."""
        from dashboard.app import _get_tracked_repo_names

        # Create mock github-repos directory structure
        github_repos = tmp_path / "github-repos"
        github_repos.mkdir()
        (github_repos / "repo-alpha").mkdir()
        (github_repos / "repo-beta").mkdir()
        (github_repos / ".hidden").mkdir()
        (github_repos / "00_Index").mkdir()

        mock_projects = [
            {"id": "github-repos"},
            {"id": "other-project"},
        ]

        with patch("dashboard.app.DatabaseManager") as MockDB:
            mock_db = MagicMock()
            mock_db.get_all_projects.return_value = mock_projects
            MockDB.return_value = mock_db

            with patch.dict(os.environ, {"PROJECTS_ROOT": str(tmp_path)}):
                result = _get_tracked_repo_names()

        assert "github-repos" not in result
        assert "repo-alpha" in result
        assert "repo-beta" in result
        assert ".hidden" not in result
        assert "00_Index" not in result
        assert "other-project" in result

    def test_github_repos_missing_dir(self, tmp_path):
        """If github-repos directory doesn't exist, it's just skipped."""
        from dashboard.app import _get_tracked_repo_names

        mock_projects = [
            {"id": "github-repos"},
            {"id": "real-project"},
        ]

        with patch("dashboard.app.DatabaseManager") as MockDB:
            mock_db = MagicMock()
            mock_db.get_all_projects.return_value = mock_projects
            MockDB.return_value = mock_db

            with patch.dict(os.environ, {"PROJECTS_ROOT": str(tmp_path)}):
                result = _get_tracked_repo_names()

        assert result == ["real-project"]

    def test_deduplication(self):
        """Duplicate project IDs are deduplicated."""
        from dashboard.app import _get_tracked_repo_names

        mock_projects = [
            {"id": "project-a"},
            {"id": "project-a"},
            {"id": "project-b"},
        ]

        with patch("dashboard.app.DatabaseManager") as MockDB:
            mock_db = MagicMock()
            mock_db.get_all_projects.return_value = mock_projects
            MockDB.return_value = mock_db

            result = _get_tracked_repo_names()

        assert result == ["project-a", "project-b"]

    def test_database_error_returns_empty_list(self):
        """Returns empty list if DatabaseManager raises an exception."""
        from dashboard.app import _get_tracked_repo_names

        with patch("dashboard.app.DatabaseManager", side_effect=Exception("DB connection failed")):
            result = _get_tracked_repo_names()

        assert result == []


class TestFetchGithubData:
    """Tests for _fetch_github_data — main data assembly function."""

    def test_returns_error_when_user_api_fails(self):
        """Returns error dict when gh api /user fails."""
        from dashboard.app import _fetch_github_data

        with patch("dashboard.app._gh_json", return_value=None):
            result = _fetch_github_data()

        assert "error" in result
        assert result["cached"] is False

    def test_returns_error_when_no_tracked_projects(self):
        """Returns error dict when no tracked projects found."""
        from dashboard.app import _fetch_github_data

        def mock_gh_json(args, timeout=30):
            if args == ["api", "/user"]:
                return {"login": "testuser"}
            return None

        with patch("dashboard.app._gh_call", side_effect=as_gh_call(mock_gh_json)):
            with patch("dashboard.app._get_tracked_repo_names", return_value=[]):
                result = _fetch_github_data()

        assert "error" in result

    def test_successful_fetch_has_required_keys(self):
        """Successful fetch returns all expected top-level keys."""
        from dashboard.app import _fetch_github_data

        user_data = {
            "login": "testuser",
            "name": "Test User",
            "avatar_url": "https://example.com/avatar.png",
            "public_repos": 10,
            "total_private_repos": 5,
            "followers": 100,
            "following": 50,
        }

        repo_data = {
            "name": "my-repo",
            "url": "https://github.com/testuser/my-repo",
            "pushedAt": "2020-01-01T00:00:00Z",
            "defaultBranchRef": {"name": "main"},
            "isPrivate": False,
            "description": "A test repo",
            "stargazerCount": 5,
            "forkCount": 1,
            "isArchived": False,
        }

        def mock_gh_json(args, timeout=30):
            if args == ["api", "/user"]:
                return user_data
            if args[0] == "repo" and args[1] == "view":
                return repo_data
            # Return empty lists/dicts for PRs, commits, runs, branches
            if args[0] == "pr":
                return []
            if "actions/runs" in str(args):
                return {"workflow_runs": []}
            if "branches" in str(args):
                return []
            if "commits" in str(args):
                return []
            return None

        with patch("dashboard.app._gh_call", side_effect=as_gh_call(mock_gh_json)):
            with patch("dashboard.app._get_tracked_repo_names", return_value=["my-repo"]):
                result = _fetch_github_data()

        assert "error" not in result
        required_keys = [
            "user", "repos", "tracked_projects", "open_pull_requests",
            "recent_commits", "workflow_runs", "branches", "summary",
            "fetched_at", "cached",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

        assert result["cached"] is False
        assert result["user"]["login"] == "testuser"
        assert len(result["repos"]) == 1
        assert result["summary"]["total_repos"] == 1

    def test_summary_counts_are_correct(self):
        """Summary section has correct computed counts."""
        from dashboard.app import _fetch_github_data

        def mock_gh_json(args, timeout=30):
            if args == ["api", "/user"]:
                return {"login": "testuser"}
            if args[0] == "repo" and args[1] == "view":
                name = args[2].split("/")[1]
                return {
                    "name": name,
                    "isArchived": name == "archived-repo",
                    "pushedAt": "2020-01-01T00:00:00Z",
                    "defaultBranchRef": {"name": "main"},
                }
            return []

        tracked = ["active-repo", "archived-repo", "missing-repo"]

        def selective_gh_json(args, timeout=30):
            from dashboard.app import GH_NOT_FOUND
            if args == ["api", "/user"]:
                return {"login": "testuser"}
            if args[0] == "repo" and args[1] == "view":
                name = args[2].split("/")[1]
                if name == "missing-repo":
                    # Genuinely absent from GitHub, not a failed fetch — the
                    # two are counted separately now.
                    return (None, GH_NOT_FOUND)
                return {
                    "name": name,
                    "isArchived": name == "archived-repo",
                    "pushedAt": "2020-01-01T00:00:00Z",
                    "defaultBranchRef": {"name": "main"},
                }
            return []

        with patch("dashboard.app._gh_call", side_effect=as_gh_call(selective_gh_json)):
            with patch("dashboard.app._get_tracked_repo_names", return_value=tracked):
                result = _fetch_github_data()

        assert result["summary"]["tracked_projects"] == 3
        assert result["summary"]["repos_found_on_github"] == 2
        assert result["summary"]["repos_not_on_github"] == 1
        assert result["summary"]["archived_repos"] == 1
        # A repo that is absent from GitHub is not a fetch failure.
        assert result["summary"]["fetch_errors"] == 0


class TestApiGithubEndpoint:
    """Tests for the /api/github endpoint — caching and response."""

    def test_returns_cached_data_within_ttl(self):
        """Endpoint returns cached data when within TTL."""
        from dashboard.app import _github_cache, api_github

        original = _github_cache.copy()
        cached_data = {
            "user": {"login": "testuser"},
            "repos": [],
            "summary": {},
            "fetched_at": "2026-01-01T00:00:00Z",
            "cached": False,
        }
        _github_cache["data"] = cached_data
        _github_cache["timestamp"] = _time()  # just now

        try:
            result = asyncio.get_event_loop().run_until_complete(api_github())
            assert result["cached"] is True
            assert result["user"]["login"] == "testuser"
        finally:
            _github_cache.update(original)

    def test_fetches_fresh_data_when_cache_expired(self):
        """Endpoint fetches fresh data when cache TTL has passed."""
        from dashboard.app import _github_cache, api_github, _GITHUB_CACHE_TTL

        original = _github_cache.copy()
        _github_cache["data"] = {"old": True}
        _github_cache["timestamp"] = _time() - _GITHUB_CACHE_TTL - 10  # expired

        fresh_data = {
            "user": {"login": "fresh"},
            "repos": [],
            "summary": {},
            "fetched_at": "2026-03-28T00:00:00Z",
            "cached": False,
        }

        try:
            with patch("dashboard.app._fetch_github_data", return_value=fresh_data):
                result = asyncio.get_event_loop().run_until_complete(api_github())
            assert result["user"]["login"] == "fresh"
            assert _github_cache["data"] is not None
        finally:
            _github_cache.update(original)

    def test_fetches_when_cache_empty(self):
        """Endpoint fetches fresh data when cache is empty."""
        from dashboard.app import _github_cache, api_github

        original = _github_cache.copy()
        _github_cache["data"] = None
        _github_cache["timestamp"] = 0

        fresh_data = {
            "user": {"login": "testuser"},
            "repos": [],
            "summary": {},
            "cached": False,
        }

        try:
            with patch("dashboard.app._fetch_github_data", return_value=fresh_data):
                result = asyncio.get_event_loop().run_until_complete(api_github())
            assert result["user"]["login"] == "testuser"
        finally:
            _github_cache.update(original)

    def test_does_not_cache_error_responses(self):
        """Error responses are not stored in the cache."""
        from dashboard.app import _github_cache, api_github

        original = _github_cache.copy()
        _github_cache["data"] = None
        _github_cache["timestamp"] = 0

        error_data = {"error": "gh CLI not available", "cached": False}

        try:
            with patch("dashboard.app._fetch_github_data", return_value=error_data):
                result = asyncio.get_event_loop().run_until_complete(api_github())
            assert "error" in result
            assert _github_cache["data"] is None  # not cached
        finally:
            _github_cache.update(original)

    def test_handles_fetch_exception(self):
        """Endpoint returns error dict when _fetch_github_data raises."""
        from dashboard.app import _github_cache, api_github

        original = _github_cache.copy()
        _github_cache["data"] = None
        _github_cache["timestamp"] = 0

        try:
            with patch("dashboard.app._fetch_github_data", side_effect=RuntimeError("boom")):
                result = asyncio.get_event_loop().run_until_complete(api_github())
            assert "error" in result
            assert result["cached"] is False
        finally:
            _github_cache.update(original)


class TestPrListFields:
    """Regression guard for #6749 — a bad --json field empties the PR panel.

    `gh pr list` rejects the entire call if any requested field is unknown, so
    a single typo turns every PR fetch into a silent no-op. These tests fail
    loudly instead.
    """

    def test_requested_fields_are_all_valid(self):
        """Every field in PR_LIST_FIELDS is accepted by `gh pr list --json`."""
        from dashboard.app import PR_LIST_FIELDS, GH_PR_LIST_VALID_FIELDS

        invalid = set(PR_LIST_FIELDS) - GH_PR_LIST_VALID_FIELDS
        assert not invalid, (
            f"Invalid `gh pr list --json` field(s): {sorted(invalid)}. "
            "gh rejects the whole call, so every PR fetch would return nothing."
        )

    def test_repository_is_not_requested(self):
        """`repository` is a `gh search prs` field, not a `gh pr list` field."""
        from dashboard.app import PR_LIST_FIELDS, GH_PR_LIST_VALID_FIELDS

        assert "repository" not in GH_PR_LIST_VALID_FIELDS
        assert "repository" not in PR_LIST_FIELDS

    def test_fields_cover_what_the_frontend_reads(self):
        """Fields the dashboard UI renders are actually requested."""
        from dashboard.app import PR_LIST_FIELDS

        for field in ("title", "number", "url", "author", "createdAt",
                      "headRefName", "isDraft", "statusCheckRollup"):
            assert field in PR_LIST_FIELDS

    def test_gh_invoked_with_valid_fields(self):
        """The actual `gh pr list` call sends only valid fields."""
        from dashboard.app import _fetch_github_data, GH_PR_LIST_VALID_FIELDS

        seen = []

        def mock_gh_json(args, timeout=30):
            if args == ["api", "/user"]:
                return {"login": "testuser"}
            if args[0] == "repo" and args[1] == "view":
                return {
                    "name": args[2].split("/")[1],
                    "isArchived": False,
                    "pushedAt": "2020-01-01T00:00:00Z",
                    "defaultBranchRef": {"name": "main"},
                }
            if args[0] == "pr":
                seen.append(args[args.index("--json") + 1])
                return []
            return []

        with patch("dashboard.app._gh_call", side_effect=as_gh_call(mock_gh_json)):
            with patch("dashboard.app._get_tracked_repo_names", return_value=["my-repo"]):
                _fetch_github_data()

        assert seen, "no `gh pr list` call was made"
        for spec in seen:
            for field in spec.split(","):
                assert field in GH_PR_LIST_VALID_FIELDS, f"invalid field: {field}"


class TestPrRepositoryAttribution:
    """PRs must carry a repository name — `gh pr list` does not supply one."""

    @staticmethod
    def _fetch(tracked, prs_by_repo):
        from dashboard.app import _fetch_github_data

        def mock_gh_json(args, timeout=30):
            if args == ["api", "/user"]:
                return {"login": "testuser"}
            if args[0] == "repo" and args[1] == "view":
                return {
                    "name": args[2].split("/")[1],
                    "isArchived": False,
                    "pushedAt": "2020-01-01T00:00:00Z",
                    "defaultBranchRef": {"name": "main"},
                }
            if args[0] == "pr":
                repo = args[args.index("--repo") + 1].split("/")[1]
                return prs_by_repo.get(repo, [])
            return []

        with patch("dashboard.app._gh_call", side_effect=as_gh_call(mock_gh_json)):
            with patch("dashboard.app._get_tracked_repo_names", return_value=tracked):
                return _fetch_github_data()

    def test_repository_name_attached_to_each_pr(self):
        """Each PR gets repository.name set from the repo it was fetched for."""
        result = self._fetch(
            ["repo-a", "repo-b"],
            {
                "repo-a": [{"number": 1, "title": "A", "headRefName": "feat/a"}],
                "repo-b": [{"number": 2, "title": "B", "headRefName": "feat/b"}],
            },
        )

        by_number = {pr["number"]: pr for pr in result["open_pull_requests"]}
        assert by_number[1]["repository"] == {"name": "repo-a"}
        assert by_number[2]["repository"] == {"name": "repo-b"}
        assert result["summary"]["open_prs"] == 2

    def test_failing_ci_correlates_pr_to_repo(self):
        """summary.failing_ci matches a failed run to a PR in the same repo."""
        from dashboard.app import _fetch_github_data

        def mock_gh_json(args, timeout=30):
            if args == ["api", "/user"]:
                return {"login": "testuser"}
            if args[0] == "repo" and args[1] == "view":
                return {
                    "name": args[2].split("/")[1],
                    "isArchived": False,
                    "pushedAt": "2020-01-01T00:00:00Z",
                    "defaultBranchRef": {"name": "main"},
                }
            if args[0] == "pr":
                return [{"number": 1, "title": "A", "headRefName": "feat/a"}]
            if "actions/runs" in str(args):
                return {"workflow_runs": [{
                    "name": "CI",
                    "status": "completed",
                    "conclusion": "failure",
                    "head_branch": "feat/a",
                    "created_at": "2026-01-01T00:00:00Z",
                    "html_url": "https://example.com/run/1",
                }]}
            return []

        with patch("dashboard.app._gh_call", side_effect=as_gh_call(mock_gh_json)):
            with patch("dashboard.app._get_tracked_repo_names", return_value=["repo-a"]):
                result = _fetch_github_data()

        assert result["summary"]["failing_ci"] == 1


class TestPrFetchErrorReporting:
    """A failed PR fetch must be distinguishable from 'no open PRs'."""

    @staticmethod
    def _fetch(pr_return):
        from dashboard.app import _fetch_github_data

        def mock_gh_json(args, timeout=30):
            if args == ["api", "/user"]:
                return {"login": "testuser"}
            if args[0] == "repo" and args[1] == "view":
                return {
                    "name": args[2].split("/")[1],
                    "isArchived": False,
                    "pushedAt": "2020-01-01T00:00:00Z",
                    "defaultBranchRef": {"name": "main"},
                }
            if args[0] == "pr":
                return pr_return
            return []

        with patch("dashboard.app._gh_call", side_effect=as_gh_call(mock_gh_json)):
            with patch("dashboard.app._get_tracked_repo_names", return_value=["repo-a"]):
                return _fetch_github_data()

    def test_failed_fetch_is_reported(self):
        """A None return from gh surfaces in fetch_errors, not as silence."""
        result = self._fetch(None)

        assert result["open_pull_requests"] == []
        assert result["summary"]["fetch_errors"] == 1
        assert any("repo-a" in e for e in result["fetch_errors"])

    def test_no_open_prs_is_not_an_error(self):
        """An empty list means the repo genuinely has no open PRs."""
        result = self._fetch([])

        assert result["open_pull_requests"] == []
        assert result["fetch_errors"] == []
        assert result["summary"]["fetch_errors"] == 0


class TestGhFieldListDrift:
    """GH_PR_LIST_VALID_FIELDS is a snapshot of gh's field list — catch drift.

    Skipped when gh is unavailable so CI without gh stays green. When gh IS
    present this asserts our snapshot still matches reality, in both
    directions: a field gh dropped (our request would break) and a field gh
    added (our snapshot would wrongly reject a valid new field).
    """

    @staticmethod
    def _live_fields():
        import shutil
        gh = shutil.which("gh")
        if not gh:
            return None
        # gh lists the valid fields in its error message for a bogus field.
        proc = subprocess.run(
            [gh, "pr", "list", "--repo", "cli/cli", "--json", "__bogus__", "--limit", "1"],
            capture_output=True, text=True, timeout=30,
        )
        text = proc.stdout + proc.stderr
        if "Available fields:" not in text:
            return None
        tail = text.split("Available fields:", 1)[1]
        return {line.strip() for line in tail.splitlines() if line.strip()}

    def test_requested_fields_still_accepted_by_live_gh(self):
        """The fields we actually request are still valid in the installed gh.

        Only the REMOVAL direction can break us: if gh drops a field we ask
        for, every PR fetch dies. A gh release that ADDS fields leaves our
        request a valid subset, so it must not turn CI red — it is reported as
        a warning instead.
        """
        import pytest
        from dashboard.app import PR_LIST_FIELDS, GH_PR_LIST_VALID_FIELDS

        live = self._live_fields()
        if live is None:
            pytest.skip("gh CLI unavailable or output format changed")

        missing = set(PR_LIST_FIELDS) - live
        assert not missing, (
            f"The installed gh no longer accepts: {sorted(missing)}. "
            "Every PR fetch would fail. Update PR_LIST_FIELDS in dashboard/app.py."
        )

        stale = set(GH_PR_LIST_VALID_FIELDS) - live
        assert not stale, (
            f"gh removed field(s) still listed in GH_PR_LIST_VALID_FIELDS: {sorted(stale)}. "
            "The snapshot would wrongly accept them. Update dashboard/app.py."
        )

        added = live - set(GH_PR_LIST_VALID_FIELDS)
        if added:
            warnings.warn(
                f"gh added `pr list --json` field(s) not in GH_PR_LIST_VALID_FIELDS: "
                f"{sorted(added)}. Nothing is broken — our request is still a valid "
                "subset — but the snapshot in dashboard/app.py is behind.",
                UserWarning,
                stacklevel=2,
            )


class TestPrPartialFailure:
    """A failure in one repo must not lose PRs from repos that succeeded."""

    def test_partial_failure_keeps_good_repos(self):
        """One repo failing must not discard PRs from repos that succeeded."""
        from dashboard.app import _fetch_github_data

        def mock_gh_json(args, timeout=30):
            if args == ["api", "/user"]:
                return {"login": "testuser"}
            if args[0] == "repo" and args[1] == "view":
                return {
                    "name": args[2].split("/")[1],
                    "isArchived": False,
                    "pushedAt": "2020-01-01T00:00:00Z",
                    "defaultBranchRef": {"name": "main"},
                }
            if args[0] == "pr":
                repo = args[args.index("--repo") + 1].split("/")[1]
                if repo == "broken-repo":
                    return None          # fetch failed
                if repo == "quiet-repo":
                    return []            # genuinely no open PRs
                return [{"number": 7, "title": "Good", "headRefName": "feat/g"}]
            return []

        with patch("dashboard.app._gh_call", side_effect=as_gh_call(mock_gh_json)):
            with patch("dashboard.app._get_tracked_repo_names",
                       return_value=["good-repo", "broken-repo", "quiet-repo"]):
                result = _fetch_github_data()

        # The working repo's PR survives its neighbour's failure.
        assert len(result["open_pull_requests"]) == 1
        assert result["open_pull_requests"][0]["repository"] == {"name": "good-repo"}
        assert result["summary"]["open_prs"] == 1

        # Only the genuine failure is reported — the empty repo is not an error.
        assert result["summary"]["fetch_errors"] == 1
        assert any("broken-repo" in e for e in result["fetch_errors"])
        assert not any("quiet-repo" in e for e in result["fetch_errors"])


class TestGhCallClassification:
    """_gh_call must tell a missing target apart from a broken fetch."""

    @staticmethod
    def _run(returncode, stdout="", stderr=""):
        from dashboard.app import _gh_call
        mock_result = MagicMock()
        mock_result.returncode = returncode
        mock_result.stdout = stdout
        mock_result.stderr = stderr
        with patch("dashboard.app.subprocess.run", return_value=mock_result):
            return _gh_call(["repo", "view", "owner/thing", "--json", "name"])

    def test_success_returns_data_and_ok(self):
        from dashboard.app import GH_OK
        assert self._run(0, '{"name": "thing"}') == ({"name": "thing"}, GH_OK)

    def test_empty_stdout_is_not_a_failure(self):
        """gh exiting 0 with no output is an empty result, not an error."""
        from dashboard.app import GH_OK
        assert self._run(0, "   ") == (None, GH_OK)

    def test_graphql_missing_repo_is_not_found(self):
        """`gh repo view` on an absent repo — the GraphQL wording."""
        from dashboard.app import GH_NOT_FOUND
        data, failure = self._run(
            1, stderr="GraphQL: Could not resolve to a Repository with the name 'x/y'. (repository)"
        )
        assert (data, failure) == (None, GH_NOT_FOUND)

    def test_rest_404_is_not_found(self):
        """`gh api` on an absent repo — the REST wording."""
        from dashboard.app import GH_NOT_FOUND
        assert self._run(1, stderr="gh: Not Found (HTTP 404)")[1] == GH_NOT_FOUND

    def test_auth_failure_is_error_not_missing(self):
        """An auth lapse must never be reported as 'repo not on GitHub'."""
        from dashboard.app import GH_ERROR
        assert self._run(1, stderr="gh: Bad credentials (HTTP 401)")[1] == GH_ERROR

    def test_rate_limit_is_error_not_missing(self):
        from dashboard.app import GH_ERROR
        assert self._run(1, stderr="API rate limit exceeded (HTTP 403)")[1] == GH_ERROR

    def test_unknown_field_is_error_not_missing(self):
        """The #6749 failure mode itself: a bad --json field is a real error."""
        from dashboard.app import GH_ERROR
        assert self._run(1, stderr='Unknown JSON field: "repository"')[1] == GH_ERROR

    def test_timeout_is_error(self):
        from dashboard.app import _gh_call, GH_ERROR
        with patch("dashboard.app.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=10)):
            assert _gh_call(["api", "/user"]) == (None, GH_ERROR)

    def test_gh_json_wrapper_still_returns_bare_data(self):
        """Existing _gh_json callers keep the old data-or-None contract."""
        from dashboard.app import _gh_json
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"login": "testuser"}'
        with patch("dashboard.app.subprocess.run", return_value=mock_result):
            assert _gh_json(["api", "/user"]) == {"login": "testuser"}


class TestNonPrFetchErrors:
    """Every gh loop in _fetch_github_data must report its own failures."""

    @staticmethod
    def _fetch(failing):
        """Run a fetch where `failing` names the call type that errors."""
        from dashboard.app import _fetch_github_data, GH_OK, GH_ERROR

        def mock_gh_call(args, timeout=30):
            if args == ["api", "/user"]:
                return ({"login": "testuser"}, GH_OK)
            if args[0] == "repo" and args[1] == "view":
                if failing == "repo":
                    return (None, GH_ERROR)
                return ({
                    "name": args[2].split("/")[1],
                    "isArchived": False,
                    # Recent enough to pull the commits branch into play.
                    "pushedAt": datetime.utcnow().isoformat() + "Z",
                    "defaultBranchRef": {"name": "main"},
                }, GH_OK)
            if args[0] == "pr":
                return ([], GH_OK)
            blob = str(args)
            if "actions/runs" in blob:
                return (None, GH_ERROR) if failing == "runs" else ({"workflow_runs": []}, GH_OK)
            if "/branches" in blob:
                return (None, GH_ERROR) if failing == "branches" else ([], GH_OK)
            if "/commits" in blob:
                return (None, GH_ERROR) if failing == "commits" else ([], GH_OK)
            return ([], GH_OK)

        with patch("dashboard.app._gh_call", side_effect=mock_gh_call):
            with patch("dashboard.app._gh_json",
                       side_effect=lambda a, timeout=30: mock_gh_call(a, timeout)[0]):
                with patch("dashboard.app._get_tracked_repo_names", return_value=["repo-a"]):
                    return _fetch_github_data()

    def test_repo_view_failure_is_not_counted_as_missing(self):
        """A broken repo fetch must not masquerade as 'not on GitHub'."""
        result = self._fetch("repo")

        assert result["summary"]["repos_not_on_github"] == 0
        assert result["summary"]["fetch_errors"] == 1
        assert any("repo metadata" in e and "repo-a" in e for e in result["fetch_errors"])

    def test_ci_runs_failure_is_reported(self):
        """A rate-limited runs endpoint must not silently blank Failing CI."""
        result = self._fetch("runs")

        assert result["workflow_runs"] == []
        assert any("CI runs" in e for e in result["fetch_errors"])

    def test_branches_failure_is_reported(self):
        result = self._fetch("branches")

        assert result["branches"] == []
        assert any("branches" in e for e in result["fetch_errors"])

    def test_commits_failure_is_reported(self):
        result = self._fetch("commits")

        assert result["recent_commits"] == []
        assert any("recent commits" in e for e in result["fetch_errors"])

    def test_healthy_fetch_reports_no_errors(self):
        """The all-green path must not manufacture errors."""
        result = self._fetch(None)

        assert result["fetch_errors"] == []
        assert result["summary"]["fetch_errors"] == 0


class TestOtherGhPrListCallSites:
    """Every `gh pr list --json` call site in the repo needs the same guard.

    dashboard/app.py is not the only caller. scripts/pt.py runs its own
    `gh pr list` for hygiene checks, and a bad field there fails the same
    silent way: gh exits non-zero and the wrapper hands back
    {"available": False}, which reads as "no PR drift" rather than "we could
    not look."
    """

    def test_pt_hygiene_fields_are_valid(self):
        """scripts/pt.py's PR fields are accepted by `gh pr list --json`."""
        from dashboard.app import GH_PR_LIST_VALID_FIELDS
        import pt

        invalid = set(pt.HYGIENE_PR_FIELDS) - GH_PR_LIST_VALID_FIELDS
        assert not invalid, (
            f"scripts/pt.py requests invalid `gh pr list --json` field(s): {sorted(invalid)}. "
            "gh rejects the whole call, so _hygiene_open_pr_drift would report "
            "available=False forever."
        )

    def test_pt_does_not_request_repository(self):
        """The #6749 field specifically — `pr list` never returns it."""
        import pt

        assert "repository" not in pt.HYGIENE_PR_FIELDS

    def test_pt_hygiene_fields_cover_what_it_reads(self):
        """Fields _hygiene_open_pr_drift actually dereferences are requested."""
        import pt

        for field in ("number", "title", "author", "createdAt"):
            assert field in pt.HYGIENE_PR_FIELDS

    def test_no_inline_gh_pr_list_json_strings_remain(self):
        """New `gh pr list --json` call sites must use a guarded constant.

        Catches a future hardcoded field string added to either module,
        which is how both existing call sites started.
        """
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        offenders = []
        for rel in ("dashboard/app.py", "scripts/pt.py"):
            text = (root / rel).read_text()
            # A --json argument given as a comma-joined literal, e.g.
            # "--json", "number,title,author"  — as opposed to ",".join(CONST).
            for match in re.finditer(r'"--json",\s*\n?\s*"([a-zA-Z]+,[a-zA-Z,]+)"', text):
                offenders.append(f"{rel}: {match.group(1)[:60]}")

        assert not offenders, (
            "Inline --json field strings found; use a validated constant instead:\n  "
            + "\n  ".join(offenders)
        )


class TestRepoViewFields:
    """`gh repo view` has its own field set — same all-or-nothing contract."""

    def test_requested_fields_are_all_valid(self):
        from dashboard.app import REPO_VIEW_FIELDS, GH_REPO_VIEW_VALID_FIELDS

        invalid = set(REPO_VIEW_FIELDS) - GH_REPO_VIEW_VALID_FIELDS
        assert not invalid, (
            f"Invalid `gh repo view --json` field(s): {sorted(invalid)}. "
            "gh rejects the whole call, so every repo would look absent."
        )

    def test_field_sets_are_not_interchangeable(self):
        """Guards the assumption that broke #6749: sets differ per subcommand."""
        from dashboard.app import GH_PR_LIST_VALID_FIELDS, GH_REPO_VIEW_VALID_FIELDS

        assert GH_PR_LIST_VALID_FIELDS != GH_REPO_VIEW_VALID_FIELDS
        # `repository` is in neither — it belongs to `gh search prs`.
        assert "repository" not in GH_PR_LIST_VALID_FIELDS
        assert "repository" not in GH_REPO_VIEW_VALID_FIELDS

    def test_fields_cover_what_fetch_uses(self):
        """Keys _fetch_github_data and the frontend read must be requested."""
        from dashboard.app import REPO_VIEW_FIELDS

        for field in ("name", "isArchived", "pushedAt", "defaultBranchRef",
                      "url", "isPrivate", "description", "stargazerCount"):
            assert field in REPO_VIEW_FIELDS

    def test_requested_fields_still_accepted_by_live_gh(self):
        """Removal direction only — additions are gh's business, not a failure."""
        import pytest
        import shutil
        from dashboard.app import REPO_VIEW_FIELDS

        gh = shutil.which("gh")
        if not gh:
            pytest.skip("gh CLI unavailable")
        proc = subprocess.run(
            [gh, "repo", "view", "cli/cli", "--json", "__bogus__"],
            capture_output=True, text=True, timeout=30,
        )
        text = proc.stdout + proc.stderr
        if "Available fields:" not in text:
            pytest.skip("gh output format changed")
        live = {l.strip() for l in text.split("Available fields:", 1)[1].splitlines() if l.strip()}

        missing = set(REPO_VIEW_FIELDS) - live
        assert not missing, (
            f"The installed gh no longer accepts: {sorted(missing)}. "
            "Every repo fetch would fail. Update REPO_VIEW_FIELDS in dashboard/app.py."
        )
