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

<!-- LIBRARIAN-INDEX-START -->

### File Index

| File | Description |
| :--- | :--- |
| [[AGENTS.md]] | > **Universal Constitution:** See `project-scaffolding/AGENTS.md` for hierarchy, workflow, and unive... |
| [[CLAUDE.md]] | 🛑 IMPORTANT: READ AGENTS.md FIRST |
| [[CODE_REVIEW_CLAUDE_v2.md]] | Code Review Checklist - project-tracker |
| [[D3_KNOWLEDGE_GRAPH_ROADMAP.md]] | D3 Knowledge Graph - Feature Roadmap |
| [[Documents/ARCHITECTURE.md]] | > **Last Updated:** January 2026 |
| [[Documents/CODE_QUALITY_STANDARDS.md]] | Code Quality Standards |
| [[Documents/CODE_REVIEW_PHASE4_TELEMETRY.md]] | Code Review: Phase 4 Telemetry Implementation |
| [[Documents/INTEGRATION_WITH_SCAFFOLDING.md]] | Integration Strategy: Project Tracker ↔ Project Scaffolding |
| [[Documents/OPERATIONS.md]] | > **Last Updated:** January 2026 |
| [[Documents/README.md]] | Project Tracker - Documents Index |
| [[Documents/REVIEWS_AND_GOVERNANCE_PROTOCOL.md]] | 🛡️ Ecosystem Governance & Review Protocol (v1.2) |
| [[Documents/SCAFFOLDING_TRANSFER_GUIDE.md]] | Scaffolding Transfer Guide: project-tracker |
| [[Documents/patterns/code-review-standard.md]] | Code Review Standardization |
| [[Documents/patterns/learning-loop-pattern.md]] | Learning Loop Pattern |
| [[Documents/reference/LEARNINGS.md]] | Project Tracker Learning Loop |
| [[Documents/reference/LOCAL_MODEL_LEARNINGS.md]] | Local Model Learnings: project-tracker |
| [[Documents/reference/MODEL_LEARNINGS.md]] | Local Model Learnings: project-tracker |
| [[Documents/reports/2026-01-11_protocol_deviation_report.md]] | Protocol Deviation Report - 2026-01-11 |
| [[Documents/templates/CODE_REVIEW.md.template]] | No description available. |
| [[QUICKSTART.md]] | 🚀 project-tracker - Quick Start |
| [[README.md]] | project-tracker |
| [[REVIEW.md]] | This document outlines the code review process for the Project Tracker application. It aims to ensur... |
| [[TODO.md]] | **Last Updated:** January 14, 2026 |
| [[USAGE.md]] | > **Quick Start:** `./pt launch` to open the dashboard |
| [[config.py]] | Configuration for project tracker. |
| [[current_orphans.txt]] | No description available. |
| [[dashboard/__init__.py]] | No description available. |
| [[dashboard/app.py]] | FastAPI web dashboard for project tracker. |
| [[dashboard/static/graph.css]] | No description available. |
| [[dashboard/static/graph.js]] | No description available. |
| [[dashboard/static/markdown.css]] | No description available. |
| [[dashboard/static/script.js]] | No description available. |
| [[dashboard/static/style.css]] | No description available. |
| [[dashboard/templates/graph.html]] | No description available. |
| [[dashboard/templates/index.html]] | No description available. |
| [[dashboard/templates/project_detail.html]] | No description available. |
| [[dashboard/templates/todo_viewer.html]] | No description available. |
| [[find_orphans.py]] | No description available. |
| [[logger.py]] | Logging configuration for project tracker. |
| [[orphans_list.txt]] | No description available. |
| [[prompts/active/document_review/architecture.md]] | You are an **architecture-focused purist reviewer** with expertise in system design, software archit... |
| [[prompts/active/document_review/performance.md]] | You are a **performance-focused critical reviewer** with expertise in scalability, database optimiza... |
| [[prompts/active/document_review/security.md]] | You are a **security-focused skeptical reviewer** with expertise in application security, authentica... |
| [[pt]] | No description available. |
| [[requirements.txt]] | No description available. |
| [[scripts/cleanup_related_docs.py]] | No description available. |
| [[scripts/db/__init__.py]] | No description available. |
| [[scripts/db/manager.py]] | Database manager for project tracker operations. |
| [[scripts/db/schema.py]] | Database schema for project tracker. |
| [[scripts/discovery/__init__.py]] | No description available. |
| [[scripts/discovery/agent_registry.py]] | Agent Registry for the Agent Dispatcher UI. |
| [[scripts/discovery/alert_detector.py]] | Alert detection for project tracker. |
| [[scripts/discovery/backup_reader.py]] | Backup Reader for rclone integration. |
| [[scripts/discovery/code_review_parser.py]] | Code Review Parser - Extract metadata from CODE_REVIEW.md files |
| [[scripts/discovery/cron_health.py]] | Cron Health Monitor - Check if scheduled jobs are running. |
| [[scripts/discovery/cron_monitor.py]] | Cron job monitoring and failure detection. |
| [[scripts/discovery/external_resources_parser.py]] | Parser for EXTERNAL_RESOURCES.yaml to extract service dependencies. |
| [[scripts/discovery/git_metadata.py]] | Git metadata extraction. |
| [[scripts/discovery/graph_builder.py]] | Graph builder for project-tracker ecosystem. |
| [[scripts/discovery/hygiene_detector.py]] | Detect and fix discrepancies in TODO.md files (Hygiene). |
| [[scripts/discovery/journal_specialist.py]] | No description available. |
| [[scripts/discovery/librarian.py]] | No description available. |
| [[scripts/discovery/project_scanner.py]] | Project scanner for auto-discovery. |
| [[scripts/discovery/providers.py]] | Metadata providers for project discovery. |
| [[scripts/discovery/telemetry_reader.py]] | Telemetry Reader for AI Router integration. |
| [[scripts/discovery/todo_parser.py]] | TODO.md parser for extracting project metadata. |
| [[scripts/doc_audit.py]] | No description available. |
| [[scripts/doc_audit_daily.sh]] | doc_audit_daily.sh - Daily documentation maintenance |
| [[scripts/doc_audit_v2.py]] | No description available. |
| [[scripts/git-pre-commit.sh]] | Pre-commit hook to prevent hardcoded absolute paths |
| [[scripts/maintenance.sh]] | maintenance.sh - Global Ecosystem Health & Networking |
| [[scripts/pre_review_scan.sh]] | pre_review_scan.sh - Run before code reviews or commits |
| [[scripts/pt.py]] | No description available. |
| [[scripts/validate_project.py]] | No description available. |
| [[scripts/warden_audit.py]] | No description available. |
| [[tests/MISSING_TESTS.md]] | Missing Tests for project-tracker |
| [[tests/test_discovery.py]] | No description available. |
| [[tests/test_parsers.py]] | Tests for TODO.md and resource parsers. |

<!-- LIBRARIAN-INDEX-END -->