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

# project-tracker

Project status monitoring and reporting system for tracking lifecycle and health across all projects. This active development system includes 17 Python scripts for project status tracking, 11 markdown documentation files, and HTML/CSS dashboards for visualizing project health, progress, and resource allocation. The tracker provides centralized visibility into which projects are active, stalled, or need attention.

## Key Components

### Tracking Scripts
- Python files (18 files)
  - Status collection automation
  - Git activity monitoring
  - Health metric calculation
  - Report generation
  - Alert triggers
  - **New:** Agent Dispatcher, Backup Auditing, & D3 Knowledge Graph Builder

### Dashboard
- `dashboard/` - Visualization (4 HTML templates)
  - Project status overview
  - Activity heatmaps
  - Agent Dispatcher UI
  - Backup Status Monitor
  - **New:** Interactive D3 Knowledge Graph (/graph)

### Documentation
- Markdown files (25+ files)
  - `AGENTS.md` - Source of Truth for AI Agents
  - `CLAUDE.md` - AI Collaboration Instructions
  - Setup guides
  - Metric definitions
  - Architecture & Operations docs
  - Integrated Archives & Planning history

### Configuration
- `requirements.txt` - Dependencies
  - Data processing libs
  - Git integration
  - Visualization tools

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


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[ai_model_comparison]] - AI models
- [[orchestration_patterns]] - orchestration


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[dashboard_architecture]] - dashboard/UI
- [[error_handling_patterns]] - error handling


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[project-scaffolding/README]] - Project Scaffolding
- [[project-tracker/README]] - Project Tracker


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[dashboard_architecture]] - dashboard/UI
- [[error_handling_patterns]] - error handling


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[ai_model_comparison]] - AI models
- [[orchestration_patterns]] - orchestration


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[dashboard_architecture]] - dashboard/UI
- [[error_handling_patterns]] - error handling


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

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
| [[REVIEW.md]] | **Review Date:** 2026-01-02 22:47:44 UTC |
| [[TODO.md]] | **Last Updated:** January 13, 2026 |
| [[USAGE.md]] | > **Quick Start:** `./pt launch` to open the dashboard |
| [[config.py]] | Configuration for project tracker. |
| [[current_orphans.txt]] | No description available. |
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
| [[scripts/db/manager.py]] | Database manager for project tracker operations. |
| [[scripts/db/schema.py]] | Database schema for project tracker. |
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
| [[scripts/discovery/librarian.py]] | No description available. |
| [[scripts/discovery/project_scanner.py]] | Project scanner for auto-discovery. |
| [[scripts/discovery/providers.py]] | Metadata providers for project discovery. |
| [[scripts/discovery/telemetry_reader.py]] | Telemetry Reader for AI Router integration. |
| [[scripts/discovery/todo_parser.py]] | TODO.md parser for extracting project metadata. |
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