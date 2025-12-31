"""Parser for EXTERNAL_RESOURCES.md to extract service dependencies."""

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import EXTERNAL_RESOURCES_FILE


def parse_external_resources(resources_path: Optional[Path] = None) -> Dict[str, List[Dict[str, any]]]:
    """
    Parse EXTERNAL_RESOURCES.md and extract services by project.
    
    Returns: {project_id: [{"service_name": str, "cost_monthly": float, "purpose": str}]}
    """
    if resources_path is None:
        resources_path = EXTERNAL_RESOURCES_FILE
    
    if not resources_path.exists():
        return {}
    
    try:
        content = resources_path.read_text()
    except Exception:
        return {}
    
    services_by_project = {}
    
    # Find "Resources by Project" section
    section_match = re.search(r"## Resources by Project\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if not section_match:
        return {}
    
    section_content = section_match.group(1)
    
    # Find all project sections using regex
    project_pattern = r"###\s+([^\n]+)\n((?:(?!###)[\s\S])*?)(?=\n###|\Z)"
    matches = re.finditer(project_pattern, section_content)
    
    for match in matches:
        project_name = match.group(1).strip()
        section_text = match.group(2)
        
        project_id = normalize_project_name(project_name)
        
        lines = section_text.split('\n')
        
        services = []
        
        for line in lines:
            # Look for service lines: - ✅ Service Name (details)
            if line.strip().startswith('-'):
                service = parse_service_line(line)
                if service:
                    services.append(service)
            
            # Stop at monthly cost line or next section
            if "**Monthly cost:**" in line or line.startswith('---'):
                break
        
        if services:
            services_by_project[project_id] = services
    
    return services_by_project


def normalize_project_name(name: str) -> str:
    """Convert project name to project ID format."""
    # Just convert to lowercase slug - DON'T strip "Projects" or "Project"
    # This needs to match how project_scanner generates IDs
    return name.lower().replace(" ", "-").strip()


def parse_service_line(line: str) -> Optional[Dict[str, any]]:
    """
    Parse a service line like:
    - ✅ Railway (hosting + Postgres)
    - ✅ OpenAI API (GPT-4o, 4o-mini, o1)
    """
    # Remove checkbox and leading/trailing whitespace
    line = line.strip().lstrip('-').strip()
    line = re.sub(r'^[✅⚠️❌]\s*', '', line)
    
    if not line:
        return None
    
    # Skip lines that are notes or metadata
    if line.startswith('Provides') or line.startswith('Uses ') or line.startswith('May have'):
        return None
    
    # Parse: Service Name (details)
    match = re.match(r'([^(]+)(?:\(([^)]+)\))?', line)
    if not match:
        return None
    
    service_name = match.group(1).strip()
    purpose = match.group(2).strip() if match.group(2) else None
    
    # Extract cost if in purpose (not always there)
    cost_monthly = None
    
    # Clean up service name (remove API, etc. suffixes for cleaner display)
    service_name = service_name.replace(' API', '')
    
    # Skip local-only tools
    if any(skip in service_name.lower() for skip in ['sqlite', 'local', 'rclone', 'python']):
        return None
    
    return {
        "service_name": service_name,
        "cost_monthly": cost_monthly,
        "purpose": purpose
    }


def get_project_monthly_cost(content: str, project_name: str) -> Optional[float]:
    """Extract monthly cost for a specific project."""
    # Find project section
    pattern = rf"###\s+{re.escape(project_name)}.*?\*\*Monthly cost:\*\*\s*([^\n]+)"
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        return None
    
    cost_text = match.group(1)
    
    # Parse cost: ~$12, $5-20, $0, etc.
    cost_match = re.search(r'\$(\d+(?:\.\d+)?)', cost_text)
    if cost_match:
        return float(cost_match.group(1))
    
    return None

