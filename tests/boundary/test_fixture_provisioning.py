"""Exercise probe provisioning even on CI hosts without a root install."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from db.dbmed_ops import ProjectTrackerOps


def test_synthetic_fixture_can_be_created_and_destroyed(client, daemon):
    before = client.call("get_all_projects")
    created = client.call("dbmed.fixture.create", {"name": "probe-test"})
    path = Path(created["path"])
    assert path == daemon["project_data"] / "fixtures/probe-test.db"
    assert path.is_file()
    assert created["project"] == "fixture-probe-test"
    assert client.call("get_all_projects") == before
    client.call("dbmed.fixture.destroy", {"name": "probe-test"})
    assert not path.exists()


def test_migration_loader_refuses_missing_registered_extension():
    backend = object.__new__(ProjectTrackerOps)
    backend.entry = SimpleNamespace(crsqlite_path=None)
    with pytest.raises(FileNotFoundError, match="no crsqlite_path"):
        backend._load_crsqlite(None)
