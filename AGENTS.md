# AGENTS.md - Source of Truth for AI Agents

> **Universal Constitution:** See `project-scaffolding/AGENTS.md` for hierarchy, workflow, and universal safety rules.
> This file contains project-specific tech stack and constraints.

---

## 🎯 Project Overview
Centralized project status monitoring and reporting system for tracking lifecycle and health across all projects in the `$PROJECTS_ROOT` workspace. The system auto-discovers projects, parses `TODO.md` and `README.md` files, monitors cron job health, and enforces project indexing standards (Critical Rule #0).

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
- [[00_Index_project-tracker]]
- `CLAUDE.md` - AI Working Instructions
- `.cursorrules` - Cursor IDE Rules
- `Documents/reference/LEARNINGS.md` - Learning Loop & Debt Tracker
- `Documents/reference/MODEL_LEARNINGS.md` - AI Model Behavior
- [[00_Index_project-scaffolding]] - Meta-project patterns


<!-- project-scaffolding template appended -->

# AGENTS.md - Source of Truth for AI Agents

## 🎯 Project Overview
{project_description}

## 🛠 Tech Stack
- Language: {language}
- Frameworks: {frameworks}
- AI Strategy: {ai_strategy}

## 📋 Definition of Done (DoD)
- [ ] Code is documented with type hints.
- [ ] Technical changes are logged to `_obsidian/WARDEN_LOG.yaml`.
- [ ] `00_Index_*.md` is updated with recent activity.
- [ ] Code validated (no hardcoded paths, no secrets exposed).
- [ ] Code review completed (if significant architectural changes).
- [ ] [Project-specific DoD item]

## 🚀 Execution Commands
- Environment: `{venv_activation}`
- Run: `{run_command}`
- Test: `{test_command}`

## ⚠️ Critical Constraints
- NEVER hard-code API keys, secrets, or credentials in script files. Use `.env` and `os.getenv()`.
- NEVER use absolute paths (e.g., machine-specific paths). ALWAYS use relative paths or `PROJECT_ROOT` env var.
- ALWAYS run validation before considering work complete: `python "./scripts/validate_project.py" [project-name]`
- {constraint_1}
- {constraint_2}

**Code Review Standards:** See `./REVIEWS_AND_GOVERNANCE_PROTOCOL.md` for full review process.

## 📖 Reference Links
- [[00_Index_{project_name}]]
- [[Project Philosophy]]


<!-- project-scaffolding template appended -->


## Related Documentation

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[automation_patterns]] - automation
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering
- [[queue_processing_guide]] - queue/workflow


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[adult_business_compliance]] - adult industry
- [[ai_model_comparison]] - AI models


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[automation_patterns]] - automation
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering
- [[queue_processing_guide]] - queue/workflow


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[project-scaffolding/README]] - Project Scaffolding


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[automation_patterns]] - automation
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering
- [[queue_processing_guide]] - queue/workflow


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[adult_business_compliance]] - adult industry
- [[ai_model_comparison]] - AI models


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[automation_patterns]] - automation
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering
- [[queue_processing_guide]] - queue/workflow


- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

