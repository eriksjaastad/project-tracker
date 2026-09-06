"""Copy-truncate rotation for logs that launchd, not Python, owns.

`RotatingFileHandler` cannot cap `StandardOutPath`/`StandardErrorPath`: launchd
opens those files and hands the process an already-open descriptor, so Python
logging never sees them. Renaming is worse than doing nothing — launchd keeps
writing into the renamed inode while the file at the original path stays empty,
so the log silently stops growing and everyone assumes it is fine.

Copy-truncate is the fix: copy the contents aside, then truncate the original
*in place* so the inode, and therefore launchd's descriptor, survives.

logs/ reached 155MB with no rotation anywhere in the repo (#6750). The
dashboard's shell launcher got this treatment first; this module is the same
logic for jobs that launchd starts directly with no shell wrapper, which is why
`sync-daemon.err` was still growing unbounded at 37MB afterwards (#6888).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUPS = 2


def rotate_if_large(
    path: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backups: int = DEFAULT_BACKUPS,
) -> bool:
    """Copy-truncate `path` when it exceeds `max_bytes`. True if rotated.

    Best-effort by design: a caller invoking this at startup must not fail to
    start because housekeeping failed. Errors are logged, never raised — but
    the file is only truncated once its copy is safely written, so a failure
    leaves an oversized log rather than an empty one.
    """
    try:
        if not path.is_file() or path.stat().st_size <= max_bytes:
            return False

        # Shift older generations down; the oldest falls off the end.
        for index in range(backups, 1, -1):
            older = path.with_suffix(path.suffix + f".{index - 1}")
            if older.exists():
                older.replace(path.with_suffix(path.suffix + f".{index}"))

        if backups >= 1:
            backup = path.with_suffix(path.suffix + ".1")
            backup.write_bytes(path.read_bytes())

        # Truncate in place — never unlink or rename. launchd holds a
        # descriptor on this inode and must keep writing to the same one.
        with open(path, "r+") as handle:
            handle.truncate(0)

        logger.info("rotated %s (was over %d bytes)", path, max_bytes)
        return True
    except OSError as exc:
        logger.warning("could not rotate %s: %s", path, exc)
        return False


def rotate_own_logs(*names: str) -> None:
    """Rotate this job's launchd log files, found under PT_HOME/logs.

    Caps come from PT_LOG_MAX_BYTES / PT_LOG_BACKUPS so a job can be tuned
    without a code change.
    """
    home = os.environ.get("PT_HOME")
    log_dir = Path(home) / "logs" if home else Path(__file__).resolve().parents[2] / "logs"

    try:
        max_bytes = int(os.environ.get("PT_LOG_MAX_BYTES", DEFAULT_MAX_BYTES))
        backups = int(os.environ.get("PT_LOG_BACKUPS", DEFAULT_BACKUPS))
    except ValueError:
        max_bytes, backups = DEFAULT_MAX_BYTES, DEFAULT_BACKUPS

    for name in names:
        rotate_if_large(log_dir / name, max_bytes=max_bytes, backups=backups)
