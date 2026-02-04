"""Project scanner for auto-discovery."""

import sys
import yaml
import subprocess
import tempfile
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from .git_metadata import get_last_modified
from .todo_parser import parse_todo
from .providers import get_provider

# Add parent directory to path for config and logger imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.config import PROJECTS_BASE_DIR
from scripts.logger import get_logger

logger = get_logger(__name__)


def clean_phase(phase: Optional[str]) -> Optional[str]:
    """Normalize phase value and drop template placeholders."""
    if not phase:
        return None
    if "{{" in phase or "}}" in phase:
        return None
    if "Foundation/MVP/Production" in phase:
        return None
    cleaned = phase.strip()
    return cleaned or None


def clean_description(text: Optional[str]) -> str:
    """Remove placeholders and malformed wiki-style links from descriptions."""
    if not text:
        return ""
    cleaned = re.sub(
        r"<!--\s*SCAFFOLD:START.*?SCAFFOLD:END.*?-->",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )
    cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\{\{[^}]+\}\}", "", cleaned)
    cleaned = re.sub(r"\[([^\]|]+)\|([^\]]+)\]\([^)]+\)", r"\2", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def _safe_iterdir(path: Path) -> List[Path]:
    """Return directory contents, logging and continuing on errors."""
    try:
        return list(path.iterdir())
    except PermissionError as e:
        logger.warning(f"Permission denied scanning {path}: {e}")
        return []
    except OSError as e:
        logger.warning(f"Filesystem error scanning {path}: {e}")
        return []


def discover_projects(
    base_path: Optional[Union[str, Path]] = None,
    sync_indexes: bool = False
) -> List[Dict[str, Any]]:
    """Scan directory for projects."""
    if base_path is None:
        base_path = PROJECTS_BASE_DIR
    if isinstance(base_path, str) and not base_path.strip():
        logger.warning("PROJECTS_BASE_DIR is empty; cannot scan for projects.")
        return []
    base = Path(base_path)
    
    if not base.exists():
        logger.warning(f"Projects base path does not exist: {base}")
        return []
    
    if not base.is_dir():
        logger.warning(f"Projects base path is not a directory: {base}")
        return []
    
    projects = []
    
    # Check if directory is empty (no subdirectories)
    subdirs = [item for item in _safe_iterdir(base) if item.is_dir()]
    if not subdirs:
        logger.info(f"Projects base path is empty (no subdirectories found): {base}")
        return []

    marker_files = [
        ".git",
        "README.md",
        "TODO.md",
        "pyproject.toml",
        "requirements.txt",
        "Pipfile",
        "package.json",
        "tsconfig.json",
        "Cargo.toml",
        "go.mod",
        "Gemfile",
        "composer.json",
        "Makefile"
    ]
    code_dirs = ["src", "lib", "app", "apps", "packages", "backend", "frontend", "server", "client"]
    code_exts = [".py", ".js", ".ts"]
    
    for item in _safe_iterdir(base):
        if not item.is_dir():
            continue
        
        # Skip common non-project directories and junk
        if should_skip_directory(item):
            continue
        
        # Check for indicators of a project (fast path)
        has_index = any(item.glob("00_Index_*.md"))
        has_marker = has_index or any((item / marker).exists() for marker in marker_files)

        # If no markers, do limited code file checks in common code dirs
        has_code = False
        if not has_marker:
            for code_dir in code_dirs:
                candidate = item / code_dir
                if not candidate.is_dir():
                    continue
                for ext in code_exts:
                    # Fast shallow check - only look at top level, not recursive
                    if any(candidate.glob(f"*{ext}")):
                        has_code = True
                        break
                if has_code:
                    break

        # If it looks like a project, extract metadata
        if has_marker or has_code:
            project = extract_project_metadata(item)
            if project:
                if sync_indexes:
                    _sync_project_index(project, item)
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
    
    # Read scaffolding version if exists
    version_file = project_path / ".scaffolding-version"
    if version_file.exists():
        try:
            import json
            version_data = json.loads(version_file.read_text())
            metadata["scaffolding_version"] = version_data.get("scaffolding_version")
            metadata["rules_version"] = version_data.get("rules_version")
            metadata["scaffolding_applied_at"] = version_data.get("applied_at")
        except Exception as e:
            logger.debug(f"Failed to read .scaffolding-version for {project_path.name}: {e}")
    else:
        metadata["scaffolding_version"] = None
        metadata["rules_version"] = None
        metadata["scaffolding_applied_at"] = None
    
    # Parse TODO.md if exists
    todo_path = project_path / "TODO.md"
    todo_content = ""
    todo_data = parse_todo(todo_path)
    
    # If TODO status is unknown or missing, try to use index status
    current_status = todo_data.get("status", "unknown")
    if current_status in ["unknown", "no TODO.md"] and metadata.get("has_index"):
        # We already have index_file from line 146
        try:
            content = index_files[0].read_text()
            if '---' in content:
                frontmatter_text = content.split('---')[1]
                # Look for status/ tag
                for line in frontmatter_text.split('\n'):
                    if 'status/' in line:
                        status_tag = line.split('status/')[1].split()[0].strip(' -[]')
                        if status_tag:
                            current_status = status_tag
                            break
        except (OSError, yaml.YAMLError) as e:
            logger.debug(f"Could not extract status from index file: {e}")

    metadata.update({
        "status": current_status,
        "phase": clean_phase(todo_data.get("phase")),
        "completion_pct": todo_data.get("completion_pct", 0),
        "ai_agents": todo_data.get("ai_agents", []),
        "cron_jobs": todo_data.get("cron_jobs", [])
    })

    if todo_path.exists():
        try:
            todo_content = todo_path.read_text()
        except Exception as e:
            logger.warning(f"Failed to read TODO.md for {project_path.name}: {e}")
        
        # Use TODO description if available
        # TODO.md descriptions are deprecated; use README.md only.
    
    # Detect infrastructure projects
    metadata["is_infrastructure"] = is_infrastructure_project(metadata["name"], todo_content)
    
    # Parse README.md for description if TODO didn't provide one
    if not metadata["description"]:
        readme_path = project_path / "README.md"
        if readme_path.exists():
            metadata["description"] = clean_description(extract_readme_description(readme_path))
    
    return metadata


def _get_git_recent_activity(project_path: Path, max_entries: int = 10) -> Optional[Dict[str, Any]]:
    """Return recent git activity and latest commit timestamp, if available."""
    try:
        result = subprocess.run(
            ["git", "log", f"-{max_entries}", "--pretty=format:%cs|%s"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug(f"Git log unavailable for {project_path}: {e}")
        return None

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return None

    entries = []
    latest_date = None
    for line in lines:
        if "|" not in line:
            continue
        date_str, message = line.split("|", 1)
        entries.append(f"- {date_str}: {message.strip()}")
        if not latest_date:
            latest_date = date_str

    if not entries:
        return None

    return {
        "entries": entries,
        "latest_date": latest_date
    }


def _replace_recent_activity_section(content: str, new_entries: List[str]) -> Optional[str]:
    """Replace or append the Recent Activity section. Return updated content if changed."""
    header_lines = [line for line in content.splitlines() if line.startswith("##")]
    recent_header = None
    for line in header_lines:
        if "recent activity" in line.lower():
            recent_header = line
            break

    new_section = "\n".join([recent_header or "## Recent Activity", ""] + new_entries + [""])

    if recent_header:
        lines = content.splitlines()
        start_idx = next(i for i, line in enumerate(lines) if line == recent_header)
        end_idx = None
        for i in range(start_idx + 1, len(lines)):
            if lines[i].startswith("## "):
                end_idx = i
                break
        before = lines[:start_idx]
        after = lines[end_idx:] if end_idx is not None else []
        updated = "\n".join(before + new_section.splitlines() + after).strip() + "\n"
    else:
        updated = content.strip() + "\n\n" + new_section + "\n"

    if updated.strip() == content.strip():
        return None
    return updated


def _atomic_write(path: Path, content: str) -> None:
    """Write content to file atomically using temp file + rename."""
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent)) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def _sync_project_index(project: Dict[str, Any], project_path: Path) -> None:
    """Update Recent Activity in index file based on git history."""
    if not project.get("has_index"):
        return

    index_files = list(project_path.glob("00_Index_*.md"))
    if not index_files:
        return

    index_path = index_files[0]
    activity = _get_git_recent_activity(project_path, max_entries=10)
    if not activity:
        return

    try:
        index_mtime = datetime.fromtimestamp(index_path.stat().st_mtime)
    except Exception as e:
        logger.debug(f"Unable to read mtime for {index_path}: {e}")
        index_mtime = None

    try:
        latest_git_date = datetime.fromisoformat(activity["latest_date"])
    except Exception:
        latest_git_date = None

    if index_mtime and latest_git_date and latest_git_date <= index_mtime:
        return

    try:
        content = index_path.read_text()
    except Exception as e:
        logger.warning(f"Failed to read index file {index_path}: {e}")
        return

    updated_content = _replace_recent_activity_section(content, activity["entries"])
    if not updated_content:
        return

    _atomic_write(index_path, updated_content)
    logger.info(f"Updated Recent Activity in {index_path.name} ({project_path.name})")


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


def _load_ptignore() -> set:
    """Load directory names to skip from .ptignore file."""
    ptignore_path = Path(PROJECTS_BASE_DIR) / ".ptignore"
    ignore_names = set()

    if ptignore_path.exists():
        try:
            for line in ptignore_path.read_text().splitlines():
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    ignore_names.add(line)
        except Exception as e:
            logger.warning(f"Failed to read .ptignore: {e}")

    return ignore_names


# Cache the ptignore contents (loaded once per process)
_ptignore_cache = None


def should_skip_directory(dir_path: Path) -> bool:
    """Determine if a directory should be skipped."""
    global _ptignore_cache

    # Load .ptignore on first call
    if _ptignore_cache is None:
        _ptignore_cache = _load_ptignore()

    # Built-in skip list (common non-project directories)
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
        ".vscode",
        "_trash",
        "trash",
        "archives",
        "logs",
        "data",
        "plugin-duplicate-detection",
        "plugin-find-names-chrome"
    }

    # Combine built-in skip list with .ptignore
    all_skip_names = skip_names | _ptignore_cache

    return dir_path.name in all_skip_names or dir_path.name.startswith('.')

