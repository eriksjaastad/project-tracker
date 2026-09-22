"""Backup settings shared by scheduled execution, manual runs, and status."""
import logging
import os
from pathlib import Path
import plistlib

logger = logging.getLogger(__name__)


def launch_agent_path() -> Path:
    return Path(os.getenv("PT_BACKUP_LAUNCH_AGENT_PATH") or
                Path.home() / "Library/LaunchAgents/com.eriksjaastad.pt-backup.plist").expanduser()


def setting(name: str, *aliases: str) -> str:
    """Explicit process settings override the scheduled job's persisted settings."""
    names = (name, *aliases)
    for key in names:
        value = os.getenv(key, "").strip()
        if value:
            return value
    path = launch_agent_path()
    try:
        with path.open("rb") as handle:
            payload = plistlib.load(handle)
        environment = payload.get("EnvironmentVariables", {})
        for key in names:
            value = environment.get(key, "")
            if isinstance(value, str) and value.strip():
                return value.strip()
    except FileNotFoundError:
        pass  # An unscheduled installation may configure manual runs via environment.
    except (OSError, ValueError, AttributeError, plistlib.InvalidFileException) as error:
        logger.warning("Cannot read backup settings from %s: %s", path, error)
    return ""


def external_backup_dir() -> Path:
    return Path(setting("PT_EXTERNAL_BACKUP_DIR", "PT_FULL_BACKUP_DIR") or
                Path.home() / ".project-tracker/backups").expanduser()


def rclone_config_path() -> Path:
    return Path(setting("RCLONE_CONFIG", "RCLONE_CONFIG_PATH") or
                Path.home() / ".config/rclone/rclone.conf").expanduser()


def rclone_destination() -> str:
    return setting("PT_BACKUP_RCLONE_DEST")
