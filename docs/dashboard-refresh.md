# Independently refreshed dashboard data

Cards: #6974 (GitHub loading), #6976 (daily API activity).

Opening `/dashboard` must render independent panels immediately. GitHub sections
show a clock while loading, then update in place. During later refreshes they
keep the previous snapshot and display its timestamp. The unhelpful “Not on
GitHub” summary card is removed; the underlying diagnostic field remains in the
raw response. Existing cost panels and their calculations are unchanged.

## GitHub response contract

`GET /api/github` returns immediately. With no snapshot it returns refresh state
without fabricated repository totals. Once populated it returns the existing
GitHub payload plus:

- `refreshing`: one background collector is running;
- `stale`: the last successful snapshot has passed its five-minute lifetime;
- `refresh_error`: a generic failure message, or null;
- `retry_after_seconds`: suggested next poll interval.

One daemon worker per server process performs the existing synchronous GitHub
collection. A lock prevents duplicate collectors. A failed refresh preserves
the previous snapshot and waits 60 seconds before another attempt. No database
schema, authentication, dependencies, or scheduled system jobs are introduced.
The cache remains in memory; restarting the server starts with an empty cache.

The frontend polls every two seconds during collection and at most once a minute
otherwise. Requests time out after ten seconds and cancel on unmount. Errors
appear in the GitHub section without hiding independent panels. This pattern
preserves the cancellation behavior being added separately under #6956.

## Daily API activity

The panel reads the existing `/api/costs/usage` endpoint, grouping recorded calls
by provider, service (falling back to model), and project. It displays counts,
recorded estimated costs, and last-observed timestamps. Missing prices are
marked incomplete. It refreshes every minute without overlapping requests and
supports date selection in the browser's local timezone. The default date
advances across midnight; an explicitly selected historical date remains fixed.

The upstream endpoint only supports a lower date bound and a limit. Requests
are capped at 5,000 records; the panel filters the selected day locally and
warns whenever the cap is reached, including when a historical day's records
may have been crowded out by newer calls. This is observed telemetry, not a
complete inventory, billing statement, or subscription-status source.

Cross-project integration discovery is tracked separately in #6977, and
subscription-account discovery in #6975. Neither adds an account connection or
scanner in this change.

## Validation and rollout

- Backend: `python -m pytest tests/test_github_cache.py tests/test_github_api.py tests/test_cost_panel.py tests/test_dashboard_health.py tests/test_dashboard_navigation.py -q` — 72 passed using the existing project virtual environment.
- Frontend: `npm test` — 21 passed; `npm run lint` and `npm run build` passed.
- Chromium against an isolated server, actual new GitHub route with an
  eight-second simulated collector, and captured real cost responses: initial
  panels 0.102 s, six fetching clocks, navigation HTTP 200 in 0.013 s while
  collecting, completed GitHub panels at 8.542 s, no JavaScript errors.
- Live cost responses were also queried independently. Some records lacked
  prices; the panel correctly displayed incomplete pricing.

The built frontend and backend contract must roll out together. After merging,
build `dashboard/frontend` and restart the normal local dashboard process, then
check `/api/health` and a cold `/dashboard` load. Until that happens, the shared
server continues to run its existing behavior. The development preview used a
separate worktree and port; its empty database guard was left enabled.

Rollback is a normal revert of the feature commit followed by a frontend rebuild
and server restart; there is no application-data migration to reverse.
