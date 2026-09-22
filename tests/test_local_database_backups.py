"""Recovery behavior after removing the mediation service."""
import sqlite3
import subprocess
from pathlib import Path

import pytest

from db.manager import DatabaseManager
from db.calendar_manager import CalendarManager
from scripts.retire_dbmed import copy_history, database_counts, snapshot


def test_local_board_calendar_and_restore_work_without_service(db, monkeypatch, tmp_path):
    monkeypatch.setenv('DBMED_SOCKET', str(tmp_path / 'absent.sock'))
    db.add_project('recovery', 'Recovery', str(tmp_path), 'active')
    first = db.add_task('Preserve this card', 'recovery')
    calendar = CalendarManager(db.db_path)
    event = calendar.add_event('Recovery drill', '2026-09-22', project_id='recovery')
    created = db.backup_create(retention_days=0)
    assert created['verified'] is True
    backup_name = Path(created['path']).name
    assert {row['name'] for row in db.backup_list()} == {backup_name}
    later = db.add_task('After snapshot', 'recovery')
    existing_reader = sqlite3.connect(db.db_path)
    try:
        assert existing_reader.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 2
        db.authorize('backup_restore', reason='Isolated recovery drill', name=backup_name)
        assert existing_reader.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 1
    finally:
        existing_reader.close()
    restored = DatabaseManager(db.db_path)
    assert restored.get_task(first['id'])['text'] == 'Preserve this card'
    assert restored.get_task(later['id']) is None
    assert CalendarManager(db.db_path).get_event(event)['title'] == 'Recovery drill'
    assert len(restored.backup_list()) == 2


def test_rclone_uploads_snapshot_and_preserves_local_copy_on_failure(db, monkeypatch, tmp_path):
    db.add_project('offsite', 'Offsite', str(tmp_path), 'active')
    db.add_task('Offsite card', 'offsite')
    created = db.backup_create(retention_days=0)
    config = tmp_path / 'rclone.conf'
    config.write_text('[synthetic]\ntype = local\n')
    monkeypatch.setenv('RCLONE_CONFIG', str(config))
    monkeypatch.setenv('PT_BACKUP_RCLONE_DEST', 'synthetic:recovery')
    monkeypatch.setattr('shutil.which', lambda name: '/synthetic/rclone')
    calls = []

    def upload(command, **kwargs):
        calls.append((command, kwargs))
        assert Path(command[2]) != db.db_path
        assert database_counts(Path(command[2]))['tasks'] == 1
        return subprocess.CompletedProcess(command, 0, '', '')

    monkeypatch.setattr(subprocess, 'run', upload)
    result = db.backup_offsite_copy(Path(created['path']).name)
    assert result['dest'].startswith('synthetic:recovery/tracker_')
    assert calls[0][0][1] == 'copyto'
    assert calls[0][1]['timeout'] == 300
    monkeypatch.setattr(subprocess, 'run', lambda command, **kw:
                        subprocess.CompletedProcess(command, 3, '', 'synthetic network failure'))
    with pytest.raises(RuntimeError, match='synthetic network failure'):
        db.backup_offsite_copy(Path(created['path']).name)
    assert db.verify_backup(created['path'])


def test_retirement_snapshot_includes_committed_wal_rows(db, tmp_path):
    source = sqlite3.connect(db.db_path)
    try:
        source.execute('PRAGMA journal_mode=WAL')
        source.execute('PRAGMA wal_autocheckpoint=0')
        source.execute("INSERT INTO projects (id, name, path, status) VALUES ('wal', 'WAL', '/synthetic', 'active')")
        source.commit()
        target = tmp_path / 'restored.db'
        counts = snapshot(db.db_path, target)
        assert counts['projects'] == 1
        assert database_counts(target) == counts
        with sqlite3.connect(target) as restored:
            assert restored.execute('SELECT name FROM projects').fetchall() == [('WAL',)]
    finally:
        source.close()


def test_retirement_preserves_existing_database(db, tmp_path):
    target = tmp_path / 'existing.db'
    target.write_bytes(b'existing user data')
    with pytest.raises(RuntimeError, match='already exists'):
        snapshot(db.db_path, target)
    assert target.read_bytes() == b'existing user data'


def test_retirement_history_preserves_conflicting_and_identical_copies(tmp_path):
    source, target = tmp_path / 'old', tmp_path / 'new'
    source.mkdir()
    target.mkdir()
    (source / 'backup.db').write_bytes(b'original')
    (target / 'backup.db').write_bytes(b'other history')
    with pytest.raises(RuntimeError, match='Conflicting recovery copy'):
        copy_history(source, target)
    assert (target / 'backup.db').read_bytes() == b'other history'
    assert (source / 'backup.db').read_bytes() == b'original'
    (target / 'backup.db').write_bytes(b'original')
    copy_history(source, target)
    assert (target / 'backup.db').read_bytes() == b'original'


def test_retirement_refuses_history_symlinks(tmp_path):
    source = tmp_path / 'source'
    source.write_bytes(b'backup')
    link = tmp_path / 'link'
    link.symlink_to(source)
    with pytest.raises(RuntimeError, match='Refusing symlink'):
        copy_history(link, tmp_path / 'new')

@pytest.fixture
def retirement_install(db, tmp_path, monkeypatch):
    from scripts import retire_dbmed as retirement
    from types import SimpleNamespace
    repo = tmp_path / 'checkout'
    (repo / 'scripts/db').mkdir(parents=True)
    (repo / 'scripts/db/manager.py').write_text('from .operations import ProjectTrackerOps\n')
    data = tmp_path / 'installed-data'
    project = data / 'project-tracker'
    project.mkdir(parents=True)
    snapshot(db.db_path, project / 'tracker.db')
    (project / 'backups').mkdir()
    (project / 'backups' / 'historical.db').write_bytes(b'history')
    plist = tmp_path / 'com.dbmed.plist'
    plist.write_text('synthetic launch daemon')
    config = tmp_path / 'installed-config'
    config.mkdir()
    (config / 'registry.toml').write_text('synthetic registry')
    archive = tmp_path / 'archive'
    monkeypatch.setattr(retirement, 'DATA', data)
    monkeypatch.setattr(retirement, 'PLIST', plist)
    monkeypatch.setattr(retirement, 'RUN_DIRECTORY', tmp_path / 'run')
    monkeypatch.setattr(retirement, 'ARCHIVE_ROOT', archive)
    monkeypatch.setattr(retirement, 'INSTALL_ROOTS', [(config, 'config')])
    monkeypatch.setattr(retirement.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(retirement.os, 'chown', lambda *a, **k: None)
    monkeypatch.setenv('SUDO_USER', 'synthetic-owner')
    monkeypatch.setattr(retirement.pwd, 'getpwnam', lambda name:
                        SimpleNamespace(pw_dir=str(tmp_path / 'owner'), pw_uid=501, pw_gid=20))
    calls = []
    def command(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ['launchctl', 'print']:
            return subprocess.CompletedProcess(argv, 113, '', 'Could not find service "com.dbmed"')
        return subprocess.CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(retirement.subprocess, 'run', command)
    return retirement, repo, data, archive, calls


def test_retirement_archives_install_and_preserves_history(retirement_install):
    retirement, repo, data, archive, calls = retirement_install
    retirement.retire(repo)
    assert database_counts(repo / 'data/tracker.db')['tasks'] == 0
    assert (repo / 'data/backups/historical.db').read_bytes() == b'history'
    saved = next(archive.iterdir())
    assert database_counts(saved / 'data/project-tracker/tracker.db')['tasks'] == 0
    assert (saved / 'config/registry.toml').read_text() == 'synthetic registry'
    assert (saved / 'com.dbmed.plist').read_text() == 'synthetic launch daemon'
    assert not data.exists()
    assert ('dscl', '.', '-delete', '/Users/_dbmed') in calls
    assert ('dscl', '.', '-delete', '/Groups/_dbmed') in calls
    recovery = next((repo / 'data').glob('dbmed-retirement-*/pre-cutover.db'))
    assert recovery.stat().st_ino != (repo / 'data/tracker.db').stat().st_ino


def test_retirement_copy_failure_restarts_original_service(retirement_install):
    retirement, repo, data, archive, calls = retirement_install
    backup = repo / 'data/backups/historical.db'
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b'different existing history')
    with pytest.raises(RuntimeError, match='Conflicting recovery copy'):
        retirement.retire(repo)
    assert backup.read_bytes() == b'different existing history'
    assert (data / 'project-tracker/tracker.db').is_file()
    assert not (repo / 'data/tracker.db').exists()
    assert ('launchctl', 'bootstrap', 'system', str(retirement.PLIST)) in calls
    assert not any('dscl' in call for call in calls)


def test_scheduled_settings_match_manual_upload_and_status(db, monkeypatch, tmp_path):
    import plistlib
    from scripts.discovery.backup_reader import get_backup_status, append_cloud_copy_log

    config = tmp_path / 'scheduled-rclone.conf'
    config.write_text('[scheduled]\ntype = local\n')
    external = tmp_path / 'scheduled-backups'
    plist = tmp_path / 'backup.plist'
    plist.write_bytes(plistlib.dumps({'EnvironmentVariables': {
        'PT_BACKUP_RCLONE_DEST': 'scheduled:recovery',
        'RCLONE_CONFIG': str(config),
        'PT_EXTERNAL_BACKUP_DIR': str(external),
    }}))
    monkeypatch.setenv('PT_BACKUP_LAUNCH_AGENT_PATH', str(plist))
    monkeypatch.setenv('PT_BACKUP_LOG_PATH', str(tmp_path / 'backup.log'))
    for key in ('PT_BACKUP_RCLONE_DEST', 'RCLONE_CONFIG', 'RCLONE_CONFIG_PATH',
                'PT_EXTERNAL_BACKUP_DIR', 'PT_FULL_BACKUP_DIR'):
        monkeypatch.delenv(key, raising=False)
    local = DatabaseManager(db.db_path)
    assert local.entry.external_backup_dir == external
    created = local.backup_create(retention_days=0)
    monkeypatch.setattr('shutil.which', lambda name: '/synthetic/rclone')
    calls = []
    def upload(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', upload)
    result = local.backup_offsite_copy(Path(created['path']).name)
    assert calls[0][3] == result['dest']
    assert calls[0][5] == str(config)
    assert result['dest'].startswith('scheduled:recovery/')
    append_cloud_copy_log(ok=True, detail=result['dest'])
    status = get_backup_status()
    assert status['backup_dir'] == str(external)
    assert status['status'] == 'healthy'
    assert status['local_full']['count'] == 1


def test_backup_settings_process_precedence_and_legacy_aliases(monkeypatch, tmp_path):
    import plistlib
    from scripts.backup_config import external_backup_dir, rclone_config_path, rclone_destination
    plist = tmp_path / 'backup.plist'
    plist.write_bytes(plistlib.dumps({'EnvironmentVariables': {
        'PT_BACKUP_RCLONE_DEST': 'scheduled:old',
        'RCLONE_CONFIG': str(tmp_path / 'scheduled.conf'),
        'PT_EXTERNAL_BACKUP_DIR': str(tmp_path / 'scheduled'),
    }}))
    monkeypatch.setenv('PT_BACKUP_LAUNCH_AGENT_PATH', str(plist))
    monkeypatch.delenv('PT_EXTERNAL_BACKUP_DIR', raising=False)
    monkeypatch.delenv('RCLONE_CONFIG', raising=False)
    monkeypatch.setenv('PT_FULL_BACKUP_DIR', str(tmp_path / 'legacy'))
    monkeypatch.setenv('RCLONE_CONFIG_PATH', str(tmp_path / 'legacy.conf'))
    monkeypatch.setenv('PT_BACKUP_RCLONE_DEST', 'manual:new')
    assert external_backup_dir() == tmp_path / 'legacy'
    assert rclone_config_path() == tmp_path / 'legacy.conf'
    assert rclone_destination() == 'manual:new'
    monkeypatch.setenv('PT_EXTERNAL_BACKUP_DIR', str(tmp_path / 'canonical'))
    monkeypatch.setenv('RCLONE_CONFIG', str(tmp_path / 'canonical.conf'))
    assert external_backup_dir() == tmp_path / 'canonical'
    assert rclone_config_path() == tmp_path / 'canonical.conf'


def test_local_interface_rejects_turso_before_opening_either_database(monkeypatch, tmp_path):
    from db import backend_manager
    monkeypatch.setattr(backend_manager, '_USE_TURSO', True)
    opened = []
    monkeypatch.setattr(backend_manager, 'DatabaseManager', lambda *a: opened.append(a))
    target = tmp_path / 'must-not-create.db'
    with pytest.raises(RuntimeError, match='refusing mixed local/remote writes'):
        DatabaseManager(target)
    with pytest.raises(RuntimeError, match='refusing mixed local/remote writes'):
        CalendarManager(target)
    assert opened == []
    assert not target.exists()


def test_retirement_owns_new_parent_before_stopping_service(retirement_install, monkeypatch):
    retirement, repo, data, archive, calls = retirement_install
    ownership = []
    monkeypatch.setattr(retirement.os, 'chown', lambda path, uid, gid, **kw:
                        ownership.append((path, uid, gid)))
    original = retirement.subprocess.run
    def command(argv, **kwargs):
        if argv[:2] == ('launchctl', 'bootout'):
            assert (repo / 'data', 501, 20) in ownership
        return original(argv, **kwargs)
    monkeypatch.setattr(retirement.subprocess, 'run', command)
    assert not (repo / 'data').exists()
    retirement.retire(repo)
    assert (repo / 'data', 501, 20) in ownership
    assert (repo / 'data').stat().st_mode & 0o777 == 0o700
    assert (repo / 'data/tracker.db').is_file()


def test_retirement_preserves_existing_parent_ownership(retirement_install, monkeypatch):
    retirement, repo, data, archive, calls = retirement_install
    parent = repo / 'data'
    parent.mkdir(mode=0o750)
    ownership = []
    monkeypatch.setattr(retirement.os, 'chown', lambda path, uid, gid, **kw:
                        ownership.append(path))
    retirement.retire(repo)
    assert parent not in ownership
    assert parent.stat().st_mode & 0o777 == 0o750
