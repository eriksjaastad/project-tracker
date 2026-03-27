"""Regression tests for config and cron fallback behavior."""

import importlib
import sqlite3
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import scripts.discovery.cron_monitor as cron_monitor
import scripts.db.schema as schema
from scripts.db.schema import _check_fresh_database


def test_config_uses_external_backup_dir_override(tmp_path, monkeypatch):
    projects_root = tmp_path / "projects"
    backup_dir = tmp_path / "external-backups"
    projects_root.mkdir()

    monkeypatch.setenv("PROJECTS_ROOT", str(projects_root))
    monkeypatch.setenv("PT_EXTERNAL_BACKUP_DIR", str(backup_dir))

    import scripts.config as config

    reloaded = importlib.reload(config)

    assert reloaded.EXTERNAL_BACKUP_DIR == backup_dir


def test_config_defaults_external_backup_dir_under_home(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    projects_root = tmp_path / "projects"
    home_dir.mkdir()
    projects_root.mkdir()

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("PROJECTS_ROOT", str(projects_root))
    monkeypatch.delenv("PT_EXTERNAL_BACKUP_DIR", raising=False)

    import scripts.config as config

    reloaded = importlib.reload(config)

    assert reloaded.EXTERNAL_BACKUP_DIR == home_dir / ".project-tracker" / "backups"


def test_is_valid_cron_accepts_special_alias_without_croniter(monkeypatch):
    monkeypatch.setattr(cron_monitor, "croniter", None)

    assert cron_monitor.is_valid_cron("@daily") is True
    assert cron_monitor.is_valid_cron("0 0 * * *") is False


def test_get_expected_next_run_handles_missing_or_broken_croniter(monkeypatch):
    last_run = datetime(2026, 3, 1, 12, 0, 0)

    monkeypatch.setattr(cron_monitor, "croniter", None)
    assert cron_monitor.get_expected_next_run("0 * * * *", last_run) is None
    assert cron_monitor.get_expected_next_run("@hourly", last_run) == last_run + timedelta(hours=1)

    def broken_croniter(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cron_monitor, "croniter", broken_croniter)
    assert cron_monitor.get_expected_next_run("0 * * * *", last_run) is None


def test_fresh_database_check_allows_scanned_projects_without_tasks(tmp_path, monkeypatch):
    db_path = tmp_path / "tracker.db"
    fingerprint_path = tmp_path / ".db-fingerprint"

    monkeypatch.delenv("PT_ALLOW_FRESH_DB", raising=False)
    monkeypatch.delenv("PT_TEST_MODE", raising=False)
    monkeypatch.setattr(schema, "sys", types.SimpleNamespace(modules={k: v for k, v in sys.modules.items() if k != "pytest"}))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)")
    cursor.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT)")
    cursor.execute("INSERT INTO projects (id, name) VALUES ('smart-invoice-workflow', 'Smart Invoice Workflow')")
    conn.commit()
    conn.close()

    fingerprint_path.write_text("test-fingerprint")

    _check_fresh_database(Path(db_path))


def test_fresh_database_check_blocks_when_prior_task_activity_exists(tmp_path, monkeypatch):
    db_path = tmp_path / "tracker.db"
    fingerprint_path = tmp_path / ".db-fingerprint"
    backup_dir = tmp_path / "backups"

    monkeypatch.delenv("PT_ALLOW_FRESH_DB", raising=False)
    monkeypatch.delenv("PT_TEST_MODE", raising=False)
    monkeypatch.setattr(schema, "sys", types.SimpleNamespace(modules={k: v for k, v in sys.modules.items() if k != "pytest"}))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)")
    cursor.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT)")
    cursor.execute("CREATE TABLE task_history (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, project_id TEXT, event_type TEXT, timestamp TEXT)")
    cursor.execute("INSERT INTO projects (id, name) VALUES ('smart-invoice-workflow', 'Smart Invoice Workflow')")
    cursor.execute("INSERT INTO task_history (task_id, project_id, event_type, timestamp) VALUES (1, 'smart-invoice-workflow', 'created', '2026-03-26T00:00:00')")
    conn.commit()
    conn.close()

    fingerprint_path.write_text("test-fingerprint")
    backup_dir.mkdir()
    (backup_dir / "tasks_safety_backup_20260327_000000.json").write_text("{}")

    with pytest.raises(Exception) as excinfo:
        _check_fresh_database(Path(db_path))

    assert "SUSPICIOUS EMPTY TASK BOARD DETECTED" in str(excinfo.value)
