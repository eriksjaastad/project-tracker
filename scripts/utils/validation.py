"""Validation utilities for Kanban board task management.

This module provides validation functions for task creation and updates,
including secret detection, text length validation, project existence checks,
enum validation for status and priority fields, and XSS sanitization.
"""

import re
import html
from typing import Optional, Tuple, Any


# Secret detection patterns from design.md
SECRET_PATTERNS = [
    r'sk-[a-zA-Z0-9]{32,}',                    # OpenAI keys
    r'api[_-]?key[_-]?=\s*["\']?[\w-]+',      # Generic API keys
    r'\d{3}-\d{2}-\d{4}',                      # SSN format
    r'[A-Z0-9]{20,}',                          # Generic long tokens
    r'password\s*=\s*["\']?[\w-]+',            # Passwords
]


# Valid status values for tasks
VALID_STATUSES = ["Backlog", "To Do", "In Progress", "Review", "Done"]

# Valid priority values for tasks
VALID_PRIORITIES = ["Critical", "High", "Medium", "Low"]


def contains_secret(text: str) -> Tuple[bool, str]:
    """Check if text contains secret patterns.
    
    Args:
        text: The text to check for secret patterns.
        
    Returns:
        A tuple of (is_secret, pattern_matched). If a secret is detected,
        returns (True, pattern). Otherwise returns (False, "").
        
    Examples:
        >>> contains_secret("sk-" + "12345678901234567890123456789012")  # Example API key pattern
        (True, 'sk-[a-zA-Z0-9]{32,}')
        >>> contains_secret("This is a normal task")
        (False, '')
    """
    for pattern in SECRET_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return (True, pattern)
    return (False, "")


def validate_task_text(text: str) -> Tuple[bool, Optional[str]]:
    """Validate task text length.
    
    Args:
        text: The task text to validate.
        
    Returns:
        A tuple of (is_valid, error_message). If valid, returns (True, None).
        If invalid, returns (False, error_message).
        
    Examples:
        >>> validate_task_text("Fix bug")
        (True, None)
        >>> validate_task_text("")
        (False, 'Task text must be between 1 and 1000 characters')
        >>> validate_task_text("x" * 1001)
        (False, 'Task text must be between 1 and 1000 characters')
    """
    if not text:
        return (False, "Task text must be between 1 and 1000 characters")
    
    if len(text) < 1:
        return (False, "Task text must be between 1 and 1000 characters")
    
    if len(text) > 1000:
        return (False, "Task text must be between 1 and 1000 characters")
    
    return (True, None)


def validate_project_exists(project_id: str, db_manager: Optional[Any] = None) -> Tuple[bool, Optional[str]]:
    """Validate that a project exists in the database.
    
    Args:
        project_id: The project ID to check.
        db_manager: Optional object with a get_project method. If not provided, creates a new DatabaseManager.
        
    Returns:
        A tuple of (exists, error_message). If project exists, returns (True, None).
        If project doesn't exist, returns (False, error_message).
        
    Examples:
        >>> from scripts.db.manager import DatabaseManager
        >>> db = DatabaseManager()
        >>> validate_project_exists("project-tracker", db)
        (True, None)
        >>> validate_project_exists("nonexistent-project", db)
        (False, "Project 'nonexistent-project' does not exist")
    """
    if not project_id:
        return (False, "Project ID is required")
    
    if db_manager is None:
        # Local import to avoid circular dependency
        from scripts.db.manager import DatabaseManager
        db_manager = DatabaseManager()
    
    project = db_manager.get_project(project_id)
    if project is None:
        return (False, f"Project '{project_id}' does not exist")
    
    return (True, None)


def validate_status(status: str) -> Tuple[bool, Optional[str]]:
    """Validate task status enum value.
    
    Args:
        status: The status value to validate.
        
    Returns:
        A tuple of (is_valid, error_message). If valid, returns (True, None).
        If invalid, returns (False, error_message).
        
    Examples:
        >>> validate_status("Backlog")
        (True, None)
        >>> validate_status("Invalid Status")
        (False, "Status must be one of: Backlog, To Do, In Progress, Done")
    """
    if status not in VALID_STATUSES:
        valid_list = ", ".join(VALID_STATUSES)
        return (False, f"Status must be one of: {valid_list}")
    
    return (True, None)


def validate_priority(priority: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate task priority enum value.
    
    Args:
        priority: The priority value to validate. Can be None.
        
    Returns:
        A tuple of (is_valid, error_message). If valid, returns (True, None).
        If invalid, returns (False, error_message).
        
    Examples:
        >>> validate_priority("High")
        (True, None)
        >>> validate_priority(None)
        (True, None)
        >>> validate_priority("Invalid Priority")
        (False, "Priority must be one of: Critical, High, Medium, Low, or None")
    """
    if priority is None:
        return (True, None)
    
    if priority not in VALID_PRIORITIES:
        valid_list = ", ".join(VALID_PRIORITIES) + ", or None"
        return (False, f"Priority must be one of: {valid_list}")
    
    return (True, None)


def sanitize_task_text(text: str) -> str:
    """Sanitize task text to prevent XSS attacks.
    
    Escapes HTML special characters to prevent script injection.
    This function should be called on all task text before storage and display.
    
    Args:
        text: The task text to sanitize.
        
    Returns:
        Sanitized text with HTML entities escaped.
        
    Examples:
        >>> sanitize_task_text("<script>alert('xss')</script>")
        "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
        >>> sanitize_task_text("Normal task text")
        "Normal task text"
    """
    return html.escape(text, quote=True)


def validate_task_input(
    text: str,
    project_id: str,
    status: str = "Backlog",
    priority: Optional[str] = None,
    db_manager: Optional[Any] = None
) -> Tuple[bool, Optional[str]]:
    """Comprehensive validation for task creation/update.
    
    Validates all task fields in a single call:
    - Task text length (1-1000 characters)
    - Secret detection
    - Project existence
    - Status enum
    - Priority enum
    
    Note: XSS sanitization is handled separately via sanitize_task_text()
    before storing in the database.
    
    Args:
        text: Task text description.
        project_id: Project ID to associate task with.
        status: Task status (default: "Backlog").
        priority: Task priority (optional).
        db_manager: Optional object with a get_project method. If not provided, creates a new DatabaseManager.
        
    Returns:
        A tuple of (is_valid, error_message). If all validations pass,
        returns (True, None). If any validation fails, returns (False, error_message).
        
    Examples:
        >>> from scripts.db.manager import DatabaseManager
        >>> db = DatabaseManager()
        >>> validate_task_input("Fix bug", "project-tracker", "Backlog", "High", db)
        (True, None)
        >>> validate_task_input("", "project-tracker", "Backlog", None, db)
        (False, 'Task text must be between 1 and 1000 characters')
    """
    # Validate text length
    is_valid, error = validate_task_text(text)
    if not is_valid:
        return (False, error)
    
    # Check for secrets
    is_secret, pattern = contains_secret(text)
    if is_secret:
        return (False, f"Task text contains potential secret pattern: {pattern}")
    
    # Validate project exists
    is_valid, error = validate_project_exists(project_id, db_manager)
    if not is_valid:
        return (False, error)
    
    # Validate status
    is_valid, error = validate_status(status)
    if not is_valid:
        return (False, error)
    
    # Validate priority
    is_valid, error = validate_priority(priority)
    if not is_valid:
        return (False, error)
    
    return (True, None)
