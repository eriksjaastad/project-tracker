# Code Review Checklist - project-tracker

**Date:** 2026-01-13
**Reviewer:** Claude (Opus 4.5)
**Pre-Review Scan:** PARTIAL PASS
**Previous Review:** v1 (2026-01-12) - Archived to Documents/archives/reviews/

---

## PRE-REVIEW SCAN RESULTS

```
Warden Audit: 1 P1-ERROR (scripts/fix_portability.py - intentional)
Project Validation: 1 DNA Defect (REVIEWS_AND_GOVERNANCE_PROTOCOL.md - example text)
```

**Notes on Scan Results:**
- The `fix_portability.py` error is a FALSE POSITIVE - the script contains the search string it replaces
- The `REVIEWS_AND_GOVERNANCE_PROTOCOL.md` defect is documentation showing what NOT to do

---

## V1 ISSUES - STATUS

| Issue | Status | Notes |
|-------|--------|-------|
| AGENTS.md hardcoded paths | FIXED | Now uses `$PROJECTS_ROOT` |
| .cursorrules hardcoded paths | FIXED | Now uses `$PROJECTS_ROOT` |
| Documents/core/ missing | FIXED | Removed from validation requirements |
| 48 markdown DNA defects | MOSTLY FIXED | Core docs now portable |

---

## TIER 1: PROPAGATION SOURCES (Must Check First)

### Templates (Highest Blast Radius)
- [x] `Documents/templates/CODE_REVIEW.md.template` - No hardcoded paths

### Root Configs (Referenced by Projects)
- [x] `AGENTS.md` - Uses `$PROJECTS_ROOT` correctly
- [x] `.cursorrules` - Uses `$PROJECTS_ROOT` correctly
- [x] `.cursorignore` - Appropriate exclusions

### Data Files (Used by Scripts)
- [x] No EXTERNAL_RESOURCES.yaml in this project (reads from scaffolding)

**Tier 1 Grade:** PASS

---

## TIER 2: EXECUTION CRITICAL

### Scripts (scripts/)
- [x] `scripts/pt.py` - Main CLI, clean
- [x] `scripts/warden_audit.py` - Proper subprocess handling with timeout
- [x] `scripts/validate_project.py` - Uses env vars correctly
- [x] `scripts/discovery/*.py` - Most modules clean

**Checks:**
- [x] No `except: pass` or silent failures
- [x] Functions have type hints
- [x] subprocess calls have timeouts (mostly)

### Issues Found:

**1. agent_registry.py - Hardcoded Paths (P1-ERROR)**

| Line | Issue | Fix Required |
|------|-------|--------------|
| 37 | `Path.home() / "projects" / "audit-agent"` | Use `PROJECTS_ROOT` env var |
| 162 | `cwd=str(Path.home() / "projects")` | Use `PROJECTS_ROOT` env var |

```python
# Current (bad):
audit_path = str(Path.home() / "projects" / "audit-agent" / "audit")

# Should be:
import os
projects_root = os.getenv("PROJECTS_ROOT", str(Path.home() / "projects"))
audit_path = str(Path(projects_root) / "audit-agent" / "audit")
```

**2. dashboard/app.py - Missing Subprocess Timeouts (P2-WARNING)**

| Lines | Function | Issue |
|-------|----------|-------|
| 324-328 | `create_index()` | No timeout on subprocess.run |
| 337-341 | `create_index()` | No timeout on rescan subprocess.run |

These could hang indefinitely if the subprocess stalls.

### Modules (dashboard/)
- [x] `dashboard/app.py` - FastAPI dashboard (see subprocess issues above)
- [x] `config.py` - Uses env var with fallback correctly

### Governance
- [ ] `.git/hooks/pre-commit` - NOT INSTALLED (P2-WARNING)
  - Script exists at `scripts/git-pre-commit.sh`
  - Not linked to `.git/hooks/pre-commit`
  - Fix: `ln -sf ../../scripts/git-pre-commit.sh .git/hooks/pre-commit`

**Tier 2 Grade:** CONDITIONAL PASS (fix agent_registry.py paths)

---

## TIER 3: DOCUMENTATION

### Core Docs
- [x] `README.md` - Uses `$PROJECTS_ROOT` correctly
- [x] `CLAUDE.md` - Clean, proper instructions
- [x] `TODO.md` - Portable
- [x] `QUICKSTART.md` - Uses relative paths
- [x] `USAGE.md` - Uses `$PROJECTS_ROOT`

### Structure
- [x] `Documents/` directory properly organized
- [x] Archives directory contains previous reviews

### Consistency
- [x] Pattern docs have scar stories
- [x] Review protocol documented
- [x] Template is portable

**Tier 3 Grade:** PASS

---

## INVERSE TEST ANALYSIS

**Test:** `tests/test_parsers.py`
- **Checks:** TODO parser functions (status extraction, completion calculation)
- **Doesn't Check:**
  - Discovery modules (project_scanner, git_metadata)
  - Database operations
  - Dashboard endpoints
  - Subprocess error handling
- **Gap Assessment:** Limited test coverage for core discovery logic

**Tool:** `scripts/warden_audit.py`
- **Checks:** Python files for secrets, silent failures, hardcoded paths
- **Doesn't Check:**
  - `Path.home() / "projects"` pattern (only catches `/Users/` prefix)
  - Markdown files for documentation examples
- **Gap Assessment:** Should detect `Path.home() / "projects"` as non-portable

**Tool:** `scripts/validate_project.py`
- **Checks:** Markdown files for absolute paths, project structure
- **Doesn't Check:** Python source code paths using Path.home()
- **Gap Assessment:** Warden should catch Python, but doesn't catch Path.home() patterns

**Coverage Assessment:**
- Moderate gap: Neither tool catches `Path.home() / "projects"` pattern
- Recommendation: Add regex for `Path\.home\(\).*projects` to warden_audit.py

---

## META-REVIEW

- [x] Checked ALL files in templates/ (1 template, clean)
- [x] Verified test scope matches claims
- [x] Scanned for deprecated APIs (dependencies are current)
- [x] Verified dependency safety (all pinned in requirements.txt)
- [x] Checked exception handling (no silent failures)
- [x] No assumptions without verification
- [x] Verified v1 fixes were applied correctly

---

## TEMPORAL RISK ANALYSIS

**What breaks in 6-12 months?**

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| `Path.home() / "projects"` breaks on different machine | HIGH | Agent dispatcher fails | Use PROJECTS_ROOT env var |
| Subprocess hangs in dashboard | LOW | Browser timeout | Add timeout parameter |
| Pre-commit hook not active | MEDIUM | Bad commits allowed | Link the hook file |
| Test coverage gaps | MEDIUM | Regressions undetected | Expand test suite |

---

## FINAL GRADE & BLOCKERS

**Overall Grade:** B+

**Ship Blockers (Must Fix):**
1. **scripts/discovery/agent_registry.py:37** - Replace `Path.home() / "projects"` with env var lookup
2. **scripts/discovery/agent_registry.py:162** - Replace hardcoded cwd with env var lookup

**Recommended Fixes (Nice to Have):**
1. **dashboard/app.py:324-341** - Add `timeout=30` to subprocess.run calls
2. **Pre-commit hook** - Run `ln -sf ../../scripts/git-pre-commit.sh .git/hooks/pre-commit`
3. **warden_audit.py** - Add detection for `Path.home() / "projects"` pattern
4. **Test coverage** - Add tests for discovery modules

**Confidence Level:** High
- Systematic tiered audit completed
- All tools ran successfully
- Inverse test analysis completed
- V1 fixes verified

**Ready to Propagate:** YES (after fixing ship blockers)

---

## SUMMARY

**Major improvement from v1.** The core propagation sources (AGENTS.md, .cursorrules) are now clean and portable. The execution layer remains solid with no silent failures.

**Remaining Issue:** The `agent_registry.py` module has two hardcoded `Path.home() / "projects"` references that bypass the `PROJECTS_ROOT` environment variable pattern used elsewhere. This will break the Agent Dispatcher feature on machines with different project directory layouts.

**Root Cause:** The agent_registry.py was added in Phase 4 after the portability fixes were applied to the main codebase, so it didn't receive the same treatment.

**Fix Complexity:** Low - Two line changes to use `os.getenv("PROJECTS_ROOT", ...)` pattern.

---

## DIFF FROM V1

| Category | V1 | V2 | Delta |
|----------|----|----|-------|
| Tier 1 Grade | FAIL | PASS | +1 tier |
| Tier 2 Grade | PASS | CONDITIONAL PASS | Minor regression (new code) |
| Tier 3 Grade | FAIL | PASS | +1 tier |
| Overall Grade | C | B+ | +2 grades |
| Ship Blockers | 4 | 2 | -2 blockers |

---

*This review follows the v1.2 Ecosystem Governance & Review Protocol.*
*Reviewed using: `Documents/templates/CODE_REVIEW.md.template`*
