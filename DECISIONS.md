# Decisions

Deliberate architectural choices. Read before changing anything structural.
To revisit a decision, don't edit — add a new entry that supersedes it.

---

## Dual-Interface Architecture (CLI + Web Dashboard)
**Accepted 2026-04-04**

**Context:** Agents need parseable output they can pipe and grep. Humans need a visual Kanban board. A single interface cannot serve both.

**Decision:** The CLI (`pt`, Click) outputs strict plain-text format (`#<id> | <status> | <priority> | <text>`) for agent parsing. A separate React/FastAPI web dashboard provides visual UX. Both share the same data layer. The CLI output format is a contract — changing it is a breaking change for all agent workflows.

| Alternative | Why rejected |
|-------------|-------------|
| API-only (JSON) | Agents can't easily pipe raw JSON without jq gymnastics |
| GUI-only | Agents can't drive a browser-based UI |
| Rich CLI formatting | Breaks agent parsing — invisible characters, variable-width columns |

**Consequences:** Two interfaces to maintain, each optimized for its audience. CLI format must be treated as a stable API.

---

## Optional Cloud Database with Automatic Fallback (Turso + Local SQLite)
**Accepted 2026-04-04**

**Context:** Production use requires cross-machine sync. But agents and developers must work offline without friction — no config, no errors, no mode flags.

**Decision:** When `TURSO_KANBAN_URL` and `TURSO_KANBAN_TOKEN` env vars are set, connect to remote Turso (libsql). When either is missing, silently fall back to local SQLite. No flags, no prompts — env var presence is the only switch.

| Alternative | Why rejected |
|-------------|-------------|
| Cloud-only (Turso always) | Breaks offline workflows, CI without credentials |
| Local-only (SQLite always) | No cross-machine sync |
| Explicit mode flag (`--remote`) | Adds friction, agents forget flags |

**Consequences:** Offline-first with optional cloud. Local and cloud databases can diverge if machines work offline simultaneously — sync conflicts must be managed externally.

---

## Safety-First Database Operations (Multi-Layer Backups)
**Accepted 2026-04-04**

**Context:** On 2026-01-27, an auto-migration dropped 94 tasks. The database is critical state. One backup location is not enough if the project directory itself is deleted.

**Decision:** Three rules, no exceptions: (1) No destructive SQL (DROP TABLE, DELETE FROM) without explicit user approval. (2) Migrations must be additive only — add columns, add tables, never drop. (3) Automatic backups to TWO locations — `data/backups/` (inside project) and `~/.project-tracker/backups/` (outside project).

| Alternative | Why rejected |
|-------------|-------------|
| Single backup location | The 2026-01-27 incident proved one location can be lost with the project |
| Allow destructive migrations with backups | Backups can fail silently |
| No backups (trust version control) | Database is not in git; binary files don't diff well |

**Consequences:** Schema changes are slower (additive only). Disk usage increases from dual backups. But task data is protected — recovery from any single point of failure is guaranteed.

---

## Handoffs are LOCAL_ONLY by design
**Accepted 2026-05-06**

**Context:** Phase D of the locked-project hygiene workflow introduces a `handoffs` table that records structured "unfinished work" / non-PR exit records. Reviewer asked whether this table should replicate cross-machine via CRR.

**Decision:** `handoffs` is classified `LOCAL_ONLY`. A handoff exists *because* there is uncommitted local work in a dirty tree. That dirty tree is, by definition, machine-local — it has not been pushed. If the handoff replicated cross-machine, an agent on Machine B would read "your branch X has dirty work" but the dirty tree itself would still be on Machine A with no way to access it. The handoff would be a tease, not a resume point. Keeping handoffs LOCAL_ONLY makes the contract honest: a handoff record is only meaningful on the machine that produced it.

| Alternative | Why rejected |
|-------------|-------------|
| CRR (replicate cross-machine) | Replicates a pointer to dirty work that doesn't exist on the receiving machine — misleading |
| CONTROL_PLANE | Not a sync coordination primitive; nothing depends on its replication |

**Consequences:** Cross-machine resumption of unfinished work is not supported through `pt handoff`. To carry work across machines an agent must commit (even a WIP commit) and push the branch — at which point the work is no longer "unfinished local" and a Phase C PR-style record is appropriate instead.
