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
from unittest.mock import patch, MagicMock
from time import time as _time


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


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

        with patch("dashboard.app._gh_json", side_effect=mock_gh_json):
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

        with patch("dashboard.app._gh_json", side_effect=mock_gh_json):
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
            if args == ["api", "/user"]:
                return {"login": "testuser"}
            if args[0] == "repo" and args[1] == "view":
                name = args[2].split("/")[1]
                if name == "missing-repo":
                    return None
                return {
                    "name": name,
                    "isArchived": name == "archived-repo",
                    "pushedAt": "2020-01-01T00:00:00Z",
                    "defaultBranchRef": {"name": "main"},
                }
            return []

        with patch("dashboard.app._gh_json", side_effect=selective_gh_json):
            with patch("dashboard.app._get_tracked_repo_names", return_value=tracked):
                result = _fetch_github_data()

        assert result["summary"]["tracked_projects"] == 3
        assert result["summary"]["repos_found_on_github"] == 2
        assert result["summary"]["repos_not_on_github"] == 1
        assert result["summary"]["archived_repos"] == 1


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
