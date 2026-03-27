"""Tests for the GitHub activity feed module."""

import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

# Ensure scripts/ is importable
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from scripts.discovery.activity_feed import get_activity_feed, _connect


class TestConnect:
    """Tests for _connect()."""

    def test_returns_none_when_no_env_vars(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _connect() is None

    def test_returns_none_with_only_url(self):
        with patch.dict(os.environ, {"TURSO_KANBAN_URL": "libsql://test"}, clear=True):
            assert _connect() is None

    def test_falls_back_to_kanban_vars(self):
        mock_libsql = MagicMock()
        with patch.dict(os.environ, {
            "TURSO_KANBAN_URL": "libsql://test",
            "TURSO_KANBAN_TOKEN": "tok123",
        }, clear=True):
            with patch.dict("sys.modules", {"libsql": mock_libsql}):
                conn = _connect()
                mock_libsql.connect.assert_called_once_with("libsql://test", auth_token="tok123")
                assert conn is not None

    def test_activity_vars_take_precedence(self):
        mock_libsql = MagicMock()
        with patch.dict(os.environ, {
            "TURSO_ACTIVITY_URL": "libsql://activity",
            "TURSO_ACTIVITY_TOKEN": "activity_tok",
            "TURSO_KANBAN_URL": "libsql://kanban",
            "TURSO_KANBAN_TOKEN": "kanban_tok",
        }, clear=True):
            with patch.dict("sys.modules", {"libsql": mock_libsql}):
                _connect()
                mock_libsql.connect.assert_called_once_with("libsql://activity", auth_token="activity_tok")

    def test_returns_none_on_import_error(self):
        with patch.dict(os.environ, {
            "TURSO_KANBAN_URL": "libsql://test",
            "TURSO_KANBAN_TOKEN": "tok",
        }, clear=True):
            with patch.dict("sys.modules", {"libsql": None}):
                result = _connect()
                assert result is None


class TestGetActivityFeed:
    """Tests for get_activity_feed()."""

    def test_returns_empty_when_no_connection(self):
        with patch("scripts.discovery.activity_feed._connect", return_value=None):
            assert get_activity_feed() == []

    def test_returns_grouped_events(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        mock_cursor.fetchall.return_value = [
            ("repo-a", "commit.pushed", "bot", "fix stuff", "https://gh/1", now),
            ("repo-a", "commit.pushed", "bot", "add thing", "https://gh/2", now),
            ("repo-b", "pull_request.merged", "user", "merge PR", "https://gh/3", now),
        ]

        with patch("scripts.discovery.activity_feed._connect", return_value=mock_conn):
            feed = get_activity_feed(limit_per_repo=4)

        assert len(feed) == 2
        slugs = {r["repo_slug"] for r in feed}
        assert slugs == {"repo-a", "repo-b"}

        repo_a = next(r for r in feed if r["repo_slug"] == "repo-a")
        assert len(repo_a["events"]) == 2
        assert repo_a["idle_hours"] >= 0

    def test_returns_empty_on_query_error(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("DB error")

        with patch("scripts.discovery.activity_feed._connect", return_value=mock_conn):
            assert get_activity_feed() == []

    def test_sorts_by_most_recent(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("old-repo", "push", "bot", "old", "#", "2026-01-01T00:00:00Z"),
            ("new-repo", "push", "bot", "new", "#", "2026-03-26T00:00:00Z"),
        ]

        with patch("scripts.discovery.activity_feed._connect", return_value=mock_conn):
            feed = get_activity_feed()

        assert feed[0]["repo_slug"] == "new-repo"
        assert feed[1]["repo_slug"] == "old-repo"
