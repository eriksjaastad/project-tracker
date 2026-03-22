---
tags:
  - map/project
  - p/project-tracker
  - type/dashboard
  - domain/project-management
  - tech/python/typer
  - tech/python/fastapi
scaffolding_version: 1.0.0
transferred_date: 2026-01-12
status: #status/complete
created: 2025-12-31
---

# Project Tracker: Centralized Project Health Monitoring

The Project Tracker is a comprehensive system designed for monitoring and reporting the status of projects throughout their lifecycle. It provides centralized visibility into project health, progress, and resource allocation, enabling proactive identification of active, stalled, or at-risk projects. This system includes Python scripts for automated status collection, Git activity monitoring, and health metric calculation, along with HTML/CSS dashboards for visualization and documentation for understanding and operating the system.

## Overview

This document serves as the index for the Project Tracker, providing a high-level overview of its components, status, recent activity, and related documentation.

## Key Components

### 1. Tracking Scripts (Python)

*   **Purpose:** Automate data collection, analysis, and reporting related to project status.
*   **Location:**  (Specify directory or link to a scripts overview document)
*   **Key Features:**
    *   Status collection automation
    *   Git activity monitoring
    *   Health metric calculation
    *   Report generation
    *   Alert triggers
    *   Agent Dispatcher
    *   Backup Auditing
    *   D3 Knowledge Graph Builder

### 2. Dashboards (HTML/CSS)

*   **Purpose:** Visualize project health, progress, and resource allocation.
*   **Location:** `dashboard/`
*   **Templates:** (4 HTML templates)
    *   Project status overview
    *   Activity heatmaps
    *   Agent Dispatcher UI
    *   Backup Status Monitor
    *   Interactive D3 Knowledge Graph (/graph)

### 3. Documentation (Markdown)

*   **Purpose:** Provide comprehensive documentation for setup, usage, architecture, and maintenance.
*   **Location:** (Specify directory or link to a documentation overview document)
*   **Key Documents:** (25+ files)
    *   `AGENTS.md` - Source of Truth for AI Agents
    *   `CLAUDE.md` - AI Collaboration Instructions
    *   Setup guides
    *   Metric definitions
    *   Architecture & Operations docs
    *   Planning history

### 4. Configuration

*   **`requirements.txt`:** Lists all Python dependencies required to run the tracking scripts. Includes libraries for data processing, Git integration, and visualization.

## Status

**Tags:** #map/project #p/project-tracker  
**Status:** #status/complete  
**Last Major Update:** Jan 2026 (D3 Knowledge Graph Complete)  
**Purpose:** Centralized project health monitoring
**Index:** `00_Index_*.md`

## Recent Activity

- 2026-03-17: fix: Move re and uuid imports to top level in app.py (#5009)
- 2026-03-17: feat: Agentic markers CRUD UI (#5009)
- 2026-03-17: fix: Remove non-standard Kanban statuses (#5013)
- 2026-03-17: fix: Distinguish structural issues from version mismatches in dashboard (#4765)
- 2026-03-17: feat: Add per-status task count pills to project cards on dashboard
- 2026-03-12: fix: prevent text overflow on Kanban task cards (#5117)
- 2026-03-12: fix: ensure all 5 Kanban columns visible without cutoff (#5115)
- 2026-03-12: feat: add visual regression testing for Kanban board UI (#5116)
- 2026-03-12: fix: prevent DONE column cutoff on Kanban board (#5115)
- 2026-03-11: feat: surface agent config health in dashboard and alerts (#5093)
## Related Documentation

- [Code Review Anti-Patterns](Documents/reference/CODE_REVIEW_ANTI_PATTERNS.md) - code review
- [Automation Reliability](patterns/automation-reliability.md) - automation
- [AI Model Cost Comparison](Documents/reference/MODEL_COST_COMPARISON.md) - AI models
- [AI Team Orchestration](patterns/ai-team-orchestration.md) - orchestration
- [Project Scaffolding](../project-scaffolding/README.md) - Project Scaffolding
- [README](README) - Project Tracker

## Getting Started

(Add a brief section on how to get started with the project tracker, e.g., installation instructions, initial configuration, etc.)

## Contributing

(Add a brief section on how to contribute to the project, including coding standards, pull request process, etc.)

<!-- LIBRARIAN-INDEX-START -->

### Subdirectories

| Directory | Files | Description |
| :--- | :---: | :--- |
| [dashboard/](dashboard/) | 2 | No description available. |
| [patterns/](patterns/) | 0 | No description available. |
| [project-graph-screenshots-movies/](project-graph-screenshots-movies/) | 80 | No description available. |
| [project-tracker/](project-tracker/) | 0 | No description available. |
| [prompts/](prompts/) | 0 | No description available. |

### Files

| File | Description |
| :--- | :--- |
| [AGENTS.md](AGENTS.md) | > **Universal Constitution:** See `project-scaffolding/AGENTS.md` for hierarchy, workflow, and unive... |
| [CLAUDE.md](CLAUDE.md) | 🛑 IMPORTANT: READ AGENTS.md FIRST |
| [DECISIONS.md](DECISIONS.md) | > *Documenting WHY we made decisions, not just WHAT we built.* |
| [README.md](README.md) | project-tracker |
| [REVIEW.md](REVIEW.md) | This document outlines the code review process for the Project Tracker application. It aims to ensur... |
| [REVIEWS_AND_GOVERNANCE_PROTOCOL.md](REVIEWS_AND_GOVERNANCE_PROTOCOL.md) | This file is managed by sync_governance.py and will be OVERWRITTEN on the next sync. |
| [USAGE.md](USAGE.md) | > **Quick Start:** `./pt launch` to open the dashboard |
| [dashboard/__init__.py](dashboard/__init__.py) | No description available. |
| [dashboard/app.py](dashboard/app.py) | FastAPI web dashboard for project tracker. |
| [dashboard/frontend/README.md](dashboard/frontend/README.md) | React + TypeScript + Vite frontend for the Kanban and Agentic SPA views, including Node version guidance and common commands. |
| [dashboard/frontend/eslint.config.js](dashboard/frontend/eslint.config.js) | No description available. |
| [dashboard/frontend/index.html](dashboard/frontend/index.html) | No description available. |
| [dashboard/frontend/package-lock.json](dashboard/frontend/package-lock.json) | No description available. |
| [dashboard/frontend/package.json](dashboard/frontend/package.json) | No description available. |
| [dashboard/frontend/public/vite.svg](dashboard/frontend/public/vite.svg) | No description available. |
| [dashboard/frontend/tsconfig.app.json](dashboard/frontend/tsconfig.app.json) | No description available. |
| [dashboard/frontend/tsconfig.json](dashboard/frontend/tsconfig.json) | No description available. |
| [dashboard/frontend/tsconfig.node.json](dashboard/frontend/tsconfig.node.json) | No description available. |
| [dashboard/frontend/vite.config.ts](dashboard/frontend/vite.config.ts) | No description available. |
| [dashboard/static/graph.css](dashboard/static/graph.css) | No description available. |
| [dashboard/static/graph.js](dashboard/static/graph.js) | No description available. |
| [dashboard/static/markdown.css](dashboard/static/markdown.css) | No description available. |
| [dashboard/static/memory.css](dashboard/static/memory.css) | No description available. |
| [dashboard/static/memory.js](dashboard/static/memory.js) | No description available. |
| [dashboard/static/memory_list.js](dashboard/static/memory_list.js) | No description available. |
| [dashboard/static/script.js](dashboard/static/script.js) | No description available. |
| [dashboard/static/style.css](dashboard/static/style.css) | No description available. |
| [find_orphans.py](find_orphans.py) | No description available. |
| [project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.11.00 AM.mov](project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.11.00 AM.mov) | No description available. |
| [project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.22.52 AM.mov](project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.22.52 AM.mov) | No description available. |
| [project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.46.56 AM.mov](project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.46.56 AM.mov) | No description available. |
| [project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.50.56 AM.mov](project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.50.56 AM.mov) | No description available. |
| [project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.54.43 AM.mov](project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.54.43 AM.mov) | No description available. |
| [project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.55.29 AM.mov](project-graph-screenshots-movies/Screen Recording 2026-01-15 at 10.55.29 AM.mov) | No description available. |
| [project-graph-screenshots-movies/Screen Recording 2026-01-15 at 11.17.19 AM.mov](project-graph-screenshots-movies/Screen Recording 2026-01-15 at 11.17.19 AM.mov) | No description available. |
| [project-graph-screenshots-movies/Screen Recording 2026-01-15 at 12.14.57 PM.mov](project-graph-screenshots-movies/Screen Recording 2026-01-15 at 12.14.57 PM.mov) | No description available. |
| [prompts/active/document_review/architecture.md](prompts/active/document_review/architecture.md) | You are an **architecture-focused purist reviewer** with expertise in system design, software archit... |
| [prompts/active/document_review/performance.md](prompts/active/document_review/performance.md) | You are a **performance-focused critical reviewer** with expertise in scalability, database optimiza... |
| [prompts/active/document_review/security.md](prompts/active/document_review/security.md) | You are a **security-focused skeptical reviewer** with expertise in application security, authentica... |
| [pt](pt) | No description available. |
| [pyproject.toml](pyproject.toml) | No description available. |
| [pyrightconfig.json](pyrightconfig.json) | No description available. |
| [requirements.txt](requirements.txt) | No description available. |
| [uv.lock](uv.lock) | No description available. |

<!-- LIBRARIAN-INDEX-END -->
