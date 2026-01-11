"""Detect and fix discrepancies in TODO.md files (Hygiene)."""

import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def detect_hygiene_issues(todo_path: Path) -> List[Dict[str, Any]]:
    """
    Detect discrepancies in TODO.md:
    - Phase marked [in_progress] but all tasks are [x].
    - Project marked 'In Progress' but current phase is complete.
    """
    if not todo_path.exists():
        return []
    
    try:
        content = todo_path.read_text()
    except Exception as e:
        logger.warning(f"Failed to read TODO file {todo_path}: {e}")
        return []
        
    issues = []
    lines = content.split('\n')
    
    # 1. Check for Current Phase staleness
    current_phase = None
    status = None
    for line in lines[:30]:
        if "Current Phase:" in line:
            current_phase = line.split("Phase:", 1)[1].strip().replace('**', '').replace('*', '')
        if "Project Status:" in line or "Status:" in line:
            status = line.lower()

    # 2. Find Phase Sections and check task completion
    phase_sections = []
    current_section = None
    
    # Regex to match headers like: ### Phase 3: Audit Agent Integration (Jan 2, 2026) [in_progress]
    phase_header_pattern = re.compile(r'^#+\s*(Phase\s*\d+[:\s].*?)\s*(?:\[(.*?)\])?$', re.IGNORECASE)
    
    for i, line in enumerate(lines):
        match = phase_header_pattern.match(line)
        if match:
            if current_section:
                phase_sections.append(current_section)
            
            phase_name = match.group(1).strip()
            phase_status = match.group(2).strip() if match.group(2) else ""
            current_section = {
                "name": phase_name,
                "status": phase_status,
                "line_index": i,
                "tasks": [],
                "content": line
            }
        elif current_section and line.strip().startswith("- ["):
            task_done = "- [x]" in line.lower()
            current_section["tasks"].append(task_done)
            
    if current_section:
        phase_sections.append(current_section)
        
    # 3. Analyze sections
    all_complete = True
    for section in phase_sections:
        if not section["tasks"]:
            continue
            
        is_done = all(section["tasks"])
        if not is_done:
            all_complete = False
            
        # If phase is done but marked in_progress
        if is_done and "in_progress" in section["status"].lower():
            issues.append({
                "type": "STALE_PHASE",
                "phase": section["name"],
                "line_index": section["line_index"],
                "message": f"Phase '{section['name']}' is complete but marked [in_progress]"
            })
            
    # 4. Check status lines (including frontmatter and bottom of file)
    status_indices = []
    for i, line in enumerate(lines):
        line_lower = line.lower()
        # Match Project Status:, Status:, or frontmatter status:
        if "project status:" in line_lower or "status:" in line_lower:
            # For frontmatter, we specifically look for #status/in-progress
            if "in progress" in line_lower or "development" in line_lower or "active" in line_lower or "#status/in-progress" in line_lower:
                status_indices.append(i)

    if all_complete and status_indices:
        for idx in status_indices:
            issues.append({
                "type": "STALE_STATUS",
                "line_index": idx,
                "message": "Project status is 'In Progress' but all tasks are complete"
            })
                
    return issues

def fix_hygiene_issues(todo_path: Path, dry_run: bool = False) -> int:
    """Fix detected hygiene issues. Returns number of fixes applied."""
    issues = detect_hygiene_issues(todo_path)
    if not issues:
        return 0
        
    if dry_run:
        return len(issues)
        
    lines = todo_path.read_text().split('\n')
    fixes = 0
    
    # Apply fixes in reverse order to keep line indices valid (though they shouldn't change here)
    for issue in sorted(issues, key=lambda x: x['line_index'], reverse=True):
        idx = issue['line_index']
        line = lines[idx]
        
        if issue["type"] == "STALE_PHASE":
            # Replace [in_progress] with [complete]
            new_line = re.sub(r'\[in_progress\]', '[complete]', line, flags=re.IGNORECASE)
            if new_line != line:
                lines[idx] = new_line
                fixes += 1
        
        elif issue["type"] == "STALE_STATUS":
            # Replace In Progress/Development/Active with Complete
            new_line = line
            # Order of replacement matters (specific to general)
            patterns = [
                (r'#status/in-progress', '#status/complete'),
                (r'In Progress 🔄', 'Complete ✅'),
                (r'in progress', 'Complete'),
                (r'Development', 'Complete'),
                (r'Active', 'Complete')
            ]
            for old, new in patterns:
                updated = re.sub(old, new, new_line, flags=re.IGNORECASE)
                if updated != new_line:
                    new_line = updated
                    break # Only apply one replacement per line
            
            if new_line != line:
                lines[idx] = new_line
                fixes += 1
                
    if fixes > 0:
        todo_path.write_text('\n'.join(lines))
        
    return fixes

