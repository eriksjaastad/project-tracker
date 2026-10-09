# project-tracker

The central nervous system for Erik's multi-project portfolio. A CLI (`pt`) and FastAPI-backed dashboard that track tasks, projects, and cross-project relationships.

## Quick Start

```bash
pt launch        # Dashboard at localhost:8000
pt tasks         # View Kanban board
pt info          # Reference data (credentials, infrastructure)
pt backup status # Full backup + off-machine backup health
pt memory search "query"  # Cross-agent shared memory
pt memory recent --since 7d --json  # Read-only cron/SSH memory query
```

## What It Does

- **Kanban** — Task management across all projects (`pt tasks`)
- **Dashboard** — Project health, GitHub activity, memory graph visualization
- **Memory** — Cross-agent semantic search via ai-memory (`pt memory`)
- **Automation** — Read-only JSON memory commands for SSH/cron integrations (`pt memory recent --json`, `pt doctor --json`, `pt hygiene --json`)
- **Info** — Centralized reference store for env vars, credentials, infrastructure (`pt info`)
- **Graph** — D3.js visualization of file relationships across the ecosystem

## Project Structure

```
project-tracker/
├── pt                      # CLI entry point
├── scripts/
│   ├── pt.py               # Click CLI (tasks, info, memory, calendar, hygiene)
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
│   ├── tracker.db          # Local SQLite
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

Visual Kanban tests (`tests/test_kanban_visual.py`) need a one-time Playwright Chromium install: `uv run --extra test --python 3.13 playwright install chromium`.

The frontend lint (`cd dashboard/frontend && npm run lint`) covers `src/` only — its eslint
config ignores `dashboard/static/*.js` and exits 0. Lint those vanilla-JS files (M5) from the
repo root instead, so the `no-redeclare` rule runs across the whole global scope:

```bash
dashboard/frontend/node_modules/.bin/eslint --no-config-lookup \
  --rule '{"no-redeclare": "error"}' dashboard/static/<file>.js
```

## CI

CI runs the test suite (`.github/workflows/tests.yml`) and no longer enforces type labels. Local preflight precedes publication; review by a separate local Codex reviewer process on the exact committed HEAD (the implementer never reviews its own work) and the CI gates are defined by `pt info get pr_merge_policy`. Follow the current PR procedure for authoring requirements until its separate label-rule update lands.

After opening or updating a PR, start `pt pr settle` and keep the owning agent
attached to its event stream. Follow the [PR settle runbook](docs/PR_SETTLE.md)
for evidence assessment, review limits, hold/stop controls and merge handoff.
