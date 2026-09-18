# PRD — dbmed: the database mediation boundary

**Cards:** #7228 (mechanism, `claude-user-config`) · #7219 (project-tracker integration) · umbrella #7217
**Author:** Floor manager, project-tracker · **Date:** 2026-09-17
**Status:** Phase 1 — mechanism + project-tracker as the reference implementation

---

## 1. Project Overview

Every database in the portfolio is currently readable and writable by any agent process,
because agents run as `eriksjaastad` and the database files are owned by `eriksjaastad`.
On 2026-01-27 an agent dropped the tasks table and destroyed 94 rows; the rules written
afterwards were documentation, not enforcement, and a source-level inventory on 2026-09-17
confirmed nothing mechanical stands in the way today.

`dbmed` is a mediation daemon that runs as a dedicated service account and owns the database
files outright, so that agent code cannot open them — not because a rule forbids it, but
because the kernel refuses. Agents reach data only through named, validated operations.

**Who it is for:** every agent and service in the portfolio that reads or writes a database;
Erik, who needs the data to survive agents.

## 2. Goals

- An agent process cannot read, write, copy, rename, replace, or delete a protected database
  file, its journals, or any real-data copy of it — through any tool, driver, shell, or path.
- Every legitimate caller keeps working: the `pt` CLI contract, the dashboard, the calendar
  poller, the backup job.
- Destructive operations refuse by default, and when authorised, produce a verified
  timestamped backup before they mutate anything.
- When the daemon is unavailable, callers fail loudly and non-zero. There is no fallback to
  direct access, because the client has no code capable of it.
- The mechanism is general enough that the other ten database projects adopt it without each
  inventing its own safety model.

## 3. Non-Goals

- **Not** a universal SQL gateway. No arbitrary SQL, arbitrary paths, database download, or
  shell execution crosses the boundary. A raw-SQL endpoint would recreate the problem.
- **Not** centralising other projects' domain logic into `pt`. Each project keeps its own
  operations; only the transport, registry, and privilege model are shared.
- **Not** restricting Erik. Human administration and emergency recovery sit outside agent
  authority by design.
- **Not** Phase 2 or Phase 3. Nine other projects, and the reusable template (#7229), are
  carded separately and follow this one.
- **Not** a Turso or hosted-database migration. DECISIONS.md settled that; the backend stays
  local SQLite.

## 4. Constraints

**Security.** The boundary must sit outside the agent's authority. Card #7228 rejects, by
name, two things that look like security and are not: same-user file permissions (the owner
can undo them) and command-name matching in a shell hook (it matches spellings, not access).
Authorisation at the socket is by peer credentials. Destructive operations require an explicit
confirmation token issued daemon-side. No client environment variable, CLI flag, alternate
interpreter, subprocess, or SSH session may widen access.

**The ceiling is `sudo`.** An agent that reaches root defeats this. Enforcement therefore
depends on every agent runtime denying `sudo`. Claude Code does today; Codex, Cursor, and Grok
must be verified before any cross-runtime claim is made.

**Tech stack.** Python 3.13 (pinned — Homebrew 3.14 broke libsql), standard library only for
the daemon and client. No new third-party dependency in the privileged path. `uv` for
execution. The daemon must load `crsqlite.dylib` from a root-owned location only.

**Deployment target.** Local, both hosts: MacBook and Mac Mini. `launchd` system domain
(`/Library/LaunchDaemons`), not a user agent. Installation requires `sudo` and is Erik's to
run; agents cannot and must not attempt it.

**Performance.** `pt tasks` is on the hot path for every agent session. Unix-domain socket
round trip must stay under 10ms at p95 for a list operation — the reason a hosted database was
rejected. The convenience hook added to `bash-validator.py` must stay pure-Python: the Bash
gate has a 5-second timeout and `bash-gate.py:28-31` documents that a hook killed at that
timeout fails open.

**AI model strategy.** None. `dbmed` performs no inference.

**Compliance.** tax-organizer (Phase 2) holds IRS-facing filing evidence; its ledger has a
fingerprinting pipeline (#7049) that a raw write would silently invalidate. The design must
not require relaxing anything for it.

## 5. Integration Context

**Existing infrastructure this uses or displaces:**

| Thing | Today | After |
|---|---|---|
| `data/tracker.db` + journals | repo, owned by Erik | `_dbmed`-owned, outside the repo |
| `data/backups/` (547 files, incl. task-row JSON) | repo, owned by Erik | behind the boundary |
| `~/.project-tracker/backups/` | home, owned by Erik | behind the boundary, still a second location |
| `com.eriksjaastad.pt-backup` LaunchAgent | shells `sqlite3` from an agent-editable script | calls a daemon operation |
| `com.eriksjaastad.project-tracker` (dashboard) | imports `DatabaseManager`, opens the file | unprivileged client |
| calendar poller cron (`*/10`) | second manager, opens the file directly | unprivileged client |
| `com.pt.sync-daemon` | **not installed** — template only | backend-side code, stays dormant |
| cr-sqlite extension | `~/.local/lib/crsqlite/`, agent-writable | vendored root-owned |

**External services needed:** none. No new accounts, no new secrets, no Doppler changes.
project-tracker's Turso credentials stay dormant (`~/projects/.turso-config.json` is
`turso_enabled: false`); if Turso is ever re-enabled, its credentials move daemon-side.

**Secrets management:** unchanged. SQLite needs none. When Phase 3 reaches hypocrisynow's
Railway Postgres and synth-insight-labs' Cloud SQL, the credential moves into the daemon's
root-owned config and leaves the agent's environment — that is the point of the registry.

**Publishing destination:** not applicable; this is infrastructure.

**Accounts Erik needs to create:** none. Erik's one required action is running the reviewed
installer with `sudo`, once per host.

**Mock-to-production cutover:** all development and every probe runs against synthetic
fixtures provisioned by the daemon and living behind the same boundary as production. The
live database is never opened for testing. Cutover is the documented WP3 sequence, and it is
reversible by a single rollback script.

## 6. Success Metrics

- Every denial probe in the evidence matrix fails to reach data, across both hosts and every
  supported runtime — or is recorded as an uncovered path, which blocks acceptance.
- Zero rows lost at cutover: count before and after, reported through the sanctioned
  operation, must match.
- No regression in the `pt` CLI contract. DECISIONS.md treats its output format as an API.
- p95 latency for `pt tasks` list within 10ms of today's local-SQLite figure.
- Zero occurrences of `sqlite3`, `psql`, or a direct driver connection in any active skill or
  instruction file.
- The test suite leaves `data/` untouched.

## 7. Key Decisions Already Made

- **Service account + root-owned daemon over a Unix socket.** Chosen by Erik on 2026-09-17
  over a hosted database and over a permissions-only approach.
- **No SQL crosses the socket.** Named operations with parameter schemas, allowlisted.
- **The existing `DatabaseManager` methods become the operation registry.** They are already
  parameterised domain methods, which is why the CLI contract survives: callers keep calling
  the same method names against an RPC proxy.
- **A missing registry entry is a deployment failure, not permission to open the file.**
- **The daemon lives in `project-tracker/dbmed/` with zero project-tracker imports**, so
  #7229 can extract it with `git mv` rather than a rewrite.
- **Additive migrations only**, and dual backups — both DECISIONS.md rules survive, with the
  backup destinations moved under `_dbmed` so an agent cannot delete them.
- **Erik runs the installer.** Agents are denied `sudo` and must not attempt escalation.

## 8. Open Questions for Downstream

- Operation granularity: mirror `DatabaseManager`'s method surface one-to-one, or define a
  coarser task-domain vocabulary? One-to-one is cheaper now and leakier later.
- Whether the socket group should be `staff` or a purpose-made `_dbmed-clients` group. The
  narrower group is better hygiene and more install complexity.
- How a copied template instance receives future security fixes (#7229's problem, but the
  version-provenance hook belongs in the daemon from the start).
- Whether the dashboard, which can call every operation, needs a narrower capability set than
  the CLI. It runs from an agent-editable script under launchd.

## 9. Release Contract

**Shipped means:**

1. The daemon is installed and running on the MacBook, `tracker.db` and every real-data copy
   live under `_dbmed` ownership, and `/usr/local/var/dbmed` is not traversable by Erik's uid.
2. `pt`, the dashboard, the calendar poller, and the backup job all work through the client,
   with no behaviour change visible to a user of the CLI.
3. `tests/boundary/` passes: every denial probe denied, every sanctioned operation working,
   daemon-down producing a non-zero exit and no file access.
4. Destructive operations refuse without a token and produce a verified timestamped backup
   with one.
5. No active skill or instruction teaches direct database access — the `pm` skill's `sqlite3`
   fallback is gone, and `PHASE_2_4_RUNBOOK.md`'s executable blocks are neutralised.
6. `EVIDENCE.md` records the runtime/host/operation matrix **and** the uncovered paths:
   non-Claude runtimes, the Mac Mini, Full Disk Access. Those are stated as unfinished, never
   as a pass.
7. A rollback script exists and has been exercised.

**Not shipped, and said so plainly:** Mac Mini installation, non-Claude runtime verification,
and the other ten projects. Those are #7228's remaining scope and Phases 2–3.
