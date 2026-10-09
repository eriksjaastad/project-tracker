import pytest
import tempfile
from pathlib import Path
from scripts.discovery.project_scanner import discover_projects, extract_project_metadata


@pytest.fixture
def temp_project():
    """Create a temporary project structure for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create a mock project
        project_path = tmp_path / "test-project"
        project_path.mkdir()

        # Add README.md
        (project_path / "README.md").write_text("# Test Project\nThis is a test.")

        # Add CLAUDE.md as project marker
        (project_path / "CLAUDE.md").write_text("# Test Project Config\n")

        yield project_path


def test_extract_project_metadata(temp_project):
    """Test the project metadata extraction."""
    project_data = extract_project_metadata(temp_project)

    assert project_data["name"] == "test-project"
    assert project_data["description"] == "This is a test."


def test_discover_projects_finds_auxesis_portfolio_children(tmp_path: Path):
    portfolio_root = tmp_path / "auxesis-projects"
    portfolio_root.mkdir()
    child_project = portfolio_root / "smart-invoice-workflow"
    child_project.mkdir()
    (child_project / "README.md").write_text("# Smart Invoice Workflow\nRun invoices faster.\n")

    projects = discover_projects(tmp_path)

    assert len(projects) == 1
    project = projects[0]
    assert project["id"] == "smart-invoice-workflow"
    assert project["portfolio_group"] == "AP"
    assert project["portfolio_label"] == "[AP]"
    assert project["portfolio_parent"] == "auxesis-projects"


def test_extract_project_metadata_infers_portfolio_from_parent_directory(tmp_path: Path):
    portfolio_root = tmp_path / "auxesis-incubators"
    portfolio_root.mkdir()
    child_project = portfolio_root / "ideas-lab"
    child_project.mkdir()
    (child_project / "README.md").write_text("# Ideas Lab\nIncubation repo.\n")

    project = extract_project_metadata(child_project)

    assert project["portfolio_group"] == "AI"
    assert project["portfolio_label"] == "[AI]"
    assert project["portfolio_parent"] == "auxesis-incubators"


def test_external_resources_parse_error_raises(tmp_path):
    """#6900: `pt scan` syncs services with deletes allowed, so a broken
    EXTERNAL_RESOURCES.yaml must raise instead of reading as "no services"."""
    import yaml

    from scripts.discovery.external_resources_parser import parse_external_resources

    broken = tmp_path / "EXTERNAL_RESOURCES.yaml"
    broken.write_text("projects:\n  demo: [unclosed\n")
    with pytest.raises(yaml.YAMLError):
        parse_external_resources(broken)


def test_journal_specialist_unreadable_graph_raises(tmp_path, monkeypatch):
    """#6900: a corrupt graph.json raises so `pt scan` reports a graph
    rebuild error instead of silently skipping the journal enrichment."""
    import json

    from scripts.discovery import journal_specialist

    graph = tmp_path / "graph.json"
    graph.write_text("{not json")
    monkeypatch.setattr(journal_specialist, "GRAPH_DATA", graph)
    specialist = journal_specialist.JournalSpecialist.__new__(journal_specialist.JournalSpecialist)
    specialist.projects = set()
    specialist.links = []
    with pytest.raises(json.JSONDecodeError):
        specialist._update_graph()


def test_discover_projects_raises_when_base_cannot_be_listed(tmp_path, monkeypatch):
    """#6900: an unlistable projects base must raise, not read as "no projects"
    (the dashboard refresh reported that as a successful 0-project refresh)."""
    real_iterdir = Path.iterdir

    def guarded_iterdir(self):
        if self == tmp_path:
            raise PermissionError("denied")
        return real_iterdir(self)

    (tmp_path / "proj").mkdir()
    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)
    with pytest.raises(PermissionError):
        discover_projects(tmp_path)


def test_telemetry_read_failure_raises_instead_of_zero_requests(tmp_path, monkeypatch):
    """#6900: an unreadable telemetry file must not report "0 requests";
    the alert detector reports the exception."""
    from scripts.discovery import telemetry_reader

    unreadable = tmp_path / "telemetry.jsonl"
    unreadable.mkdir()  # exists() is True, open() fails
    monkeypatch.setattr(telemetry_reader, "TELEMETRY_PATH", unreadable)
    with pytest.raises(IsADirectoryError):
        telemetry_reader.get_telemetry_stats(days=7)


def test_external_resources_missing_file_raises(tmp_path):
    """#6900: the registry ships in the repo, so a missing file is a
    misconfiguration, never "no services" (which `pt scan` would delete)."""
    from scripts.discovery.external_resources_parser import parse_external_resources

    with pytest.raises(FileNotFoundError, match="PT_RESOURCES_FILE"):
        parse_external_resources(tmp_path / "EXTERNAL_RESOURCES.yaml")


@pytest.mark.parametrize("body", ["", "other: {}\n", "projects:\n", "projects: [a, b]\n"])
def test_external_resources_without_projects_mapping_raises(tmp_path, body):
    from scripts.discovery.external_resources_parser import parse_external_resources

    path = tmp_path / "EXTERNAL_RESOURCES.yaml"
    path.write_text(body)
    with pytest.raises(ValueError, match="no 'projects' mapping"):
        parse_external_resources(path)


def test_external_resources_valid_registry_still_parses(tmp_path):
    from scripts.discovery.external_resources_parser import parse_external_resources

    path = tmp_path / "EXTERNAL_RESOURCES.yaml"
    path.write_text(
        "projects:\n"
        "  demo:\n"
        "    services:\n"
        "      - {name: Doppler, cost: 0, purpose: secrets}\n"
        "  empty: {}\n"
    )
    assert parse_external_resources(path) == {
        "demo": [{"service_name": "Doppler", "cost_monthly": 0, "purpose": "secrets"}]
    }
