"""Tests for /api/api-cost-stats endpoint (card #5995 sub-PR 2c).

Verifies the dashboard endpoint that reads api_cost_logs from ai-memory's
brain.db. Most tests are hermetic — they construct a temp brain.db,
populate it, monkeypatch the endpoint's path resolver, and exercise the
endpoint via the FastAPI TestClient.
"""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app


client = TestClient(app)


@pytest.fixture
def temp_brain_db(tmp_path, monkeypatch):
    """Build a temp brain.db with api_cost_logs + a small fixture set, and
    redirect the endpoint to read from it via monkeypatching `Path.home`
    so `~/projects/ai-memory/brain.db` resolves into tmp_path."""
    home = tmp_path / "home"
    (home / "projects" / "ai-memory").mkdir(parents=True)
    db_path = home / "projects" / "ai-memory" / "brain.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE api_cost_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER DEFAULT 0,
            cache_creation_tokens INTEGER DEFAULT 0,
            cost_usd REAL,
            project TEXT,
            caller TEXT,
            session_id TEXT,
            source_machine TEXT,
            service TEXT
        )
        """
    )
    today = date.today()
    rows = [
        # (timestamp, provider, model, project, caller, cost_usd, calls=1 each)
        ((today - timedelta(days=1)).isoformat(), "anthropic", "claude-opus-4-7", "ai-memory", "batcher.classify", 0.50),
        ((today - timedelta(days=1)).isoformat(), "anthropic", "claude-opus-4-7", "ai-memory", "summarizer.task", 0.30),
        ((today - timedelta(days=2)).isoformat(), "anthropic", "claude-haiku-4-5", "ai-memory", "batcher.classify", 0.05),
        ((today - timedelta(days=2)).isoformat(), "openai", "gpt-4.1-mini", "trading-copilot", "alpha_audit", 0.10),
        (today.isoformat(), "anthropic", "claude-opus-4-7", "project-tracker", "dashboard", 0.20),
    ]
    for ts, provider, model, project, caller, cost in rows:
        conn.execute(
            """
            INSERT INTO api_cost_logs (
                timestamp, provider, model, project, caller, cost_usd,
                input_tokens, output_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, provider, model, project, caller, cost, 100, 50),
        )
    conn.commit()
    conn.close()

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return db_path


def test_api_cost_stats_empty_when_db_missing(tmp_path, monkeypatch):
    """Endpoint must not crash when brain.db is absent — returns the empty
    response shape."""
    nonexistent = tmp_path / "nowhere"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: nonexistent))
    response = client.get("/api/api-cost-stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["by_date"] == []
    assert payload["summary"]["total_calls"] == 0


def test_api_cost_stats_default_keys_present():
    """Response always carries the expected top-level keys."""
    response = client.get("/api/api-cost-stats")
    assert response.status_code == 200
    payload = response.json()
    expected_keys = {
        "by_date", "by_model", "by_project", "by_caller",
        "models", "projects", "callers", "summary",
    }
    assert set(payload.keys()) == expected_keys


def test_api_cost_stats_summary_totals_match_rows(temp_brain_db):
    """summary.total_calls + total_cost_usd must match the fixture data."""
    response = client.get("/api/api-cost-stats?days=7")
    payload = response.json()
    assert payload["summary"]["total_calls"] == 5
    # 0.50 + 0.30 + 0.05 + 0.10 + 0.20 = 1.15
    assert payload["summary"]["total_cost_usd"] == pytest.approx(1.15)


def test_api_cost_stats_by_model_aggregates(temp_brain_db):
    """by_model rolls up cost+calls per (date, model)."""
    response = client.get("/api/api-cost-stats?days=7")
    payload = response.json()
    assert set(payload["models"]) == {
        "claude-opus-4-7", "claude-haiku-4-5", "gpt-4.1-mini"
    }
    # Two opus calls on (today-1), summing to 0.80.
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    opus_yest = [
        r for r in payload["by_model"]
        if r["date"] == yesterday and r["model"] == "claude-opus-4-7"
    ]
    assert len(opus_yest) == 1
    assert opus_yest[0]["calls"] == 2
    assert opus_yest[0]["cost_usd"] == pytest.approx(0.80)


def test_api_cost_stats_provider_filter(temp_brain_db):
    """Filtering by provider scopes all series — Anthropic rows only."""
    response = client.get("/api/api-cost-stats?days=7&provider=anthropic")
    payload = response.json()
    assert payload["summary"]["total_calls"] == 4
    # Only anthropic models surface.
    assert set(payload["models"]) == {"claude-opus-4-7", "claude-haiku-4-5"}
    assert "gpt-4.1-mini" not in payload["models"]


def test_api_cost_stats_caller_filter(temp_brain_db):
    """Caller filter scopes results."""
    response = client.get("/api/api-cost-stats?days=7&caller=batcher.classify")
    payload = response.json()
    assert payload["summary"]["total_calls"] == 2
    assert set(payload["callers"]) == {"batcher.classify"}


def test_api_cost_stats_days_clamps(temp_brain_db):
    """days <= 0 clamps to 1, > 365 clamps to 365 — both must respond 200."""
    low = client.get("/api/api-cost-stats?days=0")
    high = client.get("/api/api-cost-stats?days=9999")
    assert low.status_code == 200
    assert high.status_code == 200
    assert len(low.json()["by_date"]) == 1
    assert len(high.json()["by_date"]) == 365


def test_api_cost_stats_by_date_is_zero_filled(temp_brain_db):
    """by_date covers the full window even when most days have no data,
    so the chart x-axis is contiguous."""
    response = client.get("/api/api-cost-stats?days=7")
    payload = response.json()
    assert len(payload["by_date"]) == 7
    # At least one day has 0 calls (fixtures only populate today/-1/-2).
    zero_days = [r for r in payload["by_date"] if r["calls"] == 0]
    assert zero_days, "expected at least one zero-day in the 7-day window"
