"""Tests for the pt info command and project_info key-value store.

Covers:
- DatabaseManager CRUD for project_info (get, set, delete)
- Global vs project-scoped entries
- Upsert behavior (overwrite existing keys)
- CLI commands: info (default), set, get, delete, list
- JSON output mode
"""

import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.manager import DatabaseManager
from db.schema import create_database
from pt import info_group


@pytest.mark.parametrize("dry_run", [False, True])
def test_monitoring_alias_population_and_cli_lookup(db, monkeypatch, tmp_path, dry_run):
    """A fresh store gets the documented references through the real seed path."""
    from scripts import populate_info

    projects = tmp_path / "synthetic-projects"
    projects.mkdir()
    monkeypatch.setattr(populate_info, "PROJECTS_BASE_DIR", projects)
    monkeypatch.setattr(populate_info, "DatabaseManager", lambda: db)
    monkeypatch.setattr(sys, "argv", ["populate_info.py"] + (["--dry-run"] if dry_run else []))
    expected = {
        "external_resources_doc": str(populate_info.EXTERNAL_RESOURCES_FILE.resolve()),
        "remote_pt_invocation": populate_info.GLOBAL_KEYS["remote_pt_invocation"],
    }
    for key in expected:
        assert db.get_info(key=key) == []
    populate_info.main()
    with patch("pt.DatabaseManager", lambda: db):
        for key, value in expected.items():
            result = CliRunner().invoke(info_group, ["get", key], catch_exceptions=False)
            assert result.exit_code == 0
            if dry_run:
                assert db.get_info(key=key) == []
                assert result.output.strip() == f"No entry found for '{key}' (global)"
            else:
                assert result.output.strip() == value
                entry = db.get_info(key=key)[0]
                assert entry["value"] == value and entry["project_id"] is None


@pytest.mark.parametrize("resource_override", [None, "absolute", "relative"])
def test_monitoring_aliases_honor_configured_paths(db, monkeypatch, tmp_path, resource_override):
    from scripts import populate_info

    projects = tmp_path / "portfolio space's $NOT_EXPANDED"
    checkout = tmp_path / "separate checkout's $(not-a-command)"
    projects.mkdir()
    checkout.mkdir()
    registry = (tmp_path / "custom registry's $NAME.yaml" if resource_override
                else checkout / "EXTERNAL_RESOURCES.yaml")
    registry.write_text("monitoring: {}\n")
    launcher = checkout / "pt"
    launcher.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$PWD" "$PROJECTS_ROOT" "$PT_RESOURCES_FILE" "$PT_SKIP_DOPPLER" "$@"\n'
    )
    launcher.chmod(0o755)
    monkeypatch.setenv("PROJECTS_ROOT", str(projects))
    if resource_override:
        monkeypatch.chdir(tmp_path)
        configured_registry = registry.name if resource_override == "relative" else str(registry)
        monkeypatch.setenv("PT_RESOURCES_FILE", configured_registry)
    else:
        monkeypatch.delenv("PT_RESOURCES_FILE", raising=False)
    config_spec = importlib.util.spec_from_file_location(
        "synthetic_config", Path(populate_info.__file__).with_name("config.py")
    )
    config = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(config)
    assert config.PROJECTS_BASE_DIR == projects
    assert config.EXTERNAL_RESOURCES_FILE == (Path(configured_registry) if resource_override else
                                             config.PROJECT_ROOT / "EXTERNAL_RESOURCES.yaml")
    config.PROJECT_ROOT = checkout  # Simulate an installed checkout outside the scan root.
    if not resource_override:
        config.EXTERNAL_RESOURCES_FILE = registry
    monkeypatch.setitem(sys.modules, "config", config)
    seed_spec = importlib.util.spec_from_file_location("synthetic_seed", populate_info.__file__)
    seed = importlib.util.module_from_spec(seed_spec)
    seed_spec.loader.exec_module(seed)
    monkeypatch.setattr(seed, "DatabaseManager", lambda: db)
    monkeypatch.setattr(sys, "argv", ["populate_info.py"])
    seed.main()
    with patch("pt.DatabaseManager", lambda: db):
        result = CliRunner().invoke(info_group, ["get", "remote_pt_invocation", "--json"])
    assert result.exit_code == 0, result.output
    ssh_argv = shlex.split(json.loads(result.output)["value"])
    assert ssh_argv[:2] == ["ssh", "macbook-pro"] and len(ssh_argv) == 3
    # Simulate the remote shell with no inherited configuration, never real SSH.
    remote = subprocess.run(["/bin/sh", "-c", ssh_argv[2]], env={"PATH": "/usr/bin:/bin"},
                            check=True, capture_output=True, text=True, timeout=10)
    assert remote.stdout.splitlines() == [str(projects), str(projects), str(registry), "1", "tasks"]
    assert db.get_info(key="external_resources_doc")[0]["value"] == str(registry)


def _setup_db(tmp_path: Path) -> tuple[Path, DatabaseManager]:
    db_path = tmp_path / "test.db"
    create_database(db_path)
    db = DatabaseManager()
    return db_path, db


def _invoke_cli(db_path: Path, args: list) -> object:
    """Invoke info_group CLI with a patched DatabaseManager pointing to test DB."""
    runner = CliRunner()
    with patch("pt.DatabaseManager", lambda: DatabaseManager()):
        return runner.invoke(info_group, args, catch_exceptions=False)


# --- DatabaseManager tests ---


class TestProjectInfoDB:
    def test_get_info_empty(self, tmp_path: Path):
        _, db = _setup_db(tmp_path)
        entries = db.get_info()
        assert entries == []

    def test_set_and_get_global(self, tmp_path: Path):
        _, db = _setup_db(tmp_path)
        db.set_info("domain", "example.com")
        entries = db.get_info()
        assert len(entries) == 1
        assert entries[0]["key"] == "domain"
        assert entries[0]["value"] == "example.com"
        assert entries[0]["project_id"] is None

    def test_set_and_get_project_scoped(self, tmp_path: Path):
        _, db = _setup_db(tmp_path)
        db.set_info("tech_stack", "Python", project_id="my-project")
        # Global should be empty
        assert db.get_info() == []
        # Project-scoped should have the entry
        entries = db.get_info(project_id="my-project")
        assert len(entries) == 1
        assert entries[0]["key"] == "tech_stack"
        assert entries[0]["value"] == "Python"

    def test_upsert_overwrites(self, tmp_path: Path):
        _, db = _setup_db(tmp_path)
        db.set_info("domain", "old.com")
        db.set_info("domain", "new.com")
        entries = db.get_info()
        assert len(entries) == 1
        assert entries[0]["value"] == "new.com"

    def test_get_by_key(self, tmp_path: Path):
        _, db = _setup_db(tmp_path)
        db.set_info("a", "1")
        db.set_info("b", "2")
        entries = db.get_info(key="a")
        assert len(entries) == 1
        assert entries[0]["value"] == "1"

    def test_get_all_entries(self, tmp_path: Path):
        _, db = _setup_db(tmp_path)
        db.set_info("global_key", "gval")
        db.set_info("proj_key", "pval", project_id="proj")
        entries = db.get_info(project_id="__all__")
        assert len(entries) == 2

    def test_delete_global(self, tmp_path: Path):
        _, db = _setup_db(tmp_path)
        db.set_info("domain", "example.com")
        assert db.delete_info("domain") is True
        assert db.get_info() == []

    def test_delete_project_scoped(self, tmp_path: Path):
        _, db = _setup_db(tmp_path)
        db.set_info("key", "val", project_id="proj")
        assert db.delete_info("key", project_id="proj") is True
        assert db.get_info(project_id="proj") == []

    def test_delete_nonexistent(self, tmp_path: Path):
        _, db = _setup_db(tmp_path)
        assert db.delete_info("nope") is False

    def test_scopes_are_independent(self, tmp_path: Path):
        _, db = _setup_db(tmp_path)
        db.set_info("key", "global_val")
        db.set_info("key", "proj_val", project_id="proj")
        global_entries = db.get_info(key="key")
        proj_entries = db.get_info(project_id="proj", key="key")
        assert global_entries[0]["value"] == "global_val"
        assert proj_entries[0]["value"] == "proj_val"


# --- CLI tests ---


class TestProjectInfoCLI:
    def test_info_empty(self, tmp_path: Path):
        db_path, _ = _setup_db(tmp_path)
        result = _invoke_cli(db_path, [])
        assert "empty" in result.output

    def test_set_and_show(self, tmp_path: Path):
        db_path, _ = _setup_db(tmp_path)
        result = _invoke_cli(db_path, ["set", "domain", "example.com"])
        assert "Set domain = example.com" in result.output

    def test_get_existing(self, tmp_path: Path):
        db_path, db = _setup_db(tmp_path)
        db.set_info("domain", "example.com")
        result = _invoke_cli(db_path, ["get", "domain"])
        assert "example.com" in result.output

    def test_get_missing(self, tmp_path: Path):
        db_path, _ = _setup_db(tmp_path)
        result = _invoke_cli(db_path, ["get", "nope"])
        assert "No entry found" in result.output

    def test_delete_existing(self, tmp_path: Path):
        db_path, db = _setup_db(tmp_path)
        db.set_info("domain", "example.com")
        result = _invoke_cli(db_path, ["delete", "domain"])
        assert "Deleted" in result.output

    def test_delete_missing(self, tmp_path: Path):
        db_path, _ = _setup_db(tmp_path)
        result = _invoke_cli(db_path, ["delete", "nope"])
        assert "No entry found" in result.output

    def test_list_all(self, tmp_path: Path):
        db_path, db = _setup_db(tmp_path)
        db.set_info("gkey", "gval")
        db.set_info("pkey", "pval", project_id="proj")
        result = _invoke_cli(db_path, ["list"])
        assert "Global:" in result.output
        assert "proj:" in result.output

    def test_json_output(self, tmp_path: Path):
        db_path, db = _setup_db(tmp_path)
        db.set_info("domain", "example.com")
        result = _invoke_cli(db_path, ["--json"])
        assert '"key": "domain"' in result.output
