# Code Review Request: Project Tracker MVP

**Date:** December 30, 2025  
**Reviewer:** TBD  
**GitHub:** https://github.com/eriksjaastad/project-tracker

---

## ⚠️ Reviewer Instructions

**Your role:** You are a grumpy, brutally honest **Senior Principal Engineer** who has seen too many "side projects" become unmaintainable messes.

**Your job:** Find what is **fragile, over-engineered, actually harmful, or solving the wrong problem.**

### Rules:
- ✋ **No politeness, no encouragement, no compliment sandwich**
- 🔍 **Assume "it works for me" is not good enough** - This needs to work 6 months from now when I've forgotten how it works
- 💀 **If you see Theater** (complexity without payoff, automation that costs more than manual), **call it out aggressively**
- 🎯 **Focus on what will break, not what currently works**
- ⛔ **"Everything looks good!" is NOT helpful** - Find the problems or this review is wasted

**Be brutal. I need to know if this is actually useful or just me pretending to be productive.**

---

## 🎯 Project Overview

**Project Tracker** is a local-first dashboard that auto-discovers and tracks all projects in `/Users/eriksjaastad/projects/`.

**The pitch:**
- 📊 Dashboard showing 33+ projects sorted by last modified
- 📝 TODO.md viewer with markdown rendering
- ⚠️ Alerts system (blocked projects, stalled projects, missing TODOs)
- 🔧 Infrastructure project identification (5 foundational projects)
- ⏰ Cron job monitoring with failure detection
- 🔌 Service tracking from `EXTERNAL_RESOURCES.md`
- 📈 Progress bars based on TODO.md checkboxes
- 🔄 Meta-tracking: Dashboard tracks itself!

**But does it actually solve a problem or is this just procrastination disguised as productivity?**

---

## 🤔 The Problem (Allegedly)

**What I claim this solves:**

I have 33+ projects across `/Users/eriksjaastad/projects/`. Each has:
- A `TODO.md` file tracking status, phase, completion %
- AI agents working on them (documented in TODO.md)
- External services (OpenAI, Railway, etc.) costing money
- Cron jobs that might be failing silently
- Different priority levels and blockers

**The pain points:**
1. **Lost track of what needs attention** - Some projects stalled 60+ days
2. **Don't know what's costing money** - Services spread across 33 projects
3. **Cron jobs failing silently** - No monitoring, no alerts
4. **Opening 33 TODO.md files manually sucks** - Need overview

**The solution (maybe?):**
Build a dashboard that scans all projects, parses TODO.md files, tracks services, monitors cron jobs, and shows what needs attention.

**But is this actually the right solution?**

**Alternative approaches I DIDN'T do:**
- Just use a spreadsheet (manual, but simple)
- Just `grep -r "status:" */TODO.md` (ugly, but fast)
- Just set calendar reminders to check projects (low-tech, works)
- Just focus on fewer projects (eliminate the problem)

**Reviewer: Challenge this assumption. Is this solving the right problem or just building for the sake of building?**

---

## 🔍 What to Review (Be Skeptical)

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

## ❌ Critical Flaws Checklist

**Don't just check boxes. Find the problems.**

Security & Data:
- [ ] Found sensitive data or secrets in code? (paths, API keys, etc.)
- [ ] `.gitignore` has holes? (what's missing?)
- [ ] Local file scanning could be exploited? (arbitrary file access?)

Code Quality:
- [ ] Anti-patterns found? (list them with file:line)
- [ ] Error handling is broken? (silent failures, no logging)
- [ ] Functions too long/complex? (quote examples)
- [ ] Code duplication everywhere? (DRY violations)

Architecture:
- [ ] Over-engineered for the problem? (too many abstraction layers?)
- [ ] Database design has issues? (missing indexes, wrong schema)
- [ ] Performance bottlenecks obvious? (N+1 queries, no caching)
- [ ] Will break when scaled? (100+ projects, large files)

Maintainability:
- [ ] Can't figure out how it works? (poor documentation)
- [ ] Would rage-quit trying to modify it? (too complex)
- [ ] Technical debt blocks future work? (what needs refactor)

**If you checked "no problems found" for all of these, you didn't look hard enough.**

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

## 💀 Find 10 Failure Modes

**This is the most important part of the review.**

List 10 specific ways this system will **fail me when I need it most**:
- When TODO.md format changes?
- When EXTERNAL_RESOURCES.md structure changes?
- When I have 100+ projects?
- When a cron job hangs the scanner?
- When SQLite file gets corrupted?
- When I upgrade Python/dependencies?
- When file paths have special characters?
- When dashboard is running and I run `pt scan`?
- When git history is missing/corrupted?
- When...?

**Be specific. Quote file paths and line numbers where things will break.**

---

## 🎭 Theater vs. Tool Test

**Which parts of this system will actually get used vs. created once and forgotten?**

Rate each feature:
- **Will use daily:** Core value, can't live without
- **Will use occasionally:** Nice to have
- **Will never use:** Delete it

Features to rate:
- [ ] Dashboard view (vs just opening TODO.md files manually)
- [ ] TODO.md viewer (vs opening in editor)
- [ ] Alerts system (vs just scrolling the list)
- [ ] Infrastructure labels (does this actually help?)
- [ ] Cron monitoring (vs just checking manually)
- [ ] Service categorization (do I care about emoji icons?)
- [ ] Progress bars (do I actually look at these?)

**Be honest: What's actually useful vs. what's just cool to build?**

---

## 🚨 Anti-Patterns & Red Flags

**Where is this code fighting Python instead of working with it?**

Look for:
- [ ] Unnecessary abstractions (DatabaseManager wrapping SQLite?)
- [ ] Over-engineering (5 separate parser modules?)
- [ ] Brittle parsing (regex on markdown files?)
- [ ] Silent failures (`except Exception: pass` everywhere)
- [ ] Hard-coded paths/assumptions (will break on other machines?)
- [ ] N+1 query problems (loading services in a loop?)
- [ ] No tests (how do I know it works?)

**Quote specific examples with file:line numbers.**

---

## 🎯 Specific Questions for Reviewer

1. **Architecture:** Is the module separation appropriate or over-engineered? (5 parser modules seems like a lot)
2. **Database:** Should we store service categories in DB vs runtime categorization? (Current approach is fragile)
3. **Parsing:** Is regex-based EXTERNAL_RESOURCES.md parsing acceptable or is this a time bomb? (Will break on format changes)
4. **Error handling:** Should we fail loudly or silently for missing/malformed files? (Currently silent failures everywhere)
5. **Testing:** What's the minimum viable test coverage for this project? (Currently zero tests)
6. **Performance:** Are there obvious bottlenecks we should fix now? (N+1 queries, no caching)
7. **Security:** Any security concerns with local file reading/scanning? (Running arbitrary commands from TODO.md?)
8. **Complexity:** Is this solving a $10 problem with a $1000 solution?

---

## 📊 Project Stats

- **Lines of Code:** ~8,879 (38 files)
- **Languages:** Python, HTML/CSS, JavaScript
- **Dependencies:** 7 Python packages (FastAPI, Typer, Rich, Markdown, etc.)
- **Database:** SQLite (local)
- **Projects Tracked:** 33 active projects
- **Development Time:** 1 session (~4-6 hours)

---

## 💣 Your Verdict

**Choose one (and defend it):**

- ✅ **Production-Grade Tooling** - Robust, will actually save time
- ⚠️ **Needs Major Refactor** - Good ideas, bad execution  
- 🚫 **Premature Optimization** - Solving problems I don't have yet
- 🗑️ **Delete & Simplify** - More complexity than value

**The 3-Month Test:**
If I come back to this in 3 months, will I:
- Use it immediately? (Good sign)
- Need to re-learn it? (Neutral)
- Curse past-me and rewrite it? (Bad sign)

**The Core Value Question:**
What's the **single most useful** part of this system? What would I miss most if it disappeared?

**Delete Candidates:**
What should I **delete right now** because it's noise without value?

---

## 🎯 Deliverables

**Required from reviewer:**

1. **Verdict** (pick one of the 4 options above)
2. **10 Failure Modes** (specific, with file:line citations)
3. **Theater vs Tool ratings** (which features are actually useful?)
4. **5 Anti-Patterns** found in the code (with examples)
5. **Top 3 things to fix** before adding more features
6. **Top 3 things to delete** that add complexity without value

**Format:** 
- Save as `CODE_REVIEW.md` in the project root
- Markdown format, brutal honesty, specific examples
- Include date, reviewer name/role, and verdict at top

**Why CODE_REVIEW.md?**
This is a **meta-test** of the project tracker itself! Once you submit the review:
1. We'll add CODE_REVIEW.md detection to the scanner
2. The dashboard should show "Code review pending" in alerts
3. This validates the code review integration works
4. Classic dogfooding - using the tool to track its own review

**Estimated review time:** 30-45 minutes

**Priority:** HIGH (Need to know if this is worth continuing before building more)

---

## 🔥 Final Note

**I don't want a nice review. I want a USEFUL review.**

- If everything looks good, you didn't look hard enough
- If you're being polite, you're wasting my time
- If you can't find problems, this review failed

**Challenge me. Prove I'm wrong. Find the landmines before I step on them.**

*This code review follows the pattern from project-scaffolding/docs/CODE_REVIEW_PROMPT.md*

