<!-- GENERATED FROM: ~/projects/project-tracker/CLAUDE.md -->
<!-- DO NOT EDIT DIRECTLY. Edit CLAUDE.md and run instruction-writer . --changed claude --write from the project directory -->

# CLAUDE.md - project-tracker

**What this is:** project-tracker is the `pt` CLI, Kanban board, and dashboard that every other project in `~/projects` depends on for task coordination, agent memory, and cross-project messaging. If this project breaks, every other agent loses its work queue and its shared memory surface. "Broken" means: `pt` exits non-zero on common commands, the Kanban DB loses rows, or the dashboard stops loading. Treat data loss here as portfolio-wide damage, not a local bug.

> **You are the floor manager of project-tracker.** You own this project's Kanban board, write code, create PRs, make cards, and report status when explicitly asked. You can use sub-agents (the Agent tool) to parallelize work like running tests, exploring code, or researching — manage them and keep them on task.

## Whole-Project Ownership

You are responsible for the entire project-tracker worktree, not only the files you personally edited in the current session. A dirty or untracked file is not automatically "someone else's problem" just because you did not create it today. It may be generated output, follow-up work from another machine, or a file another agent prepared for you to carry forward.

Before opening a PR, committing, or declaring the tree clean, inspect and classify every dirty/untracked path in `git status`. For each path, decide one of:

- **Include:** it belongs with the current change, including generated mirrors such as `AGENTS.md` after editing `CLAUDE.md`.
- **Separate:** it is real project work but belongs in a different change set. Prefer bundling related cards into one PR (see portfolio CLAUDE.md); only open a separate PR when the work is truly unrelated.
- **Ignore for now:** it is intentionally local-only or explicitly out of scope, and you can state why.

Do not omit a file silently. If a generated file mirrors a source file you changed, regenerate it and include it. If you are unsure whether a dirty file is related, inspect it before deciding. The default posture in project-tracker is ownership of the whole board and repo, not narrow ownership of today's patch.

Read DECISIONS.md before changing architecture or infrastructure.
Before modifying code, write a pre-flight check: what does this do, why is it built this way, what are you changing? (See root CLAUDE.md.)

Run `pt info -p project-tracker` for tech stack, env vars, infrastructure, and project-specific reference data.
Run `pt memory search "project-tracker"` before starting work for prior decisions and context.

## Session Continuity

If `PROGRESS.md` exists in the project root, read it FIRST before doing anything else. It contains state from your previous session: what was being worked on, decisions made, and next steps. After reading, update or delete it as appropriate — stale PROGRESS.md files are worse than none.

**`PROGRESS.md` is always dirty in `git status`.** It's updated daily as part of normal operation — an `M PROGRESS.md` line is the expected state, not a finding. Don't flag it as uncommitted work, don't offer to commit it, and don't suggest the user review it unless you yourself just modified it in this session.

## Card Factory Auto-Validation

When you start a task whose text begins with `[Card Factory]`, run `/validate-card-factory <task-id>` FIRST before doing any work. If the validation cancels the card (issue already resolved), move on to the next task. This prevents wasting sessions on stale findings.

## Server Ownership

The dashboard server (uvicorn on port 8000) is yours to manage. Restart it whenever you need to — after code changes, after a crash, whenever. No need to ask Erik.

Standard restart: `pkill -f "uvicorn dashboard.app" && sleep 1 && doppler run -- $HOME/projects/project-tracker/.venv/bin/python -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8000 &` (bind stays on loopback — admin endpoints require loopback unless `PT_ALLOW_REMOTE_ADMIN=1`)

Verify it's up: `curl -s http://localhost:8000/api/health` or check `lsof -i :8000`.

## Authorization — Check Doppler First (#6065)

This repo runs **self-contained** through Doppler. There is no `.env`, no exported shell secret, no manual login step. `doppler.yaml` at the repo root pins `project-tracker/dev`, and the `Makefile` wraps the common commands so a cold shell with nothing exported just works: `make help` lists them.

**Before assuming an auth problem is missing infrastructure — check Doppler first.** The token almost certainly already exists; the usual cause is that the command wasn't run under `doppler run --`, or was run under the *wrong* Doppler project (see the second table).

**Tokens in this repo's own config (project: `project-tracker`, config: `dev`):**

| Token | What it's for | Required when |
|---|---|---|
| `TURSO_KANBAN_URL` | Turso cloud endpoint for the Kanban DB (tasks, projects, calendar) | Only when `~/projects/.turso-config.json` has `turso_enabled: true`. It is currently **false**, so this is dormant and the backend is local `data/tracker.db`. |
| `TURSO_KANBAN_TOKEN` | Turso auth token, paired with `TURSO_KANBAN_URL` | Same as above |
| `COST_TRACKER_API_KEY` | Auth for the SIL cost-tracker API the dashboard queries (`dashboard/app.py`) | Whenever the dashboard's cost panel needs live data |
| `DOPPLER_PROJECT`, `DOPPLER_CONFIG`, `DOPPLER_ENVIRONMENT` | Doppler's own metadata, injected automatically | Never set by hand |

**Secrets this repo's scripts need that do *not* live in `project-tracker/dev`.** This is a real deviation from the portfolio pattern: several scripts pass an explicit `--project/--config` because their secret belongs to a different product's Doppler project. Do not "fix" this by copying the secret into `project-tracker/dev`.

| Token | Doppler location | Consumer |
|---|---|---|
| `RESEND_API_KEY` | `synth-insight-labs` / `prd` | `scripts/alert_digest.py` (daily portfolio digest email), wrapped by `scripts/alert-digest.sh` and `make digest` |
| `XAI_API_KEY` | `synth-insight-labs` / `prd` | `scripts/card_factory_grok.py` (Grok card-factory shadow run) |
| `TURSO_KANBAN_URL` / `TURSO_KANBAN_TOKEN` | `openclaw` / `dev` | `scripts/turso_to_local.py` one-time Turso → local dump (`make turso-sync`) — historically these creds lived in `openclaw`, and that script still reads them there |
| `TURSO_BRAIN_URL` / `TURSO_BRAIN_TOKEN` | `ai-memory` / `dev` | `pt memory ...` shells out to `brain.py` under `doppler run --project ai-memory --config dev` itself; you do not wrap it |
| `GOOGLE_API_KEY` | `trading-copilot` / `dev` | `scripts/doc_audit_v2.py`, which fetches it via `doppler secrets get` at runtime |

**Not in Doppler at all:** Agent Chat reads `AGENT_CHAT_URL`, `AGENT_CHAT_API_KEY`, and `AGENT_CHAT_SENDER` from `~/.claude/agent-chat.env` (or the environment) — see `_load_chat_config` in `scripts/pt.py`. If `pt message ...` says "Agent Chat not configured", the fix is that file, not Doppler.

**Deviations in the `pt` launcher — read these before debugging an auth failure:**

- **`pt` wraps itself.** The launcher runs `doppler run --project ... --config ... -- uv run scripts/pt.py`. Never prefix `pt` with `doppler run --`; double-wrapping is the bug, not the fix.
- **`PT_SKIP_DOPPLER=1`** skips the wrap entirely. Used for read-only cron/SSH paths (`PT_SKIP_DOPPLER=1 pt memory recent --since 7d --json`), where the local SQLite backend needs no secret and paying Doppler's startup cost is waste. `--help`/`help` skip it automatically for the same reason.
- **`PT_DOPPLER_PROJECT` / `PT_DOPPLER_CONFIG`** override the project/config the launcher passes (defaults `project-tracker` / `dev`). Use for testing against another config; empty values are rejected.
- **The Turso switch skips Doppler.** If `~/projects/.turso-config.json` has `turso_enabled: false` — which is the **current, deliberate state** (local SQLite since 2026-04-05; Turso added ~2.5s latency per query for no benefit) — the launcher skips `doppler run` completely and execs `uv run scripts/pt.py` bare. That means: **on this machine today, a normal `pt` invocation gets NO Doppler secrets injected**, and it does not need any. If you are debugging a missing env var in `pt`, check that file before you conclude Doppler is broken. Scripts that need secrets regardless (the digest, the dashboard) do their own explicit `doppler run` and are unaffected by this switch.

**If a command fails with auth/credential errors:**
1. Confirm you ran it through `doppler run --` — or, for `pt`, that you did **not** (the launcher self-wraps).
2. Confirm you are pointed at the right Doppler project. Most auth failures here are the second table above: the secret exists, just not in `project-tracker/dev`.
3. Confirm `doppler.yaml` is intact (`cat doppler.yaml` → `project: project-tracker`, `config: dev`), then check the token exists: `make doppler-check`, or `doppler secrets --project <proj> --config <cfg> --only-names`. **Names only — never print values.**
4. If the token is genuinely missing, surface it to Erik — don't add tokens to Doppler silently.

**Deploy target:** local only. `agent-chat/` deploys to Cloud Run, but project-tracker itself — CLI, DB, dashboard — runs on the machine it lives on.

### Deploying agent-chat

`agent-chat/` is the one part of this repo that runs somewhere else: Cloud Run
service `agent-chat`, project `synth-insight-labs`, region `us-central1`.

```
make deploy-chat-status   # which git SHA is live right now
make deploy-chat          # build + deploy, WITHOUT promoting traffic
```

**Check the live version before and after every deploy.** A working Dockerfile
sat here for five months with nothing referencing it — the image was built by
hand once and the command was never written down, so production silently drifted
five months behind `main` and four server commits never shipped, including the
fix for a DM-loss incident. `make deploy-chat-status` exists so that is one
command to notice instead of forensic archaeology against response shapes.

`make deploy-chat` deploys with `--no-traffic --tag next`, so the new revision
is live at a tagged URL but serves nobody. That isolates **traffic, not the
database** — `server/app.py` calls `db.init_db()` at import time, so the new
container touches the live production Postgres on boot even at 0% traffic. The
statements are additive and idempotent, so this is safe, but `--no-traffic` is
not a dry run. Smoke-test it, then promote:

```
gcloud run services update-traffic agent-chat --to-latest \
  --region us-central1 --project synth-insight-labs
```

Roll back the same way with `--to-revisions=<previous>=100`. Cloud Run revisions
are immutable and retained, so rollback is seconds and needs no rebuild — which
is why this is a Makefile target and not a CI pipeline.

**Requires a one-time interactive `gcloud auth login`** with deploy rights on
`synth-insight-labs`. That is Erik's to run; no agent should. gcloud auth on this
machine expires often, which is exactly why "what is live?" must be answerable
by `curl /health` rather than by `gcloud run revisions list`.

Server secrets come from Doppler project `agent-chat`, config `prd`
(`AGENT_CHAT_API_KEY`, `AGENT_CHAT_DATABASE_URL`). The client side deliberately
does **not**: `~/.claude/agent-chat.env` supplies each machine's identity. Don't
merge the two — the server's secrets are shared, the identity is per-machine.

## Database Safety — CRITICAL

On 2026-01-27, an agent dropped the tasks table without backup, destroying 94 tasks. The rule below exists because of that incident. Do not skip the gate.

### GATE — run before any schema change or row-affecting statement

Before running `DROP`, `DELETE`, `TRUNCATE`, `ALTER` (non-additive), `rm *.db`, or any "reset/init/recreate" operation, write these four lines out loud in chat. If any line is blank or guessed, **stop and ask Erik**:

1. **Table:** `<name>`
2. **Row count right now:** `<integer from SELECT COUNT(*)>`
3. **Backup path:** `<absolute path of the backup you just created, or the auto-backup from pt>`
4. **Approval:** `<direct quote from Erik authorizing this specific operation>`

Additive migrations (`ALTER TABLE x ADD COLUMN y`) are the only schema changes that do not need the gate. Everything else does. Deletions of user data go through the application API (which auto-backs up) — not raw SQL.

If a schema is broken and fixing it requires a destructive op, **refuse and print manual instructions**. Do not fix it yourself.

<!-- BEGIN scaffold:hygiene -->
## Locked Hygiene Contract

This project participates in the portfolio-wide locked hygiene contract.
Hygiene guidance now lives in agent-runtime-config; the contract is still enforced by user-scope
hooks in `~/.claude/` and by `pt` CLI commands in project-tracker. **Treat this block as the portfolio hygiene contract.** Markers are author-owned (not auto-rewritten). Prefer updates guided by agent-runtime-config docs; add project-specific notes outside the markers.

### What the contract requires

1. **No direct edits on `main`/`master`/`trunk`.** A PreToolUse hook blocks
   `Edit`/`Write`/`MultiEdit`/`NotebookEdit` on tracked files while HEAD is the
   default branch. Work happens on feature branches; PRs are how changes land.
2. **Clean session exits encouraged.** Run `pt hygiene` to detect:
   - dirty working tree (PROGRESS.md is ignored),
   - commits ahead of upstream unpushed,
   - local-only branches with no remote tracking,
   - stashes,
   - open bot PRs older than 24h,
   - stale PROGRESS.md with other uncommitted work.
   
   Exit 0 = clean portfolio, exit 6 = findings. Agents should resolve findings
   before completing work. (Note: No automatic gate blocks session close; enforcement
   is manual via `pt hygiene`. The session-end gate referenced by `PT_ALLOW_DIRTY_EXIT`
   is not currently implemented as a Stop hook.)
3. **Audit trail for bulk changes.** Multi-file refactors, renames, and doc
   reorgs run inside `pt migration start <name>` … `pt migration finish <name>`
   so they are reversible (`--revert` uses `git restore` for tracked paths and
   `send2trash` for untracked — never raw `rm`).
4. **Handoffs are first-class.** If a session must end dirty (mid-rebase, mid-
   investigation), record it: `pt handoff create <card-pk> --branch <b> --intent
   <s> --status <s> --next <s> --guidance preserve|discard`. Use `pt handoff list`
   to check open handoffs before ending sessions.

### Safety valves

- **`.scratch/`** — every project has a gitignored `.scratch/` at its repo root.
  The branch-on-first-edit hook lets edits under any `.scratch/` subdir through
  unconditionally. Use it for throwaway notes, probe scripts, and reading-mode
  poking. Files there never reach a PR. If `.scratch/` work turns into real work,
  move it out before committing.
- **`PT_ALLOW_MAIN_EDIT=1`** — one-shot env var to bypass the main-edit hook.
  Use sparingly; intended for emergency fixes and tooling that must touch the
  default branch. Every use is logged to `~/.claude/state/locked_hygiene/bypasses.jsonl`.
- **`pt handoff`** — structured alternative for recording unfinished work that
  must be left in a dirty state. Use `pt handoff create` to document the context,
  then `pt handoff list` to review open handoffs before completing sessions.

### Quick reference

| Action                          | Command                                       |
| ------------------------------- | --------------------------------------------- |
| Start a recorded bulk migration | `pt migration start <name>`                   |
| Finish + write `MIGRATIONS.md`  | `pt migration finish <name>`                  |
| Revert a migration              | `pt migration finish <name> --revert`         |
| Open a handoff                  | `pt handoff create <card-pk> --branch <b> …`  |
| List open handoffs              | `pt handoff list`                             |
| Resolve a handoff               | `pt handoff resolve <id>`                     |
| Refresh this block portfolio-wide | Manual / agent-runtime-config guidance (scaffold sync CLI retired #6833) |
<!-- END scaffold:hygiene -->

## PR Workflow and Sizing Policy

### PR Sizing Target

At card pickup/scoping, aim for **one coherent PR around 500 substantive changed lines or less**.

- **500 is a target, not a hard gate.** The goal is reviewability — smaller PRs get better reviews, merge faster, and reduce rebase pain.
- **Substantive lines** exclude generated files, lockfiles (`package-lock.json`, `uv.lock`, etc.), vendored code, and mechanical snapshots (e.g., test fixtures that mirror a large input verbatim).
- **If likely materially larger** (e.g., 800+ substantive lines), split into coherent cards/PRs **before coding**. Each PR should be independently reviewable and testable. Example: extract helper functions into one PR, then use them in a second PR for the main feature.
- **Preserve Erik's anti-micro-PR rule**: related work stays bundled when it fits coherently. A 600-line PR that's one logical unit is better than three artificial 200-line splits.

### Checkpoints

1. **At card pickup/scoping**: Estimate substantive diff size. If likely >500 and naturally separable, create multiple cards. Document the split decision.
2. **At local pre-push review**: Run the local code review AND inspect actual substantive diff size:
   ```bash
   # Resolve base branch dynamically (handles main/master/trunk)
   BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main")
   git diff $BASE...HEAD --stat
   # Manually subtract generated/mechanical files from the total
   ```
   If materially over ~500 substantive lines:
   - **Split** if the PR contains multiple logical changes that can be separated.
   - **Document why not** if it's one coherent change that cannot be split cleanly without breaking atomicity.

### Do not spring the rule only at PR submission

The policy must appear at **pickup/scoping** (before coding starts) and again at **local pre-push review** (before pushing). Discovering a 1200-line diff at push time with no path to split it is the failure case this policy prevents.

<!-- BEGIN runtime-doctor:shared:code-review-rules -->
## Code Review Rules

> **Authored once, here. Propagated into every repo's `AGENTS.md` so the reviewer sees it
> in-repo.** Do not hand-copy this into a project file — if it is missing from a repo, that
> is a propagation bug, not a licence to paste.

These are the standards every PR is reviewed against, by whoever or whatever is reviewing.
They are written provider-neutral on purpose: Codex, Claude and any future reviewer read the
same list.

### Gate 0 — mechanical scan

A failure prevents a PASS, but does not end the review. Complete all independent
checks and the judgment audit, then report the supported findings together.
If a failure prevents a check from running, identify that coverage gap.

| ID | Check |
|----|-------|
| M1 | **Portable paths.** Flag machine-specific paths wired into executable code/config or prescribed setup commands. Illustrative examples, incident evidence, and committed data breadcrumbs are not runtime dependencies; do not reject them merely for spelling a path. |
| M2 | **No swallowed unexpected failures.** Flag `except: pass` when it hides an operation failure from the caller. Explicit best-effort or expected-absence handling is valid when the documented contract is preserved. |
| M3 | No real API keys, tokens, or credentials in files. Secrets come from Doppler. Clearly synthetic test fixtures and documented placeholders are permitted. |
| M4 | No unresolved placeholders in rendered deliverables or runtime configuration. Source templates and literal test fixtures may intentionally contain placeholders. |
| M5 | No JS redeclarations in changed `.js` files beneath any directory named `static`, at any depth (including nested subdirectories). If the diff touches any, run from the project root: `npx eslint --no-config-lookup --rule '{"no-redeclare": "error"}' <paths>`. Exit 0 = pass. Skip when the diff has no static JS. |

### Judgment checks — what automation cannot see

| ID | Check |
|----|-------|
| T1 | **Inverse test audit.** Not "do tests pass" but *what do the passing tests never exercise*. Name the dark territory. |
| T2 | **No weak assertions.** `isinstance(x, T)` or `x is not None` alone asserts almost nothing. |
| E1 | **Status contracts are truthful.** Check the documented exit/status protocol. A hook that returns a deny decision in JSON with exit 0 is valid when its caller consumes that protocol. |
| E2 | **No silent failure returns.** `return []` or `return ""` on a failed operation, with nothing logged, is a defect — the caller cannot tell empty from broken. |
| H1 | **Subprocess integrity.** Use a timeout and handle failure through `check=True` or explicit validation of expected return codes. Expected nonzero results must remain usable; unexpected failures must not silently become success. |
| H5 | **CASCADE DELETE documented.** Foreign-key relationships are spelled out before any `DELETE` lands. |
| H7 | **No unrequested auto-cleanup.** A "helpful" destructive addition nobody asked for is a defect, not a bonus. |

### Scope and authorisation

- **Was this behaviour actually requested?** If no, reject it — however good it is.
- **Does the change stay inside the task it claims?** Scope creep is a finding.
- **Can every change trace to a requirement?** If it traces to nothing, say so.

### Review in blast-radius order

A Tier 1 defect propagates into every downstream project, so it is read first.

- **Tier 1** — `templates/`, `AGENTS.md`, `CLAUDE.md`: propagation sources.
- **Tier 2** — `scripts/`, `scaffold/`: execution critical.
- **Tier 3** — `docs/`, `patterns/`, rules files: human reference, no code impact.

### Verdict

Local and delegated review reports end in **PASS** or **FAIL**, pinned to the
**exact commit SHA** reviewed. State that SHA in the verdict; a new commit requires
a fresh review. A local or sub-agent PASS does not replace the Codex GitHub gate.

GitHub reviewers report supported findings or a clean result in the integration's
normal format. Reviewing code does not require access to workstation tools or
merge-policy mirrors.

Agents publishing or merging a PR must follow the complete
[PR review and merge policy](https://github.com/eriksjaastad/agent-runtime-config/blob/main/docs/pr-review-policy.md).
Local installations also expose that same policy through `pt info get pr_merge_policy`
and `~/projects/Project-workflow.md`. A clean review object, completed summary, or
fresh connector thumbs-up observed on an unchanged recorded head can qualify under
that procedure without a literal PASS token. The evidence must identify the current
commit and clear findings. Pending, missing, ambiguous, or stale evidence does not
pass. If the complete policy is unavailable, stop publication or merging; this does
not prevent a reviewer from completing the code review. An explicitly authorized
exception is recorded as an exception, never as a PASS.

### How to report

Shape, not standards. Drip-fed findings cost a full cycle each — a new commit
invalidates the prior review, so a five-finding diff becomes five reviews.

- **One review per request, covering the whole diff.** Every finding, most
  severe first, each with `file:line` and a concrete failure scenario. Never
  hold one back for a later round.
- **Separate evidence from uncertainty.** Findings need a concrete failure
  scenario. Report unverified concerns as questions or coverage gaps, not defects.
  A review with no supported findings is valid; do not manufacture issues.
- **Rank use-case breakage above hypothetical hardening.** A P2 that silently
  breaks the primary workflow outranks a serious-looking edge case nobody hits.
  Say which class a finding is in.
- **Say where the change is too strict** — where it refuses, blocks or rejects
  something it should accept. Implementers cannot see this in their own work, so
  it is the direction least likely to be found without you.
- **If the diff answers your previous findings, say so**, and check whether those
  fixes opened adjacent surface. Most late-round defects live there.

### Review convergence

- **Review the behavior, not only the changed lines.** Trace affected callers,
  consumers, and execution paths. When a defect appears, inspect related forms
  before submitting the review; group examples with the same root cause.
- **Check both failure and legitimate use.** For parsers and filters, cover the
  relevant syntax variants, wrappers, normalization, and safe counterparts. For
  synchronization and conversion, check round trips and preservation of authored
  content. Select cases from the actual contract; unrelated exhaustive audits are
  outside the PR's scope.
- **Verify fixes against history.** Compare relevant behavior with the base and
  previous reviewed revision. Distinguish incomplete fixes, newly introduced
  regressions, and pre-existing issues outside the changed behavior. On follow-up
  reviews, verify prior findings and adjacent effects, retaining whole-diff context.
- **Aim to converge in two or three reviews.** If the same defect family returns,
  reassess the implementation and test coverage before another narrow patch.
  The target never waives a finding, required check, or exact-head review.
<!-- END runtime-doctor:shared:code-review-rules -->
