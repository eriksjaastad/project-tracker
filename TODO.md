---
tags:
  - p/project-tracker
  - type/documentation/todo
  - domain/project-management
status: #status/complete
created: 2025-12-22
---

# [[project-tracker]] - TODO

**Last Updated:** January 1, 2026  
**Project Status:** Complete ✅
**Current Phase:** Final Polish & Indexing Compliance
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

### What's Missing ❌
- [ ] Real-time health scores from `audit-agent`
- [ ] Cross-project task aggregation via `audit tasks`

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

## ✅ Completed Tasks

### Phase 3: Audit Agent Integration (Jan 2, 2026) [in_progress]
- [ ] **Environment Check:** Add `AUDIT_BIN_PATH` to `config.py` and verify binary presence
- [ ] **Health Scoring:** Integrate `audit health [project] --json` into the project scanner
- [ ] **Dashboard Metrics:** Add Score (0-100) and Grade (A-F) to project cards
- [ ] **Fast Tasks:** Replace Python `todo_parser.py` with `audit tasks` NDJSON feed
- [ ] **Validation Alerts:** Use `audit check` to trigger "Invalid Frontmatter" alerts in the dashboard
- [ ] **Auto-Fix Integration:** Add "Fix Frontmatter" button to detail view (calls `audit fix`)
- [ ] **Vault Logging:** Port internal logging to use `audit log` for shared activity tracking

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

*Project status: 100% Technical Completion. Entering adoption phase.* 🎯
