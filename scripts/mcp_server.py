#!/usr/bin/env python3
"""
MCP Server for Kanban Board Task Management.

This MCP server provides tools for AI agents to interact with the Kanban board,
allowing programmatic task creation and management.

Usage:
    Run as MCP server: python scripts/mcp_server.py
    Or integrate with MCP client/server infrastructure.
"""

import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.db.manager import DatabaseManager
from scripts.logger import get_logger

logger = get_logger(__name__)


def kanban_add_task(
    project: str,
    text: str,
    status: str = "Backlog",
    priority: Optional[str] = None,
    prompt: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new task in the Kanban board.
    
    This is the MCP tool handler for kanban_add_task. It validates inputs,
    checks for secrets, creates the task in the database, and returns the
    created task object.
    
    Args:
        project: Project ID (e.g., 'project-tracker')
        text: Task description (1-1000 characters)
        status: Initial task status (default: "Backlog")
        priority: Task priority (optional: "Critical", "High", "Medium", "Low")
        prompt: Structured execution instructions for agents (optional)
        
    Returns:
        Dictionary containing the created task with all fields including:
        - id: Task ID
        - text: Task description
        - status: Task status
        - project_id: Project ID
        - priority: Task priority (if set)
        - prompt: Agent execution instructions (if set)
        - created_at: ISO timestamp
        - updated_at: ISO timestamp
        - completed_at: ISO timestamp (if status is "Done")
        
    Raises:
        ValueError: If validation fails (invalid input, secret detected, project not found)
        
    Example:
        >>> result = kanban_add_task("project-tracker", "Fix bug in parser", "To Do", "High")
        >>> print(result["id"])
        42
    """
    try:
        db = DatabaseManager()
        
        # Create task (DatabaseManager handles all validation)
        task = db.add_task(
            text=text,
            project_id=project,
            status=status,
            priority=priority,
            prompt=prompt
        )
        
        logger.info(f"Created task {task['id']} for project {project}: {text[:50]}...")
        
        return {
            "success": True,
            "task": task
        }
        
    except ValueError as e:
        # Validation error - return error response
        logger.warning(f"Task creation failed for project {project}: {e}")
        return {
            "success": False,
            "error": str(e),
            "error_type": "validation_error"
        }
    except Exception as e:
        # Unexpected error
        logger.error(f"Unexpected error creating task: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Internal error: {str(e)}",
            "error_type": "internal_error"
        }


# MCP Tool Definition (JSON Schema)
KANBAN_ADD_TASK_SCHEMA = {
    "name": "kanban_add_task",
    "description": "Create a new task in the Kanban board",
    "inputSchema": {
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Project ID (e.g., 'project-tracker')"
            },
            "text": {
                "type": "string",
                "description": "Task description (1-1000 characters)",
                "minLength": 1,
                "maxLength": 1000
            },
            "status": {
                "type": "string",
                "enum": ["Backlog", "To Do", "In Progress", "Review", "Done"],
                "default": "Backlog",
                "description": "Initial task status"
            },
            "priority": {
                "type": "string",
                "enum": ["Critical", "High", "Medium", "Low"],
                "description": "Task priority (optional)"
            },
            "prompt": {
                "type": "string",
                "description": "Agent prompt (execution instructions for AI)"
            }
        },
        "required": ["project", "text"]
    }
}


# MCP Server Implementation
# This follows the MCP (Model Context Protocol) specification
# For integration with MCP clients, register this tool using the schema above

if __name__ == "__main__":
    # Standalone test mode
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Server for Kanban Board")
    parser.add_argument("--test", action="store_true", help="Run test task creation")
    parser.add_argument("--project", default="project-tracker", help="Project ID")
    parser.add_argument("--text", help="Task text")
    parser.add_argument("--status", default="Backlog", help="Task status")
    parser.add_argument("--priority", help="Task priority")
    parser.add_argument("--prompt", help="Agent prompt")
    
    args = parser.parse_args()
    
    if args.test or args.text:
        result = kanban_add_task(
            project=args.project,
            text=args.text or "Test task from MCP server",
            status=args.status,
            priority=args.priority,
            prompt=args.prompt
        )
        print(json.dumps(result, indent=2))
    else:
        print("MCP Server for Kanban Board")
        print("\nTool Schema:")
        print(json.dumps(KANBAN_ADD_TASK_SCHEMA, indent=2))
        print("\nUsage:")
        print("  python scripts/mcp_server.py --test --project project-tracker --text 'Test task'")
        print("\nFor MCP integration, use the tool schema above to register with your MCP client.")
