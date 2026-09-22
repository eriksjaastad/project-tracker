#!/usr/bin/env python3
"""Retire the laptop dbmed installation while preserving every recovery copy.

Run with sudo after deploying the local-database implementation. No production
rows are deleted. The old install and data are archived for recovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import tempfile
import time

DATA = Path('/usr/local/var/dbmed')
PLIST = Path('/Library/LaunchDaemons/com.dbmed.plist')
RUN_DIRECTORY = Path('/usr/local/var/run')
ARCHIVE_ROOT = Path('/usr/local/var/dbmed-retired')
INSTALL_ROOTS = [(Path('/usr/local/etc/dbmed'), 'config'),
                 (Path('/usr/local/libexec/dbmed'), 'code'),
                 (Path('/usr/local/libexec/dbmed-runtime'), 'runtime'),
                 (Path('/usr/local/var/run/dbmed.sock'), 'dbmed.sock')]


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=60)


def digest(path):
    with path.open('rb') as handle:
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
        return digest.hexdigest()


def copy_history(source, destination):
    """Merge recovery files without overwriting a different existing copy."""
    if not source.exists():
        return
    if source.is_symlink() or destination.is_symlink():
        raise RuntimeError(f'Refusing symlink: {source} or {destination}')
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            copy_history(child, destination / child.name)
    elif destination.exists():
        if not destination.is_file() or digest(source) != digest(destination):
            raise RuntimeError(f'Conflicting recovery copy: {destination}')
    else:
        shutil.copy2(source, destination)
        if digest(source) != digest(destination):
            raise RuntimeError(f'Copy verification failed: {destination}')


def database_counts(path):
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise RuntimeError(f'Database integrity check failed: {path}')
        names = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND sql NOT LIKE 'CREATE VIRTUAL TABLE%'"
        )]
        if not {'tasks', 'projects'} <= set(names):
            raise RuntimeError(f'Not a tracker database: {path}')
        return {name: conn.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                for name in names}
    finally:
        conn.close()


def snapshot(source, destination):
    if destination.exists():
        raise RuntimeError(f'Destination already exists: {destination}')
    source_counts = database_counts(source)
    src = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    if database_counts(destination) != source_counts:
        raise RuntimeError('Snapshot row counts differ from source')
    return source_counts


def own_tree(root, uid, gid):
    for path in [root, *root.rglob('*')]:
        os.chown(path, uid, gid, follow_symlinks=False)


def retire(repo):
    if os.geteuid() != 0 or not os.environ.get('SUDO_USER'):
        raise RuntimeError('Run through sudo as the workstation owner')
    owner = pwd.getpwnam(os.environ['SUDO_USER'])
    manager = repo / 'scripts/db/manager.py'
    if not manager.is_file() or 'from .operations import ProjectTrackerOps' not in manager.read_text():
        raise RuntimeError('Deploy the local-database code to the target checkout first')
    source = DATA / 'project-tracker/tracker.db'
    if not source.is_file() or not PLIST.is_file():
        raise RuntimeError('Expected installed database and LaunchDaemon plist are missing')
    target = repo / 'data/tracker.db'
    for path in [target, Path(str(target) + '-wal'), Path(str(target) + '-shm')]:
        if path.exists() or path.is_symlink():
            raise RuntimeError(f'Existing target requires inspection before cutover: {path}')
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%dT%H%M%S')
    stage = Path(tempfile.mkdtemp(prefix='dbmed-retirement-', dir=target.parent))
    archive = ARCHIVE_ROOT / stamp
    archive.mkdir(parents=True, mode=0o700)
    # Stop and verify the service before reading the final state. Failure here
    # is fatal; an unsuccessful bootout must never be treated as "not loaded".
    run('launchctl', 'bootout', 'system/com.dbmed')
    published = False
    try:
        probe = subprocess.run(['launchctl', 'print', 'system/com.dbmed'],
                               capture_output=True, text=True, timeout=30)
        if probe.returncode == 0:
            raise RuntimeError('dbmed is still running; nothing copied')
        if 'Could not find service' not in probe.stderr:
            raise RuntimeError(f'Cannot verify service stopped: {probe.stderr.strip()}')
        counts = snapshot(source, stage / 'tracker.db')
        copy_history(DATA / 'project-tracker/backups', target.parent / 'backups')
        external = Path(owner.pw_dir) / '.project-tracker/backups'
        copy_history(DATA / 'external/project-tracker', external)
        copy_history(DATA / 'project-tracker/attic', stage / 'historical-copies')
        if (target.parent / 'backups').exists():
            own_tree(target.parent / 'backups', owner.pw_uid, owner.pw_gid)
        if external.exists():
            own_tree(external, owner.pw_uid, owner.pw_gid)
        (stage / 'receipt.json').write_text(json.dumps({'source': str(source), 'target': str(target),
            'archive': str(archive), 'row_counts': counts}, indent=2) + '\n')
        shutil.copy2(stage / 'tracker.db', stage / 'pre-cutover.db')
        own_tree(stage, owner.pw_uid, owner.pw_gid)
        os.chmod(stage, 0o700)
        os.chmod(stage / 'tracker.db', 0o600)
        # A hard link publishes atomically and refuses to overwrite any file
        # created by a concurrent caller. pre-cutover.db is an independent recovery copy.
        os.link(stage / 'tracker.db', target)
        published = True
        installations = [(PLIST, 'com.dbmed.plist'), *INSTALL_ROOTS, (DATA, 'data')]
        for installed, name in installations:
            if installed.exists():
                destination = archive / name
                shutil.move(str(installed), destination)
                own_tree(destination, 0, 0)
        # The installer gave the shared run directory to its service user.
        # Restore system ownership only if that user still owns it.
        service_uid = pwd.getpwnam('_dbmed').pw_uid
        if RUN_DIRECTORY.exists() and RUN_DIRECTORY.stat().st_uid == service_uid:
            os.chown(RUN_DIRECTORY, 0, 0)
            os.chmod(RUN_DIRECTORY, 0o755)
        # Dedicated account/group only; never remove the shared directory.
        for record in ['/Users/_dbmed', '/Groups/_dbmed']:
            run('dscl', '.', '-delete', record)
        print(json.dumps({'retired': True, 'database': str(target), 'row_counts': counts,
                          'receipt': str(stage / 'receipt.json'), 'archive': str(archive)}, indent=2))
    except Exception:
        if not published and PLIST.exists():
            run('launchctl', 'bootstrap', 'system', str(PLIST))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    retire(args.repo.resolve())
