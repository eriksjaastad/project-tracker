# Code Review: project-tracker

**Reviewer:** Claude Opus 4.5
**Date:** 2026-01-01
**Verdict:** Functional for personal use, needs fixes before sharing
**Status:** Pending fixes

## Summary

The project-tracker is well-structured and accomplishes its goals, but has several issues ranging from a latent crash bug to hardcoded paths that would break on any other machine. The core architecture is sound.

---

## Critical Issues

### 1. work_log Table is Broken
- **Location:** `scripts/db/schema.py:103-113`, `scripts/db/manager.py:264-306`
- **Issue:** The `work_log` table creation is commented out, but `log_event()` and `get_work_log()` methods still exist and are called from `pt.py:115`
- **Impact:** Will crash on any fresh database when scan runs
- **Action:** [ ] Either uncomment table creation or remove dead methods

### 2. Database Connections Leak on Exceptions
- **Location:** `scripts/db/manager.py` (all methods)
- **Issue:** Pattern `conn = self._get_conn(); ...; conn.close()` without try/finally or context manager
- **Impact:** Connection leaks if any operation throws
- **Action:** [ ] Use `with self._get_conn() as conn:` pattern

### 3. Hardcoded Paths
- **Location:** `config.py:7`, `dashboard/app.py:288`
- **Issue:** Literal paths like `/Users/eriksjaastad/projects` baked into code
- **Impact:** Won't work on any other machine
- **Action:** [ ] Move all paths to environment variables with sensible defaults

### 4. Timezone Mixing
- **Location:** `scripts/discovery/alert_detector.py:28-30`, `dashboard/app.py:40`
- **Issue:** Comparing timezone-aware datetimes with naive `datetime.now()`
- **Impact:** Warnings or incorrect comparisons depending on Python version
- **Action:** [ ] Use consistent timezone handling throughout

---

## Medium Issues

### 5. No Transaction Safety in scan()
- **Location:** `scripts/pt.py:91-112`
- **Issue:** Deletes then recreates related data without transaction wrapper
- **Impact:** Crash mid-scan leaves inconsistent state
- **Action:** [ ] Wrap in database transaction

### 6. sys.path Manipulation is Fragile
- **Location:** Most files
- **Issue:** `sys.path.insert(0, ...)` used throughout instead of proper package structure
- **Impact:** Import order issues, harder to test, not installable
- **Action:** [ ] Convert to proper package with `__init__.py` files

### 7. Duplicate Code
- **Location:** `dashboard/app.py:36`, `scripts/discovery/cron_monitor.py:268`
- **Issue:** `format_time_ago()` defined twice identically
- **Location:** `scripts/pt.py:192-197, 305-309, 326-330, 349-352`
- **Issue:** Project lookup by name copy-pasted 4 times
- **Action:** [ ] Extract to shared utilities

### 8. Test Coverage is Minimal
- **Location:** `tests/test_parsers.py`
- **Issue:** Only 5 tests exist, covering ~10% of code
- **Missing:** Database ops, alert detection, cron monitoring, dashboard routes
- **Action:** [ ] Add tests for critical paths

### 9. discover_projects() is Inefficient
- **Location:** `scripts/discovery/project_scanner.py:50-51`
- **Issue:** `any(item.glob("**/*.py"))` scans entire directory tree per project
- **Impact:** Slow on large directories
- **Action:** [ ] Use shallow check or limit depth

### 10. Dead Code
- **Location:** `scripts/pt.py:252`
- **Issue:** `no_browser = False` hardcoded but never exposed as CLI flag
- **Action:** [ ] Either add CLI flag or remove variable

---

## Minor Issues

### 11. Dashboard Binds to 0.0.0.0
- **Location:** `scripts/pt.py:289`
- **Issue:** Exposes dashboard to network; `127.0.0.1` safer for local tool
- **Action:** [ ] Change to localhost or make configurable

### 12. No Input Validation
- **Location:** `scripts/pt.py` CLI commands
- **Issue:** `add_agent`, `add_cron` accept empty names, invalid schedules
- **Action:** [ ] Add validation

### 13. Magic Numbers
- **Locations:** Various
- **Issue:** 60 days, 100 lines, 200 chars used without named constants
- **Action:** [ ] Define as constants in config

---

## What's Done Well

- Parameterized SQL queries throughout (prevents injection)
- Whitelist validation on dynamic SQL columns in `manager.py`
- Consistent use of type hints on public functions
- Clear module separation and single responsibility
- Error logging with context instead of silent failures
- Comprehensive TODO.md parsing logic
- Good alert categorization and severity levels

---

## Checklist

- [ ] Fix work_log table (critical)
- [ ] Add context managers for DB connections (critical)
- [ ] Remove hardcoded paths (critical)
- [ ] Fix timezone handling (critical)
- [ ] Add transaction safety to scan()
- [ ] Refactor to proper package structure
- [ ] Extract duplicate code
- [ ] Add tests for database and alert detection
- [ ] Optimize project discovery
- [ ] Clean up dead code
- [ ] Bind dashboard to localhost
- [ ] Add input validation
- [ ] Define magic numbers as constants

---

*Review conducted by analyzing all source files in the repository.*
