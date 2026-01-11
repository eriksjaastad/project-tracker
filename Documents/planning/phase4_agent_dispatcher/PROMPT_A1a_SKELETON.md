# Prompt A1a: Agent Registry Skeleton

**Task:** Create agent_registry.py with imports and dataclasses only
**Estimated Time:** 3-5 minutes
**Worker Model:** qwen3:4b or deepseek-r1:14b

> **Context:** This is a simplified version after v1 timed out. We're breaking the task into 3 micro-tasks: A1a (skeleton), A1b (agent definitions), A1c (getter functions).

---

## CONSTRAINTS (READ FIRST)

- OUTPUT ONLY: imports + 2 dataclasses + empty AGENTS dict
- DO NOT add agent definitions yet (that's A1b)
- DO NOT add functions yet (that's A1c)
- KEEP IT SHORT - under 30 lines total

---

## Task Description

Create `scripts/discovery/agent_registry.py` with ONLY:
1. Module docstring (1 line)
2. Imports (pathlib, dataclasses, typing)
3. `AgentCommand` dataclass
4. `Agent` dataclass
5. Empty `AGENTS: dict[str, Agent] = {}`

---

## [ACCEPTANCE CRITERIA]

- [x] File created at `scripts/discovery/agent_registry.py`
- [x] Has `from dataclasses import dataclass, field`
- [x] Has `AgentCommand` dataclass with: name, description, args_template
- [x] Has `Agent` dataclass with: name, description, binary_path, commands, available
- [x] Has empty `AGENTS = {}` dict
- [x] File is under 35 lines
- [x] Runs without error

---

## Exact Code to Output

```python
"""Agent Registry for the Agent Dispatcher UI."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AgentCommand:
    """A command that an agent can execute."""
    name: str
    description: str
    args_template: str = ""
    dangerous: bool = False


@dataclass
class Agent:
    """An agent that can be triggered from the dashboard."""
    name: str
    description: str
    binary_path: str
    commands: list[AgentCommand] = field(default_factory=list)
    available: bool = True


# Agent registry - populated by A1b
AGENTS: dict[str, Agent] = {}
```

---

## Verification

```bash
python -c "
from scripts.discovery.agent_registry import Agent, AgentCommand, AGENTS
print(f'AgentCommand fields: {AgentCommand.__dataclass_fields__.keys()}')
print(f'Agent fields: {Agent.__dataclass_fields__.keys()}')
print(f'AGENTS is dict: {isinstance(AGENTS, dict)}')
print('OK')
"
```

---

## Result

- [x] PASS: File created and verification command succeeds
- [ ] FAIL: Describe error

**After PASS, proceed to A1b.**
