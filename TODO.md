# Project Dashboard - TODO

**Last Updated:** December 30, 2025  
**Project Status:** Active Development - Planning → Implementation  
**Current Phase:** Phase 0 - Foundation & TODO Standardization

---

## 📍 Current State

### What's Working ✅
- ✅ **MVP Complete!** Full implementation working (Dec 30, 2025)
- ✅ **Database:** SQLite with all tables (projects, cron_jobs, services, AI agents)
- ✅ **CLI Tool:** `pt` command with scan, list, launch, etc.
- ✅ **Web Dashboard:** FastAPI serving at localhost:8000
- ✅ **Auto-discovery:** Scans 36 projects successfully
- ✅ **TODO Viewer:** Renders markdown with full formatting
- ✅ **Progress Bars:** Calculates completion % from checkboxes
- ✅ **Sorting:** Newest work first (chronological)
- ✅ **Meta-tracking:** Dashboard tracks itself!

### What's Missing ❌
- **Alerts/Warnings Dashboard** - No top-level warnings table yet
- **Cron Issue Detection** - Not checking for cron job failures
- **Code Review Integration** - No code review file format/display
- **Auto-detection:** Cron jobs still only from TODO.md (not system crontab)

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

---

## ✅ Completed Tasks

### Phase 0: Planning (December 22-30, 2025)
- [x] Create project-tracker/ directory
- [x] Write comprehensive README.md with vision
- [x] Design SQLite data model
- [x] Document integration with project-scaffolding
- [x] Define success metrics
- [x] Research existing TODO formats across projects
- [x] Analyze Cortana, YouTube, actionable-ai-intel TODO patterns

---

## 📋 Pending Tasks

### 🔴 CRITICAL - Phase 0: TODO Standardization

**Status:** ✅ **COMPLETE!**

- [x] Analyze current TODO formats across 4 projects
- [x] Design TODO standard template  
- [x] Create `TODO_FORMAT_STANDARD.md` (650 lines)
- [x] Create `TODO.md.template` (250 lines)
- [x] Add to project-scaffolding
- [x] Document in PROJECT_STRUCTURE_STANDARDS.md

---

### 🟡 HIGH PRIORITY - Phase 0: Dashboard MVP

**Status:** ✅ **COMPLETE!** (Dec 30, 2025)

- [x] Create SQLite Database with all tables
- [x] Build CLI Tool (pt.py) with Typer
- [x] Implement project auto-discovery
- [x] Build web dashboard with FastAPI
- [x] Create TODO.md viewer with markdown rendering
- [x] Add 'launch' command
- [x] Test on 36 real projects
- [x] Fix virtual environment location (venv/ in root)
- [x] Fix missing jinja2 dependency
- [x] Create comprehensive documentation (USAGE.md, COMPLETION_SUMMARY.md, QUICKSTART.md)

---

### 🔵 MEDIUM PRIORITY - Phase 1: Alerts & Warnings

**Status:** ✅ **COMPLETE!** (Dec 30, 2025)

#### Task 3.1: Alerts Dashboard Table ✅
- [x] Create alerts/warnings table at top of dashboard
- [x] Show critical issues before project cards
- [x] Include alert types:
  - [x] ⚠️ Stalled projects (no work in 30+ days)
  - [x] ⚠️ Blocked projects (from TODO.md blockers section)
  - [x] ⚠️ Missing TODO.md (projects with no status)
  - [x] ⚠️ Cron job failures (detects: not installed, invalid schedule, missed runs, execution errors)
- [x] Make alerts clickable (jump to project detail)
- [x] Add severity levels (Critical, Warning, Info)
- [x] Color-code by severity (red, yellow, blue)
- [x] Make alert counts clickable to show/hide categories

**Currently detecting:**
- 🔴 Critical: Blocked projects (reads "Blockers" or "What's Missing" sections)
- ⚠️ Warning: Stalled projects (30+ days inactive)
- ℹ️ Info: Missing TODO.md or unknown status

**Found 42 alerts across 36 projects in testing!**

#### Task 3.2: Cron Issue Detection ✅

**Status:** ✅ **COMPLETE!** (Dec 30, 2025)

- [x] Parse cron job logs (if available)
- [x] Check for failed executions
- [x] Detect jobs that should have run but didn't
- [x] Show "last successful run" vs "expected schedule"
- [x] Alert if job hasn't run in expected window
- [x] Link to project's cron configuration

**Implementation details:**
- Created `cron_monitor.py` with health checking system
- Validates cron schedule expressions using `croniter`
- Checks if jobs are installed in user's crontab
- Scans for log files and parses timestamps/errors
- Detects missed runs based on schedule
- Shows alerts for: invalid schedules, not installed, execution errors, missed runs
- Severity levels: Critical (errors, missed runs), Warning (not installed, invalid)

#### Task 3.3: External Services & Process Catalog

**Status:** 📋 **DOCUMENTED** (Dec 30, 2025)

**Goal:** Catalog all external services, cron jobs, and monitoring across all projects

**Findings from EXTERNAL_RESOURCES.md:**

**Third-Party Services (Active):**
1. **Railway.app** - Trading Projects
   - Purpose: Hosting Python cron jobs + PostgreSQL
   - Cost: ~$5/month
   - Project: `appealing-embrace`, Service: `trading-copilot`
   - Status: ✅ Active
   
2. **Healthchecks.io** - AI Usage Billing Tracker
   - Purpose: Cron job monitoring and uptime checks
   - Cost: Free tier
   - Dashboard: https://healthchecks.io/projects/bea3ac8d-2c7d-4a11-b87c-14f409e13813/checks/
   - Ping URL: https://hc-ping.com/97dd5e5b-c7ac-4e7b-a8b2-d75fd8f13c36
   - Status: ✅ Active - **THIS IS OUR HEALTH MONITOR!**
   
3. **Cloudflare R2** - 3D Pose Factory
   - Purpose: S3-compatible object storage
   - Cost: $3-10/month
   - Bucket: `pose-factory`
   - Status: ✅ Active

**Cron Jobs & Scheduled Tasks:**

1. **Trading Projects (Railway)** - Multiple daily jobs ⚠️ **NEEDS HEALTHCHECKS.IO**
   - 4x daily + weekly/monthly trading signal analysis
   - Cron dispatcher pattern (handles Railway's 1-cron limit)
   - Discord notifications 4x daily
   - PostgreSQL database updates
   - **Location:** Railway cloud (not local)
   - **Status:** ✅ Running, ❌ NOT pinging Healthchecks.io
   - **Action:** Added urgent task to Trading Projects TODO.md

2. **image-workflow** - Daily backups (CURRENTLY DISABLED)
   - **Status:** 💤 Disabled - not actively working in this project
   - Backups only checking for updates or disabled entirely
   - **Action:** Added low-priority note to add Healthchecks.io when re-enabled

3. **project-tracker** - No cron needed! ✅
   - Dashboard scans automatically when launched via `./pt launch`
   - Manual refresh available via "🔄 Refresh" button or `./pt scan` command
   - **No cron job required**

**AI APIs (Per-Project Pattern):**
- OpenAI: Trading, Cortana, image-workflow (~$15/mo combined)
- Anthropic: Trading (~$2/mo)
- Google AI (Gemini): Trading (~$1/mo)
- xAI (Grok): Trading (pay-per-use)

**Notification Services:**
- Discord Webhooks: Trading (free)
- Healthchecks.io: AI Usage Billing Tracker (free)

**Storage & Backup:**
- rclone: 3D Pose Factory (R2), image-workflow (Google Drive)
- Google Drive: image-workflow backups (free personal storage)
- PostgreSQL: Trading (Railway, included in $5/mo)

#### Task 3.4: Code Review System - Create Scaffolding Templates

**Goal:** Add CODE_REVIEW.md template and documentation to project-scaffolding (similar to TODO.md template we created)

**What to add to project-scaffolding:**

1. **`templates/CODE_REVIEW.md.template`** - Standardized template with:
   - Review metadata (date, requester, reviewer)
   - What's being reviewed (files, features, changes)
   - Review checklist (security, performance, maintainability)
   - Findings and feedback
   - Status (Pending, In Progress, Changes Requested, Approved)
   - Resolution/outcome

2. **Update `docs/TODO_FORMAT_STANDARD.md`** - Add code review syntax:
   - How to reference reviews: `- [ ] Feature X **[IN REVIEW]** - See CODE_REVIEW.md #123`
   - When to use code review markers

3. **Update `docs/PROJECT_STRUCTURE_STANDARDS.md`** - Document:
   - When to create CODE_REVIEW.md files
   - Where they live in project structure
   - How to link from TODO.md

4. **Optional: `patterns/code-review-process.md`** - Best practices
   - Review workflow
   - How to request reviews
   - Review checklist guidelines

**Implementation steps:**
- [ ] Study existing code reviews in Trading Projects (`docs/reviews/` directory)
- [ ] Extract best patterns from real reviews
- [ ] Create CODE_REVIEW.md.template
- [ ] Update TODO_FORMAT_STANDARD.md with review syntax
- [ ] Update PROJECT_STRUCTURE_STANDARDS.md
- [ ] Add examples from real code reviews

**Then in project-tracker:**
- [ ] Parse CODE_REVIEW.md files from projects
- [ ] Extract review status (Pending, In Progress, Complete)
- [ ] Show pending reviews in alerts table
- [ ] Link TODO.md sections to CODE_REVIEW.md
- [ ] Display review assignee and date requested

---

### 🔵 MEDIUM PRIORITY - Phase 1: Code Review System (NEW!)

**Goal:** Standardize code review process across projects

#### Task 4.1: Code Review File Format
- [ ] Create CODE_REVIEW.md.template in project-scaffolding
- [ ] Define standard sections:
  - [ ] Review request info (date, requester, purpose)
  - [ ] Files/components under review
  - [ ] Review checklist (security, performance, maintainability)
  - [ ] Reviewer notes and feedback
  - [ ] Status (Pending, In Progress, Changes Requested, Approved)
  - [ ] Resolution (date completed, summary)
- [ ] Add examples from real code reviews
- [ ] Document in PROJECT_STRUCTURE_STANDARDS.md

#### Task 4.2: TODO.md Integration
- [ ] Add "Code Review" indicator to TODO.md format
- [ ] Link TODO tasks to CODE_REVIEW.md file
- [ ] Example: `- [ ] Feature X **[IN REVIEW]** - See CODE_REVIEW.md #123`
- [ ] Update TODO_FORMAT_STANDARD.md with review syntax
- [ ] Update template with code review examples

#### Task 4.3: Dashboard Integration
- [ ] 🔍 Parse CODE_REVIEW.md files from projects
- [ ] Show pending code reviews in alerts table
- [ ] Display review status and assignee
- [ ] Link from alerts to CODE_REVIEW.md viewer

#### Task 4.3: Dashboard Display
- [ ] Show code review count per project
- [ ] Badge/indicator on project cards
- [ ] Separate view for all pending reviews
- [ ] Filter by review status
- [ ] Show reviewer and date info

---

### 🟡 HIGH PRIORITY - Phase 1.5: Enhanced Project Cards

**Goal:** Show services and cron jobs directly on project cards for at-a-glance visibility

#### Task 5.1: Display Services & Cron Jobs on Cards

**Current state:**
- Services and cron jobs are shown on the detail page
- Cards only show: name, status, phase, last modified, AI agents, completion %

**Desired state:**
- Show external services used (OpenAI, Railway, etc.) on each card
- Show cron jobs with status indicators on each card
- At-a-glance view without clicking into details

**What to display on cards:**

1. **External Services Section:**
   - Icon/badge for each service (Railway, OpenAI, Anthropic, etc.)
   - Cost indicator (optional: show monthly cost)
   - Color coding by service type (hosting, AI, storage, etc.)
   - Example: `🔌 Railway ($5) | OpenAI ($15) | Discord (free)`

2. **Cron Jobs Section:**
   - Show cron job status with indicators:
     - ✅ Active and running (installed in crontab)
     - ⏸️ Disabled/paused (defined but not running)
     - 🔄 Smart/incremental (only processes new data)
     - ⚠️ Issues detected (missed runs, errors)
   - Show schedule summary: "4x daily", "Daily 2 AM", etc.
   - Example: `⏰ 4x daily ✅ | Daily backup ⏸️`

3. **Healthchecks.io Integration:**
   - Show if project has health monitoring enabled
   - Link to Healthchecks.io dashboard if configured
   - Example: `💓 Health monitored`

**Implementation tasks:**
- [ ] Update project card layout to include services section
- [ ] Add icons/badges for common services (Railway, OpenAI, etc.)
- [ ] Display cron job count and status on cards
- [ ] Add status indicators (active/disabled/smart/issues)
- [ ] Parse cron job type (smart vs full backup)
- [ ] Add color coding for different service types
- [ ] Ensure cards remain readable (not too cluttered)
- [ ] Make service names clickable to detail page
- [ ] Add cost information (optional, can be collapsed)

**Design considerations:**
- Keep cards scannable - use icons/badges not long text
- Group related info (all services together, all cron jobs together)
- Use color/icons to convey status at a glance
- Maintain responsive layout for different screen sizes

#### Task 5.2: Infrastructure Project Labels

**Goal:** Identify infrastructure projects (tools that support other projects)

**Philosophy:**
- **Most projects DON'T get labels** - Trading Projects, image-workflow, Hypocrisy Now, etc. are just projects
- **Only label infrastructure** - Projects that are foundational tools for other work
- This helps understand what's a "tool" vs. what's a "project using the tools"
- As we scale (imagine 50+ projects by next year), this distinction becomes critical

**Infrastructure Projects (🔧 Infra label):**

These are the **structural projects** that support other work:

1. **project-tracker** (this project!) - Dashboard to track all projects
2. **project-scaffolding** - Templates, patterns, standards for all projects
3. **agent_os** - Operating system for AI agents
4. **agent-skills-library** - Reusable AI skills/capabilities
5. **n8n** - Automation platform connecting services

**Why This Matters:**

Infrastructure projects might have **different rules/standards:**
- **Higher reliability requirements** - Other projects depend on them
- **More documentation needed** - Others need to use them
- **Stricter versioning** - Breaking changes affect multiple projects
- **More careful updates** - Can't break dependent projects
- **Better test coverage** - Failures cascade to other projects
- **Clearer API contracts** - Define how other projects interact

**Examples of different rules:**
- Infrastructure projects MUST have comprehensive README.md
- Infrastructure projects MUST document breaking changes
- Infrastructure projects SHOULD have test coverage
- Infrastructure projects MAY need deprecation policies
- Regular projects can be more experimental/flexible

**Visual Design:**

```
project-scaffolding      [Active] 🔧
Last work: 5 days ago    45% complete
🤖 AI: Claude
🔌 Services: None ($0)
```

```
Trading Projects         [Active]
Last work: 2 hours ago   65% complete
🤖 AI: Claude, GPT-4o, Gemini
🔌 Services: Railway ($5) | OpenAI ($4)
⏰ Cron: 4x daily ✅
```

**Note:** Simple 🔧 icon, no text needed. Clean and minimal.

**Detection Strategy:**

Auto-detect based on project name keywords:
- "tracker", "scaffolding", "agent", "library", "tool", "platform", "framework", "os"

Manual override in TODO.md:
- Add `**Type:** Infrastructure` to header
- Or add note in "What's Working" section

**Implementation tasks:**
- [ ] Add `is_infrastructure` boolean field to database
- [ ] Parse infrastructure flag from TODO.md
- [ ] Auto-detect based on project name keywords
- [ ] Display 🔧 icon on infrastructure project cards
- [ ] Add "Infrastructure Projects" section or filter on dashboard
- [ ] Consider different alert thresholds for infrastructure (higher priority)
- [ ] Document infrastructure project standards in project-scaffolding

**Future Considerations:**
- As we approach 50+ projects, might need additional categories
- But start simple: just "Infrastructure" vs. "Regular Projects"
- Add more labels only when there's a clear organizational need
- Examples might include: News aggregators, Client work, Production systems
- But don't over-engineer - most projects remain unlabeled

**Examples of what cards should show:**

**Trading Projects card:**
```
Trading Projects                    [Active]
Last work: 2 hours ago              65% complete

🤖 AI: Claude, GPT-4o, Gemini
🔌 Services: Railway ($5) | OpenAI ($4) | Discord
⏰ Cron: 4x daily ✅ | Weekly ✅ | ⚠️ No health monitoring
💓 Healthchecks.io: Not configured

[Details] [TODO]
```

**image-workflow card:**
```
image-workflow                      [Paused]
Last work: 45 days ago              82% complete

🤖 AI: GPT-4o
🔌 Services: OpenAI ($5-20) | Google Drive
⏰ Cron: Daily backup ⏸️ (Disabled - project paused)

[Details] [TODO]
```

---

### 🟢 LOW PRIORITY - Phase 1: Polish & Automation

#### Task 3.1: Automation
- [ ] Create `scripts/refresh_data.py` for daily updates
- [ ] Set up launchd job to refresh daily
- [ ] Add email/Discord alerts for stale projects (optional)
- [ ] Auto-detect new projects added to directory

#### Task 3.2: Enhanced Metadata
- [ ] Extract project description from README.md
- [ ] Detect project layer/phase from ROADMAP.md
- [ ] Parse requirements.txt for tech stack
- [ ] Track repository size and file count

#### Task 3.3: Dashboard Enhancements
- [ ] Add search/filter projects
- [ ] Add project grouping (by status, by service, by AI agent)
- [ ] Add timeline view (project activity over time)
- [ ] Add export to JSON/CSV

---

### 🟢 LOW PRIORITY - Phase 2: Advanced Features (Week 3+)

#### Task 4.1: Context Switching Helper
- [ ] Create `pt switch <project>` command
- [ ] Show project summary when switching
- [ ] Display quick links (README, CLAUDE.md, recent docs)
- [ ] Show active cron jobs and services
- [ ] Display reminders/warnings from project docs

#### Task 4.2: Git Integration
- [ ] Track commits per project over time
- [ ] Show "days since last commit" metric
- [ ] Detect branches and show current branch
- [ ] Alert on uncommitted changes

#### Task 4.3: Cost Tracking Integration
- [ ] Link to cost data from EXTERNAL_RESOURCES.md
- [ ] Show monthly spend per project
- [ ] Alert when costs exceed thresholds
- [ ] Project cost history charts

#### Task 4.4: Cursor Integration (Future)
- [ ] Detect which project is open in Cursor
- [ ] Show "currently working on" indicator
- [ ] Auto-update last_modified when Cursor opens project
- [ ] Parse Cursor conversation history for context

---

## 🎯 Success Criteria

### Phase 0 Complete When:
- [ ] TODO standard template exists in project-scaffolding
- [ ] At least 3 projects using standard TODO format
- [ ] Erik approves format as "this is what I want"

### Dashboard MVP Complete When:
- [ ] SQLite database exists with all tables
- [ ] CLI can add, list, and scan projects
- [ ] Web dashboard shows all projects sorted by last work **KEY**
- [ ] Dashboard displays AI agents per project **KEY**
- [ ] Dashboard shows cron jobs indicator **KEY**
- [ ] Dashboard shows services used **KEY**
- [ ] Click project → view rendered TODO.md **KEY**
- [ ] Progress bars show completion % **KEY**
- [ ] Dashboard tracks itself in projects list **META KEY**
- [ ] Successfully tested on 5+ real projects
- [ ] Erik uses dashboard daily for 1 week

### Phase 1 Complete When:
- [ ] Daily automation refreshes data
- [ ] Enhanced metadata extracted from project files
- [ ] Dashboard has search/filter/grouping

### Phase 2 Complete When:
- [ ] Context switching helper is daily-use tool
- [ ] Git integration shows meaningful metrics
- [ ] Cost tracking integrated
- [ ] Pattern extracted to project-scaffolding

---

## 📊 Notes

### TODO Format Analysis Summary

**Common Patterns Across Projects:**
1. **Header section:** Project name, status, phase, last updated
2. **Current State:** What's working, what's missing, blockers
3. **Completed section:** Chronological list with checkboxes
4. **Pending section:** Categorized by priority (🔴 🟡 🔵)
5. **Success Criteria:** Clear "done" definition
6. **Notes section:** Context, costs, time estimates

**What Works Well:**
- ✅ Cortana: Very detailed, excellent layering, clear phases
- ✅ YouTube: Stage-based breakdown, decision points
- ✅ AI Intel: Clear blockers upfront, prerequisites section
- ✅ Scaffolding: Minimal but actionable, sprint-based

**What Varies:**
- 📏 Length: 107 lines (scaffolding) to 660 lines (Cortana)
- 🗂️ Structure: Some use layers, some use phases, some use sprints
- 🎯 Detail level: High detail vs minimal actionable
- 🤖 AI agent tracking: Inconsistent or missing

**Recommendation for Standard:**
- Required: Header, Current State, Completed, Pending, Success Criteria
- Optional: AI Agents, Cron Jobs, Services, Cost/Time, Related Docs
- Keep flexible (projects vary in complexity)
- Include examples from real projects
- Add guidance comments for AI sessions

### Dashboard Metadata Requirements

**Per Project:**
- **Basic:** name, path, status, description, phase
- **Timestamps:** created_at, last_modified (from git or files)
- **AI Agents:** Which AI helping (Claude Code, Cursor, ChatGPT, etc.), role **NEW**
- **Automation:** Cron jobs (schedule, command, active status)
- **Services:** External services used (from EXTERNAL_RESOURCES.md)
- **Progress:** TODO completion % (calculated from TODO.md) **NEW**
- **Links:** README, CLAUDE.md, TODO.md, ROADMAP.md

**Sorting Priority:**
1. **Last modified DESC** (most recently worked on first) **PRIMARY**
2. Status (active > dev > paused > stalled > complete)
3. Name (alphabetical as tiebreaker)

### Technical Stack

**Backend:**
- SQLite (local database, no server needed)
- Python 3.11+ (same as other projects)
- Typer (CLI framework, same as used in Cortana plans)
- Rich (terminal formatting)

**Web Dashboard:**
- FastAPI (lightweight, async, fast)
- Jinja2 templates (HTML)
- Simple CSS (no frameworks, fast load)
- Vanilla JS (minimal, progressive enhancement)

**Dependencies:**
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `typer` - CLI framework
- `rich` - Terminal UI
- `gitpython` - Git integration (optional)
- `python-markdown` - TODO.md rendering **NEW**
- `pygments` - Syntax highlighting **NEW**

### Integration Points

**With project-scaffolding:**
- TODO.md template lives there
- EXTERNAL_RESOURCES.md is read from there
- Templates reference dashboard usage

**With agent-skills-library:**
- Dashboard detects skills library references
- Tracks which skills are in use per project
- Could create "Project Dashboard" skill in future

**With existing projects:**
- Reads TODO.md (if exists)
- Reads CLAUDE.md (if exists)
- Reads .cursorrules (if exists)
- Parses git metadata (if .git exists)
- Checks crontab and launchd plists

### Time Estimates

**Phase 0 (TODO Standardization):**
- Format analysis: 30 minutes ✅ DONE
- Template design: 1-2 hours
- Scaffolding integration: 30 minutes
- Validation: 30 minutes
- **Total:** 2-3 hours

**Dashboard MVP:**
- Database setup: 1 hour
- CLI tool: 3-4 hours
- Auto-discovery: 2-3 hours
- Web dashboard: 4-5 hours
- TODO viewer: 2 hours **NEW**
- Testing: 2-3 hours
- **Total:** 14-18 hours

**Phase 1:**
- Automation: 2 hours
- Enhanced metadata: 2-3 hours
- Dashboard polish: 2-3 hours
- **Total:** 6-8 hours

**Phase 2:**
- Context switcher: 2-3 hours
- Git integration: 2-3 hours
- Cost tracking: 2-3 hours
- **Total:** 6-9 hours

**Grand Total:** 28-38 hours over 2-3 weeks

### Cost Estimates

- **Development cost:** $0 (local only, no external services)
- **Runtime cost:** $0 (SQLite + FastAPI, runs locally)
- **Maintenance cost:** $0 (no cloud services)
- **Total:** $0

### Meta Note

**This dashboard tracks itself!**

When implemented, `project-tracker` will appear in its own dashboard with:
- Status: Active Development
- Last modified: (updated as work happens)
- AI agent: Claude Sonnet 4.5 (Project Manager + Implementation)
- Cron jobs: Auto-scan (daily at 2 AM)
- Services: None (local only)
- TODO progress: X% complete

This is intentional and useful for dogfooding!

### Automation

**Note:** No cron job needed! The dashboard scans projects automatically when launched via `./pt launch`.

To manually refresh data while dashboard is running:
- Click the "🔄 Refresh" button in the web UI, OR
- Run `./pt scan` from command line


### Related Documentation

**This project:**
- `README.md` - Full vision and architecture
- `docs/INTEGRATION_WITH_SCAFFOLDING.md` - How projects relate

**Related projects:**
- `/Users/eriksjaastad/projects/project-scaffolding/` - Templates and patterns
- `/Users/eriksjaastad/projects/agent-skills-library/` - AI skills (dashboard could become skill)
- `/Users/eriksjaastad/projects/EXTERNAL_RESOURCES.md` - Service dependency data source

**Example TODOs analyzed:**
- `/Users/eriksjaastad/projects/Cortana personal AI/TODO.md` (660 lines) - Excellent structure
- `/Users/eriksjaastad/projects/analyze-youtube-videos/TODO.md` (400 lines) - Good staging
- `/Users/eriksjaastad/projects/actionable-ai-intel/TODO.md` (350 lines) - Clear blockers
- `/Users/eriksjaastad/projects/project-scaffolding/TODO.md` (107 lines) - Minimal clarity

---

**Current Focus:** Complete TODO standardization (Phase 0) before building dashboard MVP.

**Next Session:** Create TODO.md template, add to project-scaffolding, validate format.

---

*This TODO uses the format we're standardizing - let's see if it works! 🎯*

