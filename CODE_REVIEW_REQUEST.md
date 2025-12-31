# Code Review Request: Project Tracker MVP

**Date:** December 30, 2025  
**Reviewer:** TBD  
**GitHub:** https://github.com/eriksjaastad/project-tracker

---

## 🎯 Project Overview

**Project Tracker** is a local-first dashboard that auto-discovers and tracks all projects in `/Users/eriksjaastad/projects/`. It provides:

- 📊 Dashboard showing 33+ projects sorted by last modified
- 📝 TODO.md viewer with markdown rendering
- ⚠️ Alerts system (blocked projects, stalled projects, missing TODOs)
- 🔧 Infrastructure project identification (5 foundational projects)
- ⏰ Cron job monitoring with failure detection
- 🔌 Service tracking from `EXTERNAL_RESOURCES.md`
- 📈 Progress bars based on TODO.md checkboxes
- 🔄 Meta-tracking: Dashboard tracks itself!

---

## 🔍 What to Review

### 1. **Architecture & Structure**

**Question:** Is the project structure logical and maintainable?

**Current structure:**
```
project-tracker/
├── dashboard/           # FastAPI web app
│   ├── app.py          # Main routes + service categorization
│   ├── static/         # CSS + JS
│   └── templates/      # Jinja2 HTML
├── scripts/
│   ├── db/             # SQLite database layer
│   │   ├── schema.py   # Table definitions
│   │   └── manager.py  # CRUD operations
│   ├── discovery/      # Auto-discovery & parsing
│   │   ├── project_scanner.py         # Finds projects
│   │   ├── todo_parser.py             # Extracts from TODO.md
│   │   ├── external_resources_parser.py # Reads EXTERNAL_RESOURCES.md
│   │   ├── alert_detector.py          # Detects issues
│   │   ├── cron_monitor.py            # Monitors cron jobs
│   │   └── git_metadata.py            # Git timestamps
│   └── pt.py           # CLI tool (Typer)
├── data/               # SQLite database (gitignored)
├── venv/               # Virtual environment (gitignored)
└── pt                  # Shell launcher script
```

**Concerns:**
- Is this over-engineered for an MVP?
- Should discovery modules be refactored into a single class?
- Is the separation of concerns clear?

---

### 2. **Security & Data Protection**

**Question:** Are we properly protecting sensitive data?

**Current `.gitignore`:**
- ✅ `venv/` - virtual environment
- ✅ `data/` - SQLite database
- ✅ `.env` - API keys/secrets
- ✅ `*.log` - logs
- ✅ IDE files, Python cache

**Concerns:**
- Is anything missing from `.gitignore`?
- Could any committed files contain sensitive paths or data?
- Should we have a `.env.example` file?

---

### 3. **Code Quality & Patterns**

**Question:** Is the code maintainable and following Python best practices?

**Review areas:**
- Type hints usage (some functions have them, some don't)
- Error handling (try/except blocks appropriate?)
- Function length (any functions too long?)
- Code duplication (DRY principle followed?)
- Naming conventions (clear and consistent?)

**Known issues:**
- `app.py` has a 60-line `categorize_services()` function - should this be refactored?
- Error handling is basic (`except Exception: pass`) in several places
- Some functions lack docstrings

---

### 4. **Database Design**

**Question:** Is the SQLite schema appropriate for this use case?

**Current tables:**
```sql
projects         (id, name, path, status, phase, completion_pct, is_infrastructure)
cron_jobs        (id, project_id, schedule, command, description)
service_dependencies (id, project_id, service_name, purpose, cost_monthly)
ai_agents        (id, project_id, agent_name, role)
work_log         (id, project_id, timestamp, event_type, details)
```

**Concerns:**
- Missing indexes? (some exist, are more needed?)
- Should we have foreign key constraints ON DELETE CASCADE? (already have them)
- Is `work_log` table actually used? (currently just logging scan events)
- Should services have a `category` field in DB rather than runtime categorization?

---

### 5. **External Dependencies**

**Question:** Are we reading external data correctly and safely?

**Data sources:**
1. **TODO.md files** - Parsed for status, phase, AI agents, cron jobs, completion %
2. **EXTERNAL_RESOURCES.md** - Parsed for service dependencies (in project-scaffolding)
3. **Git history** - Used for last modified timestamps
4. **README.md** - Fallback for project descriptions

**Concerns:**
- Parsing EXTERNAL_RESOURCES.md is fragile (regex-based)
- What happens if TODO.md format changes?
- Should we validate TODO.md format before parsing?
- Error handling for missing/malformed files?

---

### 6. **Performance**

**Question:** Will this scale as projects grow?

**Current stats:**
- 33 projects tracked
- ~40 database queries per dashboard load (N+1 problem?)
- Full scan takes ~2-3 seconds

**Concerns:**
- Should we cache parsed TODO.md data?
- Are we doing too many individual database queries?
- Should we use connection pooling?
- Will this be slow with 100+ projects?

---

### 7. **Cron Monitoring System**

**Question:** Is the cron monitoring implementation robust?

**Features:**
- ✅ Validates cron schedules using `croniter`
- ✅ Checks if jobs are installed in user's crontab
- ✅ Looks for log files and parses timestamps
- ✅ Detects missed runs based on schedule
- ✅ Categorizes alerts (critical, warning, info)

**Concerns:**
- Log file parsing is basic (regex for timestamps)
- Assumes log files are in standard locations
- No actual integration with Healthchecks.io yet (just detection)
- Should we ping Healthchecks.io directly from the scanner?

---

### 8. **Service Categorization**

**Question:** Is the service categorization approach maintainable?

**Current implementation:**
- Runtime categorization in `app.py` using keyword matching
- Categories: Backend, Hosting, AI, Storage, Database, Notifications, Monitoring
- Hard-coded mapping of service names to categories

**Example:**
```python
service_types = {
    "railway": "backend",
    "openai": "ai",
    "discord": "notifications",
    # ... 30+ more mappings
}
```

**Concerns:**
- Should this be data-driven (config file or database)?
- What happens with unknown services?
- How do we add new categories or services?
- Should categories be stored in the database?

---

### 9. **Testing**

**Question:** What testing do we need before this goes into production?

**Current testing:** None (manual testing only)

**Should we add:**
- [ ] Unit tests for parsers (TODO.md, EXTERNAL_RESOURCES.md)?
- [ ] Integration tests for database operations?
- [ ] End-to-end tests for dashboard?
- [ ] Test fixtures with sample TODO.md files?
- [ ] CI/CD pipeline?

---

### 10. **Documentation**

**Question:** Is the documentation sufficient?

**Current docs:**
- ✅ `README.md` - Project overview
- ✅ `USAGE.md` - User guide (comprehensive)
- ✅ `QUICKSTART.md` - 5-minute setup
- ✅ `TODO.md` - Development roadmap
- ✅ `IMPLEMENTATION_HANDOFF.md` - Original spec
- ✅ Inline docstrings (most functions)

**Concerns:**
- Should we have API documentation?
- Developer setup guide needed?
- Architecture diagram would help?

---

### 11. **Error Handling & Logging**

**Question:** Are errors handled gracefully?

**Current approach:**
- Many functions use `try/except Exception: pass` (silent failures)
- No structured logging (no `logging` module used)
- Dashboard shows generic "Error" messages
- CLI uses Rich console for colored output

**Concerns:**
- Silent failures could hide bugs
- No error reporting/alerting
- Should we use Python `logging` module?
- Should errors be logged to a file?

---

### 12. **Infrastructure Labels**

**Question:** Is the infrastructure project detection working well?

**Current detection:**
```python
infra_names = [
    "project-tracker",
    "project-scaffolding",
    "agent_os",
    "agent-skills-library",
    "n8n"
]
```

**Detected:** 5/33 projects (15%)

**Concerns:**
- Hard-coded list feels brittle
- Should this be configurable?
- What about future infrastructure projects?
- Alternative: Parse from TODO.md marker?

---

## 🎨 Bonus: UI/UX Feedback

**Current design:**
- Dark theme with card layout
- Color-coded status badges
- Emoji icons for services (🚀 ⚙️ 🤖 🔔 💓)
- Clickable alert counts to show/hide
- Progress bars for TODO completion

**Questions:**
- Is the UI too cluttered?
- Are the emoji icons helpful or distracting?
- Should we have different views (grid vs list)?
- Mobile responsive? (not tested)

---

## ✅ Checklist for Reviewer

Please confirm:
- [ ] No sensitive data or secrets in committed code
- [ ] `.gitignore` is comprehensive
- [ ] Code follows Python best practices (PEP 8)
- [ ] Error handling is appropriate
- [ ] Database design is sound
- [ ] No obvious security vulnerabilities
- [ ] Documentation is sufficient for handoff
- [ ] Architecture is maintainable
- [ ] Performance is acceptable for MVP
- [ ] No major technical debt that blocks future development

---

## 🚨 Known Issues / Technical Debt

**We're aware of:**
1. **No tests** - Need to add pytest before adding more features
2. **Silent failures** - Many `except: pass` blocks hide errors
3. **Fragile parsing** - EXTERNAL_RESOURCES.md parser is regex-based and brittle
4. **Hard-coded categories** - Service categorization should be data-driven
5. **N+1 queries** - Dashboard makes many individual database queries
6. **No logging** - Should add structured logging before deploying

**These are acceptable for MVP but should be addressed before:**
- [ ] Adding more features
- [ ] Deploying beyond local use
- [ ] Open-sourcing the project

---

## 🎯 Specific Questions for Reviewer

1. **Architecture:** Is the module separation appropriate or over-engineered?
2. **Database:** Should we store service categories in DB vs runtime categorization?
3. **Parsing:** Is regex-based EXTERNAL_RESOURCES.md parsing acceptable or should we use a structured format (JSON/YAML)?
4. **Error handling:** Should we fail loudly or silently for missing/malformed files?
5. **Testing:** What's the minimum viable test coverage for this project?
6. **Performance:** Are there obvious bottlenecks we should fix now?
7. **Security:** Any security concerns with local file reading/scanning?

---

## 📊 Project Stats

- **Lines of Code:** ~8,879 (38 files)
- **Languages:** Python, HTML/CSS, JavaScript
- **Dependencies:** 7 Python packages (FastAPI, Typer, Rich, Markdown, etc.)
- **Database:** SQLite (local)
- **Projects Tracked:** 33 active projects
- **Development Time:** 1 session (~4-6 hours)

---

## 🙏 Thank You!

This is our first major project using the new project-scaffolding patterns. Your feedback will help us:
- Establish code quality standards
- Identify blind spots
- Build better systems going forward
- Create reusable patterns for future projects

**Estimated review time:** 30-45 minutes

**Priority:** Medium (MVP working, but want to validate approach before building more)

**Questions?** Comment on this file or open GitHub issues.

---

*This code review request follows the pattern we're establishing in project-scaffolding.*

