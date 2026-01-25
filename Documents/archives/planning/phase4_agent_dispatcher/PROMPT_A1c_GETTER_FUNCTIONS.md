# Prompt A1c: Getter Functions

**Task:** Add getter functions to retrieve agents and commands
**Estimated Time:** 3-5 minutes
**Worker Model:** qwen3:4b or deepseek-r1:14b
**Depends On:** A1b (agents must be defined)

---

## CONSTRAINTS (READ FIRST)

- DO NOT rewrite the file - use StrReplace to ADD code
- ADD ONLY: 3 getter functions at end of file
- KEEP the addition under 25 lines

---

## Task Description

Add to end of `scripts/discovery/agent_registry.py`:
1. `get_available_agents()` - returns list of all agents
2. `get_agent(name)` - returns specific agent or None
3. `get_agent_command(agent_name, command_name)` - returns specific command

---

## [ACCEPTANCE CRITERIA]

- [x] `get_available_agents()` returns list of Agent objects
- [x] `get_agent("pt")` returns the pt Agent
- [x] `get_agent("nonexistent")` returns None
- [x] `get_agent_command("pt", "list")` returns AgentCommand
- [x] Runs without error

---

## Code to Add (append after _init_agents() call)

```python


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
```

---

## Verification

```bash
python -c "
from scripts.discovery.agent_registry import get_available_agents, get_agent, get_agent_command

agents = get_available_agents()
print(f'Total agents: {len(agents)}')

pt = get_agent('pt')
assert pt is not None, 'get_agent failed'
print(f'Got agent: {pt.name}')

cmd = get_agent_command('pt', 'list')
assert cmd is not None, 'get_agent_command failed'
print(f'Got command: {cmd.name}')

none_agent = get_agent('nonexistent')
assert none_agent is None, 'Should return None for unknown'
print('OK - All getters work')
"
```

---

## Result

- [x] PASS / [ ] FAIL

**After PASS, A1 is complete. Proceed to A2.**


## Related Documentation

- [Local Model Learnings](Documents/reference/LOCAL_MODEL_LEARNINGS.md) - local AI

