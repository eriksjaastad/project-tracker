import importlib
from pathlib import Path

import pytest


def _reload_modules():
    import config
    import scripts.db.schema as schema
    import scripts.db.manager as manager
    import scripts.discovery.project_scanner as project_scanner
    import scripts.pt as pt

    importlib.reload(config)
    importlib.reload(schema)
    importlib.reload(manager)
    importlib.reload(project_scanner)
    importlib.reload(pt)

    return config, schema, manager, project_scanner, pt


@pytest.fixture()
def scan_env(tmp_path, monkeypatch):
    base_dir = tmp_path / "projects"
    base_dir.mkdir()
    db_path = tmp_path / "tracker.db"

    monkeypatch.setenv("PROJECTS_ROOT", str(base_dir))
    monkeypatch.setenv("PT_DB_PATH", str(db_path))

    config, schema, manager, project_scanner, pt = _reload_modules()
    project_scanner._ptignore_cache = None

    return {
        "base_dir": base_dir,
        "db_path": db_path,
        "config": config,
        "schema": schema,
        "manager": manager,
        "project_scanner": project_scanner,
        "pt": pt,
    }


def _make_project_dir(base_dir: Path, name: str, marker: str = "README.md") -> Path:
    project_dir = base_dir / name
    project_dir.mkdir()
    (project_dir / marker).write_text("# Project\n")
    return project_dir


def _project_metadata(project_dir: Path, project_id: str, status: str = "active") -> dict:
    return {
        "id": project_id,
        "name": project_dir.name,
        "path": str(project_dir),
        "status": status,
        "phase": None,
        "description": None,
        "last_modified": "2026-01-01T00:00:00",
        "completion_pct": 0,
        "ai_agents": [],
        "cron_jobs": [],
        "services": [],
        "is_infrastructure": False,
        "has_index": False,
        "index_is_valid": False,
        "index_updated_at": None,
        "project_type": "standard",
        "scaffolding_version": None,
        "rules_version": None,
        "scaffolding_applied_at": None,
    }


def test_add_project_upsert_preserves_tasks(scan_env):
    # Prevents cascade wipe incidents caused by INSERT OR REPLACE
    schema = scan_env["schema"]
    manager = scan_env["manager"]

    schema.init_db()
    db = manager.DatabaseManager()

    db.add_project(project_id="demo", name="Demo", path="demo", status="active")
    db.add_task(text="Keep me", project_id="demo", status="Backlog", priority=None, prompt=None)

    before = db.get_tasks(project_id="demo")
    assert len(before) == 1

    db.add_project(project_id="demo", name="Demo", path="demo", status="paused")

    after = db.get_tasks(project_id="demo")
    assert len(after) == 1
    assert after[0]["text"] == "Keep me"


def test_add_project_upsert_updates_fields(scan_env):
    # Ensures upsert updates metadata without delete/insert
    schema = scan_env["schema"]
    manager = scan_env["manager"]

    schema.init_db()
    db = manager.DatabaseManager()

    db.add_project(project_id="demo", name="Demo", path="demo", status="paused")
    db.add_project(project_id="demo", name="Demo", path="demo", status="active")

    project = db.get_project("demo")
    assert project["status"] == "active"


def test_delete_project_cascades_tasks(scan_env):
    # Ensures legitimate deletes still cascade to tasks
    schema = scan_env["schema"]
    manager = scan_env["manager"]

    schema.init_db()
    db = manager.DatabaseManager()

    db.add_project(project_id="demo", name="Demo", path="demo", status="active")
    db.add_task(text="Disposable", project_id="demo", status="Backlog", priority=None, prompt=None)

    assert len(db.get_tasks(project_id="demo")) == 1
    db.delete_project("demo")
    assert len(db.get_tasks(project_id="demo")) == 0


def test_scan_integrity_check_zero_projects_aborts(scan_env, monkeypatch, capsys):
    # Prevents empty scan from wiping data
    schema = scan_env["schema"]
    manager = scan_env["manager"]
    pt = scan_env["pt"]

    schema.init_db()
    db = manager.DatabaseManager()
    db.add_project(project_id="demo", name="Demo", path="demo", status="active")

    monkeypatch.setattr(pt, "discover_projects", lambda *_args, **_kwargs: [])

    pt.scan(no_graph=True, dry_run=False, force=False)
    out = capsys.readouterr().out

    assert "Scan found 0 projects" in out
    assert len(db.get_all_projects()) == 1


def test_scan_integrity_check_drop_aborts_without_force(scan_env, monkeypatch, capsys):
    # Prevents steep drop from silently overwriting metadata
    schema = scan_env["schema"]
    manager = scan_env["manager"]
    pt = scan_env["pt"]

    schema.init_db()
    db = manager.DatabaseManager()
    for idx in range(4):
        db.add_project(
            project_id=f"proj-{idx}",
            name=f"Proj {idx}",
            path=f"proj-{idx}",
            status="active"
        )

    project_dir = _make_project_dir(scan_env["base_dir"], "proj-0")
    monkeypatch.setattr(
        pt,
        "discover_projects",
        lambda *_args, **_kwargs: [_project_metadata(project_dir, "proj-0")]
    )

    pt.scan(no_graph=True, dry_run=False, force=False)
    out = capsys.readouterr().out

    assert "far fewer projects" in out
    assert len(db.get_all_projects()) == 4


def test_scan_integrity_check_force_allows(scan_env, monkeypatch):
    # Ensures --force override allows scan to proceed
    schema = scan_env["schema"]
    manager = scan_env["manager"]
    pt = scan_env["pt"]

    schema.init_db()
    db = manager.DatabaseManager()
    for idx in range(2):
        db.add_project(
            project_id=f"proj-{idx}",
            name=f"Proj {idx}",
            path=f"proj-{idx}",
            status="paused"
        )

    project_dir = _make_project_dir(scan_env["base_dir"], "proj-0")
    monkeypatch.setattr(
        pt,
        "discover_projects",
        lambda *_args, **_kwargs: [_project_metadata(project_dir, "proj-0", status="active")]
    )
    monkeypatch.setattr(pt, "scan_health_parallel", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(pt, "parse_external_resources", lambda: {})

    pt.scan(no_graph=True, dry_run=False, force=True)

    proj = db.get_project("proj-0")
    assert proj["status"] == "active"


def test_scan_per_project_transaction_rolls_back_on_failure(scan_env, monkeypatch):
    # Prevents partial updates when a project sync fails mid-transaction
    schema = scan_env["schema"]
    manager = scan_env["manager"]
    pt = scan_env["pt"]

    schema.init_db()
    db = manager.DatabaseManager()
    db.add_project(project_id="good", name="Good", path="good", status="paused")
    db.add_project(project_id="bad", name="Bad", path="bad", status="paused")

    good_dir = _make_project_dir(scan_env["base_dir"], "good")
    bad_dir = _make_project_dir(scan_env["base_dir"], "bad")

    projects = [
        _project_metadata(good_dir, "good", status="active"),
        _project_metadata(bad_dir, "bad", status="active"),
    ]

    monkeypatch.setattr(pt, "discover_projects", lambda *_args, **_kwargs: projects)
    monkeypatch.setattr(pt, "scan_health_parallel", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(pt, "parse_external_resources", lambda: {})

    def _raise_on_bad(self, cursor, project_id, cron_jobs, allow_deletes=True):
        if project_id == "bad":
            raise RuntimeError("Injected failure")
        return {"added": 0, "updated": 0, "deleted": 0}

    monkeypatch.setattr(pt.DatabaseManager, "_sync_cron_jobs_with_cursor", _raise_on_bad)

    pt.scan(no_graph=True, dry_run=False, force=True)

    assert db.get_project("good")["status"] == "active"
    assert db.get_project("bad")["status"] == "paused"


def test_scan_per_project_transaction_commits_success(scan_env, monkeypatch):
    # Ensures successful projects all commit together
    schema = scan_env["schema"]
    manager = scan_env["manager"]
    pt = scan_env["pt"]

    schema.init_db()
    db = manager.DatabaseManager()
    db.add_project(project_id="a", name="A", path="a", status="paused")
    db.add_project(project_id="b", name="B", path="b", status="paused")

    a_dir = _make_project_dir(scan_env["base_dir"], "a")
    b_dir = _make_project_dir(scan_env["base_dir"], "b")

    projects = [
        _project_metadata(a_dir, "a", status="active"),
        _project_metadata(b_dir, "b", status="active"),
    ]

    monkeypatch.setattr(pt, "discover_projects", lambda *_args, **_kwargs: projects)
    monkeypatch.setattr(pt, "scan_health_parallel", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(pt, "parse_external_resources", lambda: {})

    pt.scan(no_graph=True, dry_run=False, force=True)

    assert db.get_project("a")["status"] == "active"
    assert db.get_project("b")["status"] == "active"


def test_scan_dry_run_skips_writes(scan_env, monkeypatch, capsys):
    # Prevents dry-run from mutating the database
    schema = scan_env["schema"]
    manager = scan_env["manager"]
    pt = scan_env["pt"]

    schema.init_db()
    db = manager.DatabaseManager()
    db.add_project(project_id="demo", name="Demo", path="demo", status="paused")

    project_dir = _make_project_dir(scan_env["base_dir"], "demo")
    monkeypatch.setattr(
        pt,
        "discover_projects",
        lambda *_args, **_kwargs: [_project_metadata(project_dir, "demo", status="active")]
    )

    pt.scan(no_graph=True, dry_run=True, force=True)
    out = capsys.readouterr().out

    assert "Dry-run" in out
    assert db.get_project("demo")["status"] == "paused"


def test_scan_dry_run_reports_projects(scan_env, monkeypatch, capsys):
    # Ensures dry-run still reports discovery count
    schema = scan_env["schema"]
    manager = scan_env["manager"]
    pt = scan_env["pt"]

    schema.init_db()
    manager.DatabaseManager()

    project_dir = _make_project_dir(scan_env["base_dir"], "demo")
    monkeypatch.setattr(
        pt,
        "discover_projects",
        lambda *_args, **_kwargs: [_project_metadata(project_dir, "demo")]
    )

    pt.scan(no_graph=True, dry_run=True, force=True)
    out = capsys.readouterr().out

    assert "Found 1 projects" in out


def test_ptignore_skips_directories(scan_env):
    # Prevents scanning of explicitly ignored directories
    project_scanner = scan_env["project_scanner"]
    base_dir = scan_env["base_dir"]

    (base_dir / ".ptignore").write_text("# Ignore list\nskip-me\n\n")

    _make_project_dir(base_dir, "keep-me")
    _make_project_dir(base_dir, "skip-me")

    project_scanner._ptignore_cache = None
    projects = project_scanner.discover_projects(base_dir, sync_indexes=False)

    names = {p["name"] for p in projects}
    assert "keep-me" in names
    assert "skip-me" not in names


def test_ptignore_missing_file_is_safe(scan_env):
    # Missing .ptignore should not block discovery
    project_scanner = scan_env["project_scanner"]
    base_dir = scan_env["base_dir"]

    _make_project_dir(base_dir, "keep-me")
    project_scanner._ptignore_cache = None

    projects = project_scanner.discover_projects(base_dir, sync_indexes=False)
    names = {p["name"] for p in projects}

    assert "keep-me" in names
