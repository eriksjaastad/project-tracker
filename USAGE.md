---
tags:
  - p/project-tracker
  - type/documentation/guide
  - domain/project-management
status: #status/active
created: 2025-12-30
---

# project-tracker - Usage Guide

> **Quick Start:** `./pt launch` to open the dashboard
**Index:** `00_Index_*.md`

---

## 🔐 Environment Variables

You can configure the behavior of Project Tracker using these environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `PT_EXTERNAL_BACKUP_DIR` | **CRITICAL for Sandbox:** Path for safety backups. Set this if your home directory is read-only. | `~/.project-tracker/backups/` |
| `PT_DB_PATH` | Path to the SQLite database file. | `data/tracker.db` |
| `PROJECTS_ROOT` | The root directory where your projects are located. | `../` |
| `PT_ALLOW_FRESH_DB` | Set to `1` to bypass the "unexpected fresh database" safety check. | `0` |
| `SAFE_MODE` | Set to `0` to allow permanent deletions (for Erik only). | `1` |
| `PT_DASHBOARD_HOST` | Bind host for the dashboard server. Stays on loopback by default so the admin API is not reachable from the LAN. | `127.0.0.1` |
| `PT_ALLOW_REMOTE_ADMIN` | Set to `1` to allow non-loopback callers to hit `/api/agents/run` (runs arbitrary agent commands). Off by default — do not enable in shared environments without a front-end auth layer. | `0` |
| `PT_FULL_BACKUP_DIR` | Directory for full `tracker_*.db` snapshot backups. | `~/.project-tracker/backups/` |
| `PT_BACKUP_LOG_PATH` | Backup job log consumed by `pt backup status` and the dashboard. | `~/.project-tracker/backup.log` |
| `PT_BACKUP_RCLONE_DEST` | Optional rclone destination for one off-machine full backup per day. | unset |
| `PT_MEMORY_DB_PATH` | Optional override for read-only `pt memory` JSON commands. | `$PROJECTS_ROOT/ai-memory/brain.db` |
| `PT_SKIP_DOPPLER` | Set to `1` for read-only SSH/cron commands that should not invoke Doppler. | `0` |
| `PT_MIGRATION_DIR` | Override for `pt migration` state files (testing/isolation). | `~/.project-tracker/migrations/` |

**Locked-hygiene safety valves:** edits in any `.scratch/` directory are exempt from the branch-on-first-edit hook. Use `pt migration start <name>` / `pt migration finish <name> [--commit | --revert]` to record bulk-operation sessions with an appended manifest at `MIGRATIONS.md` — see project `CLAUDE.md` for details.

---

## 🚀 Getting Started

### First Time Setup

1. **No installation needed!** Everything is already set up in this directory.

2. **Launch the dashboard:**
   ```bash
   cd $PROJECTS_ROOT/project-tracker
   ./pt launch
   ```

3. That's it! The dashboard will:
   - Initialize the database (if needed)
   - Scan all your projects
   - Start a web server at http://localhost:8000
   - Open your browser automatically

---

## 📊 Using the Dashboard

### Main Dashboard

The dashboard shows all your projects sorted by **last modified** (newest work first):

- **Status badges:** Active, Development, Paused, Stalled, Complete
- **AI agents:** Which AI is helping with what
- **Cron jobs:** ⏰ indicator if scheduled automation exists
- **Services:** External services used (from EXTERNAL_RESOURCES.md)

### Project Details

Click **"Details"** to see:
- Full project information
- AI agents list with roles
- Cron jobs with schedules
- External services with costs
- Recent activity log

---

## 🖥️ Command Line Interface

### Basic Commands

```bash
# Launch web dashboard (recommended)
./pt launch

# Backup health / recovery
./pt backup status
./pt backup restore ~/.project-tracker/backups/tracker_20260423_141355.db

# Initialize database
./pt init

# Scan all projects
./pt scan

# List all projects (table view)
./pt list

# Show project details
./pt status "project-name"

# Refresh all data
./pt refresh

# Sync one project only (faster than a full scan)
./pt sync-project "project-name"
```

### Managing AI Agents

```bash
# Add an AI agent to a project
./pt add-agent "project-name" "Claude Sonnet 4.5" "Implementation"

# Examples:
./pt add-agent "image-workflow" "Claude Opus 4" "Architecture review"
./pt add-agent "trading-copilot" "Cursor" "Code refactoring"
```

### Managing Cron Jobs

```bash
# Add a cron job to a project
./pt add-cron "project-name" "0 14 * * *" "python scripts/daily.py" "Daily processing"

# Examples:
./pt add-cron "image-workflow" "10 2 * * *" "python scripts/backup/daily_backup.py" "Daily backup"
./pt add-cron "trading-copilot" "0 6,12,18 * * *" "python scripts/fetch_signals.py" "Fetch trading signals"
```

### Managing Services

```bash
# Add a service dependency to a project
./pt add-service "project-name" "Service Name" --cost 5.00 --purpose "Purpose description"

# Examples:
./pt add-service "trading-copilot" "Railway" --cost 5.00 --purpose "Hosting + Postgres"
./pt add-service "image-workflow" "OpenAI" --cost 15.00 --purpose "AI processing"
```

### Sync Controls

```bash
# Show replication state
./pt sync status

# Pause data-plane replication
./pt sync pause

# Resume data-plane replication
./pt sync resume

# Rare: pause everything, including control-plane announcements
./pt sync pause --all
```

### Read-Only Memory Automation

Use these commands from SSH `BatchMode` sessions, cron jobs, or service users that need memory data without touching databases directly:

```bash
cd $PROJECTS_ROOT/project-tracker
PT_SKIP_DOPPLER=1 ./pt memory search --query "LoopLens" --since 7d --limit 50 --json
PT_SKIP_DOPPLER=1 ./pt memory recent --since 7d --project project-tracker --limit 50 --json
PT_SKIP_DOPPLER=1 ./pt memory stats --json
PT_SKIP_DOPPLER=1 ./pt memory export --format ndjson --since 7d --limit 500
PT_SKIP_DOPPLER=1 ./pt config show --effective --json
PT_SKIP_DOPPLER=1 ./pt doctor --json
PT_SKIP_DOPPLER=1 ./pt hygiene --json                         # portfolio-wide git hygiene scan
PT_SKIP_DOPPLER=1 ./pt hygiene --json --project my-project   # single repo
PT_SKIP_DOPPLER=1 ./pt hygiene --quiet                        # human output, findings only
```

JSON responses include a `schema_version`, `ok`, `read_only`, backend metadata, filters, pagination, and result rows. JSON mode does not mix prose into the payload. Validation errors exit `2`; backend/readiness failures exit `3`; query failures exit `4`.

`pt hygiene --json` emits schema `pt.hygiene.v1`. Exit `0` = all clean; exit `6` = at least one finding (useful for cron branching). Detections: dirty working tree (PROGRESS.md excluded), local-only branches, branches ahead of remote, stashes, open bot PRs older than 24h, stale PROGRESS.md (>7 days old AND repo has uncommitted work).

**Per-repo result contract (`pt.hygiene.v1`).** Each entry under `results` is one of two disjoint shapes:

- **Successful scan:** `{"project", "path", "clean": bool, "findings": {dirty_tree, local_only_branches, branches_ahead_of_remote, stashes, open_pr_drift, stale_progress_md}}`. All six finding keys are always present; iterate them with `for name, finding in repo["findings"].items(): if finding.get("present"): ...`.
- **Failed scan (broken repo isolated from siblings):** `{"project", "path", "clean": false, "error": {"class", "message"}}`. **The `findings` key is OMITTED.** Consumers MUST check for `"error"` before accessing `"findings"` — e.g. `if "error" in repo: handle_error(repo) else: iterate(repo["findings"])`. An empty `findings: {}` would read as "checked and found nothing"; absence reads correctly as "couldn't check."

---

## 🔄 How Data is Collected

### Auto-Discovery

The scanner looks for projects in `$PROJECTS_ROOT/` and checks for:

1. **Git repositories** (`.git` directory exists)
2. **README.md** files
3. **Code files** (`.py`, `.js`, `.ts`, etc.)

### Metadata Extraction

For each project found:

**From Git:**
- Last commit date (primary timestamp)
- Falls back to file modification time if git unavailable

**From README.md:**
- First paragraph as description

**From EXTERNAL_RESOURCES.md (in project-scaffolding):**
- External services used
- Monthly costs

---

## 🎯 Tips & Best Practices

### 1. Use Consistent Status Values

Supported statuses:
- `Active` → Active production use
- `Development` → Actively building features
- `Paused` → Temporarily on hold
- `Stalled` → Blocked or abandoned
- `Complete` → Finished

### 3. Track External Services

List services in EXTERNAL_RESOURCES.md to track costs.

---

## The Problem This Solves

**From Erik (Dec 22, 2025, 3:30 AM):**
> "I'm switching between Cursor windows on multiple projects. It's like keeping plates spinning. Eventually I'm gonna be in a window and my brain hasn't switched to whatever project I'm in, and I'll talk for 20 minutes in the wrong window and everything will spin out of control."

**The spinning plates problem:**
- 10+ active projects
- Multiple Cursor windows open simultaneously
- Cognitive load switching contexts
- Forgetting which project does what
- Losing track of what's running where

---

## 🛠 Requirements

- **Python 3.11+**
---

## ✨ Key Features

### 1. Chronological Sorting (Newest First)
Your most recently worked-on projects appear at the top automatically.

### 2. AI Agents Tracking
See which AI is helping with which project and what they're doing.

### 3. Cron Jobs Display
See which projects have scheduled automation (⏰ indicator).

### 4. External Services
Shows which services each project uses and monthly costs.

### 5. Meta-Tracking
**The dashboard tracks itself!** It shows up in the projects list with its own status and progress.
