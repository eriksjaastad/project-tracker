# Project Tracker Architecture

> **Last Updated:** January 2026
> **Status:** MVP Complete, Enhancement Phases Active

---

## System Overview

Project Tracker is a centralized monitoring and reporting system designed to track the lifecycle, health, and resource usage of all projects within the `$PROJECTS_ROOT` workspace. It provides both a command-line interface and a web dashboard to visualize project status, compliance with documentation standards, and various health metrics.

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
A Typer-based command-line interface that allows users to initialize the database, scan projects, list project details, and launch the web dashboard. See [[OPERATIONS]] for command details.

### Dashboard (`dashboard/`)
A FastAPI web application that provides a visual overview of all projects. It includes a main dashboard with project cards, detailed project views, and a viewer for rendered `TODO.md` files.

### Discovery Engine (`scripts/discovery/`)
The core intelligence of the system. It consists of multiple specialized scanners:
- `project_scanner.py`: Discovers project directories and basic metadata. See [[PROJECT_STRUCTURE_STANDARDS]].
- `todo_parser.py`: Extracts task status from `TODO.md` files. See [[TODO_FORMAT_STANDARD]].
- `git_metadata.py`: Collects recent git activity and branch information.
- `telemetry_reader.py`: (In progress) Reads AI Router telemetry for usage statistics.
- `hygiene_detector.py`: Checks for project standard compliance (e.g., `00_Index_*.md` files).

### Data Layer (`scripts/db/`)
Uses SQLite for persistent storage of project metadata, cron job information, AI agent tracking, and service usage. The `DatabaseManager` in `manager.py` handles all database interactions using parameterized queries.

---

## Data Flow

1. User runs `./pt scan` or dashboard triggers a scan.
2. Discovery engine scans the `projects/` root for project directories.
3. Parsers extract metadata from `TODO.md`, `README.md`, and `00_Index_*.md` files.
4. Extracted data is stored or updated in the SQLite database.
5. Dashboard or CLI queries the database to display current project statuses and metrics.

---

## Key Design Decisions

1. **Local-First:** No cloud dependencies, ensuring complete data privacy and $0 monthly cost.
2. **SQLite:** A single-file database chosen for simplicity, portability, and zero-configuration setup.
3. **00_Index Requirement:** Every project must have a `00_Index_*.md` file to be considered properly indexed.
4. **Trash, Don't Delete:** All destructive file operations are routed through `send2trash` or moved to a `_trash/` directory.

---

## External Dependencies

- None (fully local system).

---

*See also: [[SCAFFOLDING_TRANSFER_GUIDE]], [[PROJECT_STRUCTURE_STANDARDS]], and [[DOPPLER_SECRETS_MANAGEMENT]].*


## Related Documentation

- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling

- [[adult_business_compliance]] - adult industry


- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling

- [[project-tracker/README]] - Project Tracker


- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling

- [[adult_business_compliance]] - adult industry


- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling

