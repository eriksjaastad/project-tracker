"""Git metadata extraction."""

import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for logger import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from logger import get_logger

logger = get_logger(__name__)


def get_last_commit_date(project_path: Path) -> Optional[str]:
    """Get last commit date from git."""
    git_dir = project_path / ".git"
    
    if not git_dir.exists():
        return None
    
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.warning(f"Git command timed out for {project_path}")
        return None
    except FileNotFoundError:
        logger.warning(f"Git executable not found for {project_path}")
        return None
    except Exception as e:
        logger.error(f"Failed to get git commit date for {project_path}: {e}")
        return None
    
    return None


def get_last_modified_fallback(project_path: Path) -> str:
    """Fallback to file modification times if git fails."""
    try:
        # Get all files (excluding common directories)
        files = []
        for item in project_path.rglob("*"):
            if item.is_file():
                # Skip common non-project directories
                if any(part in [".git", "node_modules", "__pycache__", "venv", ".DS_Store"] 
                       for part in item.parts):
                    continue
                files.append(item)
        
        if files:
            most_recent = max(f.stat().st_mtime for f in files)
            return datetime.fromtimestamp(most_recent).isoformat()
    except Exception as e:
        logger.warning(f"Failed to get file modification times for {project_path}: {e}")
    
    return datetime.now().isoformat()


def get_last_modified(project_path: Path) -> str:
    """Get last modified timestamp (git first, fallback to files)."""
    # Try git first
    git_date = get_last_commit_date(project_path)
    if git_date:
        return git_date
    
    # Fall back to file modification times
    return get_last_modified_fallback(project_path)

