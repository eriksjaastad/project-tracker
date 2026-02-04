"""Hooks system for project tracker events."""

import subprocess
import os
from pathlib import Path
from typing import Dict, Any
from logger import get_logger

logger = get_logger(__name__)

def trigger_review_agent(task_id: int, project_id: str, task_text: str, done_criteria: str):
    """Spawn a reviewer agent for the given task."""
    logger.info(f"Triggering review agent for task #{task_id} in project {project_id}")
    
    # Resolve project path
    from db.manager import DatabaseManager
    db = DatabaseManager()
    project = db.get_project(project_id)
    if not project:
        logger.error(f"Project {project_id} not found")
        return

    project_path = Path(project['path'])
    if not project_path.is_absolute():
        project_path = Path(os.getenv("PROJECTS_ROOT", "")) / project_path

    # 1. Get git diff for the project
    try:
        diff_result = subprocess.run(
            ["git", "diff", "main...HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        # If no diff on branch, try staged/unstaged changes
        if not diff_result.stdout.strip():
            diff_result = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30
            )
        diff_text = diff_result.stdout
    except Exception as e:
        logger.error(f"Failed to get git diff for {project_id}: {e}")
        diff_text = "Error retrieving git diff"

    # 2. Prepare the review prompt
    review_prompt = f"""
    Perform a multi-AI code review for task #{task_id} in project {project_id}.
    
    Task: {task_text}
    Done Criteria: {done_criteria}
    
    Git Diff:
    {diff_text}
    
    Please provide a PASS/FAIL verdict and detailed comments.
    """

    # 3. Spawn a reviewer agent (placeholder for actual agent-hub/MCP call)
    # For now, we use a script that would interface with agent-hub
    review_script = Path(os.getenv("PROJECTS_ROOT", "")) / "_tools" / "agent-hub" / "scripts" / "dispatch_task.py"
    
    if review_script.exists():
        # This would be the actual trigger to the agent hub
        # subprocess.run([sys.executable, str(review_script), "--task", review_prompt, ...])
        logger.info(f"Review agent would be dispatched via {review_script}")
    else:
        logger.warning(f"Review dispatch script not found at {review_script}")

    logger.info(f"Review agent triggered for {project_id} with diff size {len(diff_text)} bytes")

def handle_status_change(task_id: int, old_status: str, new_status: str):
    """Handle task status transitions."""
    if new_status == "Review":
        from db.manager import DatabaseManager
        db = DatabaseManager()
        
        task = db.get_task(task_id)
        if task:
            # Extract Done Criteria from prompt
            prompt = task.get("prompt") or ""
            done_criteria = ""
            prompt_lower = prompt.lower()
            if "## done criteria" in prompt_lower:
                done_criteria = prompt_lower.split("## done criteria")[1].split("##")[0].strip()
            elif "## acceptance criteria" in prompt_lower:
                done_criteria = prompt_lower.split("## acceptance criteria")[1].split("##")[0].strip()
            
            trigger_review_agent(task_id, task['project_id'], task['text'], done_criteria)
