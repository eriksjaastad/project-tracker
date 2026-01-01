# AGENTS.md - Source of Truth for AI Agents

## 🎯 Project Overview
Centralized project status monitoring and reporting system for tracking lifecycle and health across all projects in the `/Users/eriksjaastad/projects` workspace. The system auto-discovers projects, parses `TODO.md` and `README.md` files, monitors cron job health, and enforces project indexing standards (Critical Rule #0).

## 🛠 Tech Stack
- Language: Python 3.11+
- Frameworks: FastAPI (Web Dashboard), Typer (CLI Tool), Jinja2 (Templating)
- AI Strategy: AI-initiated project designed for Claude Code and Cursor. Emphasizes "Two-Level Game" (Meta-patterns + Domain patterns).

## 📋 Definition of Done (DoD)
- [x] Code is documented with type hints.
- [x] Technical changes follow "No Silent Failures" rule (logged).
- [x] `00_Index_project-tracker.md` is updated with all status changes.
- [x] All SQLite queries use parameterized placeholders (prevent SQLi).
- [x] Dashboard successfully scans 35+ projects without crashing.

## 🚀 Execution Commands
- Environment: `source venv/bin/activate`
- Run Dashboard: `./pt launch`
- CLI Scan: `./pt scan`
- CLI List: `./pt list`
- Test: `pytest tests/test_parsers.py`

## ⚠️ Critical Constraints
- **Local Only:** Must not depend on any external cloud services (besides local filesystem).
- **Indexing Compliance:** Mandatory `00_Index_*.md` file in every project root.
- **Data Isolation:** All database files and logs must stay in `data/` and `logs/`.
- **No Silent Failures:** Bare `except: pass` is strictly forbidden.

## 📖 Reference Links
- [[00_Index_project-tracker]]
- [[Project Philosophy]]
- [[project-scaffolding]]

