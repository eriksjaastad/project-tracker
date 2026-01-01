---
tags:
  - p/project-tracker
  - type/documentation/readme
  - domain/project-management
status: #status/complete
created: 2025-12-22
---

# [[project-tracker]]

> *Track active projects, cron jobs, completion status, and prevent the "spinning plates" chaos.*

**Status:** ✅ 100% Complete - Ready for daily use
**Cost:** $0 (100% local, no external services)  
**Quick Start:** `./pt launch`
**Index:** [[00_Index_project-tracker]]

---

## What This Is

A **local web dashboard** that tracks all your projects in one place.

**One command:**
```bash
./pt launch
```

**Get instant visibility:**
- Which projects are active?
- When did I last work on each?
- What's the completion status?
- Which AI is helping with what?
- Which projects have cron jobs?
- What services does each project use?

**See screenshot in COMPLETION_SUMMARY.md**

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

## 🚀 Quick Start

```bash
cd /Users/eriksjaastad/projects/project-tracker
./pt launch
```

The dashboard will:
1. Scan all your projects (36 found)
2. Start a web server at http://localhost:8000
3. Open your browser automatically
4. Show everything sorted by last modified (newest first)

**That's literally it!**

---

## ✨ Key Features

### 1. Chronological Sorting (Newest First)
Your most recently worked-on projects appear at the top automatically.

### 2. AI Agents Tracking
See which AI is helping with which project and what they're doing.

### 3. TODO.md Viewer
Click any project to view rendered TODO.md with full markdown formatting.

### 4. Progress Bars
Based on checkbox completion in TODO.md files.

### 5. Cron Jobs Display
See which projects have scheduled automation (⏰ indicator).

### 6. External Services
Shows which services each project uses and monthly costs.

### 7. Meta-Tracking
**The dashboard tracks itself!** It shows up in the projects list with its own status and progress.

---

## 📊 What It Looks Like

Currently tracking **36 projects** including:

- **project-tracker** (Active, 6% complete) - Modified today
- **Trading Projects** (63% complete) - Modified Dec 24
- **Cortana personal AI** (Complete, on hold) - Modified Dec 18
- **image-workflow** (49% complete) - Modified Dec 6
- ... and 32 more

All automatically discovered and sorted by last work.

---

## 🎯 Use Cases

### Context Switching
Opening a project after weeks away? Check the dashboard first to see:
- Current status
- What was done
- What's next
- Which AI helped
- What's automated

### Progress Tracking
See completion percentages across all projects at a glance.

### Service Management
Quickly answer "Which project uses Railway?" or "What's using OpenAI?"

### AI Collaboration
Track which AI agents are helping with which projects.

### Automation Visibility
Know which projects have cron jobs running.

---

## 📋 CLI Commands

```bash
# Main commands
./pt launch          # Start dashboard (recommended)
./pt scan            # Scan projects directory
./pt list            # List all projects (table view)
./pt status "name"   # Show project details
./pt refresh         # Update all data

# Manage metadata
./pt add-agent "project" "AI name" "Role"
./pt add-cron "project" "schedule" "command" "description"
./pt add-service "project" "service" cost "purpose"
```

---

## 🎨 The Vision

```
PROJECT STATUS DASHBOARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 ACTIVE PROJECTS (5)
┌─────────────────────────────────────────────────┐
│ image-workflow         [ACTIVE]  ⏰ Daily 6am   │
│ └─ Last work: 2 days ago                        │
│ └─ Cron: process_crop_queue                     │
│ └─ Services: OpenAI, rclone (gbackup)          │
│                                                  │
│ Trading Co-Pilot       [ACTIVE]  ⏰ Daily 6pm   │
│ └─ Last work: 5 hours ago                       │
│ └─ Cron: fetch_signals, run_arena               │
│ └─ Services: Railway, Postgres, Discord         │
│                                                  │
│ Cortana                [ACTIVE]  ⏰ Daily 7am   │
│ └─ Last work: Today                             │
│ └─ Cron: daily_update (launchd)                 │
│ └─ Services: OpenAI                             │
└─────────────────────────────────────────────────┘

🔨 IN DEVELOPMENT (3)
┌─────────────────────────────────────────────────┐
│ project-scaffolding    [DEV]                    │
│ └─ Last work: Today                             │
│ └─ Phase: Pattern extraction complete           │
│                                                  │
│ Hologram               [DEV]                    │
│ └─ Last work: 3 days ago                        │
│ └─ Phase: Phase 3 (Week 11-12) complete         │
│                                                  │
│ agent_os               [PAUSED]                 │
│ └─ Last work: 1 week ago                        │
│ └─ Status: Vision vs reality mismatch           │
└─────────────────────────────────────────────────┘

💤 STALLED / WAITING (2)
┌─────────────────────────────────────────────────┐
│ land                   [STALLED]                │
│ └─ Last work: 2 months ago                      │
│ └─ Blocker: Need email monitoring setup         │
│                                                  │
│ AI usage-billing       [WAITING]                │
│ └─ Last work: Yesterday                         │
│ └─ Status: Waiting for Cursor alerts feature    │
└─────────────────────────────────────────────────┘

⚠️  ALERTS
• image-workflow: No work in 2 days (usually daily)
• Hologram: Stale for 3 days
• land: Stalled for 60+ days
```

---

## Core Features (MVP)

### 1. Project Registry
Simple database (SQLite) with:
- Project name
- Status (active/dev/paused/stalled/complete)
- Last modified (from git or file timestamps)
- Description
- Phase/layer
- Repository path

### 2. Cron Job Tracking
- Which projects have cron jobs?
- What do they run?
- When do they run?
- Last successful execution?

### 3. Service Dependencies
Integration with `EXTERNAL_RESOURCES.md`:
- Which services does each project use?
- Quick reference: "Which project uses Cloudflare?" → 3D Pose Factory

### 4. Status Dashboard
- Web UI (Flask/FastAPI)
- CLI tool
- Show at-a-glance project health

### 5. Context Switching Helper
When opening a project:
```bash
$ pt switch image-workflow

📂 image-workflow
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status: Active
Last work: 2 days ago
Current phase: Production (battle-tested)

⏰ Cron Jobs:
  • Daily 6am: process_crop_queue

📚 Quick links:
  • CLAUDE.md
  • Documents/core/OPERATIONS.md
  • Recent: 12-20-2025-OPUS-4-5-REAL-REVIEW.md

🔑 Services:
  • OpenAI (image-workflow-openai)
  • rclone → Google Drive (gbackup)

⚠️  Reminders:
  • No modifications to data/critical_data/ (append-only)
  • Use move_file_with_all_companions() for moves
  • Run validation: python -m pytest tests/
```

---

## Integration with Project Scaffolding

**Project Scaffolding provides:**
- Patterns for building projects
- Templates for starting projects
- Documentation structures
- Safety systems

**Project Tracker provides:**
- Visibility into ALL projects
- Status tracking
- Cron job registry
- Service dependency mapping

**Relationship:**
```
project-scaffolding (HOW to build)
        ↓
   New Project
        ↓
project-tracker (WHAT is running)
```

**Workflow:**
1. Use scaffolding templates to start new project
2. Register project in tracker
3. As project evolves, tracker shows status
4. When switching projects, tracker provides context

**Shared Data:**
- `EXTERNAL_RESOURCES.md` lives in scaffolding
- Project Tracker reads it for service dependencies
- Both are meta-level tools (Level 2 in Erik's two-level game)

---

## Technical Approach

### Option A: Simple (Ship Fast)
- SQLite database
- Python CLI tool
- Markdown reports
- Read git metadata for "last modified"
- Read EXTERNAL_RESOURCES.md for service deps
- Read crontab / launchd plists for scheduled jobs

### Option B: Full Dashboard (More Useful)
- SQLite database
- FastAPI backend
- Simple HTML/CSS frontend
- Auto-refresh dashboard
- CLI tool for quick lookups
- Integration hooks for Cursor (future)

### Option C: Hybrid (Recommended)
- Start with Option A (CLI + markdown reports)
- Add Option B web dashboard after proving value
- Ship something this week, iterate based on usage

---

## Data Model (Initial Thoughts)

```sql
-- Projects
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL,  -- active/dev/paused/stalled/complete
    description TEXT,
    phase TEXT,
    last_modified TEXT,
    created_at TEXT NOT NULL
);

-- Cron Jobs
CREATE TABLE cron_jobs (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    schedule TEXT NOT NULL,  -- "0 6 * * *" or "daily 6am"
    command TEXT NOT NULL,
    description TEXT,
    last_run TEXT,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Service Dependencies
CREATE TABLE service_dependencies (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    purpose TEXT,
    cost_monthly REAL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Work Log (Optional - track when projects were last touched)
CREATE TABLE work_log (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT,  -- commit, file_edit, cursor_open
    details TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
```

---

## Why This Project Exists (The Origin Story)

**Dec 22, 2025, 3:30 AM:**

Erik describing the spinning plates problem while working on Tiered Sprint Planner. Context switching between multiple Cursor windows, fear of talking in the wrong window for 20 minutes.

**My observation (from journal):**
> "The chaos Erik sees coming in 2026? This is the foundation for handling it."

**The realization:**
- `EXTERNAL_RESOURCES.md` prevents "which project uses Cloudflare?"
- Project Tracker prevents "which projects are active / have cron jobs / are done?"
- Together they organize the meta-level chaos

**Erik's instinct:** Build scaffolding BEFORE scale hits. "You don't put your boots on after you go out in the snow."

---

## Next Steps

**Phase 0: Proof of Concept (This Week)**
- [ ] Create simple SQLite schema
- [ ] Build CLI to add/list projects
- [ ] Read EXTERNAL_RESOURCES.md for service deps
- [ ] Generate markdown status report
- [ ] Test with 3-4 projects

**Phase 1: Cron Integration (Week 2)**
- [ ] Parse crontab for cron jobs
- [ ] Parse launchd plists (macOS)
- [ ] Associate cron jobs with projects
- [ ] Show "what's scheduled" view

**Phase 2: Auto-Discovery (Week 3)**
- [ ] Scan `/Users/eriksjaastad/projects/` for git repos
- [ ] Extract metadata (last commit, README, .cursorrules)
- [ ] Suggest projects to add to tracker
- [ ] Detect stale projects (no commits in 30+ days)

**Phase 3: Dashboard (Week 4+)**
- [ ] FastAPI backend
- [ ] Simple HTML dashboard
- [ ] Auto-refresh
- [ ] Context switching helper

---

## Success Metrics

**After 1 week:**
- [ ] Can list all active projects
- [ ] Can see which have cron jobs
- [ ] Can look up "which project uses X service?"

**After 1 month:**
- [ ] Dashboard is daily-use tool
- [ ] Context switching is less chaotic
- [ ] Haven't talked in wrong Cursor window

**After 3 months:**
- [ ] Pattern extracted to project-scaffolding
- [ ] Other people could use this system
- [ ] Chaos is measurably reduced

---

## Questions to Answer

**For Erik:**
1. Should this track git commits automatically (or manual updates)?
2. Web dashboard or CLI-first?
3. Should it integrate with Cursor somehow (detect which project is open)?
4. What's the "danger threshold" for stale projects? (30 days? 60 days?)

**Technical:**
1. How to detect cron jobs across different systems (cron, launchd, systemd)?
2. Should it track individual files or just project-level?
3. How to handle projects without git repos?
4. Should it parse CLAUDE.md or .cursorrules for metadata?

---

## Files in This Project

```
project-tracker/
├── README.md                    ← You are here
├── AGENTS.md                    ← Source of Truth for AI Agents
├── docs/
│   └── INTEGRATION_WITH_SCAFFOLDING.md  ← How these projects relate
├── patterns/                    ← (Future: patterns from this project)
├── templates/                   ← (Future: if others want project tracking)
└── examples/                    ← (Future: real usage examples)
```

---

*First AI-initiated project. Created by Claude Sonnet 4.5 on December 22, 2025.*

*Erik's idea, my structure. Let's see where this goes.*

---

**Meta note:** This project is being created IN REAL TIME as the first project where the AI (not Erik) created the directory and initial docs. That's a milestone. We're building the tools to build the tools to build the things.

**The two-level game continues.**

