"""Hooks system for project tracker events."""

import subprocess
import os
import time
import sys
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from scripts.logger import get_logger

logger = get_logger(__name__)

def _extract_verdict(text: str) -> tuple[str, str | None]:
    """Extract explicit PASS/FAIL verdict from text."""
    if not text:
        return "ERROR", "no_output"
    upper = text.upper()
    verdict_match = re.search(r"\bVERDICT:\s*(PASS|FAIL)\b", upper)
    if verdict_match:
        return verdict_match.group(1), None
    has_pass = "PASS" in upper
    has_fail = "FAIL" in upper
    if has_pass and not has_fail:
        return "PASS", None
    if has_fail and not has_pass:
        return "FAIL", None
    return "ERROR", "ambiguous_verdict"


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if not text:
        return "", False
    if len(text) <= limit:
        return text, False
    return text[:limit], True


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

    # 3. Spawn a reviewer agent
    review_script = Path(os.getenv("PROJECTS_ROOT", "")) / "_tools" / "agent-hub" / "scripts" / "dispatch_task.py"
    
    if review_script.exists():
        # Create a temporary task file for the agent hub
        project_root = Path(os.getenv("PROJECTS_ROOT", ""))
        temp_dir = project_root / "project-tracker" / "data" / "temp_reviews"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = int(time.time())
        review_file = temp_dir / f"review_{task_id}_{timestamp}.md"
        response_file = temp_dir / f"review_{task_id}_{timestamp}.json"
        with open(review_file, 'w') as f:
            f.write(review_prompt)
        
        logger.info(f"Dispatching review task to agent-hub: {review_file}")
        
        # Dispatch in background to avoid blocking the DB transition
        # We use a wrapper or nohup to ensure it keeps running
        try:
            # Use configurable review model from config or env
            from scripts.config import DEFAULT_REVIEW_MODEL
            model = DEFAULT_REVIEW_MODEL
            
            # We'll run it and capture the output to update the task later
            # For a truly non-blocking flow, this should be a separate process
            cmd = [sys.executable, str(review_script), str(review_file), model]
            
            # Start the process
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True # Detach
            )
            
            logger.info(f"Review agent dispatched (PID: {proc.pid})")
            
            # 4. Handle the response and update the task
            # We'll spawn a small thread or separate process to wait for the result
            # and then update the task via the pt CLI.
            import threading
            def update_task_after_review(p, tid, rfile, outfile):
                timeout_seconds = int(os.getenv("PT_REVIEW_TIMEOUT", "600"))
                started_at = datetime.now(timezone.utc).isoformat()
                exit_code = None
                timeout_hit = False
                stdout = ""
                stderr = ""
                
                try:
                    stdout, stderr = p.communicate(timeout=timeout_seconds)
                    exit_code = p.returncode
                except subprocess.TimeoutExpired:
                    timeout_hit = True
                    p.kill()
                    stdout, stderr = p.communicate()
                    exit_code = p.returncode
                except Exception as e:
                    stderr = f"Error collecting review output: {e}"
                    exit_code = p.returncode
                
                finished_at = datetime.now(timezone.utc).isoformat()
                verdict, reason = _extract_verdict(stdout)
                if timeout_hit:
                    verdict = "ERROR"
                    reason = "timeout"
                
                stdout_excerpt, stdout_truncated = _truncate(stdout, 2000)
                stderr_excerpt, stderr_truncated = _truncate(stderr, 2000)
                
                # Persist stable JSON response
                response_payload = {
                    "task_id": tid,
                    "project_id": project_id,
                    "model": model,
                    "verdict": verdict,
                    "reason": reason,
                    "exit_code": exit_code,
                    "timeout_seconds": timeout_seconds,
                    "timeout_hit": timeout_hit,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "stdout": stdout,
                    "stderr": stderr,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "review_file": str(rfile),
                    "response_file": str(outfile)
                }
                try:
                    with open(outfile, "w") as f:
                        json.dump(response_payload, f, indent=2)
                except Exception as e:
                    logger.error(f"Failed to write review response JSON: {e}")
                
                # Prepare review notes
                reason_line = f"Reason: {reason}\n" if reason else ""
                review_notes = (
                    f"AUTO-REVIEW: {verdict}\n"
                    f"{reason_line}"
                    f"Response JSON: {outfile}\n\n"
                    f"STDOUT:\n{stdout_excerpt}\n\n"
                    f"STDERR:\n{stderr_excerpt}"
                )
                
                # Update task status and notes via CLI
                # If PASS, keep in Review for verification; FAIL goes back to In Progress; ERROR stays in Review.
                new_status = "Review"
                if verdict == "FAIL":
                    new_status = "In Progress"
                
                cli_path = Path(os.getenv("PROJECTS_ROOT", "")) / "project-tracker" / "pt"
                # Use bash to run the pt wrapper script since it's a shell script
                subprocess.run([
                    "bash", str(cli_path), "tasks", "update", str(tid),
                    "--status", new_status,
                    "--notes", review_notes
                ])
                logger.info(f"Task #{tid} updated with review results.")

            threading.Thread(
                target=update_task_after_review,
                args=(proc, task_id, review_file, response_file)
            ).start()
            
        except Exception as e:
            logger.error(f"Failed to dispatch review agent: {e}")
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
