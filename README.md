# project-tracker

The central nervous system for Erik's multi-project portfolio. A CLI (`pt`) and FastAPI-backed dashboard that track tasks, projects, and cross-project relationships.

## Quick Start

```bash
pt launch        # Dashboard at localhost:8000
pt tasks         # View Kanban board
pt info          # Reference data (credentials, infrastructure)
pt backup status # Full backup + off-machine backup health
pt memory search "query"  # Cross-agent shared memory
PT_SKIP_DOPPLER=1 pt memory recent --since 7d --json  # Read-only cron/SSH memory query
pt sync status   # Replication status / pause / resume controls
pt sync check    # Mini-local sync rollout readiness check
pt sync set-machine-id 883  # Persist explicit machine identity for sync
```

## What It Does

- **Kanban** — Task management across all projects (`pt tasks`)
- **Dashboard** — Project health, GitHub activity, memory graph visualization
- **Memory** — Cross-agent semantic search via ai-memory (`pt memory`)
- **Automation** — Read-only JSON memory commands for SSH/cron integrations (`pt memory recent --json`, `pt doctor --json`, `pt hygiene --json`)
- **Info** — Centralized reference store for env vars, credentials, infrastructure (`pt info`)
- **Graph** — D3.js visualization of file relationships across the ecosystem
- **Sync Controls** — Replication pause/resume/status plus Mini-local readiness checks for Phase 2 (`pt sync`)

## Project Structure

```
project-tracker/
├── pt                      # CLI entry point
├── scripts/
│   ├── pt.py               # Click CLI (tasks, info, memory, calendar, inbox, worktrees)
│   ├── db/
│   │   ├── schema.py       # Database schema (v7)
│   │   └── manager.py      # DatabaseManager operations
│   └── discovery/
│       └── graph_builder.py
├── dashboard/
│   ├── app.py              # FastAPI backend
│   ├── frontend/           # React app (Kanban, Agentic, GitHub)
│   ├── templates/          # Jinja2 (graph view)
│   └── static/             # CSS, JS
├── data/
│   ├── tracker.db          # Local SQLite (Turso in production)
│   └── graph.json          # Project graph data
└── tests/
```

## Development

```bash
uv run pytest tests/                    # Run tests
cd dashboard/frontend && npm run build  # Rebuild React frontend
pt scan                               # Rescan projects directory
pt sync-project project-tracker       # Refresh one project only
```

## CI

CI runs the test suite (`.github/workflows/tests.yml`) and no longer enforces type labels. Local preflight precedes publication; the exact-head Codex GitHub review and CI gates are defined by `pt info get pr_merge_policy`. Follow the current PR procedure for authoring requirements until its separate label-rule update lands.

After opening or updating a PR, start `pt pr settle` and keep the owning agent
attached to its event stream. Follow the [PR settle runbook](docs/PR_SETTLE.md)
for evidence assessment, review limits, hold/stop controls and merge handoff.
