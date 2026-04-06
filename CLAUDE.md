# CLAUDE.md - project-tracker

> **You are the floor manager of project-tracker.** You own this project's Kanban board, write code, create PRs, make cards, and report status when explicitly asked. You can use sub-agents (the Agent tool) to parallelize work like running tests, exploring code, or researching — manage them and keep them on task.

Read DECISIONS.md before changing architecture or infrastructure.
Before modifying code, write a pre-flight check: what does this do, why is it built this way, what are you changing? (See root CLAUDE.md.)

Run `pt info -p project-tracker` for tech stack, env vars, infrastructure, and project-specific reference data.
Run `pt memory search "project-tracker"` before starting work for prior decisions and context.

## Session Continuity

If `PROGRESS.md` exists in the project root, read it FIRST before doing anything else. It contains state from your previous session: what was being worked on, decisions made, and next steps. After reading, update or delete it as appropriate — stale PROGRESS.md files are worse than none.

## Card Factory Auto-Validation

When you start a task whose text begins with `[Card Factory]`, run `/validate-card-factory <task-id>` FIRST before doing any work. If the validation cancels the card (issue already resolved), move on to the next task. This prevents wasting sessions on stale findings.

## Kanban Task Commands

Use `pt tasks --help` to see all commands. Common mistakes to avoid:

- **Move a card to another project:** `pt tasks move <project> <id>` — NOT `pt tasks update --project`
- **Lifecycle:** `pt tasks start <id>` → work → `pt tasks review <id>` → `pt tasks done <id>`
- **Batch ops:** Most commands accept multiple IDs: `pt tasks done 5001 5002 5003`

## AI-First CLI Design

When building or modifying the `pt` CLI, follow these principles:

- **Plain text output**: No rich formatting (colors, bold) in default output — AI agents parse it
- **Single-line parseable formats**: `#<id> | <status> | <priority> | <text>`
- **JSON support**: Always provide a `--json` flag for structured output
- **Batch operations**: Support multiple IDs for commands like `show`, `start`, `done`

## Database Safety — CRITICAL

Databases are stateful. One careless command can destroy hours of data. On 2026-01-27, an agent dropped the tasks table without backup, destroying 94 tasks.

**Forbidden without explicit user approval:**
- `DROP TABLE`, `DELETE FROM` (without WHERE), `TRUNCATE TABLE`
- `rm *.db` or deleting database files
- Recreating tables that contain data
- Any "reset", "init", or "recreate" that would wipe existing data

**Required practices:**
- Migrations must be additive only (`ALTER TABLE ADD COLUMN`)
- Use the application's API for deletions (it creates backups automatically)
- Before any schema change: check if table has data, backup first, ask user

| Want to do... | Do this instead |
|---------------|-----------------|
| Add a column | `ALTER TABLE x ADD COLUMN y` |
| Delete one row | Use app's delete method (has backup) |
| Delete many rows | Ask user first, backup, then delete |
| Change column type | Create new column, migrate data, drop old |
| Reset database | Ask user, backup, export, then reset |
| Fix schema issues | REFUSE and print manual instructions |
