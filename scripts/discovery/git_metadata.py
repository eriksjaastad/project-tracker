"""Git metadata extraction."""

import sys
import subprocess
from datetime import datetime, timezone
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
            return datetime.fromtimestamp(most_recent, tz=timezone.utc).isoformat()
    except Exception as e:
        logger.warning(f"Failed to get file modification times for {project_path}: {e}")
    
    return datetime.now(timezone.utc).isoformat()


def get_last_modified(project_path: Path) -> str:
    """Get last modified timestamp (latest of git commit or file edit)."""
    # Get git date if available
    git_date = get_last_commit_date(project_path)
    
    # Get file system date
    fs_date = get_last_modified_fallback(project_path)
    
    # If no git date, return fs date
    if not git_date:
        return fs_date
        
    # Return the later of the two
    try:
        # We replace Z with +00:00 for fromisoformat compatibility in Python < 3.11
        git_iso = git_date.replace('Z', '+00:00')
        fs_iso = fs_date.replace('Z', '+00:00')
        
        git_dt = datetime.fromisoformat(git_iso)
        fs_dt = datetime.fromisoformat(fs_iso)
        
        # Ensure both are offset-aware for comparison
        if git_dt.tzinfo is None:
            git_dt = git_dt.replace(tzinfo=timezone.utc)
        if fs_dt.tzinfo is None:
            fs_dt = fs_dt.replace(tzinfo=timezone.utc)
            
        return git_date if git_dt > fs_dt else fs_date
    except Exception as e:
        logger.warning(f"Error comparing dates for {project_path}: {e}")
        return git_date or fs_date

