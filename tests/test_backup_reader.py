from __future__ import annotations

from datetime import datetime, timedelta, timezone
import plistlib
from pathlib import Path

from scripts.discovery import backup_reader


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _touch_with_age(path: Path, age: timedelta, size: int = 1024) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    ts = (datetime.now(timezone.utc) - age).timestamp()
    path.touch()
    import os

    os.utime(path, (ts, ts))


def _iso_age(age: timedelta) -> str:
    return (datetime.now(timezone.utc) - age).isoformat()


def test_get_backup_status_reports_healthy_local_and_cloud(tmp_path, monkeypatch):
    backup_dir = tmp_path / "full-backups"
    log_path = tmp_path / "backup.log"
    launch_agent_path = tmp_path / "LaunchAgents" / "com.eriksjaastad.pt-backup.plist"
    rclone_config_path = tmp_path / "rclone.conf"
    db_path = tmp_path / "data" / "tracker.db"
    safety_dir = db_path.parent / "backups"

    _touch_with_age(backup_dir / "tracker_20260423_141355.db", timedelta(hours=2))
    _touch_with_age(safety_dir / "tasks_safety_backup_20260423_141355.json", timedelta(hours=1), size=128)
    _write(
        log_path,
        "\n".join(
            [
                f"{_iso_age(timedelta(hours=2))} | backup | 3510272 bytes | /tmp/tracker_20260423_141355.db",
                f"{_iso_age(timedelta(hours=2))} | cloud_copy | success | b2:tracker-backups/tracker_daily_20260423.db",
            ]
        ),
    )
    launch_agent_path.parent.mkdir(parents=True, exist_ok=True)
    with launch_agent_path.open("wb") as handle:
        plistlib.dump({"Label": "com.eriksjaastad.pt-backup", "StartInterval": 21600}, handle)
    _write(rclone_config_path, "[b2]\ntype = b2\n")

    monkeypatch.setenv("PT_FULL_BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("PT_BACKUP_LOG_PATH", str(log_path))
    monkeypatch.setenv("PT_BACKUP_LAUNCH_AGENT_PATH", str(launch_agent_path))
    monkeypatch.setenv("PT_BACKUP_RCLONE_DEST", "b2:tracker-backups")
    monkeypatch.setenv("RCLONE_CONFIG_PATH", str(rclone_config_path))
    monkeypatch.setattr(backup_reader, "DATABASE_PATH", db_path)

    status = backup_reader.get_backup_status()

    assert status["status"] == "healthy"
    assert status["local_full"]["count"] == 1
    assert status["cloud"]["status"] == "healthy"
    assert status["cloud"]["configured_dest"] == "b2:tracker-backups"
    assert status["launch_agent"]["schedule"] == "Every 6h"
    assert status["remotes"] == ["b2"]


def test_get_backup_status_reports_critical_when_no_local_backups(tmp_path, monkeypatch):
    backup_dir = tmp_path / "full-backups"
    monkeypatch.setenv("PT_FULL_BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("PT_BACKUP_LOG_PATH", str(tmp_path / "missing.log"))
    monkeypatch.setenv("PT_BACKUP_LAUNCH_AGENT_PATH", str(tmp_path / "missing.plist"))
    monkeypatch.delenv("PT_BACKUP_RCLONE_DEST", raising=False)
    monkeypatch.setattr(backup_reader, "DATABASE_PATH", tmp_path / "data" / "tracker.db")

    status = backup_reader.get_backup_status()

    assert status["status"] == "critical"
    assert status["local_full"]["status"] == "critical"
    assert status["local_full"]["state"] == "missing_directory"
    assert "No local full database backups found" in status["message"]


def test_get_backup_status_warns_when_cloud_copy_is_unconfigured(tmp_path, monkeypatch):
    backup_dir = tmp_path / "full-backups"
    log_path = tmp_path / "backup.log"
    _touch_with_age(backup_dir / "tracker_20260423_141355.db", timedelta(hours=2))
    _write(log_path, f"{_iso_age(timedelta(hours=2))} | backup | 3510272 bytes | /tmp/tracker_20260423_141355.db")

    monkeypatch.setenv("PT_FULL_BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("PT_BACKUP_LOG_PATH", str(log_path))
    monkeypatch.setenv("PT_BACKUP_LAUNCH_AGENT_PATH", str(tmp_path / "missing.plist"))
    monkeypatch.delenv("PT_BACKUP_RCLONE_DEST", raising=False)
    monkeypatch.setattr(backup_reader, "DATABASE_PATH", tmp_path / "data" / "tracker.db")

    status = backup_reader.get_backup_status()

    assert status["status"] == "warning"
    assert status["safety"]["state"] == "missing_directory"
    assert status["cloud"]["status"] == "warning"
    assert "not configured" in status["cloud"]["message"]


def test_get_backup_status_distinguishes_empty_backup_directory(tmp_path, monkeypatch):
    backup_dir = tmp_path / "full-backups"
    backup_dir.mkdir()

    monkeypatch.setenv("PT_FULL_BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("PT_BACKUP_LOG_PATH", str(tmp_path / "missing.log"))
    monkeypatch.setenv("PT_BACKUP_LAUNCH_AGENT_PATH", str(tmp_path / "missing.plist"))
    monkeypatch.delenv("PT_BACKUP_RCLONE_DEST", raising=False)
    monkeypatch.setattr(backup_reader, "DATABASE_PATH", tmp_path / "data" / "tracker.db")

    status = backup_reader.get_backup_status()

    assert status["status"] == "critical"
    assert status["local_full"]["state"] == "empty"
