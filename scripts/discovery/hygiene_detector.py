"""Hygiene detector — DEPRECATED.

TODO.md hygiene checking is obsolete. DIRECTION.md replaced TODO.md
as free-form markdown with no required structure to validate.
These stubs exist so callers don't crash if they haven't been updated yet.
"""

from pathlib import Path
from typing import List, Dict, Any


def detect_hygiene_issues(todo_path: Path) -> List[Dict[str, Any]]:
    """No-op stub. TODO.md hygiene checking is removed."""
    return []


def fix_hygiene_issues(todo_path: Path, dry_run: bool = False) -> int:
    """No-op stub. TODO.md hygiene fixing is removed."""
    return 0
