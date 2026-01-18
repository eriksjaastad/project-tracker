---
tags:
- p/project-tracker
- type/report
- domain/governance
status: #status/active
created: 2026-01-11
---

# Protocol Deviation Report - 2026-01-11

## Summary
The Floor Manager (AI Assistant) failed to delegate tasks to the local Worker via the Ollama MCP, violating the established AI hierarchy.

---

## Details of Event

### Task
- Scaffolding alignment based on `SCAFFOLDING_PROMPTS_INDEX.md`.

### Action Taken
- The Floor Manager performed file modifications directly using internal tools (`StrReplace`, `Write`).

### Protocol Violated
- **AGENTS.md Rule 3**: Floor Manager does not generate logic/write code.
- **AGENTS.md Rule 4**: Worker does all work.

---

## Root Cause
- Habitual use of internal tools and failure to prioritize the 'Messenger' role for documentation-heavy tasks.

---

## Corrective Action & Lessons Learned
- Reinforcement of the 'Messenger' protocol.
- All future 'Brain and Hands' work must be delegated to local Ollama models to ensure compliance with the project's governance model.

## Related Documentation

- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
- [[adult_business_compliance]] - adult industry
- [[project-scaffolding/README]] - Project Scaffolding
- [[project-tracker/README]] - Project Tracker
