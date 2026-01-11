---
tags:
  - p/project-tracker
  - type/documentation/todo
  - domain/project-management
status: #status/complete
created: 2025-12-22
---

# [[project-tracker]] - TODO

**Last Updated:** January 11, 2026
**Project Status:** Complete ✅
**Current Phase:** Phase 4: Mission Control & Observability
**Type:** Infrastructure
**Index:** [[00_Index_project-tracker]]

---

## 📍 Current State

### What's Working ✅
- ✅ **MVP Complete!** Full implementation working (Dec 30, 2025)
- ✅ **Database:** SQLite with all tables (projects, cron_jobs, services, AI agents, indexing)
- ✅ **CLI Tool:** `pt` command with scan, list, launch, etc.
- ✅ **Web Dashboard:** FastAPI serving at localhost:8000
- ✅ **Auto-discovery:** Scans all projects successfully
- ✅ **TODO Viewer:** Renders markdown with full formatting
- ✅ **Progress Bars:** Calculates completion % from checkboxes
- ✅ **Sorting:** Newest work first (chronological)
- ✅ **Indexing System:** tracks 00_Index_*.md compliance (Critical Rule #0)
- ✅ **Alerts:** Stalled, Blocked, Missing Index, Cron failures
- ✅ **Meta-tracking:** Dashboard tracks itself!

### In Progress 🔄
- **Adoption** - Erik using dashboard daily
- **Audit Agent Integration** - Porting scanners to Go CLI (v1.0.0)
- **AI Router Telemetry** - Surface model usage & escalation stats in Dashboard

### What's Missing ❌
→ See **Phase 3** tasks below

### Key Decisions Made
1. **Dashboard-first approach** - Build visualization before all features
2. **Standardize TODO.md** - Create template in project-scaffolding
3. **Project metadata priority:**
   - Last modified (git commits or file timestamps)
   - AI agents in use (which AI helping with what)
   - Cron jobs (scheduled automation)
   - External services (from EXTERNAL_RESOURCES.md)
4. **Chronological sorting** - Newest work first (not creation date)
5. **Meta-tracking** - Dashboard tracks itself
6. **Index Enforcement** - Direct integration with Critical Rule #0

---

## 📋 Current Tasks

### Phase 4: Mission Control & Observability (Jan 6, 2026) [complete]
- [x] **Optimization:** Removed mandatory `--reload` from `pt launch` to prevent redundant scanning.
- [x] **Optimization:** Added `--no-scan` flag to `pt launch` for instant dashboard access.
- [x] **Scaffolding Alignment:** Brought project up to scaffolding spec.
    - [x] Created `.cursorignore` for context optimization.
    - [x] Consolidated root `archive/` into `Documents/archives/` (planning, reviews, sessions).
    - [x] Updated `.cursorrules` metadata and synced index status.
- [x] **Kiro Removal:** Removed abandoned `.kiro` directory and all file references.
- [x] **Protocol Governance:** Documented protocol deviation and reinforced "Messenger" role via local worker report.
- [x] **Mission Control Hub:** Transform the dashboard from a passive monitor into an active command center.
    - [x] **Agent Dispatcher UI:** Built a UI interface to manually trigger specialized agents (audit-agent, pt) directly from the dashboard.
    - [x] **Controlled Execution (Passive-First):** Codify the "Passive Monitoring" principle—the dashboard only scans on load or manual refresh.
- [x] **Telemetry & Data Integration:** 
    - [x] **Data Source Integration:** Add `ai_router` telemetry directory as a scanned resource.
    - [x] **AI Router "Blinking Lights":** Surface real-time routing decisions, escalation rates, and model breakdowns on the dashboard.
    - [x] **Cost Savings:** Calculate and display "Estimated Savings" (Local vs. Cloud calls).
- [x] **Health & Resilience Monitoring:**
    - [x] **Critical Error Surfacing (Zero Tolerance):** Any operational error (MCP failures, Cron failures, Backup failures) MUST be surfaced immediately with [CRITICAL] flags.
    - [x] **Cron Health Sentinel:** Refine the cron monitor to provide a visual "Heartbeat" based on log file analysis (e.g., Trading arena logs).
    - [x] **Backup Audit (rclone):** Refined the dashboard to audit and surface "un-backed-up" data via `backup_reader.py` and new UI card.

### Phase 3: Audit Agent Integration (Jan 2, 2026) [complete]

#### Prerequisites
- [x] **Provider Pattern Architecture:** Create `AuditProvider` (Go) and `LegacyProvider` (Python) base classes in `scripts/discovery/`
- [x] **Binary Detection:** Check for `audit` binary on startup and select provider accordingly
- [x] **Database Schema:** Add `health_score` (INTEGER 0-100) and `health_grade` (TEXT A-F) columns to `projects` table

#### Core Integration
- [x] **Health Scoring:** Integrate `audit health [project] --json` via `AuditProvider` with `ThreadPoolExecutor` parallelization
- [x] **Fast Tasks:** ~~Replace 35+ individual `todo_parser.py` calls~~ Provider method implemented. Full integration deferred to avoid scan pipeline refactor.
- [x] **Validation Alerts:** Use `audit check` to trigger "Invalid Frontmatter" alerts in the dashboard
- [x] **Dashboard Metrics:** Add Score and Grade display to project cards

#### UI/UX
- [x] **Missing Binary Warning:** Show header/footer alert: "audit-agent not found. Health scores disabled."
- [x] **Auto-Fix Button:** Add "Fix Frontmatter" button to detail view (calls `audit fix`)
- [x] **Activity Feed:** Read activity from `~/projects/_obsidian/WARDEN_LOG.yaml` and display on dashboard

---

## 🏗 Key Architecture Decisions

| Decision | Choice |
| :--- | :--- |
| **Fallback** | Provider pattern (`AuditProvider` → `LegacyProvider`) |
| **Tasks scan** | Single global `audit tasks` call, not per-project |
| **Health parallelization** | `ThreadPoolExecutor` during `pt scan` |
| **Dashboard reads** | SQLite only (never calls binary on page load) |
| **Activity log path** | `~/projects/_obsidian/WARDEN_LOG.yaml` |

---

## ✅ Completed Tasks

### Phase 2: Indexing & Polish (Jan 1, 2026)
- [x] Add `has_index` boolean field to database schema
- [x] Scan for `00_Index_*.md` files during project discovery
- [x] Validate index files (check YAML frontmatter, required sections)
- [x] Add index status indicator to project cards
- [x] Add alert for projects without indexes
- [x] Show index file age on project cards
- [x] Add "Create Index" quick action to project cards
- [x] Add dashboard summary metric (Index Compliance)
- [x] Add filter: "Missing Indexes" (click compliance metric)
- [x] Link to project-scaffolding documentation
- [x] Fix "Last Work" logic to include uncommitted file changes

### Phase 1: Alerts & Warnings (Dec 30, 2025)
- [x] Create alerts/warnings table at top of dashboard
- [x] Show critical issues before project cards
- [x] Include alert types (Stalled, Blocked, Missing TODO, Cron)
- [x] Make alerts clickable (jump to project detail)
- [x] Add severity levels and color-coding
- [x] Create `cron_monitor.py` for health checking
- [x] Implement GitHub submission and Code Review request

### Phase 0: Foundation (Dec 22-30, 2025)
- [x] Create project-tracker/ directory
- [x] Write comprehensive README.md with vision
- [x] Design SQLite data model
- [x] Document integration with project-scaffolding
- [x] Define success metrics
- [x] Research existing TODO formats across projects
- [x] Design TODO standard template
- [x] Build CLI Tool (pt.py) with Typer
- [x] Build web dashboard with FastAPI
- [x] Create TODO.md viewer with markdown rendering

---

## 🎯 Success Criteria
- [x] TODO standard template exists in project-scaffolding
- [x] TODO format documentation exists
- [x] At least 3 projects using standard TODO format
- [x] Erik approves format as "this is what I want"
- [x] SQLite database exists with all tables
- [x] CLI can add, list, and scan projects
- [x] Web dashboard shows all projects sorted by last work
- [x] Dashboard displays AI agents per project
- [x] Dashboard shows cron jobs indicator
- [x] Dashboard shows services used
- [x] Click project → view rendered TODO.md
- [x] Progress bars show completion %
- [x] Dashboard tracks itself in projects list
- [x] Successfully tested on all 35+ projects
- [x] Project implementation complete (Jan 1, 2026)

### Adoption Metric
- Erik uses dashboard daily for 1 week (In progress)

---

## 💭 Future Ideas / Shower Thoughts
- **Timeline view** - Visual graph showing project activity over time
- **AI Router Integration** - Show which projects are using local vs cloud (via telemetry.jsonl)
- **Search/filter** - Search projects by name or technology
- **Git integration** - Show current branch and uncommitted change count
- **Cost tracking** - Monthly spend history charts
- **Roadmap parsing** - Detect project layer/phase from ROADMAP.md

---

### Related Documentation
**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `/Users/eriksjaastad/projects/audit-agent/` - Go CLI for health, tasks, and validation
- `/Users/eriksjaastad/projects/project-scaffolding/` - Templates and patterns
- `/Users/eriksjaastad/projects/agent-skills-library/` - AI skills
- `/Users/eriksjaastad/projects/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅
