"""TODO.md parser for extracting project metadata."""

import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add parent directory to path for logger import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from logger import get_logger

logger = get_logger(__name__)


def parse_todo(todo_path: Path) -> Dict[str, Any]:
    """Extract metadata from TODO.md."""
    if not todo_path.exists():
        logger.debug(f"TODO.md not found: {todo_path}")
        return {
            "status": "unknown",
            "phase": None,
            "ai_agents": [],
            "cron_jobs": [],
            "completion_pct": 0,
            "description": None
        }
    
    try:
        content = todo_path.read_text()
    except Exception as e:
        logger.error(f"Failed to read TODO.md at {todo_path}: {e}", exc_info=True)
        return {
            "status": "unknown",
            "phase": None,
            "ai_agents": [],
            "cron_jobs": [],
            "completion_pct": 0,
            "description": None
        }
    
    data = {
        "status": "unknown",
        "phase": None,
        "ai_agents": [],
        "cron_jobs": [],
        "completion_pct": 0,
        "description": None
    }
    
    # Extract header metadata (first 30 lines)
    lines = content.split('\n')
    for i, line in enumerate(lines[:30]):
        # Project Status
        if "Project Status:" in line or "**Project Status:**" in line:
            data["status"] = extract_status(line)
        
        # Current Phase
        elif "Current Phase:" in line or "**Current Phase:**" in line:
            data["phase"] = extract_phase(line)
    
    # Extract AI agents
    if "### AI Agents" in content or "## AI Agents" in content:
        data["ai_agents"] = extract_ai_agents(content)
    
    # Extract cron jobs
    if "### Cron Job" in content or "## Cron Job" in content:
        data["cron_jobs"] = extract_cron_jobs(content)
    
    # Calculate completion percentage
    data["completion_pct"] = calculate_completion(content)
    
    # Extract description (first paragraph after title)
    data["description"] = extract_description(content)
    
    return data


def extract_status(line: str) -> str:
    """Extract status from a line."""
    # Remove markdown formatting and emojis
    line = line.replace("**", "").replace("*", "")
    line = re.sub(r'[^\w\s&]', '', line) # Remove emojis and symbols
    line_lower = line.lower()
    
    # Common patterns
    if "active" in line_lower:
        return "active"
    elif "development" in line_lower or "dev" in line_lower:
        return "development"
    elif "paused" in line_lower:
        return "paused"
    elif "stalled" in line_lower:
        return "stalled"
    elif "complete" in line_lower or "done" in line_lower or "shipped" in line_lower or "production ready" in line_lower:
        return "complete"
    
    return "unknown"


def extract_phase(line: str) -> Optional[str]:
    """Extract phase from a line."""
    # Remove markdown formatting
    line = line.replace("**", "").replace("*", "")
    
    # Extract everything after "Phase:" or similar
    parts = re.split(r"Phase:", line, flags=re.IGNORECASE)
    if len(parts) > 1:
        phase = parts[1].strip()
        # Clean up common patterns
        phase = phase.split("##")[0].strip()
        phase = phase.split("\n")[0].strip()
        return phase if phase else None
    
    return None


def extract_ai_agents(content: str) -> List[Dict[str, str]]:
    """Extract AI agents from content."""
    agents = []
    
    # Find AI Agents section
    pattern = r"### AI Agents.*?(?=\n##|\n###|$)"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    
    if not match:
        return agents
    
    section = match.group(0)
    
    # Parse list items like: - **Claude Sonnet 4.5:** Role description
    for line in section.split('\n'):
        if line.strip().startswith('- '):
            # Remove leading dash
            line = line.strip()[2:]
            
            # Try to extract agent name and role
            if ':' in line:
                parts = line.split(':', 1)
                agent_name = parts[0].replace('**', '').strip()
                role = parts[1].strip() if len(parts) > 1 else None
                
                if agent_name:
                    agents.append({
                        "agent_name": agent_name,
                        "role": role
                    })
    
    return agents


def extract_cron_jobs(content: str) -> List[Dict[str, str]]:
    """Extract cron jobs from content."""
    jobs = []
    
    # Find Cron Jobs section
    pattern = r"### Cron Job.*?(?=\n##|\n###|$)"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    
    if not match:
        return jobs
    
    section = match.group(0)
    
    # Parse schedule and command
    schedule = None
    command = None
    description = None
    
    for line in section.split('\n'):
        if "Schedule:" in line:
            schedule_text = line.split("Schedule:", 1)[1].strip().replace('`', '').replace('**', '')
            # Extract just the cron expression (before any parenthetical explanation)
            schedule = schedule_text.split('(')[0].strip() if '(' in schedule_text else schedule_text
        elif "Command:" in line:
            command = line.split("Command:", 1)[1].strip().replace('`', '').replace('**', '')
        elif "Purpose:" in line or "Description:" in line:
            desc_marker = "Purpose:" if "Purpose:" in line else "Description:"
            description = line.split(desc_marker, 1)[1].strip()
    
    if schedule and command:
        jobs.append({
            "schedule": schedule,
            "command": command,
            "description": description
        })
    
    return jobs


def calculate_completion(content: str) -> int:
    """Calculate completion percentage from task checkboxes."""
    total_tasks = content.count("- [ ]") + content.count("- [x]")
    completed_tasks = content.count("- [x]")
    
    if total_tasks == 0:
        return 0
    
    return int((completed_tasks / total_tasks) * 100)


def extract_description(content: str) -> Optional[str]:
    """Extract project description (first paragraph)."""
    lines = content.split('\n')
    
    # Skip title and metadata
    in_content = False
    description_lines = []
    
    for line in lines:
        # Start collecting after we pass the header
        if line.startswith('#'):
            in_content = True
            continue
        
        # Skip empty lines at start
        if not in_content or (not description_lines and not line.strip()):
            continue
        
        # Stop at next heading or section marker
        if line.startswith('#') or line.startswith('---'):
            break
        
        # Stop at blank line after we've collected something
        if not line.strip() and description_lines:
            break
        
        if line.strip() and not line.startswith('**'):
            description_lines.append(line.strip())
    
    description = ' '.join(description_lines)
    
    # Limit length
    if len(description) > 200:
        description = description[:197] + "..."
    
    return description if description else None

