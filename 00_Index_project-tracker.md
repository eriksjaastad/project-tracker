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
    *   Integrated Archives & Planning history

### 4. Configuration

*   **`requirements.txt`:** Lists all Python dependencies required to run the tracking scripts. Includes libraries for data processing, Git integration, and visualization.

## Status

**Tags:** #map/project #p/project-tracker  
**Status:** #status/complete  
**Last Major Update:** Jan 2026 (D3 Knowledge Graph Complete)  
**Purpose:** Centralized project health monitoring
**Index:** [[00_Index_project-tracker]]

## Recent Activity

- 2026-01-13: Merge pull request #3 from eriksjaastad/claude/code-review-session-72x3V
- 2026-01-13: fix: resolve warden_audit.py syntax error and update review to final
- 2026-01-13: fix: address v2 code review blockers and enhance portability
- 2026-01-13: Merge pull request #2 from eriksjaastad/claude/code-review-session-72x3V
- 2026-01-13: docs: add code review v2, archive v1
- 2026-01-13: chore: harden project portability and governance
- 2026-01-12: Merge pull request #1 from eriksjaastad/claude/code-review-z5udV
- 2026-01-12: docs: add code review for project-tracker
- 2026-01-12: chore: apply project-scaffolding to make project standalone
- 2026-01-11: docs: final update to 00_Index counts and components

## Related Documentation

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[dashboard_architecture]] - dashboard/UI
- [[error_handling_patterns]] - error handling
- [[ai_model_comparison]] - AI models
- [[orchestration_patterns]] - orchestration
- [[project-scaffolding/README]] - Project Scaffolding
- [[project-tracker/README]] - Project Tracker

## Getting Started

(Add a brief section on how to get started with the project tracker, e.g., installation instructions, initial configuration, etc.)

## Contributing

(Add a brief section on how to contribute to the project, including coding standards, pull request process, etc.)
