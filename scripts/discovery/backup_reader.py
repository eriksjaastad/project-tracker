"""Backup Reader for rclone integration."""
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# rclone config location (configurable via environment variable)
_default_config = Path.home() / ".config" / "rclone" / "rclone.conf"
RCLONE_CONFIG_PATH = Path(os.getenv("RCLONE_CONFIG_PATH", str(_default_config)))

# Critical paths that should be backed up
CRITICAL_PATHS = [
    Path.home() / "projects",
    Path.home() / ".config",
    Path.home() / "Documents",
    Path.home() / ".ssh",
]


def _parse_rclone_config() -> dict[str, dict]:
    """Parse rclone.conf and return remote configurations.

    Returns:
        Dict mapping remote name to config dict
    """
    if not RCLONE_CONFIG_PATH.exists():
        logger.warning(f"rclone config not found: {RCLONE_CONFIG_PATH}")
        return {}

    import configparser
    config = configparser.ConfigParser()

    try:
        config.read(RCLONE_CONFIG_PATH)
        remotes = {}
        for section in config.sections():
            remotes[section] = dict(config[section])
        return remotes
    except Exception as e:
        logger.error(f"Error parsing rclone config: {e}")
        return {}


def get_backup_status() -> dict[str, Any]:
    """Get backup status for the dashboard."""
    remotes = _parse_rclone_config()
    unbacked = get_unbacked_paths()

    if not remotes:
        status, color = "critical", "red"
        message = "No rclone remotes configured!"
    elif unbacked:
        status, color = "warning", "yellow"
        message = f"{len(unbacked)} paths may not be backed up"
    else:
        status, color = "healthy", "green"
        message = f"{len(remotes)} backup remote(s) configured"

    return {
        "status": status,
        "status_color": color,
        "message": message,
        "remotes": list(remotes.keys()),
        "remote_count": len(remotes),
        "critical_unbacked": unbacked,
    }


def get_unbacked_paths() -> list[str]:
    """Get list of critical paths not covered by backups."""
    remotes = _parse_rclone_config()
    if not remotes:
        return [str(p) for p in CRITICAL_PATHS if p.exists()]
    return []
