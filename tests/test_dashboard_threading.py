"""Blocking dashboard handlers must not freeze the event loop (#8093, PR 9).

A handler declared ``async def`` that does blocking work (sqlite, subprocess,
urlopen, a directory scan) stalls every other request until it returns. These
tests run a real uvicorn server, because TestClient serializes requests and
would hide the stall, and prove that ``/api/health`` answers while a slow
handler is mid-flight.
"""

import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

import dashboard.app as dashboard_app

SLOW_SECONDS = 1.5
HEALTH_BUDGET_SECONDS = 0.75


@pytest.fixture
def live_server():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(dashboard_app.app, log_level="warning", lifespan="off")
    )
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{base}/api/health", timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        raise RuntimeError("test server did not start")
    yield base
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


def _slow(result):
    def _inner(*_args, **_kwargs):
        time.sleep(SLOW_SECONDS)
        return result

    return _inner


def _health_latency_during(base, slow_request):
    """Start ``slow_request`` in a thread, then time /api/health meanwhile."""
    done = threading.Event()

    def _go():
        try:
            slow_request()
        finally:
            done.set()

    threading.Thread(target=_go, daemon=True).start()
    time.sleep(0.3)  # let the slow request reach its blocking call
    assert not done.is_set(), "slow request finished too early to prove anything"
    started = time.monotonic()
    response = httpx.get(f"{base}/api/health", timeout=10)
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert done.wait(timeout=10)
    return elapsed


def test_refresh_scan_does_not_block_other_requests(live_server, monkeypatch):
    monkeypatch.setattr(dashboard_app, "discover_projects", _slow([]))
    monkeypatch.setattr(dashboard_app, "rebuild_project_graph", lambda: None)

    elapsed = _health_latency_during(
        live_server, lambda: httpx.post(f"{live_server}/api/refresh", timeout=10)
    )

    assert elapsed < HEALTH_BUDGET_SECONDS, f"health waited {elapsed:.2f}s behind a scan"


def test_alerts_do_not_block_other_requests(live_server, monkeypatch):
    monkeypatch.setattr(dashboard_app, "get_all_alerts", _slow([]))

    elapsed = _health_latency_during(
        live_server, lambda: httpx.get(f"{live_server}/api/alerts", timeout=10)
    )

    assert elapsed < HEALTH_BUDGET_SECONDS, f"health waited {elapsed:.2f}s behind alerts"


def test_unexpected_error_shapes_are_unchanged(monkeypatch):
    """500 bodies the frontend reads: calendar uses ``detail``, the rest do not."""

    def boom(*_a, **_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(dashboard_app, "_get_cal_manager", boom)
    client = TestClient(dashboard_app.app, raise_server_exceptions=False)

    response = client.get("/api/calendar/events")
    assert response.status_code == 500
    assert response.json() == {"detail": "kaboom"}

    monkeypatch.setattr(dashboard_app, "get_all_alerts", boom)
    response = client.get("/api/alerts")
    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_error",
        "message": "An unexpected error occurred",
    }

    assert client.get("/api/tasks/99999999").status_code == 404
    assert client.get("/api/tasks/not-a-number").status_code in (400, 404, 422)


def test_concurrent_marker_creates_are_not_lost(monkeypatch, tmp_path):
    """Marker writes are load-modify-save on one file; in the threadpool they
    must not interleave and drop each other's markers."""
    monkeypatch.setattr(dashboard_app, "MARKERS_PATH", tmp_path / "markers.json")
    real_load = dashboard_app._load_markers

    def slow_load():
        markers = real_load()
        time.sleep(0.05)  # widen the read-modify-write window
        return markers

    monkeypatch.setattr(dashboard_app, "_load_markers", slow_load)
    threads = [
        threading.Thread(
            target=dashboard_app.create_marker,
            args=(dashboard_app.MarkerCreateRequest(date="2026-10-0%d" % (i + 1), label=f"m{i}"),),
        )
        for i in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    saved = json.loads((tmp_path / "markers.json").read_text())
    assert sorted(m["label"] for m in saved) == [f"m{i}" for i in range(8)]
