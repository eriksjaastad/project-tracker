# project-tracker

The central nervous system for Erik's multi-project portfolio. A CLI (`pt`) and FastAPI-backed dashboard that track tasks, projects, and cross-project relationships.

## Quick Start

```bash
./pt launch        # Dashboard at localhost:8000
./pt tasks         # View Kanban board
./pt info          # Reference data (credentials, infrastructure)
./pt backup status # Full backup + off-machine backup health
./pt memory search "query"  # Cross-agent shared memory
PT_SKIP_DOPPLER=1 ./pt memory recent --since 7d --json  # Read-only cron/SSH memory query
./pt sync status   # Replication status / pause / resume controls
./pt sync check    # Mini-local sync rollout readiness check
./pt sync set-machine-id 883  # Persist explicit machine identity for sync
```

## What It Does

- **Kanban** — Task management across all projects (`pt tasks`)
- **Dashboard** — Project health, GitHub activity, memory graph visualization
- **Memory** — Cross-agent semantic search via Open Brain (`pt memory`)
- **Automation** — Read-only JSON memory commands for SSH/cron integrations (`pt memory recent --json`, `pt doctor --json`)
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
./pt scan                               # Rescan projects directory
./pt sync-project project-tracker       # Refresh one project only
```

## CI

PRs are reviewed by Claude Sonnet via [reusable workflow](https://github.com/eriksjaastad/tools). Auto-merges on APPROVE, blocks on REQUEST_CHANGES. Requires a label (`feature`, `bug`, `chore`, etc.).
