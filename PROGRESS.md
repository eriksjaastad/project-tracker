# PROGRESS.md — Session 2026-04-11

## What's Happening
Follow-up session clearing items from previous PROGRESS.md. All three items resolved.

## What Got Done
- Committed dead `ai-usage-billing-tracker` entry removal from populate_info.py (4e98eb7)
- Fixed dashboard launchd PATH — added brew/doppler PATH preamble to launch-dashboard.sh (08e5d95), matching card-factory-morning.sh pattern
- #5627: Open Brain scale strategy implemented (5c489aa):
  - Edge query optimized: temp table JOIN replaces full 81K-row scan + Python filter (1.7x speedup)
  - Server-side clustering: dust nodes (mention<=2, degree<=5) grouped by type into aggregate cluster nodes
  - `cluster` query param: auto (default, triggers >2K nodes), on, off
  - Frontend: cluster nodes render with dark fill + dashed colored border, tooltip shows "click to expand", click re-fetches with cluster=off
  - Stats bar shows cluster count when active
  - Current data: 4122 -> 3500 nodes (622 collapsed into 5 type clusters)
- #5784 already clean — commit 9476c97 from prior session got all TODO.md refs

## Decisions Made
- Clustering threshold: mention_count <= 2 AND degree <= 5 — balances current data (15% reduction) with future scaling (dust accumulates faster than high-value nodes)
- Edge optimization uses CREATE TEMP TABLE + JOIN rather than IN clause (avoids SQLite variable limits on large node sets)
- Cluster nodes use negative IDs to avoid collision with real node IDs

## Next Steps
- Dashboard launchd needs `launchctl unload` + `launchctl load` to pick up the PATH fix
- project-tracker board is empty — check card factory output or `pt tasks` for new work
- Main branch is 4 commits ahead of origin — push when ready

## Don't Forget
- Dashboard needs manual restart after app.py changes (no --reload flag)
- Card factory morning run creates a lock file at logs/.card-factory-last-run
