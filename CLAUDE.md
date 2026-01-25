# CLAUDE.md - project-tracker

<!-- AGENTSYNC:START - Do not edit between markers -->
<!-- To modify synced rules: Edit .agentsync/rules/*.md, then run: -->
<!-- uv run $TOOLS_ROOT/agentsync/sync_rules.py project-tracker -->

# AGENTS.md - Source of Truth for AI Agents

> **Universal Constitution:** See `project-scaffolding/AGENTS.md` for hierarchy, workflow, and universal safety rules.
> This file contains project-specific tech stack and constraints related to the AI agents used in the `project-tracker`.

---

## 🎯 Project Overview
Centralized project status monitoring and reporting system for tracking lifecycle and health across all projects in the `$PROJECTS_ROOT` workspace. The system auto-discovers projects, parses `TODO.md` and `README.md` files, monitors cron job health, and enforces project indexing standards (Critical Rule #0). This project leverages AI agents to automate tasks such as project discovery, data extraction, and report generation.

## 🤖 AI Agents

This section details the AI agents currently employed within the `project-tracker` system. Each agent description includes its purpose, responsibilities, tech stack dependencies, and any specific constraints.

### 1. Project Discovery Agent

*   **Purpose:** Automatically identifies and registers new projects within the `$PROJECTS_ROOT` workspace.
*   **Responsibilities:**
    *   Scans the filesystem for directories matching project naming conventions.
    *   Verifies the existence of a mandatory `00_Index_*.md` file.
    *   Adds new projects to the internal project registry (likely a database or configuration file).
*   **Tech Stack:**
    *   Python 3.11+
    *   `os` module for filesystem interaction
    *   Potentially uses regular expressions for project name matching.
*   **Constraints:**
    *   Must adhere to the "Local Only" constraint (no external cloud services).
    *   Must respect the "Indexing Compliance" rule.
    *   Must not access or modify files outside of the designated `$PROJECTS_ROOT` workspace.
    *   Should log all discovery attempts and outcomes (successes and failures).
*   **Prompt Template (if applicable):** N/A (primarily uses filesystem operations)

### 2. Data Extraction Agent

*   **Purpose:** Extracts relevant information from `TODO.md` and `README.md` files within each project.
*   **Responsibilities:**
    *   Parses `TODO.md` files to identify outstanding tasks and their status.
    *   Parses `README.md` files to extract project descriptions, dependencies, and other metadata.
    *   Stores extracted data in a structured format (e.g., JSON, SQLite database).
*   **Tech Stack:**
    *   Python 3.11+
    *   Potentially uses libraries like `BeautifulSoup4` or `Markdown` for parsing.
    *   Regular expressions for pattern matching.
*   **Constraints:**
    *   Must handle malformed or incomplete `TODO.md` and `README.md` files gracefully (no crashes).
    *   Must not execute any code found within the parsed files (security).
    *   Should log any parsing errors or inconsistencies.
*   **Prompt Template (if applicable):**

    ```
    You are a data extraction agent. Your task is to extract the following information from the provided text:

    - Project Description: [Extract from README.md]
    - TODO Items: [Extract all TODO items from TODO.md with status]

    Text: {file_content}

    Output (JSON):
    ```

### 3. Report Generation Agent

*   **Purpose:** Generates reports summarizing the status and health of all tracked projects.
*   **Responsibilities:**
    *   Queries the internal project registry and extracted data.
    *   Formats the data into human-readable reports (e.g., HTML, Markdown).
    *   Potentially generates visualizations (e.g., charts, graphs).
*   **Tech Stack:**
    *   Python 3.11+
    *   Jinja2 (Templating)
    *   Potentially uses libraries like `matplotlib` or `plotly` for visualizations.
*   **Constraints:**
    *   Must adhere to the "Data Isolation" rule (reports must be stored in the `data/` directory).
    *   Should provide options for filtering and sorting the report data.
*   **Prompt Template (if applicable):** N/A (primarily uses data aggregation and formatting)

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
- [ ] Code validated (no hardcoded paths, no secrets exposed).
- [ ] Code review completed (if significant architectural changes).

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
- **No Hardcoded Paths:** Reference code snippets in prompts MUST use relative paths or environment variables. Local models will copy absolute paths literally.

## 📝 Prompt Template (Structural Bridges)

### ⚠️ DOWNSTREAM HARM ESTIMATE
- **If this fails:** [What breaks? Recovery time?]
- **Known pitfalls:** [From LEARNINGS.md]
- **Assumptions:** [What logic might break?]

### 📚 LEARNINGS APPLIED
- [ ] **Floor Manager Protocol**: I am the Messenger, delegation to Worker required.
- [ ] **Portable Paths**: No absolute paths in reference snippets or code.
- [ ] **Rule #1**: Logging for all exceptions.

**Code Review Standards:** See `./Documents/REVIEWS_AND_GOVERNANCE_PROTOCOL.md` for full review process.

## 📖 Reference Links
- `Documents/REVIEWS_AND_GOVERNANCE_PROTOCOL.md` - Path standards and review process
- `00_Index_*.md`
- `CLAUDE.md` - AI Working Instructions
- `.cursorrules` - Cursor IDE Rules
- `Documents/reference/LEARNINGS.md` - Learning Loop & Debt Tracker
- `Documents/reference/MODEL_LEARNINGS.md` - AI Model Behavior
- `00_Index_*.md` - Meta-project patterns

<!-- Source: .agentsync/rules/*.md -->
<!-- AGENTSYNC:END - Custom rules below this line are preserved -->