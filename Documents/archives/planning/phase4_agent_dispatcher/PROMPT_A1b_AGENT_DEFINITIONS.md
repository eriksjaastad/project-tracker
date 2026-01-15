# Prompt A1b: Agent Definitions

**Task:** Add audit-agent and pt agent definitions to the registry
**Estimated Time:** 3-5 minutes
**Worker Model:** qwen3:4b or deepseek-r1:14b
**Depends On:** A1a (skeleton must exist)

---

## CONSTRAINTS (READ FIRST)

- DO NOT rewrite the file - use StrReplace to ADD code
- DO NOT add getter functions yet (that's A1c)
- ADD ONLY: _init_agents() function and call it
- KEEP the addition under 40 lines

---

## Task Description

Add to `scripts/discovery/agent_registry.py`:
1. Import `sys` and add path for config import
2. `_init_agents()` function that populates AGENTS dict
3. Call `_init_agents()` at module level

---

## [ACCEPTANCE CRITERIA]

- [x] `_init_agents()` function exists
- [x] AGENTS contains "audit-agent" entry
- [x] AGENTS contains "pt" entry
- [x] Each agent has at least 2 commands
- [x] Runs without error

---

## Code to Add (use StrReplace)

Replace this:
```python
# Agent registry - populated by A1b
AGENTS: dict[str, Agent] = {}
```

With this:
```python
# Agent registry
AGENTS: dict[str, Agent] = {}


def _init_agents():
    """Populate the agent registry."""
    global AGENTS

    # audit-agent
    audit_path = str(Path.home() / "projects" / "audit-agent" / "audit")
    AGENTS["audit-agent"] = Agent(
        name="audit-agent",
        description="Project health and frontmatter validation",
        binary_path=audit_path,
        available=Path(audit_path).exists(),
        commands=[
            AgentCommand("health", "Calculate project health score", "[project] --json"),
            AgentCommand("tasks", "List all TODO items", ""),
            AgentCommand("check", "Check frontmatter validity", "[file]"),
        ]
    )

    # pt (project-tracker)
    pt_path = str(Path(__file__).parent.parent.parent / "pt")
    AGENTS["pt"] = Agent(
        name="pt",
        description="Project Tracker CLI",
        binary_path=pt_path,
        available=Path(pt_path).exists(),
        commands=[
            AgentCommand("scan", "Full project scan", ""),
            AgentCommand("list", "List tracked projects", ""),
        ]
    )


# Initialize on import
_init_agents()
```

---

## Verification

```bash
python -c "
from scripts.discovery.agent_registry import AGENTS
print(f'Registered agents: {list(AGENTS.keys())}')
assert 'audit-agent' in AGENTS, 'Missing audit-agent'
assert 'pt' in AGENTS, 'Missing pt'
print(f'audit-agent commands: {[c.name for c in AGENTS[\"audit-agent\"].commands]}')
print(f'pt commands: {[c.name for c in AGENTS[\"pt\"].commands]}')
print('OK')
"
```

---

## Result

- [x] PASS / [ ] FAIL

**After PASS, proceed to A1c.**


## Related Documentation

- [[LOCAL_MODEL_LEARNINGS]] - local AI

