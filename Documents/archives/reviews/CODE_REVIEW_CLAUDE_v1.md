# Code Review Checklist - project-tracker

**Date:** 2026-01-12
**Reviewer:** Claude (Opus 4.5)
**Pre-Review Scan:** ❌ FAILED

---

## PRE-REVIEW SCAN RESULTS

```
Warden Audit: ✅ PASSED (0 Critical, 0 Error, 0 Warning)
Project Validation: ❌ FAILED
```

**Validation Failures:**
1. Missing mandatory directory: `Documents/core`
2. **48 DNA Defects** - Absolute paths found across documentation

---

## TIER 1: PROPAGATION SOURCES (Must Check First)

### Templates (Highest Blast Radius)
- [x] `Documents/templates/CODE_REVIEW.md.template` - No hardcoded paths ✅

### Root Configs (Referenced by Projects)
- [ ] `AGENTS.md` - ❌ **FAIL** - Hardcoded path on line 9:
  ```
  $PROJECTS_ROOT
  ```
- [ ] `.cursorrules` - ❌ **FAIL** - Multiple hardcoded paths:
  - Line 52: `$PROJECTS_ROOT`
  - Line 129: `$PROJECTS_ROOT/`
  - Line 130: `$PROJECTS_ROOT/project-scaffolding/EXTERNAL_RESOURCES.md`
  - Line 134: `project-scaffolding/scripts/validate_project.py`
  - Line 157: `$PROJECTS_ROOT/trading-copilot/PROJECT_PHILOSOPHY.md`
  - Line 158: `$PROJECTS_ROOT/project-scaffolding/`

### Data Files (Used by Scripts)
- [x] No EXTERNAL_RESOURCES.yaml in this project (reads from scaffolding)

**Tier 1 Grade:** ❌ FAIL
**⚠️ BLOCKING: Fix hardcoded paths in AGENTS.md and .cursorrules before continuing**

---

## TIER 2: EXECUTION CRITICAL

### Scripts (scripts/)
- [x] `scripts/pt.py` - Main CLI
- [x] `scripts/pre_review_scan.sh` - Pre-review gate
- [x] `scripts/validate_project.py` - Structure validation
- [x] `scripts/warden_audit.py` - Security audit
- [x] `scripts/discovery/*.py` - Discovery modules

**Checks:**
- [x] No hardcoded paths in `scripts/` directory ✅
- [x] No `except: pass` or silent failures ✅
- [x] Functions have type hints ✅

### Modules
- [x] `dashboard/app.py` - FastAPI dashboard
- [x] `config.py` - Configuration

**Tier 2 Grade:** ✅ PASS

---

## TIER 3: DOCUMENTATION

### Core Docs
- [ ] `README.md` - Contains hardcoded paths (DNA defect)
- [ ] `CLAUDE.md` - Contains hardcoded paths (DNA defect)
- [ ] `TODO.md` - Contains hardcoded paths (DNA defect)
- [ ] `QUICKSTART.md` - Contains hardcoded paths (DNA defect)
- [ ] `USAGE.md` - Contains hardcoded paths (DNA defect)

### Structure
- [ ] Missing `Documents/core/` directory (required by validate_project.py)

### Consistency
- [x] Pattern docs have scar stories ✅
- [x] Review protocol documented ✅

**Tier 3 Grade:** ❌ FAIL (due to hardcoded paths pervasive in docs)

---

## INVERSE TEST ANALYSIS

**Test:** `tests/test_parsers.py`
- **Checks:** Parser functions
- **Doesn't Check:** Hardcoded paths in config files
- **Action Taken:** Warden audit covers this gap

**Test:** `scripts/warden_audit.py`
- **Checks:** Python files for secrets and silent failures
- **Doesn't Check:** Markdown files for hardcoded paths
- **Gap:** validate_project.py covers markdown DNA defects

**Test:** `scripts/validate_project.py`
- **Checks:** Markdown files for absolute paths, structure
- **Doesn't Check:** Python source code paths
- **Gap:** Warden audit covers Python files

**Coverage Assessment:** Tools complement each other well. No major blind spots.

---

## META-REVIEW

- [x] Checked ALL files in templates/ (only 1 template, clean)
- [x] Verified test scope matches claims
- [ ] Scanned for deprecated APIs (pytest not available in environment)
- [x] Verified dependency safety (no external cloud deps)
- [x] Checked exception handling (no silent failures in scripts)
- [x] No assumptions without verification

---

## TEMPORAL RISK ANALYSIS

**What breaks in 6-12 months?**

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Hardcoded paths break on new machine | HIGH | Blocks all users | Fix paths to use $PROJECTS_ROOT |
| `Documents/core/` expectation unclear | MEDIUM | Validation always fails | Document or remove requirement |
| Scaffolding version drift | MEDIUM | Inconsistent standards | Add scaffolding_version tracking |

---

## FINAL GRADE & BLOCKERS

**Overall Grade:** C

**Ship Blockers (Must Fix):**
1. **AGENTS.md:9** - Replace `$PROJECTS_ROOT` with `$PROJECTS_ROOT` or relative reference
2. **.cursorrules:52,129,130,134,157,158** - Remove all absolute paths
3. **Documents/core/** - Either create directory or update validate_project.py expectation
4. **48 markdown files** - Systematic cleanup of absolute paths in documentation

**Recommended Fixes (Nice to Have):**
1. Add `scaffolding_version` field to `00_Index_project-tracker.md`
2. Add pre-commit hook to prevent new hardcoded paths
3. Document which paths should use `$PROJECTS_ROOT` vs relative

**Confidence Level:** High
- Checked everything systematically using pre_review_scan.sh + manual Tier audit
- All tools ran successfully (warden, validate)
- Inverse test analysis completed

**Ready to Propagate:** ❌ NO

---

## SUMMARY

The **execution layer is solid** - scripts are clean, no silent failures, proper type hints. The **governance layer is broken** - AGENTS.md and .cursorrules contain hardcoded paths that will propagate to any project copying from this one.

**Root Cause:** This project predates the "No Hardcoded Paths" standard. The documentation was written with absolute paths that were fine for single-machine use but violate portability requirements.

**Recommended Action:**
1. Create a `scripts/fix_hardcoded_paths.py` utility to systematically replace `$PROJECTS_ROOT` with `$PROJECTS_ROOT`
2. Run across all affected files
3. Re-run `./scripts/pre_review_scan.sh` to verify
4. Then this project is ready to be a proper scaffolding child

---

*This review follows the v1.1 Ecosystem Governance & Review Protocol.*
*Reviewed using: `Documents/templates/CODE_REVIEW.md.template`*


## Related Documentation

- [Code Review Anti-Patterns](Documents/reference/CODE_REVIEW_ANTI_PATTERNS.md) - code review
- [Doppler Secrets Management](Documents/reference/DOPPLER_SECRETS_MANAGEMENT.md) - secrets management

