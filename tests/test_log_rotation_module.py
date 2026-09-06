"""Copy-truncate rotation for launchd-owned logs (#6888).

The inode assertion is the point of this file. launchd hands the process an
already-open descriptor, so rotating by rename leaves it writing into the
renamed inode while the file at the original path stays empty — the log
silently stops growing and looks healthy. Truncating in place keeps the
descriptor valid.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.log_rotation import rotate_if_large, rotate_own_logs  # noqa: E402


def test_small_log_is_left_alone(tmp_path: Path) -> None:
    log = tmp_path / "job.err"
    log.write_text("still small\n")

    assert rotate_if_large(log, max_bytes=1024) is False
    assert log.read_text() == "still small\n"
    assert not (tmp_path / "job.err.1").exists()


def test_oversized_log_is_copy_truncated_preserving_inode(tmp_path: Path) -> None:
    log = tmp_path / "job.err"
    log.write_text("x" * 500)
    inode_before = log.stat().st_ino

    assert rotate_if_large(log, max_bytes=100) is True

    assert log.stat().st_size == 0
    assert log.stat().st_ino == inode_before, (
        "rotation changed the inode — launchd would keep writing to the old one "
        "and this log would appear to stop growing"
    )
    assert (tmp_path / "job.err.1").read_text() == "x" * 500


def test_generations_shift_and_oldest_is_dropped(tmp_path: Path) -> None:
    log = tmp_path / "job.err"
    log.write_text("newest" * 100)
    (tmp_path / "job.err.1").write_text("previous")
    (tmp_path / "job.err.2").write_text("ancient")

    rotate_if_large(log, max_bytes=100, backups=2)

    assert (tmp_path / "job.err.1").read_text() == "newest" * 100
    assert (tmp_path / "job.err.2").read_text() == "previous"
    assert not (tmp_path / "job.err.3").exists()


def test_missing_log_is_a_noop(tmp_path: Path) -> None:
    assert rotate_if_large(tmp_path / "never-created.err") is False


def test_failure_leaves_the_log_intact_rather_than_empty(tmp_path: Path) -> None:
    """If the backup copy cannot be written, do not truncate.

    Truncating a log we failed to preserve destroys the very thing rotation
    exists to protect.
    """
    import os

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log = log_dir / "job.err"
    log.write_text("y" * 500)
    # Unwritable directory: the .1 backup cannot be created, while the existing
    # log file itself stays writable. That is exactly the shape that makes an
    # unguarded rotation destructive — the copy is impossible but the truncate
    # would still succeed.
    os.chmod(log_dir, 0o555)
    try:
        assert rotate_if_large(log, max_bytes=100) is False
        assert log.read_text() == "y" * 500, "log was truncated despite a failed backup"
    finally:
        os.chmod(log_dir, 0o755)


def test_rotate_own_logs_uses_pt_home(tmp_path: Path, monkeypatch) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    err = logs / "sync-daemon.err"
    err.write_text("z" * 400)
    monkeypatch.setenv("PT_HOME", str(tmp_path))
    monkeypatch.setenv("PT_LOG_MAX_BYTES", "100")

    rotate_own_logs("sync-daemon.err")

    assert err.stat().st_size == 0
    assert (logs / "sync-daemon.err.1").read_text() == "z" * 400


def test_rotate_own_logs_survives_bad_env_values(tmp_path: Path, monkeypatch) -> None:
    """A malformed cap must fall back to the default, not crash the daemon."""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "sync-daemon.err").write_text("small")
    monkeypatch.setenv("PT_HOME", str(tmp_path))
    monkeypatch.setenv("PT_LOG_MAX_BYTES", "not-a-number")

    rotate_own_logs("sync-daemon.err")  # must not raise

    assert (logs / "sync-daemon.err").read_text() == "small"
