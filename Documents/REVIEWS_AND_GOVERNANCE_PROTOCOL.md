# 🛡️ Ecosystem Governance & Review Protocol (v1.4)

**Date:** 2026-01-27
**Status:** ACTIVE - POST-INCIDENT HARDENING
**Goal:** Transition from "Rapid Experimentation" to "Industrial-Grade Hardening."

> ⚠️ **CRITICAL INCIDENT NOTICE (2026-01-27):** This protocol was updated following a catastrophic data loss where 94 tasks were deleted due to cascading failures in the scanning code. Version 1.4 adds mandatory robotic checks, explicit grep patterns, and a known violations tracker. ALL code reviews must now complete the enhanced checklist.

---

## 🚨 Part 0: The 2026-01-27 Incident Post-Mortem

### What Happened
1. An AI agent added unrequested "auto-cleanup" logic to the `scan` command in `pt.py`
2. The logic: "If a project is in the database but not found in scan, delete it"
3. The `discover_projects()` function in `project_scanner.py` returned an empty list `[]` when `PROJECTS_ROOT` pointed to a non-existent directory
4. **No warning was logged** - the function silently returned empty
5. The scan command interpreted "0 projects found" as "delete all projects not found"
6. Due to CASCADE foreign keys, deleting projects also deleted all 94 tasks

### Root Causes (Multi-Factor Failure)
| Factor | Location | Violation |
|--------|----------|-----------|
| **Silent Failure** | `project_scanner.py:34-35` | `return []` without logging when directory doesn't exist |
| **No Zero-Result Sanity Check** | `project_scanner.py` | No warning when 0 projects found in a directory that should have many |
| **Unbounded Recursive Globs** | `project_scanner.py:51-52` | `any(item.glob("**/*.py"))` scans entire subtree including node_modules |
| **No Env Var Validation** | `config.py:7` | `PROJECTS_ROOT` not validated to exist and be a directory |
| **Unrequested Destructive Feature** | `pt.py` (old code) | Auto-delete logic was never requested by Conductor |
| **No Exception Handling** | `project_scanner.py:39` | `iterdir()` not wrapped in try/except |

### The Lesson
The incident required **5 simultaneous failures** to cause data loss. Any single defensive layer would have prevented it. The protocol must now mandate **defense in depth** - multiple redundant safety checks.

### Current Status
- ✅ Auto-delete logic removed from `pt.py` (commit 0240649)
- ✅ Backup-before-delete implemented in `manager.py`
- ✅ Audit triggers added to schema.py
- ❌ **STILL ACTIVE**: Silent failure in `project_scanner.py:34-35`
- ❌ **STILL ACTIVE**: Unbounded recursive globs in `project_scanner.py:51-52`
- ❌ **STILL ACTIVE**: No exception handling around `iterdir()` in `project_scanner.py:39`
- ❌ **STILL ACTIVE**: No PROJECTS_ROOT validation in `config.py`

---

## 🔴 Known Active Violations Tracker

> **Purpose:** Track known defects that violate this protocol until they are fixed. Updated each review.
> **Last Updated:** 2026-01-27

| ID | File:Line | Violation | Severity | Task # |
|----|-----------|-----------|----------|--------|
| V1 | `project_scanner.py:34-35` | Silent `return []` when base doesn't exist | CRITICAL | #4617 |
| V2 | `project_scanner.py:51-52` | Unbounded recursive globs `**/*.py`, `**/*.js` | HIGH | #4618 |
| V3 | `project_scanner.py:39` | No try/except around `iterdir()` | HIGH | #4619 |
| V4 | `config.py:7` | No validation that PROJECTS_ROOT is a valid directory | HIGH | #4620 |
| V5 | `pt.py:101-102` | Silent `except Exception: return None, None` | MEDIUM | #4621 |

**Rule:** No PR can be merged if it introduces NEW violations. Existing violations must be tracked and scheduled for fix.

---

## 🏛️ Part 1: The Core Architecture (Checklist-First)
*Intelligence belongs in the checklist, not the prompt.*

### 1. The Fundamental Pivot
Prompts are subjective and mood-dependent; checklists are versioned, auditable specifications of what "reviewed" means.
*   **Evidence-First Rule:** Every check requires an evidence field (e.g., a `grep` output). Empty evidence = Incomplete Review.
*   **The Artifact:** The review deliverable is a completed evidence trail, not an unstructured prose opinion.

### 2. The Blast Radius Prioritization
Audit files in order of their potential to infect the ecosystem:
1.  **Tier 1: Propagation Sources (Highest Impact):** `templates/`, `.cursorrules`, `AGENTS.md`. If these fail, every downstream project inherits the defect.
2.  **Tier 2: Execution Critical:** `scripts/`, `scaffold/`. These run the automation but don't propagate DNA.
3.  **Tier 3: Documentation:** `Documents/`, `patterns/`. Important for humans, zero impact on code execution.

---

## 🏛️ Part 2: The Two-Layer Defense Model

### Layer 1: Robotic Scan (Gatekeeper)
A mechanical script (`pre_review_scan.sh`) that catches hardcoded paths, secrets, and silent errors. A single "FAIL" blocks the AI/Human review. This is integrated into the `Project-workflow.md` (lives at projects root) as the mandatory Gate 0.

#### Mandatory Grep Patterns (pre_review_scan.sh must check ALL of these):

```bash
# === CRITICAL: Patterns that caused 2026-01-27 incident ===

# 1. Silent failure patterns - return empty without logging
grep -rn "return \[\]$" scripts/ --include="*.py"
grep -rn "return None$" scripts/ --include="*.py"
grep -rn "return {}$" scripts/ --include="*.py"
# RULE: Every instance must have a logger.warning() within 3 lines BEFORE the return

# 2. Unbounded recursive globs
grep -rn '\.glob("\*\*/' scripts/ --include="*.py"
grep -rn "\.glob('\*\*/" scripts/ --include="*.py"
# RULE: Zero tolerance. Must use bounded alternatives.

# 3. Unhandled filesystem iterators
grep -rn "\.iterdir()" scripts/ --include="*.py"
grep -rn "for .* in .*\.glob(" scripts/ --include="*.py"
# RULE: Must be wrapped in try/except with logging

# 4. Silent exception swallowing
grep -rn "except.*:" scripts/ --include="*.py" -A1 | grep -E "(pass$|return None|return \[\])"
grep -rn "except Exception:" scripts/ --include="*.py" -A1 | grep -v "logger\."
# RULE: Every except block must log or re-raise

# 5. Environment variable without validation
grep -rn "os\.getenv" scripts/ config.py --include="*.py"
# RULE: Critical path env vars must have is_dir()/exists() validation

# 6. DELETE/CASCADE patterns without backup
grep -rn "DELETE FROM" scripts/ --include="*.py"
grep -rn "\.delete_" scripts/ --include="*.py"
# RULE: Must have _backup_before_delete() call prior

# === EXISTING CHECKS (keep these) ===

# 7. Hardcoded paths
grep -rn "/Users/" . --include="*.py" --include="*.sh" --include="*.md"
grep -rn "/home/" . --include="*.py" --include="*.sh" --exclude-dir=venv

# 8. API keys and secrets
grep -rn "sk-" . --include="*.py" --include="*.md" --include="*.yaml"
grep -rn "ANTHROPIC_API_KEY.*=" . --include="*.py"

# 9. Silent except:pass
grep -rn "except.*:.*pass" . --include="*.py"
```

**Exit Criteria:** If ANY of patterns 1-6 are found without proper mitigation, the scan MUST fail.

### Layer 2: Cognitive Audit (Architect Work)
AI Architects focus on judgment-heavy tasks that automation misses:
*   **Inverse Test Analysis:** For every passing test, document what is **NOT** being checked. Identify the "Dark Territory."
*   **Temporal Risk Analysis:** Identify what breaks in 1, 6, or 12 months (e.g., unpinned dependencies, API deprecations).
*   **Propagation Impact:** Verify that Tier 1 files contain no machine-specific assumptions.

---

## 🏛️ Part 3: The Industrial Hardening Audit
*Mandatory checks for projects transitioning from Prototype to Production.*

### 1. The "Data Clobber" Guard
Reviewers must verify that any script writing to global or external paths (e.g., `agent-skills-library`) includes:
*   **Path Validation:** Explicit check that the destination directory exists and is valid.
*   **Dry-Run Mandate:** A `--dry-run` flag that parses all logic but performs zero disk writes.
*   **Safety Gate:** Refuse to write if the `target_path` is not explicitly validated against a whitelist of project roots.

**Database Operations (Added 2026-01-27 after 94-task data loss):**

Reviewers must verify that any code performing database DELETE operations includes:
*   **CASCADE Awareness:** Document foreign key relationships. A `DELETE FROM projects` may cascade to tasks, history, etc.
*   **Backup Before Delete:** Bulk deletions (>1 row) must create a backup first (JSON export or table copy).
*   **Confirmation Gate:** Auto-cleanup logic (e.g., "delete stale entries") requires explicit user confirmation, not silent execution.
*   **No Unrequested Cleanup:** Never add "delete items not found" logic without explicit authorization from the Conductor.

**The 2026-01-27 Incident:** An AI added unrequested auto-delete logic to a scan function. When the scan temporarily found zero projects (due to path issues), it deleted all projects, which CASCADE-deleted 94 tasks. This section exists to prevent that class of failure.

### 1b. Feature Authorization (Scope Creep Prevention)
Reviewers must verify that code changes do not introduce unrequested destructive behavior:
*   **Authorization Check:** Any new DELETE, DROP, TRUNCATE, or cleanup logic must trace to an explicit user request.
*   **Scope Boundary:** "Helpful" additions that weren't asked for are defects, not features—especially if destructive.
*   **The Test:** Ask "Did the Conductor explicitly request this behavior?" If no, reject it.

### 2. Subprocess Integrity
Every `subprocess.run` call must follow the **Production Standard**:
*   `check=True`: Fail loudly on non-zero exit codes.
*   `timeout=X`: Never allow a subprocess to hang indefinitely (e.g., `yt-dlp` or `ollama` hangs).
*   `capture_output=True`: Ensure stdout/stderr are captured for telemetry if a failure occurs.

### 3. Frontmatter & Schema Validation
For projects that generate files:
*   **Schema Enforcement:** Generated markdown must be validated against the project's frontmatter taxonomy.
*   **Escape Verbatim:** Verbatim text (like transcripts) must be escaped or truncated to prevent breaking YAML parser logic.

### 4. Test Fixture Integrity
For projects with filesystem or external dependencies:
*   **Isolation Mandate:** All tests must use temporary directories (`tmp_path`, `tempfile`). No tests should read/write to real project paths.
*   **Realistic Structures:** Fixtures must create file structures that mirror production (not empty dirs or single files).
*   **Mock External Calls:** `subprocess.run`, network calls, and system queries must be mocked to prevent flaky tests.
*   **Composable Fixtures:** Build complex fixtures from simpler ones (e.g., `project_with_wikilinks` builds on `project_with_markdown`).
*   **No Weak Assertions:** Tests must verify specific values and behaviors, not just types. `assert isinstance(result, list)` is insufficient; `assert len(result) > 0` and `assert result[0].field == expected` are required.

### 5. Placeholder Integrity (Gate 2)
Every scaffolded project must be validated for unfilled template placeholders:
*   **The Check:** Run `scripts/validate_project.py` or `scripts/audit_all_projects.py`.
*   **The Standard:** Zero results for `{{VAR}}` patterns in any `.md`, `.py`, or `.sh` files.
*   **The Enforcement:** A single unfilled placeholder triggers a **Scaffolding Failure** alert to Discord.

### 6. Silent Failure Prevention (Added 2026-01-27)

> ⚠️ **This section exists because of the 2026-01-27 incident.** The `discover_projects()` function returned an empty list when PROJECTS_ROOT pointed to a non-existent path. No warning was logged. Downstream code interpreted "0 projects" as "delete everything not found." This caused 94 tasks to be CASCADE-deleted.

Functions that discover, scan, or aggregate data must NEVER silently return empty results when the underlying operation failed:

#### 6.1 No Silent Empty Returns
`return []` without logging is a **DEFECT**. If a directory doesn't exist, LOG a warning, don't just return empty.

```python
# ❌ BAD - Silent failure (ACTUAL BUG in project_scanner.py:34-35)
def discover_projects(base_path=None):
    if base_path is None:
        base_path = PROJECTS_BASE_DIR
    base = Path(base_path)

    if not base.exists():
        return []  # DEFECT: No logging, caller has no idea why

    projects = []
    for item in base.iterdir():  # DEFECT: Can raise PermissionError
        # ...

# ✅ GOOD - Explicit failure with logging
def discover_projects(base_path=None):
    if base_path is None:
        base_path = PROJECTS_BASE_DIR
    base = Path(base_path)

    if not base.exists():
        logger.error(f"CRITICAL: Projects directory does not exist: {base}")
        return []  # Logged - caller can see the warning

    if not base.is_dir():
        logger.error(f"CRITICAL: Projects path is not a directory: {base}")
        return []

    projects = []
    try:
        for item in base.iterdir():
            # ...
    except PermissionError as e:
        logger.error(f"Permission denied reading {base}: {e}")
        return []
    except OSError as e:
        logger.error(f"OS error reading {base}: {e}")
        return []
```

#### 6.2 Distinguish "Nothing Found" from "Couldn't Look"
A scanner finding 0 items in a valid directory is different from a scanner failing to read the directory. Use different log levels and messages:

```python
# ✅ GOOD - Distinguishes empty results from failure
def discover_projects(base_path):
    base = Path(base_path)

    # Failure to look - ERROR
    if not base.exists():
        logger.error(f"Cannot scan: directory does not exist: {base}")
        return []

    projects = []
    # ... scanning logic ...

    # Nothing found in valid directory - WARNING (unusual but not an error)
    if len(projects) == 0:
        logger.warning(f"Zero projects found in {base}. Is this expected?")

    return projects
```

#### 6.3 Exception Handling Around Filesystem Iterators
`iterdir()`, `glob()`, and similar operations can raise `PermissionError`, `OSError`. ALWAYS wrap in try/except:

```python
# ❌ BAD - No exception handling (ACTUAL BUG in project_scanner.py:39)
for item in base.iterdir():
    if item.is_dir():
        # ...

# ✅ GOOD - Wrapped with exception handling
try:
    for item in base.iterdir():
        if item.is_dir():
            # ...
except PermissionError as e:
    logger.error(f"Permission denied: {e}")
except OSError as e:
    logger.error(f"OS error during iteration: {e}")
```

#### 6.4 Mandatory Grep Check for Silent Returns
Run this command and verify EVERY match has logging within 3 lines before:
```bash
grep -rn "return \[\]$\|return None$\|return {}$" scripts/ --include="*.py"
```

### 7. Environment Variable Standards

> ⚠️ **This section exists because of the 2026-01-27 incident.** When `PROJECTS_ROOT` pointed to a non-existent directory, the scanner silently returned empty results, which triggered cascade deletion of 94 tasks.

Critical environment variables that affect data paths must be validated at startup:

#### 7.1 The PROJECTS_ROOT Standard
This is the most critical path in the project-tracker. It determines where we scan for projects.

| Requirement | Description |
|-------------|-------------|
| **Validation at startup** | Must check `exists()`, `is_dir()`, and `access(os.R_OK)` |
| **No empty-string fallback** | `Path("")` resolves to cwd, which is NEVER correct for PROJECTS_ROOT |
| **Log the resolved path** | Always log what path is being used for debugging |
| **Fail fast** | If invalid, raise an exception immediately - don't wait for runtime failure |

#### 7.2 Current Defect in config.py

```python
# ❌ BAD - ACTUAL CURRENT CODE (config.py:7)
PROJECTS_BASE_DIR = Path(os.getenv("PROJECTS_ROOT", Path(__file__).resolve().parent.parent))
# Problems:
# 1. No check that the path exists
# 2. No check that it's a directory
# 3. No logging of which path was resolved
# 4. If PROJECTS_ROOT is set to garbage, code proceeds silently

# ✅ GOOD - Proper validation
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def _validate_projects_root() -> Path:
    """Validate and return PROJECTS_ROOT with proper error handling."""
    env_value = os.getenv("PROJECTS_ROOT")

    if env_value:
        base = Path(env_value)
        source = "environment variable"
    else:
        # Explicit default - NOT empty string
        base = Path(__file__).resolve().parent.parent
        source = "default (parent of project-tracker)"
        logger.info(f"PROJECTS_ROOT not set, using {source}: {base}")

    # Validation checks
    if not base.exists():
        raise ValueError(f"PROJECTS_ROOT does not exist: {base} (from {source})")

    if not base.is_dir():
        raise ValueError(f"PROJECTS_ROOT is not a directory: {base} (from {source})")

    if not os.access(base, os.R_OK):
        raise ValueError(f"PROJECTS_ROOT is not readable: {base} (from {source})")

    logger.info(f"PROJECTS_ROOT validated: {base} (from {source})")
    return base

PROJECTS_BASE_DIR = _validate_projects_root()
```

#### 7.3 Other Environment Variables
Apply the same standard to:
- `PT_DB_PATH` - Database path
- `PT_RESOURCES_FILE` - External resources file

#### 7.4 Mandatory Grep Check
```bash
# Find all env var usage
grep -rn "os\.getenv" scripts/ config.py --include="*.py"
# RULE: Each match must have validation logic within 10 lines
```

### 8. Performance Guards

> ⚠️ **This section exists because of the 2026-01-27 incident.** The scanner used unbounded recursive globs (`**/*.py`) which scanned every single file in every project's node_modules, causing extreme slowness and unpredictable behavior.

Filesystem operations that scale with codebase size must be bounded:

#### 8.1 No Unbounded Recursive Globs
The pattern `any(item.glob("**/*.py"))` scans the ENTIRE subtree. For 35+ projects with node_modules, this is **catastrophic**.

```python
# ❌ BAD - ACTUAL CURRENT CODE (project_scanner.py:51-52)
has_python = any(item.glob("**/*.py"))  # Scans ENTIRE subtree
has_js = any(item.glob("**/*.js")) or any(item.glob("**/*.ts"))  # EVEN WORSE - scans twice

# For a project with node_modules containing 50,000+ files, this is catastrophic.
# Multiply by 35 projects = potential for millions of file checks.

# ✅ GOOD - Bounded alternatives
# Option 1: Check only root-level files
has_python = any(item.glob("*.py"))

# Option 2: Check specific known locations
has_python = (item / "setup.py").exists() or (item / "pyproject.toml").exists()

# Option 3: Check one level deep max
has_python = any(item.glob("*.py")) or any(item.glob("*/*.py"))

# Option 4: Use cached metadata from prior scans
# (already stored in database, no need to re-scan filesystem)

# Option 5: Check specific directories only
has_python = any((item / "scripts").glob("*.py")) if (item / "scripts").exists() else False
```

#### 8.2 Performance Impact Table

| Pattern | 35 projects, no node_modules | 35 projects WITH node_modules |
|---------|------------------------------|-------------------------------|
| `*.py` (root only) | ~35 glob ops | ~35 glob ops |
| `*/*.py` (1 level) | ~350 glob ops | ~350 glob ops |
| `**/*.py` (unbounded) | ~1,000 glob ops | **~1,000,000+ file checks** |

#### 8.3 Sanity Checks for Zero Results
If a scanner expects to find items and finds zero, emit a WARNING:

```python
# ❌ BAD - Silent on zero results
projects = discover_projects(PROJECTS_BASE_DIR)
# Proceeds without warning if projects is empty

# ✅ GOOD - Sanity check on zero results
projects = discover_projects(PROJECTS_BASE_DIR)
if len(projects) == 0:
    logger.warning(f"SANITY CHECK: Zero projects found in {PROJECTS_BASE_DIR}. Expected 35+.")
    # Consider: Should we abort destructive operations here?
```

#### 8.4 Mandatory Grep Check for Unbounded Globs
```bash
# Find all unbounded recursive globs
grep -rn '\.glob("\*\*/' scripts/ --include="*.py"
grep -rn "\.glob('\*\*/" scripts/ --include="*.py"
# RULE: Zero tolerance. ALL matches must be fixed.
```

#### 8.5 The Fix Pattern
When you find an unbounded glob, replace with bounded alternative:

```python
# From:
has_python = any(item.glob("**/*.py"))

# To:
has_python = (
    any(item.glob("*.py")) or
    any(item.glob("scripts/*.py")) or
    (item / "setup.py").exists() or
    (item / "pyproject.toml").exists()
)
```

### 9. Defense in Depth (CASCADE Failure Prevention)

> ⚠️ **This section exists because the 2026-01-27 incident required 5 simultaneous failures.** Any single defensive layer would have prevented data loss. This section mandates multiple redundant safety checks.

#### 9.1 The Five Layers of Defense
For any operation that could cause data loss, ALL five layers must be present:

| Layer | Description | 2026-01-27 Status |
|-------|-------------|-------------------|
| **L1: Input Validation** | Validate paths exist, env vars are set | ❌ Failed - PROJECTS_ROOT not validated |
| **L2: Sanity Checks** | Warn on unexpected results (0 projects) | ❌ Failed - No warning on empty results |
| **L3: Explicit Authorization** | Destructive actions require user request | ❌ Failed - Auto-delete was unrequested |
| **L4: Confirmation Gates** | User confirms before destructive actions | ❌ Failed - No confirmation |
| **L5: Recovery Mechanism** | Backups exist before any delete | ✅ Now present - backup_before_delete |

#### 9.2 Minimum Viable Defense
For **any** operation that could delete data, at minimum:
1. **Log what you're about to do** BEFORE doing it
2. **Create a backup** BEFORE deleting
3. **Warn on unexpected inputs** (0 items, non-existent paths)

```python
# ✅ GOOD - Defense in depth for bulk operations
def process_scan_results(discovered_projects):
    existing_projects = db.get_all_projects()
    stale_ids = {p["id"] for p in existing_projects} - {p["id"] for p in discovered_projects}

    # L2: Sanity check
    if len(discovered_projects) == 0:
        logger.warning("SANITY: Zero projects discovered. Aborting any cleanup.")
        return

    # L2: Another sanity check
    if len(stale_ids) > len(discovered_projects):
        logger.warning(f"SANITY: More stale ({len(stale_ids)}) than discovered ({len(discovered_projects)}). Suspicious.")
        return

    # L3: No auto-delete without explicit request
    # L4: Confirmation gate
    if stale_ids:
        logger.info(f"{len(stale_ids)} projects not found in scan (preserved in DB)")
        # DO NOT DELETE - require explicit `./pt remove <project>` command
```

#### 9.3 CASCADE Awareness Requirement
Any code that deletes from a table with foreign keys MUST:
1. Document what will CASCADE
2. Backup ALL related tables
3. Log the full scope of deletion

```python
# ✅ GOOD - CASCADE-aware deletion
def delete_project(project_id):
    """Delete a project and all related data.

    CASCADE IMPACT:
    - tasks: All tasks for this project will be deleted
    - ai_agents: All agents for this project will be deleted
    - cron_jobs: All cron jobs for this project will be deleted
    - service_dependencies: All services for this project will be deleted
    - task_history: All history for project tasks will be deleted
    """
    # Backup ALL related data
    self._backup_before_delete("projects", "id = ?", (project_id,), f"Deleting: {project_id}")
    self._backup_before_delete("tasks", "project_id = ?", (project_id,), f"CASCADE: {project_id}")
    self._backup_before_delete("ai_agents", "project_id = ?", (project_id,), f"CASCADE: {project_id}")
    self._backup_before_delete("cron_jobs", "project_id = ?", (project_id,), f"CASCADE: {project_id}")
    self._backup_before_delete("service_dependencies", "project_id = ?", (project_id,), f"CASCADE: {project_id}")

    # Now safe to delete
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
```

---

## 🏛️ Part 4: Scalability Analysis
*Reviewers must document the "Ceiling" of the current architecture.*

### 1. The Context Window Limit
Any logic that aggregates multiple files (e.g., `synthesize.py` reading an entire library) must be flagged for:
*   **The Truncation Risk:** When does the library size exceed the LLM's context window?
*   **Strategy:** Is there a Map-Reduce, RAG, or Tiered Synthesis plan for scale?

### 2. Repository Bloat
Audit for logic that dumps massive verbatim data (e.g., 2-hour video transcripts) into the main repository. Recommend strategies for externalizing large assets if they don't serve the core LLM reasoning.

---

## 🧠 Part 5: Continual Learning (The Control Loop)
*How we turn "Scars" into "Standards."*

### 1. The "Scar Tissue" SLA
Any new defect type found must be added to the **Robotic Scan** and the **Checklist** within **24 hours**.

### 2. Regression Harnessing
Every bug found must result in a **Reproducer Test** in CI. These tests are the "immune system" of the repo.

### 3. Context-Aware "Mission Orders" (RISEN)
Use the **RISEN Framework** (Role, Instructions, Steps, Expectations, Narrowing) to create a behavioral contract for the auditor.

---

## 📋 Part 6: The Master Review Checklist (Template)

> ⚠️ **Updated 2026-01-27:** Added 10 new checks (C1-C10) specifically for the patterns that caused the 94-task data loss.

### Critical Checks (Added after 2026-01-27 Incident)
| ID | Category | Check Item | Evidence Requirement | Grep Pattern |
|----|----------|------------|----------------------|--------------|
| **C1** | **CRITICAL** | No silent `return []` without logging | Must have `logger.warning/error` within 3 lines before | `grep -rn "return \[\]$" scripts/` |
| **C2** | **CRITICAL** | No unbounded recursive globs | Zero tolerance for `**/*.py` patterns | `grep -rn '\.glob("\*\*/' scripts/` |
| **C3** | **CRITICAL** | Exception handling on `iterdir()` | Every `iterdir()` wrapped in try/except | `grep -rn "\.iterdir()" scripts/` |
| **C4** | **CRITICAL** | PROJECTS_ROOT validated | Check exists(), is_dir() at startup | Review `config.py` |
| **C5** | **CRITICAL** | Zero-result sanity warning | Warn when scanner finds 0 items | Review discover functions |
| **C6** | **CRITICAL** | No unrequested auto-delete | DELETE logic traces to user request | `grep -rn "DELETE FROM" scripts/` |
| **C7** | **CRITICAL** | CASCADE documented | All FK cascades listed in docstring | Review delete functions |
| **C8** | **CRITICAL** | Backup before bulk delete | `_backup_before_delete()` called | Review delete functions |
| **C9** | **CRITICAL** | No silent exception swallowing | Every `except` has logging or re-raise | `grep -rn "except.*:" scripts/ -A1` |
| **C10** | **CRITICAL** | Defense in depth | 5 layers present for destructive ops | See Section 9 |

### Standard Checks (Previously Existing)
| ID | Category | Check Item | Evidence Requirement |
|----|----------|------------|----------------------|
| **M1** | **Robot** | No hardcoded `/Users/` or `/home/` paths | Paste `grep` output (all files) |
| **M2** | **Robot** | No silent `except: pass` patterns | Paste `grep` output (Python files) |
| **M3** | **Robot** | No API keys (`sk-...`) in code/templates | Paste `grep` output |
| **M4** | **Robot** | Zero unfilled `{{VAR}}` placeholders | Paste `validate_project.py` output |
| **P1** | **DNA** | Templates contain no machine-specific data | List files checked in `templates/` |
| **P2** | **DNA** | `.cursorrules` is portable | Verify path placeholders used |
| **T1** | **Tests** | Inverse Audit: What do tests MISS? | Map "Dark Territory" |
| **T2** | **Tests** | No weak assertions (`isinstance`, `is not None` alone) | Grep for assertion patterns |
| **T3** | **Tests** | Every public class/function has test coverage | Coverage report or file audit |
| **T4** | **Tests** | External dependencies mocked (subprocess, network) | Verify `@patch` or mock usage |
| **E1** | **Errors** | Exit codes are accurate (non-zero on fail) | Document manual test of failure path |
| **E2** | **Errors** | No silent failure returns (`return []` without warning) | Grep for `return []`, `return None`, `return {}` - verify logging/warning |
| **E3** | **Errors** | Critical env vars validated at startup | List env vars, verify validation logic exists |
| **E4** | **Errors** | Zero-result sanity checks (warn when 0 items found) | Verify scanner/discovery functions have sanity warnings |
| **D1** | **Deps** | Dependency versions are pinned/bounded | Paste `requirements.txt` snapshot |
| **H1** | **Hardening**| Subprocess `check=True` and `timeout` used | List files/lines checked |
| **H2** | **Hardening**| Dry-run flag implemented for global writes | Verify `--dry-run` logic exists |
| **H3** | **Hardening**| Atomic writes used for critical file updates | Verify temp-and-rename pattern |
| **H4** | **Hardening**| Path Safety (safe_slug + traversal check) | Verify all user-input paths are sanitized |
| **H5** | **Hardening**| CASCADE DELETE documented for all DB deletions | List FK relationships and what cascades |
| **H6** | **Hardening**| Bulk DELETE has backup-before-delete | Verify backup logic in delete functions |
| **H7** | **Hardening**| No unrequested auto-cleanup/delete logic | Grep for DELETE/drop patterns, verify authorization |
| **H8** | **Hardening**| No unbounded recursive globs (`**/*.py`) | Grep for `.glob("**` patterns, verify bounded or cached |
| **H9** | **Hardening**| Exception handling around filesystem iterators | Verify `iterdir()`, `glob()` wrapped in try/except |
| **R1** | **Reviews** | **Active Review Location** | Must be in project root: `CODE_REVIEW_{MODEL}_{VERSION}.md` |
| **R2** | **Reviews** | **Review Archival** | Previous versions MUST be moved to `Documents/archives/reviews/` |
| **S1** | **Scaling** | Context ceiling strategy (Map-Reduce/RAG) | Document the architectural ceiling |
| **S2** | **Scaling** | Memory/OOM guards for unbounded processing | Verify size-aware batching logic |

### Quick Reference Commands
```bash
# Run all critical pattern checks
echo "=== C1: Silent return [] ==="
grep -rn "return \[\]$" scripts/ --include="*.py"

echo "=== C2: Unbounded globs ==="
grep -rn '\.glob("\*\*/' scripts/ --include="*.py"

echo "=== C3: Unhandled iterdir ==="
grep -rn "\.iterdir()" scripts/ --include="*.py"

echo "=== C6: DELETE patterns ==="
grep -rn "DELETE FROM" scripts/ --include="*.py"

echo "=== C9: Silent exceptions ==="
grep -rn "except.*:" scripts/ --include="*.py" -A1 | grep -E "(pass$|return None|return \[\])"
```

---

## 🛠️ Immediate Action Items

### Critical (Must Fix - Caused 2026-01-27 Incident)
- [ ] **#4617:** Fix `project_scanner.py:34-35` - Add logging when base doesn't exist
- [ ] **#4618:** Fix `project_scanner.py:51-52` - Replace unbounded `**/*.py` globs with bounded alternatives
- [ ] **#4619:** Fix `project_scanner.py:39` - Add try/except around `iterdir()`
- [ ] **#4620:** Fix `config.py` - Add PROJECTS_ROOT validation (exists, is_dir, readable)
- [ ] **#4621:** Fix `pt.py:101-102` - Add logging to silent exception handler
- [ ] **#4622:** Update `pre_review_scan.sh` to check for ALL patterns in Section 6-8
- [ ] **#4623:** Create standalone PROJECTS_ROOT validation module

### Previously Completed
- [x] **Task 1:** Finalize `scripts/pre_review_scan.sh` as the mandatory Gate 0.
- [x] **Task 4:** Implement `scripts/audit_all_projects.py` for ecosystem-wide placeholder scanning.
- [x] **Task 5:** Add database safety rules (H5-H7) and incident documentation (2026-01-27).
- [x] **Task 6:** Add silent failure prevention rules (E2-E4, Section 6-8) after code quality audit.

### Pending (Non-Critical)
- [ ] **Task 2:** Refactor `test_scripts_follow_standards.py` to `test_ecosystem_dna_integrity.py`.
- [ ] **Task 3:** Establish the "Vault" protocol for the local `.env` record of API keys.

---
**Protocol Authorized by:** The Phase 5 Judge (Super Manager)
**Strategic Alignment:** Infrastructure (Root)

## Related Documentation

- [Project Workflow](../Project-workflow.md) - master workflow at projects root
- [Doppler Secrets Management](Documents/reference/DOPPLER_SECRETS_MANAGEMENT.md) - secrets management
- [Local Model Learnings](Documents/reference/LOCAL_MODEL_LEARNINGS.md) - local AI
- [Automation Reliability](patterns/automation-reliability.md) - automation
- [Tiered AI Sprint Planning](patterns/tiered-ai-sprint-planning.md) - prompt engineering
- [AI Model Cost Comparison](Documents/reference/MODEL_COST_COMPARISON.md) - AI models
- [Safety Systems](patterns/safety-systems.md) - security
- [Agent Skills Library](../agent-skills-library/README.md) - Agent Skills

