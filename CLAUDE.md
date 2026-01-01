# CLAUDE.md - AI Collaboration Instructions

## 🛑 IMPORTANT: READ AGENTS.md FIRST
`AGENTS.md` is the universal source of truth for this project. Always consult it for project-specific rules, tech stack, and execution commands.

## 📚 Required Reading
1. **[[AGENTS.md]]** - Source of Truth for AI Agents (Read this first!)
2. **[[README.md]]** - Project overview and quick start
3. **[[TODO.md]]** - Project status and completed tasks
4. **[[00_Index_project-tracker]]** - Project index and metadata

## 📋 Project Summary
**What this project does:**
Centralized dashboard and CLI tool for tracking the status, health, and resource usage of all projects in the workspace. It auto-discovers projects and enforces documentation standards.

**Current status:**
100% Complete. All MVP features implemented. Entering adoption and maintenance phase.

**Key constraints:**
- 100% Local (no cloud dependencies).
- $0 Monthly Cost.
- Mandatory `00_Index_*.md` files.

## 🛠 Coding Standards
- **Language:** Python 3.11+
- **Type Hints:** Mandatory for all public functions.
- **Error Handling:** No silent failures. Always log exceptions with context.
- **SQL Safety:** Use parameterized queries for all SQLite operations.
- **Logging:** Use the `logger.py` module for all logging.

## 🚀 Key Commands
- **Launch Dashboard:** `./pt launch`
- **Full Project Scan:** `./pt scan`
- **List Projects:** `./pt list`
- **Run Tests:** `pytest tests/`

---
*This file follows the [[project-scaffolding]] collaboration pattern.*

