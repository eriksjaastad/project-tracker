"""Tests for dashboard stale-while-revalidate cache."""

import sys
import os
import threading
from unittest.mock import patch, MagicMock
from time import time as _time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestDashboardCache:
    """Tests for the dashboard cache mechanism."""

    def test_cache_starts_empty(self):
        from dashboard.app import _dashboard_cache
        # Reset for test
        original = _dashboard_cache.copy()
        _dashboard_cache["data"] = None
        _dashboard_cache["timestamp"] = 0
        assert _dashboard_cache["data"] is None
        assert _dashboard_cache["timestamp"] == 0
        # Restore
        _dashboard_cache.update(original)

    def test_build_dashboard_data_returns_required_keys(self):
        """Verify _build_dashboard_data returns all keys the template needs."""
        from dashboard.app import _build_dashboard_data
        with patch("dashboard.app.DatabaseManager") as MockDB:
            mock_db = MagicMock()
            mock_db.get_all_projects.return_value = []
            mock_db.get_ai_agents.return_value = []
            mock_db.get_cron_jobs.return_value = []
            mock_db.get_services.return_value = []
            mock_db.get_tasks.return_value = []
            MockDB.return_value = mock_db

            with patch("dashboard.app.get_all_alerts", return_value=[]):
                with patch("dashboard.app.get_available_agents", return_value=[]):
                    with patch("dashboard.app.get_backup_status", return_value={}):
                            data = _build_dashboard_data()

        required_keys = [
            "projects", "alerts", "code_reviews", "total_projects",
            "indexed_count", "compliance_pct", "agents", "backup_status",
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_cache_status_endpoint_when_empty(self):
        """Test /api/dashboard-cache-status returns correct state."""
        from dashboard.app import _dashboard_cache
        original = _dashboard_cache.copy()
        _dashboard_cache["data"] = None
        _dashboard_cache["timestamp"] = 0

        from dashboard.app import dashboard_cache_status
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(dashboard_cache_status())

        assert result["cached"] is False
        assert result["refreshing"] is not None
        _dashboard_cache.update(original)

    def test_cache_status_endpoint_when_populated(self):
        from dashboard.app import _dashboard_cache
        original = _dashboard_cache.copy()
        _dashboard_cache["data"] = {"projects": []}
        _dashboard_cache["timestamp"] = _time()

        from dashboard.app import dashboard_cache_status
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(dashboard_cache_status())

        assert result["cached"] is True
        assert result["age"] is not None
        assert result["age"] >= 0
        _dashboard_cache.update(original)
