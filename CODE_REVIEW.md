# Code Review Results: Project Tracker MVP

**Reviewer:** Grumpy Senior Principal Engineer
**Date:** December 30, 2025
**Verdict:** **NEEDS MAJOR REFACTOR** - Good ideas, bad execution

---

## The Verdict

This is a **$1000 solution to a $10 problem** that also has **SQL injection vulnerabilities** and **will break the moment you try to run it on any machine other than yours**.

The core idea is fine. The execution has fundamental flaws that need fixing before you write another line of code.

---

## 10 Failure Modes (Specific, With Citations)

### 1. SQL Injection in `manager.py:69`
```python
query = f"SELECT * FROM projects ORDER BY {order_by}"
cursor.execute(query)
```
The `order_by` parameter is directly interpolated into SQL. Called from `app.py:161` with user-controllable value `"last_modified DESC"`. If anyone ever makes this web-accessible or adds a sort parameter to the UI, you've got SQL injection.

**Also in `manager.py:85-88`:**
```python
fields = ", ".join(f"{key} = ?" for key in kwargs.keys())
cursor.execute(f"UPDATE projects SET {fields} WHERE id = ?", values)
```
Field names from kwargs go straight into SQL. Not exploitable right now, but a landmine.

### 2. Hardcoded Paths That Break Immediately

**`project_scanner.py:11`:**
```python
def discover_projects(base_path: str = "/Users/eriksjaastad/projects") -> List[Dict[str, Any]]:
```

**`external_resources_parser.py:15`:**
```python
resources_path = Path("/Users/eriksjaastad/projects/project-scaffolding/EXTERNAL_RESOURCES.md")
```

**`pt.py:45`:**
```python
path = "/Users/eriksjaastad/projects"
```

This code is **useless on any other machine**. It's not even configurable. The moment you share this or move directories, everything breaks.

### 3. Silent Failures Hide Every Bug

**`todo_parser.py:22-30`:** Exception swallowed, returns defaults
**`project_scanner.py:106-107`:** `except Exception: pass`
**`alert_detector.py:31-32`:** `except Exception: pass`
**`alert_detector.py:113-114`:** `except Exception: pass`
**`git_metadata.py:27-28`:** `except (..., Exception): pass`
**`git_metadata.py:49-50`:** `except Exception: pass`
**`cron_monitor.py:121-123`:** `except Exception: return False, None`
**`cron_monitor.py:202-203`:** `except Exception: return None, None`

When something goes wrong, you'll have **zero idea** what happened. The system will just show wrong data and you'll trust it.

### 4. N+1 Query Problem Tanks Performance

**`app.py:134-154` - `enrich_project_data()`:**
```python
def enrich_project_data(project: dict, db: DatabaseManager) -> dict:
    agents = db.get_ai_agents(project["id"])      # Query 1
    jobs = db.get_cron_jobs(project["id"])        # Query 2
    services = db.get_services(project["id"])     # Query 3
```

Called in a loop at `app.py:164`:
```python
enriched_projects = [enrich_project_data(p, db) for p in projects]
```

**33 projects × 3 queries = 99 queries per page load.** Add the initial query, that's 100 database round-trips to load the dashboard.

### 5. Database Connection Churn

**`manager.py:18-22`:**
```python
def _get_conn(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

Every. Single. Operation. Opens a new connection. Look at any method - they all do `conn = self._get_conn()` then `conn.close()`. No connection reuse, no context managers for cleanup on exceptions.

### 6. TODO.md Format Changes Break Everything

**`todo_parser.py:45-50`:**
```python
if "Project Status:" in line or "**Project Status:**" in line:
    data["status"] = extract_status(line)
elif "Current Phase:" in line or "**Current Phase:**" in line:
    data["phase"] = extract_phase(line)
```

This is string matching, not parsing. If someone writes `**Status:**` instead of `**Project Status:**`, it won't match. No warning, no error - just wrong data.

### 7. EXTERNAL_RESOURCES.md Regex Will Explode

**`external_resources_parser.py:28-36`:**
```python
section_match = re.search(r"## Resources by Project\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
# ...
project_pattern = r"###\s+([^\n]+)\n((?:(?!###)[\s\S])*?)(?=\n###|\Z)"
```

Regex on markdown. The moment that file's format changes even slightly - different heading levels, extra whitespace, nested sections - this silently returns empty results.

### 8. Cron Monitor Runs Subprocess With No Error Handling

**`cron_monitor.py:102-107`:**
```python
result = subprocess.run(
    ["crontab", "-l"],
    capture_output=True,
    text=True,
    timeout=5
)
```

What if `crontab` doesn't exist? What if the user has no crontab? The timeout is good, but the error handling at line 121-123 just returns `False, None` with no indication of why.

### 9. `rglob("*")` on Large Projects is a Performance Bomb

**`git_metadata.py:38-44`:**
```python
for item in project_path.rglob("*"):
    if item.is_file():
        if any(part in [".git", "node_modules", ...] for part in item.parts):
            continue
        files.append(item)
```

This walks the **entire directory tree** of every project that doesn't have git. If you have a project with a large `node_modules` that wasn't excluded properly, or any large directory, this will hang.

### 10. Concurrent Access Will Corrupt Data

**`app.py:238-272` - `/api/refresh`:**
The refresh endpoint calls `discover_projects()` and updates the database. If someone clicks refresh while the dashboard is loading, or runs `pt scan` while the dashboard is open, you'll get race conditions. SQLite can handle concurrent reads, but concurrent writes with no locking will cause issues.

---

## Theater vs. Tool Ratings

| Feature | Rating | Reasoning |
|---------|--------|-----------|
| Dashboard view | **Will use occasionally** | Opening 33 TODO.md files does suck, but you'll forget this exists |
| TODO.md viewer | **Will never use** | You have an editor. Just open the file. |
| Alerts system | **Will use occasionally** | Actually useful IF it worked reliably |
| Infrastructure labels | **Delete it** | A hardcoded list of 5 project names? Come on. |
| Cron monitoring | **Will never use** | You'll just check manually because you won't trust this |
| Service categorization | **Delete it** | Emoji icons for services? Who cares? |
| Progress bars | **Will use occasionally** | Mildly useful visual |
| work_log table | **Delete it** | Only logs "scan" events. Completely useless. |

**Honest assessment:** The only genuinely useful thing here is "show me all my projects sorted by last modified with their status." Everything else is decoration.

---

## 5 Anti-Patterns Found

### 1. Fighting Python's Import System

**`app.py:15`:**
```python
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
```

**`pt.py:17`:**
```python
sys.path.insert(0, str(Path(__file__).parent))
```

You're manipulating `sys.path` because you didn't set up the project as a proper Python package. This is a red flag that the project structure is fighting the language.

### 2. God Object Database Manager

**`manager.py`** - 281 lines of repetitive CRUD methods that all do the same thing: open connection, execute query, close connection. No abstraction, just copy-paste with different table names.

### 3. Parsing Markdown With Regex

**`external_resources_parser.py`**, **`todo_parser.py`** - Markdown is not a regular language. Regex cannot reliably parse it. Every edge case will silently fail.

### 4. Stringly-Typed Everything

Status is a string. Phase is a string. Severity is a string. No enums, no validation. You can have `status = "actve"` (typo) and it'll happily store and display it.

### 5. Configuration Embedded in Code

Hardcoded paths, hardcoded infrastructure project names, hardcoded service categories. None of this is configurable without editing source code.

---

## Top 3 Things to Fix Before Adding Features

### 1. Fix the SQL Injection (30 minutes)

**`manager.py:69`** - Whitelist allowed order_by values:
```python
ALLOWED_ORDER_BY = {"last_modified DESC", "name ASC", "status"}
if order_by not in ALLOWED_ORDER_BY:
    order_by = "last_modified DESC"
```

### 2. Make Paths Configurable (1 hour)

Create a config file or use environment variables:
```python
PROJECTS_DIR = os.environ.get("PROJECT_TRACKER_DIR", os.path.expanduser("~/projects"))
```

Without this, nobody else can use this tool and you can't move your projects directory.

### 3. Add Actual Logging (2 hours)

Replace every `except Exception: pass` with:
```python
import logging
logger = logging.getLogger(__name__)

try:
    ...
except Exception as e:
    logger.warning(f"Failed to parse TODO.md for {project}: {e}")
    return default_value
```

At minimum you'll know when things break.

---

## Top 3 Things to Delete

### 1. Delete `work_log` Table and All References

**`schema.py:84-94`**, **`manager.py:236-280`**

It only logs "scan" and "refresh" events. You'll never look at this data. It's just making the database bigger.

### 2. Delete Service Categorization

**`app.py:57-131`** - `categorize_services()`

60 lines of hardcoded mappings to show emoji icons next to service names. The information is already there in the service name. The categorization adds nothing useful.

### 3. Delete Infrastructure Labels Detection

**`project_scanner.py:52-80`** - `is_infrastructure_project()`

A hardcoded list of 5 project names. Just add a field to TODO.md if you care about this. The code is more complex than the problem.

---

## Critical Flaws Checklist

| Issue | Found? | Details |
|-------|--------|---------|
| Sensitive data in code | **YES** | Hardcoded username paths everywhere |
| `.gitignore` holes | No | Actually decent |
| SQL injection | **YES** | `manager.py:69`, `manager.py:88` |
| Silent failures | **YES** | 10+ instances of `except: pass` |
| N+1 queries | **YES** | 99 queries per dashboard load |
| Over-engineered | **YES** | 5 parser modules, work_log table, service categories |
| No tests | **YES** | Zero tests, zero confidence |
| Will break on other machines | **YES** | Hardcoded paths |

---

## The Core Value Question

**What's the single most useful part?**

`pt scan && pt list` - Scan all projects, show them in a table sorted by last modified. That's it. That's the only thing you'll actually use.

**What should you miss most if it disappeared?**

The "stalled projects" alert. Knowing which projects haven't been touched in 60+ days is genuinely useful.

**What's pure theater?**

- Service categorization with emoji icons
- Infrastructure project detection
- The entire work_log system
- TODO.md viewer (you have an editor)

---

## The 3-Month Test

When you come back to this in 3 months, you will:

1. Try to run it
2. Get confused why it's looking for `/Users/eriksjaastad/projects`
3. Grep for the path, change it in 3 different files
4. Run it, see wrong data, have no idea why (silent failures)
5. Give up and just `ls -lt ~/projects | head -20`

---

## Final Verdict: NEEDS MAJOR REFACTOR

**The good:**
- The problem is real (tracking 33+ projects is annoying)
- The core idea is sound (scan, parse, display)
- The code is readable and well-organized

**The bad:**
- SQL injection vulnerabilities
- Hardcoded paths make it useless to anyone else
- Silent failures make it untrustworthy
- Massive over-engineering for what it does

**The ugly:**
- You built a dashboard, database layer, 5 parser modules, cron monitoring, service categorization, and a CLI... to replace `ls -lt | head -20` and occasionally opening a TODO.md file.

---

## What You Should Actually Do

- [ ] 1. **Fix the SQL injection** (non-negotiable)
- [ ] 2. **Make paths configurable** (or it's just a personal toy)
- [ ] 3. **Add logging** (or you'll never know when it breaks)
- [ ] 4. **Delete work_log, service categories, infrastructure detection** (noise)
- [ ] 5. **Write 5 tests for the parsers** (or you can't trust the data)

Then decide if you actually use it for 2 weeks. If you don't, delete the project and use a spreadsheet like a normal person.

---

## Progress Update (Dec 31, 2025)

**New features built DURING code review:**
- ✅ Code review tracking system with progress bars
- ✅ Full border highlighting for projects with open reviews
- ✅ Prominent code review status on project cards
- ✅ CODE_QUALITY_STANDARDS.md added to project-scaffolding (NO SILENT FAILURES rule)
- ✅ Meta-tracking works: Dashboard tracks its own code review

**Review action items:** 0/5 completed (see checkboxes above)

---

*Review complete. No compliment sandwich. You asked for brutal, you got brutal.*
