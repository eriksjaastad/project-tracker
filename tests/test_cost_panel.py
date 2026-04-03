"""Tests for the API cost proxy endpoint (#5447)."""

import sys
import os
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dashboard.app import app

client = TestClient(app)


def test_cost_proxy_rejects_invalid_path():
    """Path validation blocks unknown endpoints."""
    response = client.get("/api/costs/admin")
    assert response.status_code == 400

    response = client.get("/api/costs/secret/keys")
    assert response.status_code == 400


def test_cost_proxy_allows_valid_paths():
    """All 6 known cost endpoints are allowed through the allowlist."""
    import httpx as _httpx

    for path in ("daily", "providers", "projects", "models", "callers", "usage"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(_httpx, "AsyncClient", return_value=mock_client):
            response = client.get(f"/api/costs/{path}")
            assert response.status_code == 200, f"Failed for path: {path}"


def test_cost_proxy_returns_502_on_connection_error():
    """Proxy returns 502 when upstream is unreachable."""
    import httpx as _httpx

    mock_client = AsyncMock()
    mock_client.get.side_effect = _httpx.RequestError("Connection refused")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(_httpx, "AsyncClient", return_value=mock_client):
        response = client.get("/api/costs/daily")
        assert response.status_code == 502
        assert "unavailable" in response.json()["error"]


def test_cost_proxy_passes_query_params():
    """Query parameters are forwarded to upstream."""
    import httpx as _httpx

    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(_httpx, "AsyncClient", return_value=mock_client):
        client.get("/api/costs/daily?days=30")
        call_url = mock_client.get.call_args[0][0]
        assert "days=30" in call_url
