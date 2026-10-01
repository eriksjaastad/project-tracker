"""Regression tests for schema safety backup retention."""

import sys
from pathlib import Path

import scripts.db.schema as schema
from scripts.db.backend_manager import DatabaseManager

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def _seed_backup_files(directory: Path, count: int) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for index in range(count):
        filename = f"tasks_safety_backup_20240101_0000{index:02d}.json"
        path = directory / filename
        path.write_text("{}")
        created.append(path)
    return created


def test_safety_backup_rotation_sends_old_backups_to_trash(tmp_path, monkeypatch):
    db_path = tmp_path / "tracker.db"
    external_backup_dir = tmp_path / "external-backups"
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()

    schema.create_database(db_path)
    db = DatabaseManager(db_path)
    db.add_project(project_id="demo", name="Demo", path="./demo", status="active")
    db.add_task(text="Keep me safe", project_id="demo", status="Backlog")

    local_backup_dir = db_path.parent / "backups"
    local_old = _seed_backup_files(local_backup_dir, 11)
    external_old = _seed_backup_files(external_backup_dir, 11)

    trashed: list[Path] = []

    def fake_send2trash(path_str: str) -> None:
        source = Path(path_str)
        destination = trash_dir / f"{source.parent.name}__{source.name}"
        source.rename(destination)
        trashed.append(source)

    monkeypatch.setattr(schema, "EXTERNAL_BACKUP_DIR", external_backup_dir)
    monkeypatch.setattr(schema, "send2trash", fake_send2trash)

    backup_path = schema._safety_backup_tasks(db_path)

    assert backup_path is not None
    assert backup_path.exists()
    assert len(list(local_backup_dir.glob("tasks_safety_backup_*.json"))) == 10
    assert len(list(external_backup_dir.glob("tasks_safety_backup_*.json"))) == 10
    assert len(trashed) == 4
    assert local_old[0] in trashed
    assert local_old[1] in trashed
    assert external_old[0] in trashed
    assert external_old[1] in trashed


def test_current_schema_startup_does_not_create_safety_backup(tmp_path, monkeypatch):
    db_path = tmp_path / "tracker.db"
    external_backup_dir = tmp_path / "external-backups"

    monkeypatch.setattr(schema, "EXTERNAL_BACKUP_DIR", external_backup_dir)

    schema.create_database(db_path)
    db = DatabaseManager(db_path)
    db.add_project(project_id="demo", name="Demo", path="./demo", status="active")
    db.add_task(text="Do not back up on read-only startup", project_id="demo", status="Backlog")

    local_backup_dir = db_path.parent / "backups"
    for path in local_backup_dir.glob("tasks_safety_backup_*.json"):
        path.unlink()
    for path in external_backup_dir.glob("tasks_safety_backup_*.json"):
        path.unlink()

    schema.create_database(db_path)

    assert list(local_backup_dir.glob("tasks_safety_backup_*.json")) == []
    assert list(external_backup_dir.glob("tasks_safety_backup_*.json")) == []


def test_fingerprint_read_failure_raises_instead_of_skipping_mismatch_check(tmp_path, monkeypatch):
    """#6900: an unreadable DB fingerprint must not read as "no fingerprint".

    That path skipped the mismatch guard and returned the file fingerprint,
    which create_database then wrote over the database's own.
    """
    import sqlite3

    import pytest

    db_path = tmp_path / "tracker.db"
    sqlite3.connect(db_path).close()
    (tmp_path / ".db-fingerprint").write_text("file-fingerprint")

    def locked(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(schema.sqlite3, "connect", locked)
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        schema._get_or_create_fingerprint(db_path)


def _seeded_db(tmp_path, monkeypatch):
    db_path = tmp_path / "tracker.db"
    monkeypatch.setattr(schema, "EXTERNAL_BACKUP_DIR", tmp_path / "external-backups")
    schema.create_database(db_path)
    db = DatabaseManager(db_path)
    db.add_project(project_id="demo", name="Demo", path="./demo", status="active")
    db.add_task(text="Must survive a migration", project_id="demo", status="Backlog")
    return db_path


def _make_migration_pending(db_path):
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM schema_version")
    conn.execute(
        "INSERT INTO schema_version (version, updated_at) VALUES (?, '2026-01-01')",
        (schema.CURRENT_SCHEMA_VERSION - 1,),
    )
    conn.commit()
    conn.close()


def _snapshot(db_path):
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        return (
            conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall(),
            conn.execute("SELECT * FROM schema_version").fetchall(),
            conn.execute("SELECT id, text FROM tasks ORDER BY id").fetchall(),
        )
    finally:
        conn.close()


def test_pending_migration_with_failed_safety_backup_raises_and_leaves_db_unchanged(tmp_path, monkeypatch):
    """#6900: the pre-migration backup is a precondition. A failed backup used
    to print a warning and migrate the live database anyway."""
    import pytest

    db_path = _seeded_db(tmp_path, monkeypatch)
    _make_migration_pending(db_path)
    before = _snapshot(db_path)

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup_dir.chmod(0o500)  # unwritable
    try:
        with pytest.raises(schema.SafetyBackupError) as excinfo:
            schema.create_database(db_path)
    finally:
        backup_dir.chmod(0o700)

    message = str(excinfo.value)
    assert str(backup_dir) in message
    assert "PermissionError" in message
    assert _snapshot(db_path) == before
    assert isinstance(excinfo.value, schema.SafetyError)  # pt's _LOCAL_DB_ERRORS reports it


def test_no_pending_migration_ignores_an_unwritable_backup_dir(tmp_path, monkeypatch):
    """A current schema never takes a safety backup, so an unwritable backups
    directory must not affect ordinary commands."""
    db_path = _seeded_db(tmp_path, monkeypatch)

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup_dir.chmod(0o500)
    try:
        schema.create_database(db_path)
        db = DatabaseManager(db_path)
        created = db.add_task(text="Still writable", project_id="demo", status="Backlog")
        assert db.get_task(created["id"])["text"] == "Still writable"
    finally:
        backup_dir.chmod(0o700)


def test_pending_migration_with_working_backup_still_migrates(tmp_path, monkeypatch):
    db_path = _seeded_db(tmp_path, monkeypatch)
    _make_migration_pending(db_path)

    schema.create_database(db_path)

    import sqlite3

    conn = sqlite3.connect(db_path)
    version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    conn.close()
    assert version == schema.CURRENT_SCHEMA_VERSION
    assert list((db_path.parent / "backups").glob("tasks_safety_backup_*.json"))
