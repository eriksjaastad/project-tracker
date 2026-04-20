# CLAUDE.md - project-tracker

**What this is:** project-tracker is the `pt` CLI, Kanban board, and dashboard that every other project in `~/projects` depends on for task coordination, agent memory, and cross-project messaging. If this project breaks, every other agent loses its work queue and its shared memory surface. "Broken" means: `pt` exits non-zero on common commands, the Kanban DB loses rows, or the dashboard stops loading. Treat data loss here as portfolio-wide damage, not a local bug.

> **You are the floor manager of project-tracker.** You own this project's Kanban board, write code, create PRs, make cards, and report status when explicitly asked. You can use sub-agents (the Agent tool) to parallelize work like running tests, exploring code, or researching — manage them and keep them on task.

Read DECISIONS.md before changing architecture or infrastructure.
Before modifying code, write a pre-flight check: what does this do, why is it built this way, what are you changing? (See root CLAUDE.md.)

Run `pt info -p project-tracker` for tech stack, env vars, infrastructure, and project-specific reference data.
Run `pt memory search "project-tracker"` before starting work for prior decisions and context.

## Session Continuity

If `PROGRESS.md` exists in the project root, read it FIRST before doing anything else. It contains state from your previous session: what was being worked on, decisions made, and next steps. After reading, update or delete it as appropriate — stale PROGRESS.md files are worse than none.

**`PROGRESS.md` is always dirty in `git status`.** It's updated daily as part of normal operation — an `M PROGRESS.md` line is the expected state, not a finding. Don't flag it as uncommitted work, don't offer to commit it, and don't suggest the user review it unless you yourself just modified it in this session.

## Card Factory Auto-Validation

When you start a task whose text begins with `[Card Factory]`, run `/validate-card-factory <task-id>` FIRST before doing any work. If the validation cancels the card (issue already resolved), move on to the next task. This prevents wasting sessions on stale findings.

## Database Safety — CRITICAL

On 2026-01-27, an agent dropped the tasks table without backup, destroying 94 tasks. The rule below exists because of that incident. Do not skip the gate.

### GATE — run before any schema change or row-affecting statement

Before running `DROP`, `DELETE`, `TRUNCATE`, `ALTER` (non-additive), `rm *.db`, or any "reset/init/recreate" operation, write these four lines out loud in chat. If any line is blank or guessed, **stop and ask Erik**:

1. **Table:** `<name>`
2. **Row count right now:** `<integer from SELECT COUNT(*)>`
3. **Backup path:** `<absolute path of the backup you just created, or the auto-backup from pt>`
4. **Approval:** `<direct quote from Erik authorizing this specific operation>`

Additive migrations (`ALTER TABLE x ADD COLUMN y`) are the only schema changes that do not need the gate. Everything else does. Deletions of user data go through the application API (which auto-backs up) — not raw SQL.

If a schema is broken and fixing it requires a destructive op, **refuse and print manual instructions**. Do not fix it yourself.
