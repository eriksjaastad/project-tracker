"""Tests for /api/bash-stats anomaly telemetry."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import dashboard.app as dashboard_app


def _freeze_now(monkeypatch: pytest.MonkeyPatch, frozen_now: datetime) -> None:
    class FrozenDateTime:
        @classmethod
        def now(cls) -> datetime:
            return frozen_now

    monkeypatch.setattr(dashboard_app, "datetime", FrozenDateTime)


def _brain_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    brain_dir = tmp_path / "projects" / "ai-memory"
    brain_dir.mkdir(parents=True, exist_ok=True)
    return brain_dir / "brain.db"


def test_bash_stats_returns_empty_payload_when_brain_db_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _brain_db_path(tmp_path, monkeypatch)
    _freeze_now(monkeypatch, datetime(2026, 4, 21, 12, 0, 0))

    response = TestClient(dashboard_app.app).get("/api/bash-stats?days=3")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "by_date": [],
        "by_project": [],
        "projects": [],
        "summary": {
            "total": 0,
            "errors": 0,
            "error_rate": 0.0,
            "retries": 0,
            "retry_rate": 0.0,
            "hook_blocks": 0,
            "hook_block_rate": 0.0,
            "auth_errors": 0,
            "auth_error_rate": 0.0,
        },
        "anomalies_by_date": [],
        "error_kinds": [],
        "top_prefixes": [],
        "by_caller_type": [],
    }


def test_bash_stats_returns_empty_payload_when_bash_calls_table_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    brain_db = _brain_db_path(tmp_path, monkeypatch)
    _freeze_now(monkeypatch, datetime(2026, 4, 21, 12, 0, 0))

    with sqlite3.connect(brain_db) as conn:
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
        conn.commit()

    response = TestClient(dashboard_app.app).get("/api/bash-stats?days=3")

    assert response.status_code == 200, response.text
    assert response.json()["summary"]["total"] == 0
    assert response.json()["anomalies_by_date"] == []
    assert response.json()["error_kinds"] == []


def test_bash_stats_aggregates_anomaly_telemetry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    brain_db = _brain_db_path(tmp_path, monkeypatch)
    _freeze_now(monkeypatch, datetime(2026, 4, 21, 12, 0, 0))

    with sqlite3.connect(brain_db) as conn:
        conn.execute(
            """
            CREATE TABLE bash_calls (
                invoked_at TEXT NOT NULL,
                project TEXT,
                is_error INTEGER DEFAULT 0,
                is_retry INTEGER DEFAULT 0,
                is_hook_blocked INTEGER DEFAULT 0,
                is_auth_error INTEGER DEFAULT 0,
                error_kind TEXT,
                caller_type TEXT,
                command_prefix TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO bash_calls (
                invoked_at, project, is_error, is_retry, is_hook_blocked,
                is_auth_error, error_kind, caller_type, command_prefix
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-04-19T09:00:00", "project-tracker", 1, 1, 0, 0, "usage_error", "main", "npm test"),
                ("2026-04-19T09:05:00", "project-tracker", 0, 0, 0, 0, None, "main", "npm test"),
                ("2026-04-20T10:00:00", "project-tracker", 1, 0, 1, 0, "hook_block", "subagent", "git push"),
                ("2026-04-20T10:15:00", "ai-memory", 1, 1, 0, 1, "auth_error", "subagent", "git push"),
                ("2026-04-21T11:00:00", None, 0, 0, 0, 0, None, "main", "npm test"),
                ("2026-04-18T07:00:00", "project-tracker", 1, 1, 1, 1, "usage_error", "main", "old prefix"),
            ],
        )
        conn.commit()

    response = TestClient(dashboard_app.app).get("/api/bash-stats?days=3")

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["by_date"] == [
        {"date": "2026-04-19", "error_rate": 50.0, "total": 2, "errors": 1},
        {"date": "2026-04-20", "error_rate": 100.0, "total": 2, "errors": 2},
        {"date": "2026-04-21", "error_rate": 0.0, "total": 1, "errors": 0},
    ]
    assert payload["projects"] == ["ai-memory", "project-tracker", "unknown"]
    assert payload["by_project"] == [
        {"date": "2026-04-19", "project": "project-tracker", "error_rate": 50.0},
        {"date": "2026-04-20", "project": "ai-memory", "error_rate": 100.0},
        {"date": "2026-04-20", "project": "project-tracker", "error_rate": 100.0},
        {"date": "2026-04-21", "project": "unknown", "error_rate": 0.0},
    ]
    assert payload["summary"] == {
        "total": 5,
        "errors": 3,
        "error_rate": 60.0,
        "retries": 2,
        "retry_rate": 40.0,
        "hook_blocks": 1,
        "hook_block_rate": 20.0,
        "auth_errors": 1,
        "auth_error_rate": 20.0,
    }
    assert payload["anomalies_by_date"] == [
        {"date": "2026-04-19", "retries": 1, "hook_blocks": 0, "auth_errors": 0, "usage_errors": 1},
        {"date": "2026-04-20", "retries": 1, "hook_blocks": 1, "auth_errors": 1, "usage_errors": 0},
        {"date": "2026-04-21", "retries": 0, "hook_blocks": 0, "auth_errors": 0, "usage_errors": 0},
    ]
    assert payload["error_kinds"] == [
        {"error_kind": "auth_error", "count": 1},
        {"error_kind": "hook_block", "count": 1},
        {"error_kind": "usage_error", "count": 1},
    ]
    assert payload["top_prefixes"] == [
        {"command_prefix": "npm test", "total": 3, "errors": 1, "hook_blocks": 0, "auth_errors": 0},
        {"command_prefix": "git push", "total": 2, "errors": 2, "hook_blocks": 1, "auth_errors": 1},
    ]
    assert payload["by_caller_type"] == [
        {"caller_type": "main", "total": 3, "errors": 1, "error_rate": 33.3},
        {"caller_type": "subagent", "total": 2, "errors": 2, "error_rate": 100.0},
    ]
