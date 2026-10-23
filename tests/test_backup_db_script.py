"""scripts/backup-db.sh copies the enclosing rules repo off-site as a git bundle."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
UV = Path.home() / ".local/bin/uv"
pytestmark = pytest.mark.skipif(
    not (UV.is_file() and shutil.which("rclone")), reason="needs uv and rclone"
)


def _run_job(tmp_path, dest):
    """Run the job with a stub ./pt and PROJECTS_ROOT=<tmp>/rules; return (result, rules)."""
    rules = tmp_path / "rules"
    rules.mkdir()
    git = ["git", "-C", str(rules), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(rules)], check=True)
    (rules / "AGENTS.md").write_text("rules\n")
    subprocess.run([*git, "add", "AGENTS.md"], check=True)
    subprocess.run([*git, "commit", "-qm", "rules"], check=True)
    tracker = rules / "tracker"
    (tracker / "scripts").mkdir(parents=True)
    for name in ("backup-db.sh", "backup_config.py", "config.py"):
        shutil.copy(SCRIPTS / name, tracker / "scripts" / name)
    (tracker / "pt").write_text('#!/bin/bash\necho "pt $*"\n')
    (tracker / "pt").chmod(0o755)
    (tmp_path / "rclone.conf").write_text("")
    env = {**os.environ, "PT_BACKUP_RCLONE_DEST": dest, "PROJECTS_ROOT": str(rules),
           "RCLONE_CONFIG": str(tmp_path / "rclone.conf"),
           "PT_BACKUP_LAUNCH_AGENT_PATH": str(tmp_path / "absent.plist")}
    result = subprocess.run(["bash", str(tracker / "scripts/backup-db.sh")],
                            check=False, env=env, capture_output=True, text=True,
                            timeout=120)
    return result, rules


def test_bundle_restores_rules_repo_head(tmp_path):
    result, rules = _run_job(tmp_path, str(tmp_path / "remote"))
    assert result.returncode == 0, result.stderr
    assert "| rules_copy | ok |" in result.stdout
    clone = tmp_path / "restored"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "remote/projects.bundle"), str(clone)],
                   check=True)
    head = ["git", "rev-parse", "HEAD"]
    assert subprocess.check_output(head, cwd=clone) == subprocess.check_output(head, cwd=rules)


@pytest.mark.parametrize("dest, reason", [
    ("missingremote:backups", "missingremote"),
    ("", "Set PT_BACKUP_RCLONE_DEST"),
])
def test_bundle_failure_is_logged_and_db_backup_stands(tmp_path, dest, reason):
    result, _ = _run_job(tmp_path, dest)
    assert result.returncode == 0, result.stderr
    assert "| backup | pt backup create" in result.stdout
    # One log line carries the whole failure, even when the output was multiline.
    [rules_line] = [line for line in result.stdout.splitlines() if "| rules_copy |" in line]
    assert "| rules_copy | failed |" in rules_line and reason in rules_line
    assert "| prune | ok | pt backup prune" in result.stdout
