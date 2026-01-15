---
tags:
  - p/project-tracker
  - type/documentation/todo
  - domain/project-management
status: #status/complete
created: 2025-12-22
---

# project-tracker - TODO

**Last Updated:** January 13, 2026
**Project Status:** Active (Phase 5 pending)
**Current Phase:** Phase 5: Index Auto-Sync
**Type:** Infrastructure
**Index:** [[00_Index_project-tracker]]

---

### 🚨 Governance & Portability (Code Review v2) [complete]
- [x] **Ship Blockers:**
    - [x] Fix hardcoded paths in `agent_registry.py`.
    - [x] Install pre-commit hook (`scripts/git-pre-commit.sh` linked to `.git/hooks/pre-commit`).
- [x] **Recommended Fixes:**
    - [x] Add timeouts to `subprocess.run` calls in `dashboard/app.py`.
    - [x] Update `warden_audit.py` to detect `Path.home()` patterns.
    - [x] Expand test coverage (added `tests/test_discovery.py` and `tests/MISSING_TESTS.md`).

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
- **Index Auto-Sync** - See Phase 5 below (CRITICAL)

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

### Phase 5: Index Auto-Sync (PENDING)

**Problem:** The `00_Index_*.md` files are the Source of Truth for the dashboard, but they require manual updates. Floor Managers forget to update them when they get busy doing actual work. This causes "Dashboard Drift" where projects appear stale even when active.

**Solution:** Project-tracker should WRITE to index files, not just READ them.

**Requirements:**
- [ ] **Trigger on launch** - NOT a cron job. Runs when `pt launch` or `pt scan` is called.
- [ ] **Auto-update "Recent Activity"** - Pull from git log and write to index file.
- [ ] **Detect drift** - Compare git activity timestamp vs index file mtime.
- [ ] **Preserve manual content** - Don't clobber description, components, or other human-written sections.
- [ ] **Atomic writes** - Use temp-file-and-rename pattern for safety.

**Implementation Notes:**
- Add `sync_index()` function to `project_scanner.py`
- Call during scan phase, after reading project metadata
- Only update "Recent Activity" section (regex/marker-based replacement)
- Log what was updated for visibility

**Why this matters:**
Currently project-tracker can tell you "this index is stale" but can't fix it. That's like a smoke detector that can't call the fire department. The Floor Manager shouldn't be responsible for remembering routine administrative updates - that's exactly what automation is for.

---

### Phase 4: Mission Control & Observability (Jan 6, 2026) [complete]
- [x] **Optimization:** Removed mandatory `--reload` from `pt launch` to prevent redundant scanning.
- [x] **Optimization:** Added `--no-scan` flag to `pt launch` for instant dashboard access.
- [x] **Scaffolding Alignment:** Brought project up to scaffolding spec.
    - [x] Created `.cursorignore` for context optimization.
    - [x] Consolidated root `archive/` into `Documents/archives/` (planning, reviews, sessions).
    - [x] Updated `.cursorrules` metadata and synced index status.
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
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_schema]] - database design
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[adult_business_compliance]] - adult industry
- [[deployment_patterns]] - deployment
- [[orchestration_patterns]] - orchestration
- [[performance_optimization]] - performance
- [[project_planning]] - planning/roadmap
- [[research_methodology]] - research
- [[agent-skills-library/README]] - Agent Skills
- [[audit-agent/README]] - Audit Agent
- [[project-scaffolding/README]] - Project Scaffolding
- [[project-tracker/README]] - Project Tracker
## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_schema]] - database design
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_schema]] - database design
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[adult_business_compliance]] - adult industry
- [[deployment_patterns]] - deployment
- [[orchestration_patterns]] - orchestration
- [[performance_optimization]] - performance
- [[project_planning]] - planning/roadmap
- [[research_methodology]] - research
## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_schema]] - database design
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->



**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `$PROJECTS_ROOT/audit-agent/` - Go CLI for health, tasks, and validation
- `$PROJECTS_ROOT/project-scaffolding/` - Templates and patterns
- `$PROJECTS_ROOT/agent-skills-library/` - AI skills
- `$PROJECTS_ROOT/EXTERNAL_RESOURCES.md` - Service dependency data source

---

*Project status: Phase 4 Complete. Mission Control & Observability.* ✅


<!-- project-scaffolding template appended -->

# {{PROJECT_NAME}} - TODO

**Last Updated:** {{DATE}}  
**Project Status:** {{STATUS}} (In Progress/Active/Development/Paused/Stalled/Complete)  
**Current Phase:** {{PHASE}} (Foundation/MVP/Production/etc.)

---

## 📍 Current State

### What's Working ✅
<!-- List what's operational and tested -->
- **Feature 1:** Brief description of what works
- **Feature 2:** Another working component
- **Automation:** Any scheduled jobs or automated processes

### What's Missing ❌
<!-- Honest assessment of gaps -->
- **Feature X:** Not implemented yet
- **Integration Y:** Needs setup
- **Documentation Z:** Incomplete

### Blockers & Dependencies
<!-- What's stopping progress? -->
- ⛔ **Blocker:** Clear description of what blocks progress
- 🔗 **Dependency:** External service, API key, or approval needed
- ⏳ **Waiting:** What you're waiting for

---

## ✅ Completed Tasks

### Phase {{PHASE_NUMBER}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Task description with clear outcome
- [x] Another completed task
- [x] Task that was finished

### Phase {{PREVIOUS_PHASE}}: {{PHASE_NAME}} ({{DATE_RANGE}})
- [x] Historical completed task
- [x] Another past milestone

---

## 📋 Pending Tasks

### Phase 0: Industrial Hardening (Gate 0)
- [ ] **Dependency Pinning:** Replace `>=` with `~=` or `==` in `requirements.txt`.
- [ ] **DNA Check:** Verify zero machine-specific absolute paths remain in codebase.
- [ ] **Error Audit:** Replace `except: pass` with explicit logging.
- [ ] **Subprocess Audit:** Ensure all CLI calls have `check=True` and `timeout`.

### 🔴 CRITICAL - Must Do First
<!-- High-priority, blocking other work -->

#### Task Group 1: {{TASK_GROUP_NAME}}
- [ ] Specific actionable task
- [ ] Another task with clear success criteria
- [ ] Task that depends on previous tasks

#### Task Group 2: {{TASK_GROUP_NAME}}
- [ ] Task description
  - [ ] Sub-task (if needed)
  - [ ] Another sub-task

---

### 🟡 HIGH PRIORITY - Important
<!-- Important but not blocking -->

#### Task Group 3: {{TASK_GROUP_NAME}}
- [ ] High-value task
- [ ] Another important task

---

### 🔵 MEDIUM PRIORITY - Nice to Have
<!-- Useful but can wait -->

#### Task Group 4: {{TASK_GROUP_NAME}}
- [ ] Enhancement or improvement
- [ ] Optional feature

---

### 🟢 LOW PRIORITY - Future
<!-- Backlog items, not urgent -->

#### Task Group 5: {{TASK_GROUP_NAME}}
- [ ] Long-term idea
- [ ] Nice-to-have feature

---

## 🎯 Success Criteria

### {{PHASE}} Complete When:
- [ ] Clear, measurable criterion
- [ ] Another specific goal
- [ ] Outcome that defines "done"

### Project Complete When:
- [ ] Final outcome achieved
- [ ] All core features working
- [ ] Documentation complete

---

## 📊 Notes

### AI Agents in Use
<!-- Which AI is helping with what? NEW SECTION -->
- **{{AI_NAME}} ({{MODEL}}):** Role description (e.g., "Implementation", "Code Review", "Architecture")
- **{{AI_NAME}}:** Another AI agent and its role

### Cron Jobs / Automation
<!-- Scheduled tasks for this project -->
- **Schedule:** `{{CRON_EXPRESSION}}` (e.g., "0 14 * * *" = daily 2 PM)
- **Command:** `{{COMMAND}}`
- **Purpose:** What it does
- **Status:** Active/Inactive

### External Services Used
<!-- From project-scaffolding/EXTERNAL_RESOURCES.md -->
- **{{SERVICE_NAME}}:** Purpose, cost
- **{{SERVICE_NAME}}:** Another service

### Cost Estimates
<!-- If applicable -->
- **Development:** Estimated time or cost
- **Monthly:** Recurring costs (API, hosting, etc.)
- **One-time:** Setup or infrastructure costs

### Time Estimates
<!-- Rough guidance -->
- **{{PHASE}}:** X-Y hours
- **Total project:** X-Y hours/weeks
- **Next milestone:** X hours

### Related Projects & Documentation
<!-- Links to other relevant projects or docs -->
- **{{PROJECT_NAME}}:** How it relates
- **{{DOC_PATH}}:** Important reference document

### Technical Stack
<!-- Key technologies -->
- **Language:** Python 3.11+ / JavaScript / etc.
- **Framework:** FastAPI / React / etc.
- **Database:** SQLite / PostgreSQL / etc.
- **Deployment:** Railway / Local / etc.

### Key Decisions Made
<!-- Important choices for future reference -->
1. **Decision:** Rationale and date
2. **Decision:** Another key choice

### Open Questions
<!-- Unresolved items needing discussion -->
- ❓ Question that needs answering
- ❓ Choice that needs to be made

---

## 🔄 Change Log (Optional)

### {{DATE}} - {{PHASE_NAME}}
- Major milestone or significant change
- Another important update

### {{PREVIOUS_DATE}} - {{PREVIOUS_PHASE}}
- Historical change
- Past update

---

<!-- 
=============================================================================
GUIDANCE FOR AI SESSIONS:
=============================================================================

This TODO is designed to be both HUMAN and AI readable.

When updating this file:
1. Always update "Last Updated" date at the top
2. Move completed tasks from Pending → Completed (keep the checkbox [x])
3. Add dates to completed phases
4. Update "Current State" section as project evolves
5. Keep Blockers section honest and current
6. Mark tasks as [x] when done, don't delete them (shows progress)
7. Update Success Criteria as understanding improves
8. Keep Notes section current (costs, time, related projects)

When reading this file at session start:
1. Read "Current State" first (understand where things are)
2. Check "Blockers & Dependencies" (know what's stopping progress)
3. Review "Pending Tasks" (understand what's next)
4. Check "Success Criteria" (know what "done" looks like)
5. Scan "Notes" for context (costs, related projects, decisions)

Priority Emojis:
- 🔴 CRITICAL: Must do first, blocking other work
- 🟡 HIGH: Important but not blocking
- 🔵 MEDIUM: Nice to have, can wait
- 🟢 LOW: Backlog, future consideration

Task Status:
- [ ] Not started
- [x] Completed (never delete, shows progress!)

Formatting:
- Use clear hierarchy (Phase → Task Group → Task → Sub-task)
- Keep task descriptions actionable ("Create X", not "X needs creating")
- Include enough context for a new AI session to understand

Meta-Philosophy:
- This is a living document
- Honest assessment > optimistic projection
- Show progress (keep completed tasks)
- Context for future you/AI (notes, decisions, questions)

=============================================================================
-->

---

*Template Version: 1.0*  
*Last Modified: December 30, 2025*  
*Source: ./templates/TODO.md.template*


<!-- project-scaffolding template appended -->


