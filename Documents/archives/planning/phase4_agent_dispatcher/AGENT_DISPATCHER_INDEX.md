# Phase 4: Agent Dispatcher UI - Prompts Index

**Feature:** Build UI to manually trigger specialized agents from the dashboard
**Created:** January 11, 2026
**Executor:** Floor Manager (via Ollama MCP)
**Worker Models:** qwen3:4b (primary), deepseek-r1:14b (reasoning)

---

## Context

From TODO.md:
> **Mission Control Hub:** Transform the dashboard from a passive monitor into an active command center.
> **Agent Dispatcher UI:** Build a UI interface to manually trigger specialized agents (e.g., `audit-agent` for security, Scaffolding Sync agent) directly from the dashboard.

The project-tracker already has:
- `scripts/discovery/providers.py` - AuditProvider that calls the `audit` binary
- `audit-agent` CLI with commands: `health`, `check`, `fix`, `tasks`, `log`
- Dashboard at `dashboard/app.py` and `dashboard/templates/`

This feature transforms the dashboard from passive monitoring to active command execution.

---

## Done Criteria (Overall Feature)

All must pass for feature complete:

- [x] **A1: Agent Registry** - `scripts/discovery/agent_registry.py` defines available agents
- [x] **A2: Agent Executor** - Can run agent commands and capture output
- [x] **A3: API Endpoints** - `/api/agents` lists agents, `/api/agents/run` triggers commands
- [x] **A4: Dashboard UI** - Agent Dispatcher section visible with trigger buttons
- [x] **A5: Output Display** - Command output shown in UI after execution
- [x] **A6: Verification** - All verification tests pass

---

## Prompt Execution Order

Execute prompts in sequence. Each builds on the previous.

| # | Prompt File | Description | Est. Time |
|---|-------------|-------------|-----------|
| 1a | `PROMPT_A1a_SKELETON.md` | Create agent_registry.py skeleton (imports + dataclasses) | 3-5 min |
| 1b | `PROMPT_A1b_AGENT_DEFINITIONS.md` | Add audit-agent and pt definitions | 3-5 min |
| 1c | `PROMPT_A1c_GETTER_FUNCTIONS.md` | Add getter functions | 3-5 min |
| 2 | `PROMPT_A2_AGENT_EXECUTOR.md` | Add execution logic with subprocess and output capture | 5-10 min |
| 3 | `PROMPT_A3_API_ENDPOINTS.md` | Add /api/agents and /api/agents/run endpoints | 5-10 min |
| 4 | `PROMPT_A4_DASHBOARD_UI.md` | Add Agent Dispatcher section to dashboard | 5-10 min |
| 5 | `PROMPT_A5_OUTPUT_DISPLAY.md` | Show command output in UI after execution | 5-10 min |
| 6 | `PROMPT_A6_VERIFICATION.md` | Verification tests for all components | 5 min |

> **Note:** A1 was split into A1a/A1b/A1c after v1 timed out on both qwen3:4b and deepseek-r1:14b.
> See `PROMPT_A1_AGENT_REGISTRY_v1_FAILED.md` for failure record.

---

## Key Constraints (Apply to ALL Prompts)

These constraints must be included in every prompt:

```markdown
## CONSTRAINTS (READ FIRST)
- DO NOT add authentication - keep it simple for local use
- DO NOT allow arbitrary command execution - only registered agents
- DO NOT run commands that modify data without user confirmation concept
- COPY patterns from existing providers.py and telemetry_reader.py
- TIMEOUT: Keep tasks atomic (5-10 min max)
```

---

## Available Agents (For Reference)

### audit-agent (Go CLI)
**Binary:** `~/projects/audit-agent/audit` (or in PATH)
**Commands:**
- `audit health [project]` - Calculate project health score
- `audit check [file]` - Check frontmatter/health of file
- `audit fix [file]` - Auto-fix frontmatter issues via AI
- `audit tasks` - Aggregate all TODO items
- `audit log [message]` - Append to activity log

### pt (project-tracker CLI)
**Binary:** `./pt` (in project root)
**Commands:**
- `./pt scan` - Full project scan
- `./pt list` - List all projects

### Future Agents (Placeholder)
- Scaffolding Sync - Sync project with scaffolding templates
- Security Audit - Run security checks

---

## Reference Files

Floor Manager should provide these as context:

1. **Existing provider pattern:** `scripts/discovery/providers.py` (lines 41-75)
2. **Dashboard app:** `dashboard/app.py`
3. **Config:** `config.py` (for AUDIT_BIN_PATH)

---

## Escalation Protocol

If a Worker times out or fails:

1. **Strike 1:** Retry with same model
2. **Strike 2:** Switch model (qwen3:4b → deepseek-r1:14b)
3. **Strike 3:** HALT and report to Conductor

DO NOT manually implement failed Worker tasks.

---

## Progress Tracking

| Prompt | Status | Worker Model | Notes |
|--------|--------|--------------|-------|
| A1 (v1) | [x] FAILED | qwen3:4b, deepseek-r1:14b | Both timed out. Split into A1a/A1b/A1c |
| A1a | [x] Complete | FM Direct | model output corruption issue |
| A1b | [x] Complete | deepseek-r1 | FM Cleaned |
| A1c | [x] Complete | deepseek-r1 | FM Cleaned |
| A2 | [x] Complete | deepseek-r1 | FM Cleaned |
| A3 | [x] Complete | deepseek-r1 | FM Cleaned |
| A4 | [x] Complete | deepseek-r1 | FM Cleaned |
| A5 | [x] Complete | deepseek-r1 | FM Cleaned |
| A6 | [x] Complete | FM Direct | - |

**Overall Status:** [ ] Not Started / [ ] In Progress / [x] Complete

---

**Hand to Floor Manager to begin execution.**


## Related Documentation

- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

