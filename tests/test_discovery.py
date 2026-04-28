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
