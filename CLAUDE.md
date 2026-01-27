# CLAUDE.md - project-tracker

<!-- AGENTSYNC:START - Do not edit between markers -->
<!-- To modify synced rules: Edit .agentsync/rules/*.md, then run: -->
<!-- uv run $PROJECTS_ROOT/project-scaffolding/agentsync/sync_rules.py project-tracker -->

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
- CLI Tasks: `./pt tasks` (see below)
- Test: `pytest tests/test_parsers.py`

### Task Management CLI

**Agents can check and manage tasks from any project using the CLI:**

```bash
# List open tasks (all projects):
$PROJECTS_ROOT/project-tracker/pt tasks

# Filter by project:
$PROJECTS_ROOT/project-tracker/pt tasks -p <project-name>

# Filter by status (Backlog, To Do, In Progress, Done):
$PROJECTS_ROOT/project-tracker/pt tasks -s "In Progress"

# Show all tasks including completed:
$PROJECTS_ROOT/project-tracker/pt tasks --all

# Combine filters:
$PROJECTS_ROOT/project-tracker/pt tasks -p project-tracker -s "To Do"

# Create a new task (quick capture):
$PROJECTS_ROOT/project-tracker/pt tasks create "Fix the login bug" -p <project-name>
$PROJECTS_ROOT/project-tracker/pt tasks create "Add tests" -p myproject -s "To Do" --priority High

# Start working on a task (moves to In Progress):
$PROJECTS_ROOT/project-tracker/pt tasks start <task-id>

# Update a task:
$PROJECTS_ROOT/project-tracker/pt tasks update <task-id> -s "To Do" --priority Medium
$PROJECTS_ROOT/project-tracker/pt tasks update <task-id> -t "New task description"

# Mark a task as done:
$PROJECTS_ROOT/project-tracker/pt tasks done <task-id>
```

**Usage notes for agents:**
- Check `./pt tasks -p <your-project>` before starting work to see pending tasks
- Use `./pt tasks start <id>` when beginning work on a task
- Use `./pt tasks done <id>` when completing a task
- Tasks are tracked in a Kanban board (Backlog → To Do → In Progress → Done)
- The web dashboard at `localhost:8000/kanban` provides a visual interface
- Task IDs are unique integers that can be referenced in commits

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

# project-tracker

> Brief description of the project's purpose

## Tech Stack

- **Language:** Python
- **Frameworks:** None

## Commands

- **Run:** `python main.py`
- **Test:** `pytest`

# Workflow

## Agent Hierarchy

### 1. The Conductor (Erik)
- **Role:** Human-in-the-Loop / Vision / Command
- **Authority:** Final approval on all architecture, logic, and project direction

### 2. The Super Manager (Strategy & Context)
- **Role:** Strategic Planner and Prompt Engineer
- **Constraint:** STRICTLY PROHIBITED from writing code or using tools
- **Mandate:** Drafts prompts with acceptance criteria as checklists

### 3. The Floor Manager (QA & Execution)
- **Role:** Orchestrator, Quality Assurance Lead, File Operator
- **Constraint:** STRICTLY PROHIBITED from generating logic or writing code
- **Mandate:** Verify work against checklists, perform file operations

### 4. The Workers (Local Models via Ollama)
- **Role:** Primary Implementers of logic and code generation
- **Mandate:** Generate code, report completion for inspection

## Workflow Steps

1. **Drafting:** Super Manager writes task prompt with acceptance criteria
2. **Handoff:** Pass to Floor Manager
3. **Execution:** Floor Manager delegates to Worker, provides context
4. **Inspection:** Floor Manager checks each acceptance criteria item
5. **Loop/Correction:** If fail, send back to Worker (max 3 attempts)
6. **Finalization:** Task marked complete after sign-off

**CRITICAL:** Only Workers write code. Super Manager and Floor Manager never generate code.

# Universal Constraints

## Never Do

- NEVER modify `.env` or `venv/`
- NEVER install dependencies globally (use project-local venv, uv, pipx, or poetry)
- NEVER hard-code API keys, secrets, or credentials (use `.env` and `os.getenv()`)
- NEVER use absolute paths (e.g., `/Users/...`) - use relative paths or env variables
- NEVER use `rm` for file deletion - use `trash` command instead
- NEVER use `--no-verify` or `-n` with git commit/push - fix the hook issue, don't bypass it

## Always Do

- ALWAYS update `EXTERNAL_RESOURCES.yaml` when adding external services
- ALWAYS use retry logic and cost tracking for API calls
- ALWAYS use `$HOME/.local/bin/uv run` for Python script execution in hooks/automation

# Safety Rules

## File Operations

- **Trash, Don't Delete:** NEVER use `rm` or permanent deletion
- Use `trash` CLI (preferred) or `send2trash` (Python)
- Use `git restore` for reverting tracked files

## Context Protocol

If context is missing or a file is unknown:
- **STOP** and request information from the Floor Manager
- **DO NOT GUESS**

## Failure Protocol

If Worker fails **3 times** on the same task:
- Halt and alert the Conductor
- Do not continue attempting

# AI-First Development Guidelines

## CLI Design
- **Plain text output**: Avoid rich formatting (colors, bold) in default output to ensure easy parsing by AI agents.
- **Single-line parseable formats**: For lists (like tasks), use single-line formats: `#<id> | <status> | <priority> | <text>`.
- **JSON support**: Always provide a `--json` flag for structured output.
- **Batch operations**: Support multiple IDs for commands like `show`, `start`, `done` to reduce round-trips.

## File Operations
- **Read before edit**: Always read the file content before performing a search-replace or write.
- **Preserve custom content**: Use marker-based updates (e.g., `<!-- SCAFFOLD:START -->`) to preserve project-specific logic while updating governed sections.
- **DNA Integrity**: Never use hardcoded absolute paths. Use relative paths or environment variables.

## Task Workflow
- **State Management**: Use `./pt tasks start <id>` when beginning work and `./pt tasks done <id>` when finished.
- **Context Awareness**: Use `./pt tasks show <id>` to read the full task prompt, including Overview, Execution, and Done Criteria.
- **Traceability**: All major changes should be linked to a task ID in the project tracker.

## Communication
- **Direct and Concise**: Avoid fluff in assistant responses.
- **Proactive Planning**: Use `todo_write` to maintain a clear plan of action.
- **Soulful Journaling**: Log strategic decisions and detours in the AI Journal for future context.

<!-- Source: .agentsync/rules/*.md -->
<!-- AGENTSYNC:END - Custom rules below this line are preserved -->