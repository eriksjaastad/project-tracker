---
tags:
  - p/project-tracker
  - type/documentation/readme
  - domain/project-management
status: #status/active
created: 2025-12-22
updated: 2026-01-25
---

# project-tracker

> *Track active projects, tasks, and visualize your ecosystem.*

**Quick Start:** `./pt launch` → http://localhost:8000

---

## What This Is

A **local web dashboard** that tracks all your projects in one place:
- **Dashboard** - Project overview sorted by last modified
- **Kanban** - Task management per project
- **Graph** - D3.js visualization of file relationships across your ecosystem

**Cost:** $0 (100% local, no external services)

---

## Quick Start

```bash
cd $PROJECTS_ROOT/project-tracker
./pt launch
```

This will:
1. Scan all projects in `$PROJECTS_ROOT`
2. Start a web server at http://localhost:8000
3. Open your browser automatically

---

## Features

### Dashboard (`/`)

The main view showing all projects sorted by last modified:
- Project status and completion percentage
- Quick links to Kanban board and Graph for each project
- AI agents tracking
- Cron job indicators
- Service dependencies

### Kanban Board (`/kanban` or `/kanban/{project}`)

Task management with four columns:
- **Backlog** - Ideas and future work
- **To Do** - Ready to start
- **In Progress** - Currently working on
- **Done** - Completed tasks

**Adding tasks:**
- Click "+ Add Task" in any column
- Or use the CLI/database directly (see below)

**Moving tasks:**
- Drag and drop between columns
- Tasks auto-save on move

### Knowledge Graph (`/graph`)

Interactive D3.js force-directed graph showing:
- All files across projects as nodes
- Connections between files (imports, references, links)
- Color-coded by project
- Node size = number of connections (hubs are bigger)

**Controls:**
- Filter by project
- Filter by file type
- Toggle orphan visibility
- Set minimum connection threshold
- Click nodes for details

**Rebuilding graph data:**
```bash
python scripts/discovery/graph_builder.py
```

---

## CLI Commands

```bash
# Dashboard
./pt launch          # Start web dashboard
./pt scan            # Rescan projects directory
./pt list            # List all projects (table view)
./pt status "name"   # Show project details
./pt refresh         # Update all project data

# Metadata management
./pt add-agent "project" "AI name" "Role"
./pt add-cron "project" "schedule" "command" "description"
./pt add-service "project" "service" cost "purpose"
```

---

## Adding Tasks Programmatically

### Via Python

```python
from scripts.db.manager import DatabaseManager

db = DatabaseManager()

# Add a task
db.add_task(
    text="Implement feature X",
    project_id="my-project",
    status="To Do",  # Backlog, To Do, In Progress, Done
    priority="High"  # Critical, High, Medium, Low, or None
)

# List tasks for a project
tasks = db.get_tasks_by_project("my-project")

# Update task status
db.update_task_status(task_id=1, new_status="In Progress")

# Delete a task
db.delete_task(task_id=1)
```

### Via SQLite

```bash
sqlite3 data/tracker.db

# Add a task
INSERT INTO tasks (text, status, project_id, priority, created_at, updated_at)
VALUES ('My task', 'To Do', 'my-project', 'Medium', datetime('now'), datetime('now'));

# View tasks
SELECT * FROM tasks WHERE project_id = 'my-project';
```

---

## Database Schema

Located at `data/tracker.db`:

- **projects** - Project registry with status, path, completion %
- **tasks** - Kanban tasks with status, priority, timestamps
- **task_history** - Status change log for productivity graphs
- **cron_jobs** - Scheduled automation per project
- **service_dependencies** - External services used
- **ai_agents** - AI assistance tracking

---

## Project Structure

```
project-tracker/
├── pt                      # CLI entry point
├── cli.py                  # Typer CLI implementation
├── config.py               # Configuration (paths, settings)
├── data/
│   ├── tracker.db          # SQLite database
│   └── graph.json          # Knowledge graph data
├── dashboard/
│   ├── app.py              # FastAPI backend
│   ├── templates/          # Jinja2 templates (graph.html)
│   ├── static/             # CSS, JS (graph.js, graph.css)
│   └── frontend/           # React app (Kanban)
├── scripts/
│   ├── db/
│   │   ├── schema.py       # Database schema
│   │   └── manager.py      # Database operations
│   └── discovery/
│       └── graph_builder.py # Build knowledge graph
└── README.md               # You are here
```

---

## Requirements

- Python 3.11+
- Node.js (for React frontend build)
- Dependencies: `pip install -r requirements.txt`

---

## Development

**Rebuild React frontend:**
```bash
cd dashboard/frontend
npm install
npm run build
```

**Rebuild graph data:**
```bash
python scripts/discovery/graph_builder.py
```

**Run tests:**
```bash
pytest tests/
```

---

*First AI-initiated project. Created December 22, 2025.*
