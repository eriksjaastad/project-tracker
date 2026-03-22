
<!-- SCAFFOLD:START - Do not edit between markers -->
# Architectural Decisions - project-tracker

> *Documenting WHY we made decisions, not just WHAT we built.*
>
> Without documented reasoning, even the people who made the decisions forget why.

---

## How to Use This File

When you make a significant decision, add an entry:

```markdown
### YYYY-MM-DD: Brief Title

**Context:** What situation led to this decision?

**Decision:** What did we decide?

**Reasoning:** Why this choice over alternatives?

**Alternatives considered:** What else did we consider and why not?
```

Good candidates for entries:
- Choosing a library/framework over another
- Architectural patterns (why monolith vs microservices, why this folder structure)
- Build/deploy choices (why Railway vs Vercel, why SQLite vs Postgres)
- Process decisions (why we use X workflow)
- Anything where future-you might ask "why did we do it this way?"

---

## Decision Log

### 2026-01-27: Project Created

**Context:** Starting project-tracker.

**Decision:** Using project-scaffolding templates for initial structure.

**Reasoning:** Consistent setup across projects. Battle-tested patterns. Don't reinvent file structures.

---

### 2026-03-22: tracker.db → Turso (libsql) for Cross-Machine Shared Kanban

**Context:** tracker.db is local to each machine. Working across laptop and Mac Mini
means the Kanban state is fragmented — changes made on one machine are invisible on
the other.

**Decision:** Migrate tracker.db to Turso (libsql cloud) as the "open-kanban" database.
The `pt` CLI and dashboard use `DatabaseManager._get_conn()`, which now uses libsql
when `TURSO_KANBAN_URL` + `TURSO_KANBAN_TOKEN` are set, and falls back to local
SQLite transparently (no code changes needed for offline/dev/test work).

**Reasoning:** Turso is a libsql fork of SQLite with a python client (`libsql`) that
has an identical API to `sqlite3`. The change was a ~30-line swap in `manager.py`,
all SQL remained identical. Free tier covers 5 databases at 500MB — plenty of headroom.
Eliminates the need to manually sync task state between machines.

**Alternatives considered:**
- Postgres/Supabase: Schema migration overhead, $0 free tier for production workloads
- SQLite + rsync: Race conditions, no real-time sync
- Keep local + export/import: Fragile, manual process

---

## Principles (Optional)

Document recurring principles that guide decisions in this project:

<!-- Example:
### Local-First

We prefer local processing over cloud APIs when possible. Reduces cost, improves privacy, works offline.

### Simple Over Clever

Choose boring technology. Complexity must justify itself.
-->

---

## Open Questions

Decisions we haven't made yet but need to:

<!-- Example:
### Should we use a database or flat files?

**Current state:** Using JSON files for simplicity.

**Trigger to revisit:** If we hit performance issues or need concurrent writes.
-->

---

*Last updated: 2026-01-27*

<!-- SCAFFOLD:END - Custom content below is preserved -->