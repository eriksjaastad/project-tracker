# Prompt 2b: Create ARCHITECTURE.md

**Estimated Time:** 10 minutes
**Model:** Any
**File to Create:** `Documents/ARCHITECTURE.md`

---

## Objective

Create an ARCHITECTURE.md document at the Documents/ root that describes the system design of project-tracker.

---

## CONSTRAINTS (READ FIRST)

- DO NOT invent features that don't exist — only document what's there
- DO NOT use hardcoded absolute paths
- DO NOT put in a subdirectory — it goes at Documents/ root
- EXTRACT information from existing AGENTS.md and CLAUDE.md
- FOLLOW the template structure below

---

## Context to Extract From

Read these files to understand the architecture:
- `AGENTS.md` — Tech stack, constraints
- `CLAUDE.md` — Project structure, commands
- `dashboard/app.py` — Web application structure
- `pt.py` — CLI entry point
- `scripts/discovery/` — Scanner modules

---

## Template

```markdown
# Project Tracker Architecture

> **Last Updated:** January 2026
> **Status:** MVP Complete, Enhancement Phases Active

---

## System Overview

[2-3 sentences describing what project-tracker does and its core purpose]

---

## Component Diagram

```
┌─────────────────────────────────────────────────────┐
│                    project-tracker                   │
├─────────────────────────────────────────────────────┤
│  CLI (pt.py)              │  Dashboard (FastAPI)    │
│  - Typer commands         │  - Web UI               │
│  - Rich formatting        │  - Jinja2 templates     │
├─────────────────────────────────────────────────────┤
│              Discovery Engine (scripts/)             │
│  - project_scanner.py     - todo_parser.py          │
│  - git_scanner.py         - telemetry_reader.py     │
│  - cron_health.py         - hygiene_detector.py     │
├─────────────────────────────────────────────────────┤
│              Data Layer (SQLite)                     │
│  - projects.db            - Schema in scripts/db/   │
└─────────────────────────────────────────────────────┘
```

---

## Key Components

### CLI (`pt.py`)
[Brief description of CLI commands and purpose]

### Dashboard (`dashboard/`)
[Brief description of web interface]

### Discovery Engine (`scripts/discovery/`)
[Brief description of scanners and what they detect]

### Data Layer (`scripts/db/`)
[Brief description of database schema]

---

## Data Flow

1. User runs `./pt scan` or dashboard triggers scan
2. Discovery engine scans `~/projects/` for project directories
3. Parsers extract metadata from TODO.md, README.md, 00_Index_*.md
4. Data stored in SQLite database
5. Dashboard/CLI queries database to display status

---

## Key Design Decisions

1. **Local-First:** No cloud dependencies, $0 monthly cost
2. **SQLite:** Single-file database for simplicity
3. **00_Index Requirement:** Every project must have an index file
4. **Trash, Don't Delete:** All file operations use send2trash

---

## External Dependencies

- None (fully local)

---

*Part of project-scaffolding documentation standard.*
```

---

## Acceptance Criteria

- [ ] **Exists:** File is at `Documents/ARCHITECTURE.md`
- [ ] **Accurate:** Describes actual components (CLI, Dashboard, Discovery)
- [ ] **Complete:** Has all template sections filled in
- [ ] **No hardcoded paths:** Uses relative references or ~ notation

---

**Hand back to Floor Manager when complete.**


## Related Documentation

- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

