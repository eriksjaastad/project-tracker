# Prompt A2: Agent Executor

**Task:** Add execution logic to run agent commands and capture output
**Estimated Time:** 5-10 minutes
**Worker Model:** qwen3:4b (preferred) or deepseek-r1:14b
**Depends On:** A1 (agent_registry.py must exist)

---

## CONSTRAINTS (READ FIRST)

- DO NOT allow arbitrary commands - only registered agents
- DO NOT run in background - synchronous execution for MVP
- DO NOT modify agent_registry.py structure - add new functions only
- COPY subprocess pattern from providers.py (AuditProvider)
- TIMEOUT: Set 60 second timeout on all commands

---

## Task Description

Add to `scripts/discovery/agent_registry.py`:
1. `run_agent_command()` function that executes a command
2. Capture stdout, stderr, and return code
3. Return structured result dict
4. Handle timeouts gracefully

---

## [ACCEPTANCE CRITERIA] (MANDATORY CHECKLIST)

- [x] **Function Exists:** `run_agent_command(agent_name, command_name, args)` exists
- [x] **Validates Agent:** Returns error if agent not found
- [x] **Validates Command:** Returns error if command not found
- [x] **Captures Output:** Returns stdout, stderr, return_code
- [x] **Handles Timeout:** 60 second timeout with graceful error
- [x] **Returns Structured Data:** Dict with success, output, error, duration_ms

---

## Context Bridge: Subprocess Pattern

Copy this pattern from `providers.py`:

```python
import subprocess
import time
from typing import Any


@dataclass
class CommandResult:
    """Result of running an agent command."""
    success: bool
    output: str
    error: str
    return_code: int
    duration_ms: int
    command: str


def run_agent_command(
    agent_name: str,
    command_name: str,
    args: str = ""
) -> CommandResult:
    """
    Execute an agent command and capture output.

    Args:
        agent_name: Name of the agent (e.g., "audit-agent")
        command_name: Name of the command (e.g., "health")
        args: Additional arguments as string

    Returns:
        CommandResult with output and status
    """
    agent = get_agent(agent_name)
    if not agent:
        return CommandResult(
            success=False,
            output="",
            error=f"Agent not found: {agent_name}",
            return_code=-1,
            duration_ms=0,
            command=""
        )

    if not agent.available:
        return CommandResult(
            success=False,
            output="",
            error=f"Agent binary not found: {agent.binary_path}",
            return_code=-1,
            duration_ms=0,
            command=""
        )

    command = get_agent_command(agent_name, command_name)
    if not command:
        return CommandResult(
            success=False,
            output="",
            error=f"Command not found: {command_name}",
            return_code=-1,
            duration_ms=0,
            command=""
        )

    # Build command line
    cmd_parts = [agent.binary_path, command_name]
    if args:
        cmd_parts.extend(args.split())

    full_command = " ".join(cmd_parts)

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path.home() / "projects")
        )
        duration_ms = int((time.time() - start_time) * 1000)

        return CommandResult(
            success=result.returncode == 0,
            output=result.stdout,
            error=result.stderr,
            return_code=result.returncode,
            duration_ms=duration_ms,
            command=full_command
        )

    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start_time) * 1000)
        return CommandResult(
            success=False,
            output="",
            error="Command timed out after 60 seconds",
            return_code=-1,
            duration_ms=duration_ms,
            command=full_command
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return CommandResult(
            success=False,
            output="",
            error=str(e),
            return_code=-1,
            duration_ms=duration_ms,
            command=full_command
        )
```

---

## Verification Command

After implementing, run:

```bash
cd $PROJECTS_ROOT/project-tracker
python -c "
from scripts.discovery.agent_registry import run_agent_command

# Test with pt list (should work)
result = run_agent_command('pt', 'list')
print(f'Command: {result.command}')
print(f'Success: {result.success}')
print(f'Duration: {result.duration_ms}ms')
print(f'Output preview: {result.output[:100]}...' if result.output else 'No output')

if result.error:
    print(f'Error: {result.error}')

# Test error case
bad_result = run_agent_command('nonexistent', 'foo')
assert not bad_result.success, 'ERROR: Should fail for unknown agent'
print('OK - Executor working')
"
```

**Expected:** Runs pt list and shows output.

---

## Result

- [x] PASS: Executor runs commands and captures output
- [ ] FAIL: Describe error

**Hand back to Floor Manager when complete.**


## Related Documentation

- [Local Model Learnings](Documents/reference/LOCAL_MODEL_LEARNINGS.md) - local AI

