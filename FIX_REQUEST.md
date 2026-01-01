# Fix Request: Remaining Code Review Issues

## Before You Start

Pull the latest code review from the `claude/code-review-project-E8TqD` branch:

```bash
git fetch origin claude/code-review-project-E8TqD
git merge origin/claude/code-review-project-E8TqD
```

Read `CODE_REVIEW.md` in the project root for full context.

---

## Issues to Fix

### 1. work_log Table Crash Bug (CRITICAL)

**Problem:** The `work_log` table creation is commented out in `schema.py`, but `log_event()` and `get_work_log()` methods still exist in `manager.py` and are actively called from `pt.py:115`. This will crash on any fresh database.

**Fix:** Remove ALL work_log code entirely. Do not comment it out - delete it.

Files to modify:
- `scripts/db/schema.py` - Delete the commented-out work_log table creation (lines ~103-113) and index (lines ~141-144)
- `scripts/db/manager.py` - Delete `log_event()` method and `get_work_log()` method entirely
- `scripts/pt.py` - Delete the call to `db.log_event()` at line 115
- `dashboard/app.py` - Check for and remove any `get_work_log()` calls

**Verification:**
```bash
grep -rn "work_log\|log_event\|get_work_log" scripts/ dashboard/ --include="*.py"
# Must return: zero results
```

---

### 2. Hardcoded Path in app.py (CRITICAL)

**Problem:** `dashboard/app.py:288` still has a hardcoded path:
```python
script_path = "/Users/eriksjaastad/projects/project-scaffolding/scripts/reindex_projects.py"
```

**Fix:** Move this to `config.py` as an environment variable with a sensible default, or remove the feature if the script doesn't exist.

**Verification:**
```bash
grep -rn "/Users/" scripts/ dashboard/ --include="*.py" | grep -v config.py
# Must return: zero results
```

---

### 3. Database Connection Leaks

**Problem:** Every method in `manager.py` does:
```python
conn = self._get_conn()
cursor = conn.cursor()
# ... operations that can throw ...
conn.close()
```

If an exception occurs, the connection is never closed.

**Fix:** Use context managers or try/finally:
```python
def some_method(self):
    conn = self._get_conn()
    try:
        cursor = conn.cursor()
        # ... operations ...
        conn.commit()
    finally:
        conn.close()
```

Or even better, make `_get_conn()` return a context manager.

**Verification:** Every method that calls `_get_conn()` must have the `conn.close()` in a `finally` block or use `with`.

---

### 4. Timezone Mixing

**Problem:** Code compares timezone-aware datetimes with naive `datetime.now()`:
- `scripts/discovery/alert_detector.py:28-30`
- `dashboard/app.py:40`

**Fix:** Use consistent timezone handling. Either:
- Strip timezone info when parsing: `datetime.fromisoformat(iso_date.replace('Z', '').split('+')[0])`
- Or use timezone-aware now: `datetime.now(timezone.utc)`

---

## House Rules

### No Commented-Out Code

Do not leave commented-out code in the codebase. If code is not needed, delete it. Comments like these are not acceptable:

```python
# cursor.execute("""CREATE TABLE IF NOT EXISTS work_log...""")
# This feature was removed
# Old implementation:
# def old_function():
#     pass
```

If you need to preserve history, that's what git is for. The codebase should only contain code that runs.

**Verification:**
```bash
# Check for suspicious commented code blocks
grep -rn "^#.*cursor.execute\|^#.*def \|^#.*CREATE TABLE" scripts/ dashboard/ --include="*.py"
# Should return: zero results (or only legitimate comments)
```

### No Dead Code

If a function is not called, delete it. If a variable is not used, delete it. If a feature is deprecated, remove it entirely - don't leave skeleton code behind.

---

## Definition of Done

All of these must pass:

```bash
# 1. No work_log references
grep -rn "work_log\|log_event\|get_work_log" scripts/ dashboard/ --include="*.py"
# Returns: nothing

# 2. No hardcoded paths outside config
grep -rn "/Users/" scripts/ dashboard/ --include="*.py" | grep -v config.py
# Returns: nothing

# 3. No commented-out table definitions
grep -rn "^#.*CREATE TABLE" scripts/ --include="*.py"
# Returns: nothing

# 4. Tests still pass
pytest tests/ -v
# Returns: all pass
```

---

## After Fixing

1. Run all verification commands above
2. Run the dashboard: `./pt launch`
3. Verify it starts without errors
4. Commit with message: `[Project Tracker] Remove dead code and fix remaining review issues`
