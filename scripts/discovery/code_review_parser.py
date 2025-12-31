"""
Code Review Parser - Extract metadata from CODE_REVIEW.md files
"""

import sys
from pathlib import Path
from typing import Dict, Optional
import re
from datetime import datetime

# Add parent directory to path for logger import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from logger import get_logger

logger = get_logger(__name__)


def parse_code_review(file_path: Path) -> Optional[Dict]:
    """
    Parse a CODE_REVIEW.md file to extract review metadata.
    
    Returns dict with:
    - reviewer: str
    - date: str (ISO format)
    - verdict: str (e.g., "NEEDS MAJOR REFACTOR")
    - status: str ("pending", "in_progress", "completed")
    - summary: str (first paragraph after verdict)
    - action_items: List[Dict] with text and checked status
    - completion_pct: int (0-100)
    """
    if not file_path.exists():
        return None
    
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # Extract reviewer
        reviewer_match = re.search(r'\*\*Reviewer:\*\*\s*(.+)', content)
        reviewer = reviewer_match.group(1).strip() if reviewer_match else "Unknown"
        
        # Extract date
        date_match = re.search(r'\*\*Date:\*\*\s*(.+)', content)
        date_str = date_match.group(1).strip() if date_match else None
        
        # Extract verdict
        verdict_match = re.search(r'\*\*Verdict:\*\*\s*\*\*(.+?)\*\*', content)
        verdict = verdict_match.group(1).strip() if verdict_match else "Unknown"
        
        # Try to parse date
        review_date = None
        if date_str:
            try:
                # Try common formats
                for fmt in ["%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
                    try:
                        review_date = datetime.strptime(date_str, fmt).isoformat()
                        break
                    except ValueError:
                        continue
            except Exception as e:
                logger.debug(f"Failed to parse review date '{date_str}': {e}")
                review_date = date_str  # Fallback to original string
        
        # Extract summary (first paragraph after "The Verdict" section)
        summary_match = re.search(r'## The Verdict\n\n(.+?)\n\n', content, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else ""
        
        # Extract action items (look for numbered list items or checkboxes)
        action_items = []
        
        # First, look for checkboxes (- [ ] or - [x])
        checkbox_pattern = r'^- \[([ x])\]\s*(.+)$'
        for match in re.finditer(checkbox_pattern, content, re.MULTILINE):
            checked = match.group(1).lower() == 'x'
            text = match.group(2).strip()
            action_items.append({"text": text, "checked": checked})
        
        # If no checkboxes, look for numbered action items in "What You Should Actually Do" section
        if not action_items:
            action_section_match = re.search(
                r'## What You Should Actually Do\n\n(.+?)(?:\n##|\Z)',
                content,
                re.DOTALL
            )
            if action_section_match:
                action_text = action_section_match.group(1)
                # Extract numbered items (1. Item, 2. Item, etc.)
                for match in re.finditer(r'^\d+\.\s*\*\*(.+?)\*\*', action_text, re.MULTILINE):
                    action_items.append({"text": match.group(1).strip(), "checked": False})
        
        # Calculate completion percentage
        completion_pct = 0
        if action_items:
            checked_count = sum(1 for item in action_items if item["checked"])
            completion_pct = int((checked_count / len(action_items)) * 100)
        
        # Determine status based on verdict and completion
        status = "in_progress"
        if completion_pct == 100:
            status = "completed"
        elif completion_pct == 0:
            status = "pending"
        
        return {
            "reviewer": reviewer,
            "date": review_date or date_str or "Unknown",
            "verdict": verdict,
            "status": status,
            "summary": summary[:200] if summary else "",  # Truncate to 200 chars
            "action_items": action_items,
            "completion_pct": completion_pct
        }
        
    except Exception as e:
        logger.error(f"Error parsing CODE_REVIEW.md at {file_path}: {e}")
        return None

