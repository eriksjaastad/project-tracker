---
tags:
- p/project-tracker
- type/documentation
- domain/governance
status: #status/active
created: 2026-01-11
---

# Project Tracker Learning Loop

**Purpose:** Centralized reinforcement learning hub.

## Loop Protocol

### Triggers
- **Preventable Failure**: A known pitfall or skip in logic that could have been avoided with existing knowledge.
- **Protocol Deviation**: A bypass of established hierarchy or workflow rules during execution.
- **Scanner/Parser Regression**: Failure in scanning or parsing logic due to unhandled edge cases or input changes.
- **Security/Path Error**: Issues arising from hardcoded paths, insecure practices, or unauthorized access attempts.

### Reinforcement Path
1. **Document** in `LEARNINGS.md` or `MODEL_LEARNINGS.md`.
2. **Add to Debt Tracker** (table below).
3. **Compile**: After 2+ preventable failures, pattern MUST be compiled into `AGENTS.md` or `.cursorrules`.

## Learning Debt Tracker

| Learning                          | Documented Date | Compiled Into                 |
|-----------------------------------|-----------------|-------------------------------|
| Floor Manager Protocol            | 2026-01-11      | AGENTS.md                     |
| No hardcoded paths in prompts     | 2026-01-11      | CODE_QUALITY_STANDARDS.md     |
| Learning loop pattern integration | 2026-01-11      | LEARNINGS.md                  |

## Preventable Failure Log

| Date       | Failure                   | Preventable? | Which Learning?      |
|------------|---------------------------|--------------|----------------------|
| 2026-01-11 | Floor Manager role bypass | YES          | Universal AGENTS.md  |

## Success Patterns

| Pattern                  | Why it works      |
|--------------------------|-------------------|
| Micro-task decomposition | Prevents timeouts |

## Related Documentation

- [[prompt_engineering_guide]] - prompt engineering
- [[queue_processing_guide]] - queue/workflow
- [[security_patterns]] - security
- [[project-tracker/README]] - Project Tracker
