"""Tests for TODO.md and resource parsers."""

import pytest
from pathlib import Path
import tempfile
import sys

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from discovery.todo_parser import parse_todo, extract_status, calculate_completion


class TestTODOParser:
    """Tests for TODO.md parsing."""
    
    def test_parse_nonexistent_file(self):
        """Test parsing a file that doesn't exist returns safe defaults."""
        result = parse_todo(Path("/nonexistent/TODO.md"))
        assert result["status"] == "unknown"
        assert result["completion_pct"] == 0
        assert result["ai_agents"] == []
    
    def test_extract_status(self):
        """Test status extraction from various formats."""
        assert extract_status("**Project Status:** Active") == "active"
        assert extract_status("Project Status: Development") == "development"
        assert extract_status("Status: Complete") == "complete"
        assert extract_status("No status here") == "unknown"
    
    def test_calculate_completion(self):
        """Test TODO checkbox completion calculation."""
        content_100 = "- [x] Task 1\n- [x] Task 2"
        assert calculate_completion(content_100) == 100
        
        content_50 = "- [x] Done\n- [ ] Todo"
        assert calculate_completion(content_50) == 50
        
        content_0 = "- [ ] Todo 1\n- [ ] Todo 2"
        assert calculate_completion(content_0) == 0
        
        content_empty = "No checkboxes here"
        assert calculate_completion(content_empty) == 0
    
    def test_parse_todo_with_real_file(self):
        """Test parsing an actual TODO.md file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("""# Project TODO

**Project Status:** Active
**Current Phase:** Phase 1 - Development

## Tasks
- [x] Task 1
- [ ] Task 2
- [x] Task 3

## AI Agents
- Claude Sonnet (architecture)
""")
            temp_path = Path(f.name)
        
        try:
            result = parse_todo(temp_path)
            assert result["status"] == "active"
            assert result["phase"] == "Phase 1 - Development"
            assert result["completion_pct"] == 66  # 2/3 complete
        finally:
            temp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

