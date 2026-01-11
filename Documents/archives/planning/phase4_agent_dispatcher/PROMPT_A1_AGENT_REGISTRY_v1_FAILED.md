# Prompt A1: Agent Registry (v1 - FAILED)

> **FAILURE RECORD**
> - **Date:** 2026-01-11
> - **Strike 1:** qwen3:4b - Timeout at 120s. Model entered analysis loop on Context Bridge code, never started output.
> - **Strike 2:** deepseek-r1:14b - Timeout at 120s. Model started output but cut off at line 115 (defining `pt` agent).
> - **Root Cause:** Context Bridge section (~80 lines of code) too large. Models spent reasoning time parsing example instead of executing.
> - **Resolution:** Split into A1a/A1b/A1c micro-tasks. See `PROMPT_A1a_*.md`, `PROMPT_A1b_*.md`, `PROMPT_A1c_*.md`.

---

**Task:** Create agent_registry.py with definitions of available agents
**Estimated Time:** 5-10 minutes
**Worker Model:** qwen3:4b (preferred) or deepseek-r1:14b

---

## CONSTRAINTS (READ FIRST)

- DO NOT implement execution logic yet - registry only
- DO NOT hardcode binary paths - use config.py pattern
- DO NOT add more than 2-3 agents for MVP
- COPY the structure pattern from providers.py
- OUTPUT a single complete file

---

## Task Description

Create `scripts/discovery/agent_registry.py` with:
1. Agent dataclass/dict structure defining available agents
2. Command definitions for each agent
3. Function to list available agents
4. Function to get agent by name

---

## [ACCEPTANCE CRITERIA] (MANDATORY CHECKLIST)

- [ ] **File Created:** `scripts/discovery/agent_registry.py` exists
- [ ] **Agent Structure:** Each agent has: name, description, commands list
- [ ] **Command Structure:** Each command has: name, description, args pattern
- [ ] **audit-agent Defined:** Includes health, check, tasks commands
- [ ] **pt Defined:** Includes scan command
- [ ] **List Function:** `get_available_agents()` returns list of agents
- [ ] **Get Function:** `get_agent(name)` returns specific agent or None
- [ ] **Runs Without Error:** Import works

---

## Context Bridge: Agent Definition Pattern

```python
"""
Agent Registry for the Agent Dispatcher UI.
Defines available agents and their commands for dashboard triggering.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Import config for paths
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import AUDIT_BIN_PATH


@dataclass
class AgentCommand:
    """A single command that an agent can execute."""
    name: str
    description: str
    args_template: str = ""  # e.g., "[project_path]" or "--json"
    dangerous: bool = False  # If True, show warning before running


@dataclass
class Agent:
    """An agent that can be triggered from the dashboard."""
    name: str
    description: str
    binary_path: str
    commands: list[AgentCommand] = field(default_factory=list)
    available: bool = True  # Set to False if binary not found


# Define available agents
AGENTS: dict[str, Agent] = {}


def _init_agents():
    """Initialize agent registry with available agents."""
    global AGENTS

    # audit-agent
    audit_path = AUDIT_BIN_PATH or str(Path.home() / "projects" / "audit-agent" / "audit")
    audit_available = Path(audit_path).exists()

    AGENTS["audit-agent"] = Agent(
        name="audit-agent",
        description="Project health, frontmatter validation, and task aggregation",
        binary_path=audit_path,
        available=audit_available,
        commands=[
            AgentCommand(
                name="health",
                description="Calculate health score for a project",
                args_template="[project_path] --json"
            ),
            AgentCommand(
                name="tasks",
                description="Aggregate all TODO items across projects",
                args_template=""
            ),
            AgentCommand(
                name="check",
                description="Check frontmatter validity of files",
                args_template="[file_or_dir]"
            ),
        ]
    )

    # pt (project-tracker)
    pt_path = str(Path(__file__).parent.parent.parent / "pt")
    pt_available = Path(pt_path).exists()

    AGENTS["pt"] = Agent(
        name="pt",
        description="Project Tracker CLI for scanning and listing projects",
        binary_path=pt_path,
        available=pt_available,
        commands=[
            AgentCommand(
                name="scan",
                description="Full scan of all projects",
                args_template=""
            ),
            AgentCommand(
                name="list",
                description="List all tracked projects",
                args_template=""
            ),
        ]
    )


# Initialize on import
_init_agents()


def get_available_agents() -> list[Agent]:
    """Return list of all registered agents."""
    return list(AGENTS.values())


def get_agent(name: str) -> Optional[Agent]:
    """Get agent by name, or None if not found."""
    return AGENTS.get(name)


def get_agent_command(agent_name: str, command_name: str) -> Optional[AgentCommand]:
    """Get specific command from an agent."""
    agent = get_agent(agent_name)
    if not agent:
        return None
    for cmd in agent.commands:
        if cmd.name == command_name:
            return cmd
    return None


if __name__ == "__main__":
    # Quick test
    print("Available Agents:")
    for agent in get_available_agents():
        status = "OK" if agent.available else "NOT FOUND"
        print(f"\n  {agent.name} [{status}]")
        print(f"    {agent.description}")
        print(f"    Binary: {agent.binary_path}")
        print(f"    Commands:")
        for cmd in agent.commands:
            print(f"      - {cmd.name}: {cmd.description}")
```

---

## Verification Command

After creating the file, run:

```bash
cd /Users/eriksjaastad/projects/project-tracker
python -c "
from scripts.discovery.agent_registry import get_available_agents, get_agent

agents = get_available_agents()
print(f'Found {len(agents)} agents:')
for a in agents:
    print(f'  - {a.name}: {len(a.commands)} commands, available={a.available}')

audit = get_agent('audit-agent')
assert audit is not None, 'ERROR: audit-agent not found'
assert len(audit.commands) >= 2, 'ERROR: audit-agent needs commands'

print('OK - Agent registry created successfully')
"
```

**Expected:** Lists agents with their availability status.

---

## Result

- [ ] PASS: File created and verification command succeeds
- [ ] FAIL: Describe error

**Hand back to Floor Manager when complete.**
