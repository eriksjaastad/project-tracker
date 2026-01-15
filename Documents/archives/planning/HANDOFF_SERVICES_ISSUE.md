# Handoff: Services Not Displaying on Project Cards

**Date:** December 31, 2025  
**Status:** STUCK - Need fresh eyes  
**Issue:** Services (Backend, AI, Monitoring) not showing on trading-copilot card despite being in database

---

## 🚨 The Problem

**User expects to see on trading-copilot card:**
- ⚙️ Backend: Railway ($5)
- 🤖 AI: OpenAI, Anthropic, Google AI, xAI
- 🔔 Notifications: Discord Webhooks
- 💓 Monitoring: Healthchecks.io

**What's actually showing:** Nothing - services section is completely missing from card

---

## ✅ What's Working

1. **Database has correct data:**
   ```bash
   sqlite3 data/tracker.db "SELECT * FROM service_dependencies WHERE project_id='trading-projects';"
   # Returns 7 services correctly
   ```

2. **Services are queryable:**
   ```python
   db.get_services('trading-projects')  # Returns 7 services
   ```

3. **Code review tracking works perfectly:**
   - Orange border on project-tracker card ✅
   - Two progress bars (project + code review) ✅
   - Status bar shows "NEEDS MAJOR REFACTOR - 0% resolved" ✅

4. **Service categorization function exists:**
   - `dashboard/app.py:58` - `categorize_services(services)`
   - Groups by: backend, hosting, ai, storage, database, notifications, monitoring

5. **Template has service display sections:**
   - `dashboard/templates/index.html` lines 145-215
   - Checks for `project.services_by_category.backend`, `.ai`, etc.

---

## 🔴 What's Broken

**Services are in database but not reaching the template.**

### Evidence of disconnect:

1. **enrich_project_data() is called** in `dashboard/app.py:165`
2. **It should call categorize_services()** at line 150
3. **Template expects `project.services_by_category`** dict
4. **But it's empty/None when rendering**

### Previous debugging attempts (all failed):
- ✅ Cleared orphaned services from DB
- ✅ Rescanned projects (services loaded correctly)
- ✅ Cleared Python bytecode cache (`__pycache__/`)
- ✅ Killed and restarted dashboard multiple times
- ✅ Hard refresh browser (Cmd+Shift+R)
- ❌ Services still not showing

---

## 📂 Key Files to Check

### 1. `dashboard/app.py`

**Lines 135-155:** `enrich_project_data()` function
```python
def enrich_project_data(project: dict, db: DatabaseManager) -> dict:
    # ...
    services = db.get_services(project["id"])  # Line 147
    project["services"] = [s["service_name"] for s in services]
    project["service_details"] = services
    project["services_by_category"] = categorize_services(services)  # Line 150
    # ...
```

**Lines 58-135:** `categorize_services()` function
- Takes `services` list
- Returns dict: `{"backend": [...], "ai": [...], "monitoring": [...]}`

**Lines 158-185:** `dashboard()` route
- Calls `enrich_project_data()` for each project
- Passes enriched projects to template

### 2. `dashboard/templates/index.html`

**Lines 143-215:** Service display sections
```html
{% if project.services_by_category.backend %}
<div class="meta-row">
    <span class="meta-label">⚙️ Backend:</span>
    <span class="meta-value">
        {% for service in project.services_by_category.backend %}
            {{ service.service_name }}
        {% endfor %}
    </span>
</div>
{% endif %}
```

### 3. `scripts/db/manager.py`

**Lines 195-210:** `get_services()` method
```python
def get_services(self, project_id: str) -> List[Dict]:
    cursor.execute(
        "SELECT * FROM service_dependencies WHERE project_id = ?",
        (project_id,)
    )
    # Returns list of dicts with service_name, purpose, cost_monthly
```

---

## 🧪 Diagnostic Commands

### 1. Verify database has services:
```bash
sqlite3 data/tracker.db "SELECT project_id, COUNT(*) FROM service_dependencies GROUP BY project_id;"
# Should show: trading-projects|7
```

### 2. Test Python data flow:
```python
cd $PROJECTS_ROOT/project-tracker
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from db.manager import DatabaseManager
from dashboard.app import categorize_services

db = DatabaseManager()
services = db.get_services('trading-projects')
print(f'Raw services: {len(services)}')
categorized = categorize_services(services)
print(f'Categorized: {categorized.keys()}')
for category, items in categorized.items():
    if items:
        print(f'  {category}: {len(items)} services')
"
```

### 3. Check what template receives:
```python
# Add debug print in dashboard/app.py line 166:
enriched_projects = [enrich_project_data(p, db) for p in projects]
for p in enriched_projects:
    if p['id'] == 'trading-projects':
        print(f"DEBUG: {p['name']} services_by_category = {p.get('services_by_category')}")
```

---

## 🤔 Hypotheses (NOT YET TESTED)

1. **Template caching?**
   - Browser cache: User did hard refresh
   - Python bytecode: Cleared `__pycache__`
   - Jinja2 template cache? Not checked yet
   - **Try:** Set `auto_reload=True` in Jinja2Templates?

2. **Data passing issue?**
   - `categorize_services()` returns empty dict?
   - Services list empty when passed to categorization?
   - **Try:** Add print statements in `enrich_project_data()`

3. **Template conditional failing?**
   - `{% if project.services_by_category.backend %}`
   - Maybe checking wrong dict structure?
   - **Try:** Just `{% if project.services_by_category %}` first

4. **Dashboard not reloading code?**
   - Using `--reload` flag but maybe not working?
   - **Try:** Stop completely, run fresh `./pt launch`

5. **Wrong project being checked?**
   - User sees "trading-copilot" card
   - Code looks for "trading-projects" ID
   - IDs match in database... but maybe template uses different key?
   - **Try:** Check template loops through projects by what field?

---

## 🎯 Next Steps for Fresh AI

1. **Stop and restart dashboard cleanly:**
   ```bash
   pkill -9 -f "pt launch"
   cd $PROJECTS_ROOT/project-tracker
   ./pt launch
   ```

2. **Add debug logging to app.py:**
   ```python
   # In enrich_project_data(), after line 150:
   if project["id"] == "trading-projects":
       print(f"DEBUG Trading: services={len(services)}")
       print(f"DEBUG Trading: services_by_category={project['services_by_category']}")
   ```

3. **Check terminal output** when dashboard loads - see if debug prints appear

4. **Verify template receives data:**
   ```python
   # In dashboard() route, before returning:
   for p in enriched_projects:
       if p['id'] == 'trading-projects':
           print(f"Template will receive: {p.keys()}")
           print(f"services_by_category: {p.get('services_by_category')}")
   ```

5. **If still not showing, check browser network tab:**
   - Is HTML actually changing?
   - Is browser serving cached version?

---

## 📸 What User Sees (Screenshots Context)

**User showed two screenshots:**

1. **Project Card** - Shows:
   - Orange border ✅ (has code review)
   - Green progress bar: 32% complete ✅
   - Orange code review bar: "NEEDS MAJOR REFACTOR - 0% resolved" ✅
   - **Missing:** All service sections (Backend, AI, Monitoring)

2. **Code Review Banner** (Now Removed):
   - Large section at top showing review details
   - User feedback: "Too large, remove it"
   - **Fixed:** Removed in commit 9e4ccfc

---

## 💡 User Preferences

1. **NO big banner at top** - Just card-level indicators
2. **Orange border** works great
3. **Two progress bars** (project + code review) work great
4. **Services display is critical** - Must show on cards

---

## 🔧 Recent Changes (Last Hour)

1. ✅ Fixed project ID normalization ("trading" → "trading-projects")
2. ✅ Cleaned orphaned services from database
3. ✅ Added code review status bars to project cards
4. ✅ Removed large code review banner from top
5. ❌ Services still not showing (STUCK HERE)

---

## 📋 Project Context

- **Goal:** Dashboard tracks 33+ projects with services, cron jobs, code reviews
- **Status:** 95% working, just services display broken
- **Tech:** Python FastAPI, SQLite, Jinja2 templates
- **Port:** http://localhost:8000
- **Launcher:** `./pt launch` (runs `uvicorn dashboard.app:app`)

---

## 🆘 I Got Stuck Because...

- Tried same debugging approaches multiple times
- Cleared cache, restarted, rescanned - no change
- Data is IN database, query works, function exists, template has HTML
- But somehow data isn't reaching template rendering
- Need fresh perspective to find the disconnect

---

**Good luck! The answer is probably something simple I kept missing.**


## Related Documentation

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review

