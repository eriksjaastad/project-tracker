"""Project scanner for auto-discovery."""

import sys
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from .git_metadata import get_last_modified
from .todo_parser import parse_todo
from .providers import get_provider

# Add parent directory to path for config and logger imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import PROJECTS_BASE_DIR
from logger import get_logger

logger = get_logger(__name__)


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


def scan_health_parallel(projects: List[Dict], max_workers: int = 8) -> Dict[str, Dict]:
    """Run health checks in parallel, return {project_id: {"score": N, "grade": "X"}}."""
    provider = get_provider()
    results = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(provider.get_health, p["path"]): p["id"]
            for p in projects
        }
        for future in as_completed(futures):
            project_id = futures[future]
            try:
                results[project_id] = future.result()
            except Exception as e:
                logger.error(f"Health check failed for {project_id}: {e}")
                results[project_id] = None
    
    return results


def is_infrastructure_project(project_name: str, todo_content: str = "") -> bool:
    """Detect if a project is infrastructure based on TODO.md marker only."""
    # Infrastructure detection is data-driven: projects must explicitly declare
    # their type in TODO.md with: **Type:** Infrastructure
    # NO hardcoded lists. NO name matching. Data lives with the project.
    return "**Type:** Infrastructure" in todo_content or "**Type:** Infra" in todo_content


def validate_index_file(index_path: Path) -> bool:
    """Basic validation of index file according to Critical Rule #0."""
    try:
        content = index_path.read_text()
        
        # Check for YAML frontmatter
        if not content.strip().startswith('---'):
            return False
            
        # Check for required tags
        required_tags = ["map/project", "p/", "type/", "domain/", "status/", "tech/"]
        tags_section = content.split('---')[1]
        if not all(tag in tags_section for tag in required_tags):
            return False
            
        # Check for required sections (case-insensitive and partial match)
        required_sections = ["Key Components", "Status"]
        content_upper = content.upper()
        for section in required_sections:
            if f"## {section.upper()}" not in content_upper and f"### {section.upper()}" not in content_upper:
                # Also check for variants with icons like "## 🎯 Status"
                if not any(f"{section.upper()}" in line.upper() for line in content.split('\n') if line.startswith('##')):
                    return False
            
        return True
    except Exception as e:
        logger.warning(f"Error validating index file {index_path}: {e}")
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
        "is_infrastructure": False,
        "has_index": False,
        "index_is_valid": False,
        "index_updated_at": None,
        "project_type": "standard"
    }
    
    # Check for index file (00_Index_*.md)
    index_files = list(project_path.glob("00_Index_*.md"))
    if index_files:
        index_file = index_files[0]
        metadata["has_index"] = True
        metadata["index_is_valid"] = validate_index_file(index_file)
        try:
            metadata["index_updated_at"] = datetime.fromtimestamp(index_file.stat().st_mtime).isoformat()
            
            # Extract project_type from YAML tags
            content = index_file.read_text()
            if content.strip().startswith('---'):
                try:
                    frontmatter = yaml.safe_load(content.split('---')[1])
                    if frontmatter and "tags" in frontmatter:
                        for tag in frontmatter["tags"]:
                            if tag.startswith("type/"):
                                metadata["project_type"] = tag.replace("type/", "")
                                break
                except Exception as e:
                    logger.debug(f"Failed to parse YAML for {index_file}: {e}")
        except Exception as e:
            logger.warning(f"Failed to get metadata from index file {index_file}: {e}")
    
    # Parse TODO.md if exists
    todo_path = project_path / "TODO.md"
    todo_content = ""
    if todo_path.exists():
        try:
            todo_content = todo_path.read_text()
        except Exception as e:
            logger.warning(f"Failed to read TODO.md for {project_path.name}: {e}")
        
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
    except Exception as e:
        logger.warning(f"Failed to extract description from {readme_path}: {e}")
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

