"""Project scanner for auto-discovery."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from .git_metadata import get_last_modified
from .todo_parser import parse_todo

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import PROJECTS_BASE_DIR


def discover_projects(base_path: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
    """Scan directory for projects."""
    if base_path is None:
        base_path = PROJECTS_BASE_DIR
    base = Path(base_path)
    
    if not base.exists():
        return []
    
    projects = []
    
    for item in base.iterdir():
        if not item.is_dir():
            continue
        
        # Skip common non-project directories
        if item.name in ["node_modules", ".git", "__pycache__", "venv", ".DS_Store"]:
            continue
        
        # Skip hidden directories (starting with .)
        if item.name.startswith('.'):
            continue
        
        # Skip utility directories (starting with _)
        if item.name.startswith('_'):
            continue
        
        # Check for indicators of a project
        has_git = (item / ".git").exists()
        has_readme = (item / "README.md").exists()
        has_todo = (item / "TODO.md").exists()
        has_python = any(item.glob("**/*.py"))
        has_js = any(item.glob("**/*.js")) or any(item.glob("**/*.ts"))
        
        # If it looks like a project, extract metadata
        if has_git or has_readme or has_todo or has_python or has_js:
            project = extract_project_metadata(item)
            if project:
                projects.append(project)
    
    return projects


def is_infrastructure_project(project_name: str, todo_content: str = "") -> bool:
    """Detect if a project is infrastructure based on name and TODO content."""
    # Specific infrastructure project names
    infra_names = [
        "project-tracker",
        "project-scaffolding", 
        "agent_os",
        "agent-skills-library",
        "n8n"
    ]
    
    # Check exact name matches (case-insensitive)
    name_lower = project_name.lower()
    name_slug = name_lower.replace(" ", "-")
    
    if name_slug in infra_names or name_lower in infra_names:
        return True
    
    # Keywords that indicate infrastructure (more specific)
    # Only match as complete words
    infra_keywords = ["scaffolding", "scaffold", "library", "platform", "framework"]
    if any(keyword in name_lower for keyword in infra_keywords):
        return True
    
    # Check TODO.md for explicit infrastructure marker
    if "**Type:** Infrastructure" in todo_content or "**Type:** Infra" in todo_content:
        return True
    
    return False


def extract_project_metadata(project_path: Path) -> Dict[str, Any]:
    """Extract all metadata from a project."""
    metadata = {
        "id": project_path.name.lower().replace(" ", "-"),
        "name": project_path.name,
        "path": str(project_path),
        "last_modified": get_last_modified(project_path),
        "status": "unknown",
        "phase": None,
        "description": None,
        "completion_pct": 0,
        "ai_agents": [],
        "cron_jobs": [],
        "services": [],
        "is_infrastructure": False
    }
    
    # Parse TODO.md if exists
    todo_path = project_path / "TODO.md"
    todo_content = ""
    if todo_path.exists():
        try:
            todo_content = todo_path.read_text()
        except Exception:
            pass
        
        todo_data = parse_todo(todo_path)
        metadata.update({
            "status": todo_data.get("status", "unknown"),
            "phase": todo_data.get("phase"),
            "completion_pct": todo_data.get("completion_pct", 0),
            "ai_agents": todo_data.get("ai_agents", []),
            "cron_jobs": todo_data.get("cron_jobs", [])
        })
        
        # Use TODO description if available
        if todo_data.get("description"):
            metadata["description"] = todo_data["description"]
    
    # Detect infrastructure projects
    metadata["is_infrastructure"] = is_infrastructure_project(metadata["name"], todo_content)
    
    # Parse README.md for description if TODO didn't provide one
    if not metadata["description"]:
        readme_path = project_path / "README.md"
        if readme_path.exists():
            metadata["description"] = extract_readme_description(readme_path)
    
    return metadata


def extract_readme_description(readme_path: Path) -> str:
    """Extract first paragraph from README."""
    try:
        content = readme_path.read_text()
        lines = content.split('\n')
        
        # Skip title and empty lines
        description_lines = []
        skip_initial = True
        
        for line in lines:
            # Skip title
            if line.startswith('#'):
                skip_initial = False
                continue
            
            # Skip metadata/badges
            if line.startswith('[![') or line.startswith('[!'):
                continue
            
            # Skip empty lines at start
            if skip_initial and not line.strip():
                continue
            
            skip_initial = False
            
            # Stop at next heading
            if line.startswith('#'):
                break
            
            # Stop at horizontal rule
            if line.startswith('---'):
                break
            
            # Collect non-empty lines
            if line.strip():
                description_lines.append(line.strip())
            elif description_lines:
                # Stop at first blank line after content
                break
        
        description = ' '.join(description_lines)
        
        # Limit length
        if len(description) > 200:
            description = description[:197] + "..."
        
        return description
    except Exception:
        return ""


def should_skip_directory(dir_path: Path) -> bool:
    """Determine if a directory should be skipped."""
    skip_names = {
        "node_modules",
        ".git",
        "__pycache__",
        "venv",
        "env",
        ".venv",
        "dist",
        "build",
        ".DS_Store",
        ".idea",
        ".vscode"
    }
    
    return dir_path.name in skip_names or dir_path.name.startswith('.')

