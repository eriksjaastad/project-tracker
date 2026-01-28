# Complete Violation Inventory - 2026-01-28

**Purpose:** Actionable fix list for all governance protocol violations discovered during post-incident audit.
**Total Violations:** 52 instances across 15 files

---

## Summary Table

| Category | Count | Severity | Files Affected |
|----------|-------|----------|----------------|
| C1: Silent `return []` | 9 | CRITICAL | 6 files |
| C2: Unbounded globs | 3 | CRITICAL | 2 files |
| C3: Unhandled `iterdir()` | 12 | HIGH | 7 files |
| C4: Unvalidated `os.getenv` | 14 | HIGH | 6 files |
| C9: Silent exceptions | 28 | MEDIUM-HIGH | 9 files |

---

## C1: Silent `return []` Without Logging (9 instances)

**Rule:** Every `return []` must have `logger.warning()` or `logger.error()` within 3 lines before.

| # | File | Line | Context | Fix |
|---|------|------|---------|-----|
| 1 | `scripts/discovery/project_scanner.py` | 35 | `if not base.exists(): return []` | Add `logger.error(f"CRITICAL: Projects directory does not exist: {base}")` before return |
| 2 | `scripts/discovery/providers.py` | 88 | Inside exception handler | Add logging before return |
| 3 | `scripts/discovery/providers.py` | 97 | Inside exception handler | Add logging before return |
| 4 | `scripts/discovery/telemetry_reader.py` | 41 | Unknown context | Read file, add logging |
| 5 | `scripts/discovery/telemetry_reader.py` | 71 | Unknown context | Read file, add logging |
| 6 | `scripts/discovery/hygiene_detector.py` | 17 | Unknown context | Read file, add logging |
| 7 | `scripts/discovery/hygiene_detector.py` | 23 | Unknown context | Read file, add logging |
| 8 | `scripts/discovery/backup_reader.py` | 76 | Unknown context | Read file, add logging |
| 9 | `scripts/db/manager.py` | 390 | `get_activity()` placeholder | Add `logger.debug("Activity feed not implemented")` or remove TODO |

---

## C2: Unbounded Recursive Globs (3 instances)

**Rule:** Zero tolerance. Replace `**/*.py` with bounded alternatives.

| # | File | Line | Current Code | Fix |
|---|------|------|--------------|-----|
| 1 | `scripts/discovery/project_scanner.py` | 51 | `any(item.glob("**/*.py"))` | Replace with `any(item.glob("*.py")) or (item / "setup.py").exists() or (item / "pyproject.toml").exists()` |
| 2 | `scripts/discovery/project_scanner.py` | 52 | `any(item.glob("**/*.js")) or any(item.glob("**/*.ts"))` | Replace with `any(item.glob("*.js")) or (item / "package.json").exists()` |
| 3 | `scripts/discovery/journal_specialist.py` | 38 | `JOURNAL_DIR.glob("**/*.md")` | Replace with bounded depth or specific subdirs |

---

## C3: Unhandled `iterdir()` (12 instances)

**Rule:** Every `iterdir()` must be wrapped in `try/except (PermissionError, OSError)` with logging.

| # | File | Line | Fix |
|---|------|------|-----|
| 1 | `scripts/discovery/project_scanner.py` | 39 | Wrap in try/except with logging |
| 2 | `scripts/pt.py` | 124 | Wrap in try/except with logging |
| 3 | `scripts/validate_project.py` | 69 | Wrap in try/except with logging |
| 4 | `scripts/discovery/journal_specialist.py` | 26 | Wrap in try/except with logging |
| 5 | `scripts/discovery/librarian.py` | 334 | Wrap in try/except with logging |
| 6 | `scripts/discovery/librarian.py` | 343 | Wrap in try/except with logging |
| 7 | `scripts/discovery/librarian.py` | 482 | Wrap in try/except with logging |
| 8 | `scripts/discovery/librarian.py` | 575 | Wrap in try/except with logging |
| 9 | `scripts/doc_audit.py` | 214 | Wrap in try/except with logging |
| 10 | `scripts/doc_audit.py` | 313 | Wrap in try/except with logging |
| 11 | `scripts/doc_audit_v2.py` | 151 | Wrap in try/except with logging |
| 12 | `scripts/doc_audit_v2.py` | 981 | Wrap in try/except with logging |

**Fix Template:**
```python
# BEFORE
for item in directory.iterdir():
    # ...

# AFTER
try:
    for item in directory.iterdir():
        # ...
except PermissionError as e:
    logger.error(f"Permission denied reading {directory}: {e}")
except OSError as e:
    logger.error(f"OS error reading {directory}: {e}")
```

---

## C4: Unvalidated `os.getenv` for Critical Paths (14 instances)

**Rule:** Critical path env vars must validate `exists()`, `is_dir()` at startup.

| # | File | Line | Env Var | Fix |
|---|------|------|---------|-----|
| 1 | `config.py` | 7 | `PROJECTS_ROOT` | **PRIORITY 1** - Add validation function |
| 2 | `config.py` | 10 | `PT_DB_PATH` | Add exists check for parent dir |
| 3 | `config.py` | 14 | Unknown | Review and validate |
| 4 | `config.py` | 25 | `PT_AUDIT_BIN` | Already has exists check - OK |
| 5 | `scripts/discovery/graph_builder.py` | 21 | `PROJECTS_ROOT` | Duplicate - use config.py instead |
| 6 | `scripts/discovery/librarian.py` | 71 | `PROJECTS_ROOT` | Duplicate - use config.py instead |
| 7 | `scripts/discovery/librarian.py` | 476 | `PROJECTS_ROOT` | Duplicate - use config.py instead |
| 8 | `scripts/discovery/cron_health.py` | 13 | `PROJECTS_ROOT` | Duplicate - use config.py instead |
| 9 | `scripts/discovery/cron_health.py` | 17-21 | Multiple | Review trading arena paths |
| 10 | `scripts/discovery/agent_registry.py` | 11 | `PROJECTS_ROOT` | Duplicate - use config.py instead |
| 11 | `scripts/discovery/telemetry_reader.py` | 16 | `TELEMETRY_PATH` | Add exists check |
| 12 | `scripts/discovery/backup_reader.py` | 11 | `RCLONE_CONFIG_PATH` | Add exists check |
| 13 | `scripts/validate_project.py` | 27 | `PROJECTS_ROOT` | Duplicate - use config.py instead |

**Note:** There are 6 different files defining their own `PROJECTS_ROOT`. This should be centralized to `config.py` with proper validation.

---

## C9: Silent Exception Swallowing (28 instances)

**Rule:** Every `except` block must either log or re-raise. No bare `pass`.

### schema.py (15 instances - lines 133-305)
All are `except sqlite3.OperationalError: pass` in migration code.
**Assessment:** These may be intentional (idempotent migrations). Add comment explaining why, or add `logger.debug()`.

### doc_audit_v2.py (4 instances)
| Line | Current | Fix |
|------|---------|-----|
| 347-348 | `except: pass` | Add `logger.warning()` or specific exception |
| 514-515 | `except: pass` | Add `logger.warning()` or specific exception |
| 837-838 | `except: pass` | Add `logger.warning()` or specific exception |
| 1017-1018 | `except Exception: pass` | Add `logger.warning()` or specific exception |

### warden_audit.py (2 instances)
| Line | Current | Fix |
|------|---------|-----|
| 85-86 | `except Exception: pass` | Add `logger.warning()` - this is the AUDIT TOOL itself |
| 95-96 | `except Exception: pass` | Add `logger.warning()` |

### Other files
| File | Line | Fix |
|------|------|-----|
| `graph_builder.py` | 316-317 | Add logging |
| `journal_specialist.py` | 54-55 | Add logging (currently `return`) |
| `librarian.py` | 305-306 | Add logging |
| `providers.py` | 170-171, 184-185 | Add logging |
| `project_scanner.py` | 205-206 | Add logging |
| `validate_project.py` | 302-303 | Add logging |

---

## Priority Order for Fixes

### P0 - CRITICAL (Caused the incident)
1. `project_scanner.py:35` - Silent return when base doesn't exist
2. `project_scanner.py:51-52` - Unbounded globs
3. `project_scanner.py:39` - Unhandled iterdir
4. `config.py:7` - PROJECTS_ROOT not validated

### P1 - HIGH (Same pattern, different files)
5. All other `iterdir()` instances (11 remaining)
6. All other `return []` instances (8 remaining)
7. Centralize PROJECTS_ROOT to config.py (6 duplicates)

### P2 - MEDIUM (Exception handling)
8. `warden_audit.py` silent exceptions (audit tool itself)
9. All other silent exceptions (26 remaining)

### P3 - LOW (Cleanup)
10. `journal_specialist.py:38` unbounded glob (lower traffic)
11. schema.py migrations (document why pass is OK, or add debug logging)

---

## Verification Commands

After fixes, run these to verify zero violations:

```bash
# Should return 0 lines (or only documented exceptions)
grep -rn "return \[\]$" scripts/ --include="*.py" | grep -v "# LOGGED"

# Should return 0 lines
grep -rn '\.glob("\*\*' scripts/ --include="*.py"

# Should return 0 lines (all wrapped in try/except)
# Manual review required

# Should return 0 lines
grep -rn "except.*:" scripts/ --include="*.py" -A1 | grep -E "pass$" | grep -v "# INTENTIONAL"
```

---

## Files Requiring Changes (by priority)

| Priority | File | Changes Needed |
|----------|------|----------------|
| P0 | `scripts/discovery/project_scanner.py` | Lines 35, 39, 51-52, 205-206 |
| P0 | `config.py` | Line 7 - add validation |
| P1 | `scripts/pt.py` | Line 101-102, 124 |
| P1 | `scripts/discovery/librarian.py` | Lines 71, 305, 334, 343, 476, 482, 575 |
| P1 | `scripts/validate_project.py` | Lines 27, 69, 302-303 |
| P1 | `scripts/discovery/providers.py` | Lines 88, 97, 170-171, 184-185 |
| P2 | `scripts/warden_audit.py` | Lines 85-86, 95-96 |
| P2 | `scripts/doc_audit_v2.py` | Lines 151, 347, 514, 837, 981, 1017 |
| P2 | `scripts/doc_audit.py` | Lines 214, 313 |
| P2 | `scripts/db/schema.py` | Lines 133-305 (15 instances) - document or log |
| P2 | `scripts/discovery/graph_builder.py` | Lines 21, 316-317 |
| P2 | `scripts/discovery/journal_specialist.py` | Lines 26, 38, 54-55 |
| P2 | `scripts/discovery/telemetry_reader.py` | Lines 16, 41, 71 |
| P2 | `scripts/discovery/backup_reader.py` | Lines 11, 76 |
| P2 | `scripts/discovery/hygiene_detector.py` | Lines 17, 23 |
| P2 | `scripts/discovery/cron_health.py` | Lines 13, 17, 21 |
| P2 | `scripts/discovery/agent_registry.py` | Line 11 |

---

**Document Created:** 2026-01-28
**Created By:** Claude Code audit
**Next Step:** Fix P0 items, then re-run verification commands
