"""Tests for /api/tool-stats endpoint (card #6048).

Exercises the live brain.db when present (mostly an end-to-end smoke against
the user's real machine). Skip-gracefully if brain.db is missing so CI on
fresh clones still passes.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app


client = TestClient(app)

BRAIN_DB = Path.home() / "projects" / "ai-memory" / "brain.db"
BRAIN_AVAILABLE = BRAIN_DB.is_file()


def _empty_response_shape(payload: dict) -> None:
    """Assert the empty-DB response shape (used when brain.db is unavailable)."""
    assert payload == {
        "by_date": [],
        "by_project": [],
        "by_model": [],
        "projects": [],
        "models": [],
    }


def test_tool_stats_default_shape_when_brain_db_missing():
    """When brain.db is absent the endpoint must return the empty shape, not
    500. Simulates a fresh clone or CI without portfolio state."""
    if BRAIN_AVAILABLE:
        pytest.skip("brain.db exists locally; covered by other tests")
    response = client.get("/api/tool-stats")
    assert response.status_code == 200
    _empty_response_shape(response.json())


def test_tool_stats_default_returns_expected_keys():
    """Response always carries the five top-level series/lists, even when the
    DB exists and is queried."""
    response = client.get("/api/tool-stats")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"by_date", "by_project", "by_model", "projects", "models"}


@pytest.mark.skipif(not BRAIN_AVAILABLE, reason="brain.db not present on this machine")
def test_tool_stats_by_model_includes_known_models():
    """When data is present, by_model should be non-empty and the models list
    should include at least one of the canonical opus/sonnet/haiku families
    that this user's log captures (validates the new model breakdown).

    Substring match so this passes both for normalized names (e.g. "opus")
    and full model IDs (e.g. "claude-opus-4-7")."""
    response = client.get("/api/tool-stats?days=90")
    payload = response.json()
    assert payload["by_model"], "by_model should be populated when brain.db has data"
    # Models list is the de-duplicated set of model names appearing in by_model.
    derived = {row["model"] for row in payload["by_model"]}
    assert set(payload["models"]) == derived
    families = ("opus", "sonnet", "haiku")
    assert any(any(fam in m for fam in families) for m in payload["models"]), (
        f"expected at least one opus/sonnet/haiku model in window, got {payload['models']}"
    )


@pytest.mark.skipif(not BRAIN_AVAILABLE, reason="brain.db not present on this machine")
def test_tool_stats_filter_by_model_scopes_all_three_series():
    """A model filter must restrict every series (by_model, by_project,
    by_date totals) to that single model — they share the same WHERE
    clause server-side, but the test guards against future divergence."""
    # Probe the unfiltered response for an available model.
    base = client.get("/api/tool-stats?days=90").json()
    if not base["models"]:
        pytest.skip("no models in window")
    target = base["models"][0]

    filtered = client.get(f"/api/tool-stats?days=90&model={target}").json()

    # by_model only carries the target.
    seen_models = {row["model"] for row in filtered["by_model"]}
    assert seen_models <= {target}, f"by_model leaked: {seen_models - {target}}"
    assert filtered["models"] == [target] or filtered["models"] == []

    # by_date totals must equal the per-day target-model counts from the
    # unfiltered response. If by_date wasn't model-scoped, it would carry
    # totals across all models and these would diverge.
    unfiltered_target_per_day: dict[str, int] = {}
    for row in base["by_model"]:
        if row["model"] == target:
            unfiltered_target_per_day[row["date"]] = (
                unfiltered_target_per_day.get(row["date"], 0) + row["count"]
            )
    filtered_per_day = {
        row["date"]: row["total"] for row in filtered["by_date"] if row["total"] > 0
    }
    assert filtered_per_day == unfiltered_target_per_day, (
        "by_date totals don't match the target-model counts derived from the "
        "unfiltered by_model series — the model filter isn't being applied "
        "uniformly across all three queries"
    )


def test_tool_stats_filter_by_unknown_tool_returns_empty():
    """A nonsense tool filter returns empty series, not 500. by_date is still
    a fully-padded date series of zeros so the frontend chart renders."""
    response = client.get("/api/tool-stats?tool=NonexistentToolXYZZY&days=7")
    assert response.status_code == 200
    payload = response.json()
    assert payload["by_project"] == []
    assert payload["by_model"] == []
    assert payload["projects"] == []
    assert payload["models"] == []
    # by_date is zero-filled across the 7-day window.
    assert len(payload["by_date"]) == 7
    assert all(row["total"] == 0 for row in payload["by_date"])


def test_tool_stats_days_clamps_to_valid_range():
    """days <= 0 should clamp to 1 (not negative-zero or 365), days > 365
    should clamp to 365. Both must respond 200."""
    low = client.get("/api/tool-stats?days=0")
    high = client.get("/api/tool-stats?days=9999")
    assert low.status_code == 200
    assert high.status_code == 200
    assert len(low.json()["by_date"]) == 1
    assert len(high.json()["by_date"]) == 365


@pytest.mark.skipif(not BRAIN_AVAILABLE, reason="brain.db not present on this machine")
def test_tool_stats_apr_18_zero_search_anomaly_visible():
    """Regression test for card #6048's motivating use-case: April 18 2026
    should appear as a zero-call day in the WebSearch by_date series."""
    # Window wide enough to span Apr 18 from "today" — request 365 days.
    response = client.get("/api/tool-stats?tool=WebSearch&days=365")
    payload = response.json()
    apr_18 = [row for row in payload["by_date"] if row["date"] == "2026-04-18"]
    if not apr_18:
        pytest.skip("Apr 18 outside the 365-day window from now")
    assert apr_18[0]["total"] == 0, (
        f"Apr 18 expected to show the zero-search anomaly, got {apr_18[0]['total']}"
    )
