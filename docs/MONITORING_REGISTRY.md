# Monitoring registry and the Saga sweep

**Locked 2026-09-22.** Saga is the general monitor, running on the Mac Mini.
This document is the contract it operates under.

## Where the facts live

There is one registry file, not several:

```text
~/projects/project-tracker/EXTERNAL_RESOURCES.yaml
```

Its `projects:` block (pre-existing) is the authority on **which third-party
services each project uses**, account ownership and cost. Its `monitoring:`
block (added 2026-09-22) adds only what a monitor needs: production URL, repo,
provider, health check, scheduled jobs, backup destination, owner.

`pt info get external_resources_doc` points at this file. Nothing else is a
source of truth for external connections, and no second copy may be created —
including on the Mini.

**`UNKNOWN` is a real value.** It means nobody has established the fact yet.
It is Saga's work queue. It is never to be guessed at, inferred from observed
behaviour, or quietly filled in.

## Ownership: laptop writes, Saga reads

```text
Mini (Saga)                        Laptop (macbook-pro)
-----------                        --------------------
ssh macbook-pro  ──── read ────▶   EXTERNAL_RESOURCES.yaml
                                   pt tasks create  ◀── drift card
Writes: none
```

Saga **never writes the registry** and never commits to the project-tracker
repo. When it finds drift — a new Vercel project, a job that stopped running, a
service in Doppler that the registry does not list, an `UNKNOWN` it can now
answer — it opens a Kanban card against the owning project and stops there.

This is the same shape as Hermes, and it is deliberate. Two machines writing one
tracked YAML is what killed the cross-machine Kanban sync in September 2026.
One writer, one file, no merge conflicts.

## SSH, both directions

Use tailnet names. **`.local` does not resolve on this network** — Starlink,
Wi-Fi only, no Ethernet.

```bash
# From the laptop, to the Mini:
ssh eriks-mac-mini              # 100.68.223.79

# From the Mini (Saga), to the laptop:
ssh macbook-pro                 # 100.124.58.49
```

Verify the tailnet before diagnosing anything else: `tailscale status`.

### The laptop sleeps

This is the single biggest limitation on "nothing slips through the cracks,"
and it must be designed around rather than discovered during an incident.

The registry, the Kanban board, dbmed, and every local SQLite database live on
the **laptop**. The laptop is a MacBook that sleeps when the lid closes. Sleep
is currently held off only by `caffeinate`, which is not permanent.

Consequences Saga must encode:

- **Failed SSH does not prove sleep.** Check the Mini's Tailscale health and
  the laptop's peer status independently. Only a healthy tailnet reporting the
  laptop offline suppresses host-dependent checks for that cycle; label it
  `HOST_OFFLINE`, not confirmed sleep. Keep checking public services and queue
  board updates. An online peer with failed DNS, SSH, or authentication is
  `SSH_UNAVAILABLE`. Missing peer data or an unhealthy Mini tailnet is
  `REACHABILITY_UNKNOWN`, never sleep or a healthy result.
- **Persistent access failures need an independent alert.** Retry after five
  minutes. If `SSH_UNAVAILABLE` or `REACHABILITY_UNKNOWN` persists, send one
  transition alert through the Mini's existing Discord #alerts path, including
  the SSH error and tailnet evidence. Queue the same incident for the board;
  SSH cannot be its only delivery path. Alert on recovery and flush queued
  updates after a successful connection. Never bypass SSH host-key checks.
- **A missed scheduled run during sleep is not a failure.** Before opening a
  card for a job that did not run, Saga must establish that the host was awake
  at the scheduled time. A job that "ran and failed" and a job that "never got
  the chance" are different findings and must not be reported as the same one.
- **Overnight findings queue rather than vanish.** Hermes already writes to
  `.scratch/pending-board-updates.md` when the laptop is unreachable; Saga uses
  the same pattern and flushes on the next successful connection.

What does *not* depend on the laptop: the Vercel API, the Railway API, Cloud
Run, and any public URL. Those can be checked 24/7 from the Mini and are the right place to
start.

### Where checks execute

Registry commands are invoked by Saga on the Mini. Commands requiring the
laptop's checkout, launchd state, logs, backup files, or loopback services must
explicitly use `ssh macbook-pro`. Single-quote the remote command so `~`, `$HOME`
and `$(id -u)` resolve on the laptop. Use the explicit `~/.local/bin/uv` path
inside SSH; an interactive shell's PATH and aliases are not available there.
Bound each invocation in the sweep runner and retain stderr and exit status;
SSH connection timeout alone does not bound a stalled remote command.

The muffin deep check reads public Blob data, but its installed script and
integrity-checking code are authoritative on the laptop. Run that code there,
and interpret its printed `OK`/`DEGRADED`/`unknown` verdict: it always exits 0
because it was designed as a nonblocking session hook. Failed or missing output
is unknown coverage. Never substitute a stale Mini checkout. The same host rule
applies to the watchdog's launchd command and `127.0.0.1:8000` health probe.

When SSH fails, use the host states and independent alert path above; do not
turn missing laptop evidence into a healthy result or a job failure. Public URL
and provider API checks continue directly from the Mini during host outages.

## What Saga sweeps

| Surface | Source of truth | Check |
|---|---|---|
| Live sites | `monitoring.<project>.health` | HTTP check against `prod_url`; Vercel API for last deploy state |
| Scheduled jobs | `monitoring._scheduled_jobs` | Run/exit evidence while awake; require log growth only where successful runs are documented to log |
| Backups | `monitoring._backups` | Snapshot freshness; offsite copy present at `gbackup:db-backups/<project>/` |
| Third-party connections | `projects:` block | Services actually in use vs. services the registry lists |

### Agent Chat deployment drift

`make deploy-chat-status` displays `/health`; its exit status does not prove
health or freshness. Read the health JSON and compare its `version` with the
expected full SHA from GitHub's current `main`, using the registry's commands.
Resolve a short deployed version through the repository's commits API; accept
only an unambiguous commit, never a prefix comparison. Record both full SHAs.

Equal SHAs mean current. For different SHAs, compare the `agent-chat/` source
trees at those exact commits through GitHub: this directory is the complete
Cloud Run build context (`make deploy-chat` uses `--source .` inside it).
Use the Git trees API at each full commit SHA and compare the `sha` of the
`agent-chat` entry with type `tree`; reject truncated or missing entries.
Different trees mean deployment drift and require a card even with HTTP 200.
Equal trees mean the deployed source is current despite unrelated tracker
commits; record the SHA mismatch without an outage alert. If health fails,
report service failure. A missing/`unknown` version, unresolved commit, API
failure, or incomplete tree comparison is `UNKNOWN` coverage, never a pass.
Saga reports drift; it never deploys or promotes traffic.

### Silent scheduled jobs

The dashboard watchdog exits successfully without writing stdout when health
is good. Inspect `launchctl print` run counts and last exit status across an
awake interval longer than its five-minute schedule. A flat log is normal.
Probe the dashboard separately: healthy HTTP alone does not prove the watchdog
ran. After a launchd reload, establish a new run-count baseline; insufficient
awake observations mean unknown coverage, not a stopped job.

### Corrections to the initial blocker list

Four of the five blockers Saga reported are already resolved or were misread:

1. **"OpenClaw secret store is empty"** — correct, and it stays empty. Doppler
   is the only secret store. Saga reads secrets at point of use with
   `doppler run --`, and copies none.
2. **"Vercel plugin is not installed"** — no plugin exists or is needed. The
   laptop's `vercel` CLI is authenticated as `eriksjaastad`. For the Mini, put
   a Vercel API token in Doppler.
3. **"RunPod needs a token"** — the token exists:
   `MUFFIN_RUNPOD_API_KEY` in the muffinpanrecipes Doppler config. The account
   is spudlogic personal, not SIL.
4. **"Hosted DB monitoring depends on provider: Neon/Supabase"** — there is no
   Supabase and no Neon in the registry. The portfolio has two hosted
   databases: hypocrisynow's Railway Postgres, and agent-chat's production
   Postgres behind Cloud Run (its host provider is `UNKNOWN` in the registry).
   Everything else is local SQLite (project-tracker's behind dbmed; the rest
   plain files).
5. **"Need the live project list"** — the only genuine blocker, and the
   `monitoring:` block now answers it.

## Keeping it current

Saga's sweep produces cards, not edits. The cards are what keep the registry
true as projects are added and retired:

- New Vercel project, Railway project or Cloud Run service with no
  `monitoring:` entry → card.
- Registry entry whose `prod_url` no longer resolves → card.
- Scheduled job in launchd/crontab with no `_scheduled_jobs` entry → card.
- Registry job that no longer exists on the host → card.
- Service in a Doppler config that the `projects:` block does not list → card.
- Any `UNKNOWN` Saga can now answer → card naming the answer and its evidence.

A human or a floor manager applies the change on the laptop and it lands
through a PR, like every other change to a tracked file.

## What is already on the Mini (verified 2026-09-22)

Saga is not starting from nothing, and two existing facts constrain it.

### 1. There is already a monitor, and it has been dead since June

`com.openclaw.monitor` (`~/.openclaw/workspace/agents/monitor/`, built
2026-04-29) runs a check set, diffs against `state.json`, and posts to Discord
**#alerts** on transitions only.

- **It is not loaded.** `launchctl print` finds nothing.
- **Last run: 2026-06-02 13:17** — its `state.json` and `last-run.json` have not
  moved since. `launchd.err` stops at 2026-07-06.
- **Its check set is Mini-runtime only**: ollama-server, openclaw-gateway,
  auxesis-worker, auxesis-operator-api, disk-usage, tailscale. It never checked
  a website, a Vercel deploy, a cron job, or a backup — so it would not have
  caught the muffinpanrecipes failures regardless.
- **Two of its six checks are now permanently obsolete**: auxesis-worker and
  auxesis-operator-api were already reporting `broken` on the last run, and
  Auxesis was retired 2026-08-09.

Saga should **inherit, not rebuild**: the Discord #alerts path, the
transitions-only design (alert on state change, not every tick), and one
hard-won lesson recorded in that code —

> V1: deterministic formatter only. The LLM rendering path was tested and
> produced hallucinated details (made-up HTTP codes, fake recoveries). For a
> status alert, faithfulness beats fluency. Keep it boring.

That comment is the most valuable thing in the old agent. A fresh Saga that
renders alerts through an LLM will re-learn it the expensive way.

### 2. The Mini has a stale copy of the Kanban board — Saga must not write to it

`pt` is installed on the Mini and `~/projects/project-tracker/data/tracker.db`
exists there with **226 tasks, last written 2026-08-03**. The laptop's live
board has 429 open tasks. The Mini's copy is the orphan of the cross-machine
sync retired 2026-09-16.

**Consequence:** a card created with plain `pt tasks create` on the Mini lands
in a dead database that nobody reads. Saga would report "card filed" and the
card would not exist. That failure is silent and would hollow out the entire
"nothing slips through the cracks" guarantee.

**Rule:** every board write from the Mini goes over SSH to the laptop.

```bash
# Correct — writes the live board:
ssh macbook-pro 'cd ~/projects && PT_SKIP_DOPPLER=1 ~/projects/project-tracker/pt tasks create "..." -p <project>'

# WRONG — writes the Mini's dead 2026-08-03 copy (and bare `pt` over ssh
# fails anyway: on the laptop it is an alias, see section 3):
pt tasks create "..." -p <project>
```

The same applies to `pt info` and `pt memory`: read them over SSH, or accept
that you are reading August.

### 3. Hermes' board access was broken, and this is why (corrected 2026-09-22)

Hermes **is** instructed to update the laptop board over SSH. Its own cron
output from 2026-09-22 11:38 records the failure:

```text
- MacBook/PT still unreachable:
  - `ssh macbook.local` → DNS resolution failure.
```

Two independent faults, both now understood:

1. **Wrong hostname.** Hermes calls `ssh macbook.local`. `.local` does not
   resolve on this network. The working name is `macbook-pro` (tailnet).
2. **`pt` is a shell alias on the laptop**, not a binary on `PATH`:
   `alias pt=~/projects/project-tracker/pt`. A
   non-interactive SSH session does not source the alias, so even a correct
   hostname yields `zsh:1: command not found: pt`.

The working invocation, verified end to end from the Mini:

```bash
ssh macbook-pro 'cd ~/projects && PT_SKIP_DOPPLER=1 ~/projects/project-tracker/pt tasks -p <project>'
```

Also recorded as `pt info get remote_pt_invocation`.

**There is queued work sitting in the fallback.**
`~/projects/holoscape-agent/.scratch/pending-board-updates.md` on the Mini
(last written 2026-09-22 11:37) holds four intended board moves with commit
SHAs and test counts — `#5888` → Done, `#6030` → In Progress plus three
progress notes. On the live board `#6030` still reads **To Do**. That gap is
not a Hermes bug; it is the SSH fault above, and it is exactly the class of
silent loss Saga exists to catch.

The Mini's local fallback was doubly blocked: its own `pt tasks` fails on a
pending migration (`012_add_tasks_archived_at` / `no such column: archived_at`),
so no local board mutation was safe either.
