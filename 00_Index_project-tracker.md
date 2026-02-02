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

- 2026-02-01: feat: Add learning measurement dashboard and fix validation issues (#4686, #4689)
- 2026-01-30: docs: Update index and add graph garbage nodes review report
- 2026-01-29: feat: Major session - 11 tasks completed
- 2026-01-29: feat: Project filter modal and iterdir exception handling
- 2026-01-29: feat: Ideas section UI components and cleanup
- 2026-01-29: feat: Database safety, validation improvements, and scan optimizations
- 2026-01-29: fix: Guard incomplete subtasks methods to prevent dashboard crash
- 2026-01-28: Merge remote-tracking branch 'origin/claude/fix-database-scanning-bugs-s6YJY'
- 2026-01-28: docs: Document agent deletion safety bypass and fixes
- 2026-01-28: Merge branch 'main' into claude/fix-database-scanning-bugs-s6YJY
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
| [Documents/](Documents/README.md) | 8 | *Auto-generated index. Last updated: 2026-01-24* |
| [dashboard/](dashboard/) | 2 | No description available. |
| [patterns/](patterns/) | 0 | No description available. |
| [project-tracker/](project-tracker/) | 0 | No description available. |
| [prompts/](prompts/) | 0 | No description available. |

### Files

| File | Description |
| :--- | :--- |
| [AGENTS.md](AGENTS.md) | > **Universal Constitution:** See `project-scaffolding/AGENTS.md` for hierarchy, workflow, and unive... |
| [CLAUDE.md](CLAUDE.md) | 🛑 IMPORTANT: READ AGENTS.md FIRST |
| [DECISIONS.md](DECISIONS.md) | > *Documenting WHY we made decisions, not just WHAT we built.* |
| [Documents/ARCHITECTURE.md](Documents/ARCHITECTURE.md) | > **Last Updated:** January 2026 |
| [Documents/CODE_QUALITY_STANDARDS.md](Documents/CODE_QUALITY_STANDARDS.md) | Code Quality Standards |
| [Documents/CODE_REVIEW_PHASE4_TELEMETRY.md](Documents/CODE_REVIEW_PHASE4_TELEMETRY.md) | Code Review: Phase 4 Telemetry Implementation |
| [Documents/INTEGRATION_WITH_SCAFFOLDING.md](Documents/INTEGRATION_WITH_SCAFFOLDING.md) | Integration Strategy: Project Tracker ↔ Project Scaffolding |
| [Documents/OPERATIONS.md](Documents/OPERATIONS.md) | > **Last Updated:** January 2026 |
| [Documents/README.md](Documents/README.md) | Project Tracker - Documents Index |
| [Documents/REVIEWS_AND_GOVERNANCE_PROTOCOL.md](Documents/REVIEWS_AND_GOVERNANCE_PROTOCOL.md) | 🛡️ Ecosystem Governance & Review Protocol (v1.2) |
| [Documents/SCAFFOLDING_TRANSFER_GUIDE.md](Documents/SCAFFOLDING_TRANSFER_GUIDE.md) | Scaffolding Transfer Guide: project-tracker |
| [Documents/patterns/code-review-standard.md](Documents/patterns/code-review-standard.md) | Code Review Standardization |
| [Documents/patterns/learning-loop-pattern.md](Documents/patterns/learning-loop-pattern.md) | Learning Loop Pattern |
| [Documents/reference/AI_JOURNAL.md](Documents/reference/AI_JOURNAL.md) | Strategic decisions, significant events, and reflections for future context. |
| [Documents/reference/LEARNINGS.md](Documents/reference/LEARNINGS.md) | Project Tracker Learning Loop |
| [Documents/reference/LOCAL_MODEL_LEARNINGS.md](Documents/reference/LOCAL_MODEL_LEARNINGS.md) | Local Model Learnings: project-tracker |
| [Documents/reference/MODEL_LEARNINGS.md](Documents/reference/MODEL_LEARNINGS.md) | Local Model Learnings: project-tracker |
| [PRD_KANBAN.md](PRD_KANBAN.md) | > **Type:** Feature PRD (adding to existing project) |
| [QUICKSTART.md](QUICKSTART.md) | 🚀 project-tracker - Quick Start |
| [README.md](README.md) | project-tracker |
| [REVIEW.md](REVIEW.md) | This document outlines the code review process for the Project Tracker application. It aims to ensur... |
| [TODO.md](TODO.md) | **Last Updated:** January 14, 2026 |
| [USAGE.md](USAGE.md) | > **Quick Start:** `./pt launch` to open the dashboard |
| [config.py](config.py) | Configuration for project tracker. |
| [dashboard/__init__.py](dashboard/__init__.py) | No description available. |
| [dashboard/app.py](dashboard/app.py) | FastAPI web dashboard for project tracker. |
| [dashboard/frontend/README.md](dashboard/frontend/README.md) | This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules. |
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
| [dashboard/static/script.js](dashboard/static/script.js) | No description available. |
| [dashboard/static/style.css](dashboard/static/style.css) | No description available. |
| [find_orphans.py](find_orphans.py) | No description available. |
| [logger.py](logger.py) | Logging configuration for project tracker. |
| [prompts/active/document_review/architecture.md](prompts/active/document_review/architecture.md) | You are an **architecture-focused purist reviewer** with expertise in system design, software archit... |
| [prompts/active/document_review/performance.md](prompts/active/document_review/performance.md) | You are a **performance-focused critical reviewer** with expertise in scalability, database optimiza... |
| [prompts/active/document_review/security.md](prompts/active/document_review/security.md) | You are a **security-focused skeptical reviewer** with expertise in application security, authentica... |
| [pt](pt) | No description available. |
| [requirements.txt](requirements.txt) | No description available. |

<!-- LIBRARIAN-INDEX-END -->
