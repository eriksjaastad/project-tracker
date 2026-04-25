"""Regression tests for schema safety backup retention."""

import sys
from pathlib import Path

import scripts.db.schema as schema
from scripts.db.manager import DatabaseManager

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
    db = DatabaseManager(db_path=db_path)
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
    db = DatabaseManager(db_path=db_path)
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
