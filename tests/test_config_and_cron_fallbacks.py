"""Regression tests for config and cron fallback behavior."""

import importlib
from datetime import datetime, timedelta

import scripts.discovery.cron_monitor as cron_monitor


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
