import pytest
import tempfile
from pathlib import Path
from scripts.discovery.project_scanner import extract_project_metadata


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


def test_extract_project_metadata_includes_agent_config_health(temp_project):
    claude_md = temp_project / "CLAUDE.md"
    claude_md.write_text("\n".join([f"- rule {i}" for i in range(205)]) + "\n")

    project_data = extract_project_metadata(temp_project)

    assert project_data["agent_config_health"]["has_claude_md"] is True
    assert project_data["agent_config_health"]["warning_count"] == 1
    claude_health = next(
        file_health
        for file_health in project_data["agent_config_health"]["files"]
        if file_health["path"] == "CLAUDE.md"
    )
    assert claude_health["over_limit"] is True
    assert any("205 lines" in warning for warning in claude_health["warnings"])
