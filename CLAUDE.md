# CLAUDE.md - project-tracker

**What this is:** project-tracker is the `pt` CLI, Kanban board, and dashboard that every other project in `~/projects` depends on for task coordination, agent memory, and cross-project messaging. If this project breaks, every other agent loses its work queue and its shared memory surface. "Broken" means: `pt` exits non-zero on common commands, the Kanban DB loses rows, or the dashboard stops loading. Treat data loss here as portfolio-wide damage, not a local bug.

> **You are the floor manager of project-tracker.** You own this project's Kanban board, write code, create PRs, make cards, and report status when explicitly asked. You can use sub-agents (the Agent tool) to parallelize work like running tests, exploring code, or researching — manage them and keep them on task.

## Whole-Project Ownership

You are responsible for the entire project-tracker worktree, not only the files you personally edited in the current session. A dirty or untracked file is not automatically "someone else's problem" just because you did not create it today. It may be generated output, follow-up work from another machine, or a file another agent prepared for you to carry forward.

Before opening a PR, committing, or declaring the tree clean, inspect and classify every dirty/untracked path in `git status`. For each path, decide one of:

- **Include:** it belongs with the current change, including generated mirrors such as `AGENTS.md` after editing `CLAUDE.md`.
- **Separate:** it is real project work but belongs in its own commit/PR/card.
- **Ignore for now:** it is intentionally local-only or explicitly out of scope, and you can state why.

Do not omit a file silently. If a generated file mirrors a source file you changed, regenerate it and include it. If you are unsure whether a dirty file is related, inspect it before deciding. The default posture in project-tracker is ownership of the whole board and repo, not narrow ownership of today's patch.

Read DECISIONS.md before changing architecture or infrastructure.
Before modifying code, write a pre-flight check: what does this do, why is it built this way, what are you changing? (See root CLAUDE.md.)

Run `pt info -p project-tracker` for tech stack, env vars, infrastructure, and project-specific reference data.
Run `pt memory search "project-tracker"` before starting work for prior decisions and context.

## Session Continuity

If `PROGRESS.md` exists in the project root, read it FIRST before doing anything else. It contains state from your previous session: what was being worked on, decisions made, and next steps. After reading, update or delete it as appropriate — stale PROGRESS.md files are worse than none.

**`PROGRESS.md` is always dirty in `git status`.** It's updated daily as part of normal operation — an `M PROGRESS.md` line is the expected state, not a finding. Don't flag it as uncommitted work, don't offer to commit it, and don't suggest the user review it unless you yourself just modified it in this session.

## Card Factory Auto-Validation

When you start a task whose text begins with `[Card Factory]`, run `/validate-card-factory <task-id>` FIRST before doing any work. If the validation cancels the card (issue already resolved), move on to the next task. This prevents wasting sessions on stale findings.

## Server Ownership

The dashboard server (uvicorn on port 8000) is yours to manage. Restart it whenever you need to — after code changes, after a crash, whenever. No need to ask Erik.

Standard restart: `pkill -f "uvicorn dashboard.app" && sleep 1 && doppler run -- $HOME/projects/project-tracker/venv/bin/python -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8000 &` (bind stays on loopback — admin endpoints require loopback unless `PT_ALLOW_REMOTE_ADMIN=1`)

Verify it's up: `curl -s http://localhost:8000/api/health` or check `lsof -i :8000`.

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

<!-- BEGIN scaffold:hygiene -->
## Locked Hygiene Contract

This project participates in the portfolio-wide locked hygiene contract
installed by `scaffold install-hygiene`. The contract is enforced by user-scope
hooks in `~/.claude/` and by `pt` CLI commands in project-tracker. **Do not edit
this block by hand** — `scaffold sync` rewrites it. Add project-specific notes
outside the markers.

### What the contract requires

1. **No direct edits on `main`/`master`/`trunk`.** A Stop-event hook blocks
   `Edit`/`Write`/`MultiEdit`/`NotebookEdit` on tracked files while HEAD is the
   default branch. Work happens on feature branches; PRs are how changes land.
2. **No dirty session exits.** A session-end gate refuses to close while any of
   four conditions hold:
   - dirty working tree (PROGRESS.md is ignored),
   - commits ahead of upstream unpushed,
   - branch with no PR opened,
   - an authored PR still open against this repo.
3. **Audit trail for bulk changes.** Multi-file refactors, renames, and doc
   reorgs run inside `pt migration start <name>` … `pt migration finish <name>`
   so they are reversible (`--revert` uses `git restore` for tracked paths and
   `send2trash` for untracked — never raw `rm`).
4. **Handoffs are first-class.** If a session must end dirty (mid-rebase, mid-
   investigation), record it: `pt handoff create <card-pk> --branch <b> --intent
   <s> --status <s> --next <s> --guidance preserve|discard`. The session-end
   gate honors an open handoff covering the current branch.

### Safety valves

- **`.scratch/`** — every project has a gitignored `.scratch/` at its repo root.
  The branch-on-first-edit hook lets edits under any `.scratch/` subdir through
  unconditionally. Use it for throwaway notes, probe scripts, and reading-mode
  poking. Files there never reach a PR. If `.scratch/` work turns into real work,
  move it out before committing.
- **`PT_ALLOW_MAIN_EDIT=1`** — one-shot env var to bypass the main-edit hook.
  Use sparingly; intended for emergency fixes and tooling that must touch the
  default branch.
- **`PT_ALLOW_DIRTY_EXIT=1`** — one-shot env var to bypass the session-end gate.
  Every use is logged to `~/.claude/state/locked_hygiene/bypasses.jsonl`.
- **`pt handoff`** — durable alternative to the env-var bypass: the gate
  recognizes an active handoff record for the current branch and lets the
  session close.

### Quick reference

| Action                          | Command                                       |
| ------------------------------- | --------------------------------------------- |
| Start a recorded bulk migration | `pt migration start <name>`                   |
| Finish + write `MIGRATIONS.md`  | `pt migration finish <name>`                  |
| Revert a migration              | `pt migration finish <name> --revert`         |
| Open a handoff                  | `pt handoff create <card-pk> --branch <b> …`  |
| List open handoffs              | `pt handoff list`                             |
| Resolve a handoff               | `pt handoff resolve <id>`                     |
| Refresh this block portfolio-wide | `scaffold sync --apply` (from project-scaffolding) |
<!-- END scaffold:hygiene -->
