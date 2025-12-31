"""Parser for EXTERNAL_RESOURCES.yaml to extract service dependencies."""

import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for config and logger imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import EXTERNAL_RESOURCES_FILE
from logger import get_logger

logger = get_logger(__name__)


def parse_external_resources(resources_path: Optional[Path] = None) -> Dict[str, List[Dict[str, any]]]:
    """
    Parse EXTERNAL_RESOURCES.yaml and extract services by project.
    
    Returns: {project_id: [{"service_name": str, "cost_monthly": float, "purpose": str}]}
    """
    if resources_path is None:
        resources_path = EXTERNAL_RESOURCES_FILE
    
    # Try .yaml extension first, fall back to .md for backwards compatibility
    if not resources_path.exists():
        yaml_path = resources_path.parent / "EXTERNAL_RESOURCES.yaml"
        if yaml_path.exists():
            resources_path = yaml_path
        else:
            logger.warning(f"Neither {resources_path} nor {yaml_path} exists")
            return {}
    
    try:
        with open(resources_path, 'r') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to read EXTERNAL_RESOURCES.yaml at {resources_path}: {e}")
        return {}
    
    if not data or 'projects' not in data:
        logger.warning(f"No 'projects' key found in {resources_path}")
        return {}
    
    services_by_project = {}
    
    for project_name, project_data in data['projects'].items():
        # project_name is already in the right format (e.g., "trading-projects")
        project_id = project_name
        
        if 'services' not in project_data:
            continue
        
        services = []
        for service in project_data['services']:
            # Skip local-only tools (SQLite, rclone, local services)
            service_type = service.get('type', '').lower()
            if service_type == 'local':
                continue
            
            # Skip database services (they're infrastructure, not external services)
            if service_type == 'database':
                continue
            
            service_name = service.get('name', '')
            if not service_name:
                continue
            
            services.append({
                "service_name": service_name,
                "cost_monthly": service.get('cost', 0),
                "purpose": service.get('purpose', '')
            })
        
        if services:
            services_by_project[project_id] = services
    
    return services_by_project



