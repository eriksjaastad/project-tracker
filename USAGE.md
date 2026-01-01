---
tags:
  - p/project-tracker
  - type/documentation/guide
  - domain/project-management
status: #status/active
created: 2025-12-30
---

# [[project-tracker]] - Usage Guide

> **Quick Start:** `./pt launch` to open the dashboard
**Index:** [[00_Index_project-tracker]]

---

## 🚀 Getting Started

### First Time Setup

1. **No installation needed!** Everything is already set up in this directory.

2. **Launch the dashboard:**
   ```bash
   cd /Users/eriksjaastad/projects/project-tracker
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
- **Progress bars:** Based on TODO.md completion %
- **AI agents:** Which AI is helping with what
- **Cron jobs:** ⏰ indicator if scheduled automation exists
- **Services:** External services used (from EXTERNAL_RESOURCES.md)

### Viewing TODOs

Click **"View TODO"** on any project card to see the rendered TODO.md file with full markdown formatting.

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
```

### Managing AI Agents

```bash
# Add an AI agent to a project
./pt add-agent "project-name" "Claude Sonnet 4.5" "Implementation"

# Examples:
./pt add-agent "image-workflow" "Claude Opus 4" "Architecture review"
./pt add-agent "Trading Projects" "Cursor" "Code refactoring"
```

### Managing Cron Jobs

```bash
# Add a cron job to a project
./pt add-cron "project-name" "0 14 * * *" "python scripts/daily.py" "Daily processing"

# Examples:
./pt add-cron "image-workflow" "10 2 * * *" "python scripts/backup/daily_backup.py" "Daily backup"
./pt add-cron "Trading Projects" "0 6,12,18 * * *" "python scripts/fetch_signals.py" "Fetch trading signals"
```

### Managing Services

```bash
# Add a service dependency to a project
./pt add-service "project-name" "Service Name" 5.00 "Purpose description"

# Examples:
./pt add-service "Trading Projects" "Railway" 5.00 "Hosting + Postgres"
./pt add-service "image-workflow" "OpenAI" 15.00 "AI processing"
```

---

## 🔄 How Data is Collected

### Auto-Discovery

The scanner looks for projects in `/Users/eriksjaastad/projects/` and checks for:

1. **Git repositories** (`.git` directory exists)
2. **README.md** files
3. **TODO.md** files
4. **Code files** (`.py`, `.js`, `.ts`, etc.)

### Metadata Extraction

For each project found:

**From Git:**
- Last commit date (primary timestamp)
- Falls back to file modification time if git unavailable

**From TODO.md:**
- Project status (Active, Development, Paused, Stalled, Complete)
- Current phase
- AI agents in use
- Cron jobs defined
- Completion percentage (based on `- [x]` checkboxes)

**From README.md:**
- First paragraph as description (if TODO doesn't provide one)

**From EXTERNAL_RESOURCES.md (in project-scaffolding):**
- External services used
- Monthly costs

---

## 📝 TODO.md Format

For best results, structure your TODO.md files like this:

```markdown
# Project Name - TODO

**Last Updated:** December 30, 2025  
**Project Status:** Active Development  
**Current Phase:** Phase 1 - Implementation

## 📍 Current State

### What's Working ✅
- Feature A is operational
- Feature B is tested

### What's Missing ❌
- Feature C not started
- Feature D incomplete

## 📋 Pending Tasks

### 🔴 CRITICAL
- [ ] High priority task
- [x] Completed critical task

### 🟡 HIGH PRIORITY
- [ ] Important task

## 📊 Notes

### AI Agents in Use
- **Claude Sonnet 4.5:** Project management and architecture
- **Cursor:** Code implementation

### Cron Jobs / Automation
- **Schedule:** `0 14 * * *` (daily 2 PM)
- **Command:** `python scripts/daily_update.py`
- **Purpose:** Process daily data
```

The dashboard will automatically extract:
- Status → "Active Development"
- Phase → "Phase 1 - Implementation"
- AI Agents → Claude Sonnet 4.5, Cursor
- Cron Jobs → Daily 2 PM schedule
- Completion % → (completed tasks / total tasks)

---

## 🎯 Tips & Best Practices

### 1. Keep TODO.md Updated

The dashboard reads TODO.md to get project status, AI agents, and completion %. Update these regularly for accurate tracking.

### 2. Use Consistent Status Values

Supported statuses:
- `Active` → Active production use
- `Development` → Actively building features
- `Paused` → Temporarily on hold
- `Stalled` → Blocked or abandoned
- `Complete` → Finished

### 3. Document AI Agents

When an AI starts helping with a project, add it to TODO.md:

```markdown
### AI Agents in Use
- **AI Name:** Role description
```

This helps track which projects have AI assistance and what they're doing.

### 4. Track Cron Jobs in TODO

If your project has scheduled automation, document it:

```markdown
### Cron Jobs / Automation
- **Schedule:** Cron expression or human-readable
- **Command:** What runs
- **Purpose:** Why it exists
```

### 5. Refresh Data Regularly

The dashboard doesn't monitor file changes in real-time. After updating TODO.md files:

- Click **🔄 Refresh** in the web dashboard, OR
- Run `./pt refresh` from command line

The dashboard auto-refreshes every 5 minutes, but manual refresh is instant.

---

## 🔍 Sorting & Organization

### Primary Sort: Last Modified (DESC)

Projects are sorted by **when you last worked on them** (newest first).

This is determined by:
1. Last git commit date (if git repo exists)
2. Most recent file modification time (fallback)

This means the projects you're actively working on appear at the top automatically!

### Secondary Sort: Status

Within the same "last modified" timeframe, projects are ordered:
1. Active
2. Development
3. Paused
4. Stalled
5. Complete

### Example Order

```
1. project-tracker    (modified today, active)
2. image-workflow     (modified today, development)
3. Trading Projects   (modified yesterday, active)
4. Cortana           (modified 2 weeks ago, complete)
```

---

## 🛠️ Troubleshooting

### Dashboard won't start

```bash
# Check if port 8000 is already in use
lsof -i :8000

# Kill existing process if needed
kill -9 <PID>

# Try launching again
./pt launch
```

### Projects not showing up

```bash
# Re-scan projects directory
./pt scan

# Check database
./pt list
```

### TODO.md not parsing correctly

Make sure your TODO.md has:
- `**Project Status:**` line with status keyword
- `**Current Phase:**` line with phase description
- Proper checkbox format: `- [ ]` or `- [x]`

### Completion % is wrong

The completion % is calculated from:
- Total checkboxes: `- [ ]` + `- [x]`
- Completed: `- [x]`
- Formula: `(completed / total) * 100`

If it seems wrong, check:
- Are all your tasks marked with `- [ ]` or `- [x]`?
- Remove any example/template checkboxes that aren't real tasks

---

## 🔐 Security & Privacy

### All Local, No Cloud

- **Database:** SQLite file in `data/tracker.db`
- **Web Server:** FastAPI running on localhost only
- **No external requests:** All data stays on your machine
- **No API keys needed:** Zero external services
- **Cost:** $0

### Data Stored

The database contains:
- Project names and paths
- Last modified timestamps
- Status, phase, description
- AI agents, cron jobs, services (as documented in TODO.md)
- Work log (scan events)

All data is read from your local files and stored locally.

---

## 📈 Advanced Usage

### Integration with Scripts

The CLI can be used in scripts:

```bash
#!/bin/bash
# Example: Daily project status report

./pt scan > /dev/null 2>&1
./pt list > /tmp/projects.txt
mail -s "Daily Project Status" you@example.com < /tmp/projects.txt
```

### Custom Queries

Access the database directly for custom queries:

```bash
sqlite3 data/tracker.db "SELECT name, status, completion_pct FROM projects WHERE status='active' ORDER BY last_modified DESC;"
```

### Export Data

```bash
# Export all projects as JSON
curl http://localhost:8000/api/projects > projects.json

# Export stats
curl http://localhost:8000/api/stats > stats.json
```

---

## 🤝 Meta-Tracking

**The dashboard tracks itself!**

When you run `./pt scan`, it will discover `project-tracker` and include it in the dashboard.

This means:
- You can see this project's TODO progress
- It shows AI agents working on the dashboard
- It demonstrates dogfooding in action

This is intentional and useful for testing/validation!

---

## 📞 Support

If something isn't working:

1. Check this guide first
2. Look at TODO.md in this project (we track our own issues there)
3. Check the implementation handoff doc: `IMPLEMENTATION_HANDOFF.md`
4. Review the main README: `README.md`

---

## 🎉 Quick Reference

```bash
# Most common commands
./pt launch          # Start dashboard (recommended)
./pt scan            # Scan for projects
./pt list            # List all projects
./pt refresh         # Update all data
./pt status "name"   # Project details
```

**Dashboard URL:** http://localhost:8000

**Database location:** `data/tracker.db`

**Configuration:** None needed (convention over configuration)

---

*Built with ❤️ for Erik's "spinning plates" problem*

