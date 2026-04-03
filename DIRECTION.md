# DIRECTION.md — project-tracker

## Goal
The central nervous system for Erik's multi-project portfolio. A CLI (`pt`) and Flask dashboard that tracks tasks, project health, and cross-project activity from a single pane of glass.

## Type: Continual development
This is evergreen infrastructure, not building toward a ship date. It evolves as the portfolio grows — new data sources (GitHub activity feed, memory graph), new views (scaffolding alerts, sync health), and better performance as project count scales.

## North Star
One command or one browser tab gives Erik (or any agent) full situational awareness across all projects — what exists, what's healthy, what needs attention, what's next.

## Current Focus
- **Dashboard enrichment** — wiring GitHub activity feed, project status management, and stale-project detection into the web UI.
- **Performance / reliability** — async refresh (currently 7+ min synchronous scan), Doppler routing audit, Turso sync health.
- **Agent-facing ergonomics** — single-project sync, proposal flag for Card Factory, DIRECTION.md files for every project.
