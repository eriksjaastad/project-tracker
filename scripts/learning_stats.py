"""Learning measurement and tracking for projects.

Scans LEARNINGS.md files across projects to measure learning activity,
track debt compilation, and identify stale learning loops.
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import PROJECTS_BASE_DIR
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class LearningStats:
    """Statistics for a project's learning activity."""
    project_id: str
    has_learnings: bool
    total_entries: int
    entries_this_week: int
    entries_this_month: int
    last_entry_date: Optional[str]
    days_since_last_entry: Optional[int]
    entries_with_task_links: int
    debt_tracker_entries: int
    compiled_entries: int
    compile_rate: float  # Percentage of debt entries that have been compiled


def parse_learnings_file(learnings_path: Path) -> Dict:
    """Parse a LEARNINGS.md file and extract statistics.
    
    Args:
        learnings_path: Path to the LEARNINGS.md file
        
    Returns:
        Dictionary with learning statistics
    """
    try:
        content = learnings_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Could not read {learnings_path}: {e}")
        return {
            "total_entries": 0,
            "entries_with_dates": [],
            "entries_with_task_links": 0,
            "debt_tracker_entries": 0,
            "compiled_entries": 0
        }
    
    # Find all date-based entries (## 2026-01-11 format)
    date_pattern = r'^## (\d{4}-\d{2}-\d{2})'
    date_entries = re.findall(date_pattern, content, re.MULTILINE)
    
    # Find task linkages (#4685, #task_id, etc.)
    task_link_pattern = r'#\d{4,}'
    task_links = re.findall(task_link_pattern, content)
    
    # Count debt tracker entries (lines in the Learning Debt Tracker table)
    debt_tracker_section = re.search(
        r'## Learning Debt Tracker\s*\n\s*\|.*?\n\s*\|[-\s|]+\n((?:\|.*?\n)+)',
        content,
        re.MULTILINE
    )
    debt_entries = 0
    compiled_count = 0
    if debt_tracker_section:
        debt_lines = debt_tracker_section.group(1).strip().split('\n')
        debt_entries = len([line for line in debt_lines if line.strip().startswith('|')])
        # Count compiled entries (those with a value in the "Compiled Into" column)
        for line in debt_lines:
            if '|' in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4 and parts[3]:  # Has "Compiled Into" value
                    compiled_count += 1
    
    return {
        "total_entries": len(date_entries),
        "entries_with_dates": sorted(date_entries, reverse=True),
        "entries_with_task_links": len(task_links),
        "debt_tracker_entries": debt_entries,
        "compiled_entries": compiled_count
    }


def get_project_learning_stats(project_path: Path, project_id: str) -> LearningStats:
    """Get learning statistics for a single project.
    
    Args:
        project_path: Path to the project directory
        project_id: Project identifier
        
    Returns:
        LearningStats object with all statistics
    """
    learnings_path = project_path / "Documents" / "reference" / "LEARNINGS.md"
    
    if not learnings_path.exists():
        return LearningStats(
            project_id=project_id,
            has_learnings=False,
            total_entries=0,
            entries_this_week=0,
            entries_this_month=0,
            last_entry_date=None,
            days_since_last_entry=None,
            entries_with_task_links=0,
            debt_tracker_entries=0,
            compiled_entries=0,
            compile_rate=0.0
        )
    
    stats = parse_learnings_file(learnings_path)
    
    # Calculate time-based metrics
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    entries_this_week = 0
    entries_this_month = 0
    last_entry_date = None
    days_since_last = None
    
    for date_str in stats["entries_with_dates"]:
        try:
            entry_date = datetime.strptime(date_str, "%Y-%m-%d")
            if entry_date >= week_ago:
                entries_this_week += 1
            if entry_date >= month_ago:
                entries_this_month += 1
            if last_entry_date is None:
                last_entry_date = date_str
                days_since_last = (now - entry_date).days
        except ValueError as e:
            logger.debug(f"Could not parse date {date_str}: {e}")
            continue
    
    # Calculate compile rate
    compile_rate = 0.0
    if stats["debt_tracker_entries"] > 0:
        compile_rate = (stats["compiled_entries"] / stats["debt_tracker_entries"]) * 100
    
    return LearningStats(
        project_id=project_id,
        has_learnings=True,
        total_entries=stats["total_entries"],
        entries_this_week=entries_this_week,
        entries_this_month=entries_this_month,
        last_entry_date=last_entry_date,
        days_since_last_entry=days_since_last,
        entries_with_task_links=stats["entries_with_task_links"],
        debt_tracker_entries=stats["debt_tracker_entries"],
        compiled_entries=stats["compiled_entries"],
        compile_rate=round(compile_rate, 1)
    )


def get_all_learning_stats() -> List[Dict]:
    """Get learning statistics for all projects.
    
    Returns:
        List of dictionaries with learning stats for each project
    """
    base_path = Path(PROJECTS_BASE_DIR)
    all_stats = []
    
    if not base_path.exists() or not base_path.is_dir():
        logger.warning(f"Projects base directory does not exist: {base_path}")
        return []
    
    for project_dir in base_path.iterdir():
        if not project_dir.is_dir():
            continue
        if project_dir.name.startswith('.') or project_dir.name.startswith('_'):
            continue
        
        project_id = project_dir.name.lower().replace(' ', '-')
        stats = get_project_learning_stats(project_dir, project_id)
        all_stats.append(asdict(stats))
    
    # Sort by recent activity (most recent first)
    all_stats.sort(key=lambda x: (
        x['has_learnings'],
        x['last_entry_date'] or '1900-01-01'
    ), reverse=True)
    
    return all_stats


if __name__ == "__main__":
    # Test the scanner
    stats = get_all_learning_stats()
    print(f"Found learning stats for {len(stats)} projects")
    for stat in stats[:5]:
        if stat['has_learnings']:
            print(f"\n{stat['project_id']}:")
            print(f"  Total entries: {stat['total_entries']}")
            print(f"  Last entry: {stat['last_entry_date']} ({stat['days_since_last_entry']} days ago)")
            print(f"  Compile rate: {stat['compile_rate']}%")
