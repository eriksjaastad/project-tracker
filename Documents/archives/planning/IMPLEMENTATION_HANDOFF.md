# Project Dashboard - Implementation Handoff

> **Date:** December 30, 2025  
> **From:** Project Manager (Claude Sonnet 4.5)  
> **To:** Implementation Team (AI session in project-tracker/)  
> **Type:** Full MVP Implementation

---

## 🎯 Project Goal

Build a **local web dashboard** that shows all of Erik's projects with:
- Chronological sorting (newest work first)
- AI agents tracking (which AI helping with what)
- Cron jobs display
- External services used
- TODO.md viewer (click to view rendered markdown)
- Progress bars (based on TODO completion)
- Dashboard tracks itself (meta!)

**Why:** Erik has 20+ active projects across multiple Cursor windows. Dashboard solves the "spinning plates" problem by providing visibility into what's active, what's stalled, and what needs attention.

---

## 📚 Context: What's Already Done

### Documentation Complete ✅
All planning and design work is done:

1. **Project Vision:** `README.md` (367 lines)
   - Full mockup of what dashboard looks like
   - Data model design
   - Integration with project-scaffolding

2. **Implementation TODO:** `TODO.md` (464 lines)
   - Complete task breakdown
   - All requirements listed
   - Time estimates
   - Success criteria

3. **TODO Standard:** `../project-scaffolding/docs/TODO_FORMAT_STANDARD.md` (650 lines)
   - Analysis of existing TODO formats
   - New standard defined
   - Dashboard integration details

4. **TODO Template:** `../project-scaffolding/templates/TODO.md.template` (250 lines)
   - Standard format template
   - Guidance for AI sessions

5. **Discussion Summary:** `DISCUSSION_SUMMARY_2025-12-30.md`
   - What was decided
   - Requirements breakdown
   - Questions answered

### Key Decisions Made ✅

**Architecture:**
- Local-first (SQLite + FastAPI, no cloud)
- Auto-discovery (scan projects directory)
- Git integration (last modified timestamps)
- Cost: $0 (all local)

**Data Sources:**
- Git metadata (last commit date)
- File timestamps (fallback)
- TODO.md parsing (AI agents, completion %)
- Crontab + launchd plists (scheduled jobs)
- EXTERNAL_RESOURCES.md (service dependencies)

**Sorting Priority:**
1. Last modified DESC (PRIMARY - newest work first)
2. Status (active > dev > paused > stalled)
3. Name (alphabetical tiebreaker)

**Tech Stack:**
- Python 3.11+
- SQLite (local database)
- FastAPI (web framework)
- Typer (CLI framework)
- Rich (terminal formatting)
- Python-markdown (TODO rendering)

---

## 🚀 Your Mission

**Build the complete Dashboard MVP following TODO.md.**

You'll create:
1. SQLite database with full schema
2. Python CLI tool (`pt` command)
3. Auto-discovery system (scan projects, detect metadata)
4. Web dashboard (FastAPI + HTML)
5. TODO.md markdown viewer
6. Progress calculation
7. Testing on real projects

**Expected time:** 14-18 hours of implementation

---

## 📋 Implementation Checklist

### Phase 1: Database Setup (1 hour)

**Create:** `data/tracker.db` with schema:

```sql
-- Core projects
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL,
    description TEXT,
    phase TEXT,
    last_modified TEXT,  -- ISO 8601 format
    created_at TEXT NOT NULL
);

-- Scheduled automation
CREATE TABLE cron_jobs (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    schedule TEXT NOT NULL,
    command TEXT NOT NULL,
    description TEXT,
    last_run TEXT,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- External services
CREATE TABLE service_dependencies (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    purpose TEXT,
    cost_monthly REAL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- AI assistance tracking
CREATE TABLE ai_agents (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,  -- "Claude Sonnet 4.5", "Cursor", etc.
    role TEXT,  -- "Implementation", "Code Review", etc.
    notes TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Activity log
CREATE TABLE work_log (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT,  -- "scan", "manual_update", etc.
    details TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
```

**Create indexes:**
```sql
CREATE INDEX idx_projects_last_modified ON projects(last_modified DESC);
CREATE INDEX idx_projects_status ON projects(status);
CREATE INDEX idx_cron_jobs_project ON cron_jobs(project_id);
CREATE INDEX idx_ai_agents_project ON ai_agents(project_id);
CREATE INDEX idx_service_deps_project ON service_dependencies(project_id);
```

**File location:** `scripts/db/schema.py` (create schema) + `scripts/db/manager.py` (DB operations)

---

### Phase 2: CLI Tool (3-4 hours)

**Create:** `scripts/pt.py` (main CLI using Typer)

**Commands to implement:**

```python
# Project management
pt add <name> <path>           # Add project manually
pt list                        # List all projects
pt status <name>               # Show project details
pt update <name>               # Refresh single project metadata

# Bulk operations
pt scan                        # Auto-discover projects in /Users/eriksjaastad/projects/
pt refresh                     # Update all project metadata

# Cron jobs
pt cron add <project> <schedule> <command>    # Add cron job
pt cron list [project]                        # List cron jobs

# AI agents
pt agent add <project> <agent_name> <role>    # Track AI agent
pt agent list [project]                       # List AI agents

# Services
pt service add <project> <service> <cost>     # Add service dependency
pt service list [project]                     # List services
```

**Installation:**
- Create symlink: `ln -s $(pwd)/scripts/pt.py ~/bin/pt`
- Or add to PATH

---

### Phase 3: Auto-Discovery (2-3 hours)

**Create:** `scripts/discovery/` directory

**Files:**
- `project_scanner.py` - Scan /Users/eriksjaastad/projects/ for directories
- `git_metadata.py` - Extract git last commit date, check for .git/
- `todo_parser.py` - Parse TODO.md for AI agents, status, phase, completion %
- `cron_detector.py` - Read crontab, parse launchd plists
- `service_parser.py` - Parse EXTERNAL_RESOURCES.md

**Key logic:**

```python
def discover_projects(base_path="/Users/eriksjaastad/projects"):
    """Scan directory for projects."""
    projects = []
    
    for item in Path(base_path).iterdir():
        if not item.is_dir():
            continue
        
        # Skip common non-project directories
        if item.name in ['node_modules', '.git', '__pycache__', 'venv']:
            continue
            
        # Check for indicators of a project
        has_git = (item / '.git').exists()
        has_readme = (item / 'README.md').exists()
        has_todo = (item / 'TODO.md').exists()
        has_code = any(item.glob('**/*.py')) or any(item.glob('**/*.js'))
        
        if has_git or has_readme or has_todo or has_code:
            project = extract_project_metadata(item)
            projects.append(project)
    
    return projects

def extract_project_metadata(project_path):
    """Extract all metadata from project."""
    metadata = {
        'name': project_path.name,
        'path': str(project_path),
        'last_modified': get_last_modified(project_path),
        'status': 'unknown',
        'phase': None,
        'description': None,
        'ai_agents': [],
        'cron_jobs': [],
        'services': []
    }
    
    # Parse TODO.md if exists
    todo_path = project_path / 'TODO.md'
    if todo_path.exists():
        todo_data = parse_todo(todo_path)
        metadata.update({
            'status': todo_data.get('status', 'unknown'),
            'phase': todo_data.get('phase'),
            'ai_agents': todo_data.get('ai_agents', []),
            'cron_jobs': todo_data.get('cron_jobs', []),
            'completion_pct': todo_data.get('completion_pct', 0)
        })
    
    # Parse README.md for description
    readme_path = project_path / 'README.md'
    if readme_path.exists():
        metadata['description'] = extract_first_paragraph(readme_path)
    
    return metadata

def get_last_modified(project_path):
    """Get last modified timestamp (git or file mtime)."""
    git_dir = project_path / '.git'
    
    if git_dir.exists():
        # Use git last commit date
        import subprocess
        try:
            result = subprocess.run(
                ['git', 'log', '-1', '--format=%cI'],
                cwd=project_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
    
    # Fall back to most recent file modification
    files = list(project_path.rglob('*'))
    if files:
        most_recent = max(f.stat().st_mtime for f in files if f.is_file())
        return datetime.fromtimestamp(most_recent).isoformat()
    
    return datetime.now().isoformat()
```

**TODO.md parsing:**
```python
def parse_todo(todo_path):
    """Extract metadata from TODO.md."""
    content = todo_path.read_text()
    data = {
        'status': 'unknown',
        'phase': None,
        'ai_agents': [],
        'cron_jobs': [],
        'completion_pct': 0
    }
    
    # Extract header metadata
    for line in content.split('\n')[:20]:  # Check first 20 lines
        if line.startswith('**Project Status:**'):
            data['status'] = extract_status(line)
        elif line.startswith('**Current Phase:**'):
            data['phase'] = extract_phase(line)
    
    # Extract AI agents section
    if '### AI Agents in Use' in content:
        agents_section = extract_section(content, '### AI Agents in Use')
        data['ai_agents'] = parse_ai_agents(agents_section)
    
    # Extract cron jobs section
    if '### Cron Jobs' in content:
        cron_section = extract_section(content, '### Cron Jobs')
        data['cron_jobs'] = parse_cron_jobs(cron_section)
    
    # Calculate completion percentage
    total_tasks = content.count('- [ ]') + content.count('- [x]')
    completed_tasks = content.count('- [x]')
    if total_tasks > 0:
        data['completion_pct'] = int((completed_tasks / total_tasks) * 100)
    
    return data
```

**Cron detection:**
```python
def detect_cron_jobs():
    """Detect cron jobs from crontab and launchd."""
    jobs = []
    
    # Check crontab
    import subprocess
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if result.returncode == 0:
            jobs.extend(parse_crontab(result.stdout))
    except Exception:
        pass
    
    # Check launchd plists
    launchd_dir = Path.home() / 'Library' / 'LaunchAgents'
    if launchd_dir.exists():
        for plist in launchd_dir.glob('*.plist'):
            jobs.append(parse_launchd_plist(plist))
    
    return jobs
```

**Service parsing:**
```python
def parse_external_resources():
    """Parse EXTERNAL_RESOURCES.md for service dependencies."""
    resources_path = Path('/Users/eriksjaastad/projects/project-scaffolding/EXTERNAL_RESOURCES.md')
    
    if not resources_path.exists():
        return {}
    
    content = resources_path.read_text()
    
    # Parse table format
    # Look for lines like: | Service | Projects | Cost | Status |
    services_by_project = {}
    
    # Simple parsing - can be enhanced
    for line in content.split('\n'):
        if '|' in line and 'projects' in line.lower():
            # Extract service, projects, cost
            # Map to projects dictionary
            pass
    
    return services_by_project
```

---

### Phase 4: Web Dashboard (4-5 hours)

**Create:** `dashboard/app.py` (FastAPI application)

**Routes:**
```python
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI()
templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

@app.get("/")
async def dashboard(request: Request):
    """Main dashboard view."""
    projects = get_all_projects_sorted()  # From DB, sorted by last_modified DESC
    return templates.TemplateResponse("index.html", {
        "request": request,
        "projects": projects
    })

@app.get("/project/{project_id}")
async def project_detail(request: Request, project_id: str):
    """Project detail view."""
    project = get_project_by_id(project_id)
    ai_agents = get_ai_agents(project_id)
    cron_jobs = get_cron_jobs(project_id)
    services = get_services(project_id)
    
    return templates.TemplateResponse("project_detail.html", {
        "request": request,
        "project": project,
        "ai_agents": ai_agents,
        "cron_jobs": cron_jobs,
        "services": services
    })

@app.get("/todo/{project_id}")
async def view_todo(request: Request, project_id: str):
    """View rendered TODO.md."""
    project = get_project_by_id(project_id)
    todo_path = Path(project['path']) / 'TODO.md'
    
    if not todo_path.exists():
        todo_html = "<p>No TODO.md found</p>"
    else:
        import markdown
        todo_content = todo_path.read_text()
        todo_html = markdown.markdown(
            todo_content,
            extensions=['tables', 'fenced_code', 'codehilite']
        )
    
    return templates.TemplateResponse("todo_viewer.html", {
        "request": request,
        "project": project,
        "todo_html": todo_html
    })

@app.post("/api/refresh")
async def refresh_data():
    """Trigger full data refresh."""
    # Run discovery scan
    # Update database
    return {"status": "success", "message": "Data refreshed"}

@app.get("/api/projects")
async def api_projects():
    """JSON API for projects."""
    projects = get_all_projects_sorted()
    return {"projects": projects}
```

**HTML Template:** `dashboard/templates/index.html`
```html
<!DOCTYPE html>
<html>
<head>
    <title>Project Dashboard</title>
    <link rel="stylesheet" href="/static/style.css">
    <meta http-equiv="refresh" content="60">  <!-- Auto-refresh every 60s -->
</head>
<body>
    <header>
        <h1>📊 Project Dashboard</h1>
        <button onclick="refreshData()">🔄 Refresh</button>
    </header>
    
    <main>
        <div class="projects-grid">
            {% for project in projects %}
            <div class="project-card status-{{ project.status }}">
                <div class="project-header">
                    <h2>{{ project.name }}</h2>
                    <span class="status-badge">{{ project.status }}</span>
                </div>
                
                <div class="project-meta">
                    <div class="meta-row">
                        <span class="meta-label">Last work:</span>
                        <span class="meta-value">{{ project.last_modified_human }}</span>
                    </div>
                    
                    {% if project.phase %}
                    <div class="meta-row">
                        <span class="meta-label">Phase:</span>
                        <span class="meta-value">{{ project.phase }}</span>
                    </div>
                    {% endif %}
                    
                    {% if project.ai_agents %}
                    <div class="meta-row">
                        <span class="meta-label">🤖 AI:</span>
                        <span class="meta-value">{{ project.ai_agents|join(', ') }}</span>
                    </div>
                    {% endif %}
                    
                    {% if project.has_cron %}
                    <div class="meta-row">
                        <span class="indicator">⏰ Scheduled jobs</span>
                    </div>
                    {% endif %}
                    
                    {% if project.services %}
                    <div class="meta-row">
                        <span class="meta-label">Services:</span>
                        <span class="meta-value">{{ project.services|join(', ') }}</span>
                    </div>
                    {% endif %}
                </div>
                
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {{ project.completion_pct }}%"></div>
                    <span class="progress-label">{{ project.completion_pct }}% complete</span>
                </div>
                
                <div class="project-actions">
                    <a href="/project/{{ project.id }}" class="btn">Details</a>
                    <a href="/todo/{{ project.id }}" class="btn">View TODO</a>
                </div>
            </div>
            {% endfor %}
        </div>
    </main>
    
    <script src="/static/script.js"></script>
</body>
</html>
```

**CSS:** `dashboard/static/style.css`
```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #1a1a1a;
    color: #e0e0e0;
    padding: 20px;
}

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 30px;
}

.projects-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
    gap: 20px;
}

.project-card {
    background: #2a2a2a;
    border-radius: 8px;
    padding: 20px;
    border-left: 4px solid #888;
}

.project-card.status-active {
    border-left-color: #4caf50;
}

.project-card.status-development {
    border-left-color: #2196f3;
}

.project-card.status-paused {
    border-left-color: #ff9800;
}

.project-card.status-stalled {
    border-left-color: #f44336;
}

.project-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
}

.status-badge {
    background: #444;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    text-transform: uppercase;
}

.project-meta {
    margin-bottom: 15px;
}

.meta-row {
    display: flex;
    justify-content: space-between;
    padding: 5px 0;
    font-size: 14px;
}

.meta-label {
    color: #999;
}

.progress-bar {
    background: #333;
    height: 24px;
    border-radius: 4px;
    overflow: hidden;
    position: relative;
    margin-bottom: 15px;
}

.progress-fill {
    background: linear-gradient(90deg, #4caf50, #8bc34a);
    height: 100%;
    transition: width 0.3s;
}

.progress-label {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 12px;
    font-weight: bold;
    color: #fff;
    text-shadow: 0 0 3px rgba(0,0,0,0.5);
}

.project-actions {
    display: flex;
    gap: 10px;
}

.btn {
    flex: 1;
    padding: 8px;
    background: #444;
    color: #fff;
    text-decoration: none;
    text-align: center;
    border-radius: 4px;
    transition: background 0.2s;
}

.btn:hover {
    background: #555;
}

button {
    padding: 10px 20px;
    background: #2196f3;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}

button:hover {
    background: #1976d2;
}
```

**JavaScript:** `dashboard/static/script.js`
```javascript
function refreshData() {
    fetch('/api/refresh', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                location.reload();
            }
        })
        .catch(error => console.error('Refresh failed:', error));
}

// Human-readable time formatting
function formatTimeAgo(isoDate) {
    const date = new Date(isoDate);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString();
}
```

---

### Phase 5: TODO.md Viewer (2 hours)

**Create:** `dashboard/templates/todo_viewer.html`

```html
<!DOCTYPE html>
<html>
<head>
    <title>{{ project.name }} - TODO</title>
    <link rel="stylesheet" href="/static/style.css">
    <link rel="stylesheet" href="/static/markdown.css">
</head>
<body>
    <header>
        <h1>📋 {{ project.name }} - TODO</h1>
        <a href="/" class="btn">← Back to Dashboard</a>
    </header>
    
    <main>
        <div class="todo-container">
            {{ todo_html|safe }}
        </div>
    </main>
</body>
</html>
```

**Markdown CSS:** `dashboard/static/markdown.css`
```css
.todo-container {
    max-width: 900px;
    margin: 0 auto;
    background: #2a2a2a;
    padding: 40px;
    border-radius: 8px;
}

.todo-container h1 {
    color: #4caf50;
    margin-bottom: 10px;
}

.todo-container h2 {
    color: #2196f3;
    margin-top: 30px;
    margin-bottom: 10px;
}

.todo-container h3 {
    color: #ff9800;
    margin-top: 20px;
    margin-bottom: 10px;
}

.todo-container ul {
    list-style-position: inside;
    margin-left: 20px;
}

.todo-container li {
    margin: 5px 0;
}

.todo-container input[type="checkbox"] {
    margin-right: 8px;
}

.todo-container code {
    background: #1a1a1a;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: 'Monaco', 'Courier New', monospace;
}

.todo-container pre {
    background: #1a1a1a;
    padding: 15px;
    border-radius: 4px;
    overflow-x: auto;
}

.todo-container table {
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
}

.todo-container th,
.todo-container td {
    border: 1px solid #444;
    padding: 10px;
    text-align: left;
}

.todo-container th {
    background: #333;
}
```

**Python markdown rendering:**
```bash
pip install markdown pygments
```

---

### Phase 6: Testing (2-3 hours)

**Create:** `tests/` directory

**Test script:** `tests/test_discovery.py`
```python
def test_scan_projects():
    """Test project discovery."""
    projects = discover_projects('/Users/eriksjaastad/projects')
    
    assert len(projects) > 0, "Should find projects"
    
    # Check required fields
    for project in projects:
        assert 'name' in project
        assert 'path' in project
        assert 'last_modified' in project

def test_parse_todo():
    """Test TODO.md parsing."""
    # Test with project-tracker's own TODO
    todo_path = Path(__file__).parent.parent / 'TODO.md'
    data = parse_todo(todo_path)
    
    assert data['status'] != 'unknown'
    assert 'completion_pct' in data
    assert data['completion_pct'] >= 0

def test_git_metadata():
    """Test git last modified extraction."""
    # Test with project-tracker (has git)
    project_path = Path(__file__).parent.parent
    timestamp = get_last_modified(project_path)
    
    assert timestamp is not None
    # Should be ISO 8601 format
    datetime.fromisoformat(timestamp)

def test_dashboard_loads():
    """Test dashboard page loads."""
    from fastapi.testclient import TestClient
    from dashboard.app import app
    
    client = TestClient(app)
    response = client.get("/")
    
    assert response.status_code == 200
    assert "Project Dashboard" in response.text
```

**Manual testing:**
1. Run `pt scan` - Should discover 20+ projects
2. Check database - Should have data in all tables
3. Start dashboard: `uvicorn dashboard.app:app --reload`
4. Visit http://localhost:8000
5. Verify sorting (newest work first)
6. Click project → View details
7. Click "View TODO" → Verify rendering
8. Check progress bars match reality

---

### Phase 7: Meta-Tracking Setup (30 minutes)

**Ensure project-tracker tracks itself:**

1. Run `pt scan` - Should auto-discover project-tracker
2. Verify in database:
   - Name: project-tracker
   - Status: Active Development (from TODO.md)
   - Phase: Phase 0 (from TODO.md)
   - AI agents: Claude Sonnet 4.5 - Project Manager + Implementation
   - Last modified: Updates as work happens
3. Check dashboard - project-tracker should appear in list
4. Click "View TODO" - Should render this project's TODO.md

**This proves dogfooding works!**

---

## 🎯 Success Criteria

### Dashboard MVP Complete When:
- [ ] SQLite database exists with all tables and indexes
- [ ] CLI tool works: `pt scan`, `pt list`, `pt add`, etc.
- [ ] Auto-discovery finds all Erik's projects
- [ ] Projects sorted by last modified (newest first) ✨ KEY
- [ ] Dashboard displays AI agents per project ✨ KEY
- [ ] Dashboard shows cron job indicators ✨ KEY
- [ ] Dashboard shows services used ✨ KEY
- [ ] Click project → view rendered TODO.md ✨ KEY
- [ ] Progress bars show real completion % ✨ KEY
- [ ] project-tracker tracks itself in dashboard ✨ META KEY
- [ ] Successfully tested on 5+ real projects
- [ ] Web dashboard loads in < 1 second
- [ ] No errors in logs

### Quality Checks:
- [ ] Code follows Python best practices (type hints, docstrings)
- [ ] Error handling on all external operations (git, file reads)
- [ ] Graceful fallbacks (git fails → use file mtime)
- [ ] SQL injection prevention (use parameterized queries)
- [ ] Performance acceptable (scan all projects < 10 seconds)

---

## 📚 Key References

### Documentation to Read First:
1. `README.md` - Project vision and mockup
2. `TODO.md` - Complete task breakdown (this is your checklist)
3. `../project-scaffolding/docs/TODO_FORMAT_STANDARD.md` - How to parse TODO files

### Data Sources:
- **Projects:** `/Users/eriksjaastad/projects/`
- **Services:** `/Users/eriksjaastad/projects/project-scaffolding/EXTERNAL_RESOURCES.md`
- **Cron jobs:** `crontab -l` + `~/Library/LaunchAgents/*.plist`
- **Git metadata:** `.git/` in each project

### Example TODOs to Test Against:
- `../Cortana personal AI/TODO.md` (660 lines, excellent structure)
- `../analyze-youtube-videos/TODO.md` (400 lines, stage-based)
- `../actionable-ai-intel/TODO.md` (350 lines, clear blockers)
- `./TODO.md` (this project - test meta-tracking!)

---

## 🔧 Technical Guidance

### Virtual Environment Setup
```bash
cd /Users/eriksjaastad/projects/project-tracker
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn typer rich markdown pygments gitpython
pip freeze > requirements.txt
```

### Project Structure
```
project-tracker/
├── README.md
├── TODO.md                      # Your implementation checklist
├── requirements.txt             # Dependencies
├── data/
│   └── tracker.db              # SQLite database
├── scripts/
│   ├── pt.py                   # Main CLI tool
│   ├── db/
│   │   ├── schema.py           # Database schema
│   │   └── manager.py          # DB operations
│   └── discovery/
│       ├── project_scanner.py  # Scan projects directory
│       ├── git_metadata.py     # Git integration
│       ├── todo_parser.py      # Parse TODO.md files
│       ├── cron_detector.py    # Detect cron/launchd
│       └── service_parser.py   # Parse EXTERNAL_RESOURCES.md
├── dashboard/
│   ├── app.py                  # FastAPI application
│   ├── templates/
│   │   ├── index.html         # Main dashboard
│   │   ├── project_detail.html
│   │   └── todo_viewer.html   # TODO markdown viewer
│   └── static/
│       ├── style.css          # Main styles
│       ├── markdown.css       # TODO rendering styles
│       └── script.js          # JavaScript
└── tests/
    ├── test_discovery.py
    ├── test_cli.py
    └── test_dashboard.py
```

### Development Workflow
1. **Start with database** - Create schema first
2. **Build CLI next** - Easier to test than web UI
3. **Add discovery** - Test with `pt scan`
4. **Build web UI** - Should display data from CLI/scan
5. **Add TODO viewer** - Markdown rendering
6. **Test on real projects** - Use Erik's actual projects directory

### Error Handling Patterns
```python
def safe_git_metadata(project_path):
    """Get git metadata with fallback."""
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%cI'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        # Log error but don't crash
        print(f"Git metadata failed for {project_path}: {e}")
    
    # Fall back to file mtime
    return fallback_to_file_mtime(project_path)
```

### Performance Considerations
- **SQLite:** Use indexes on last_modified, status
- **Scanning:** Cache results, don't re-scan on every page load
- **Git:** Run git commands with timeout (5s max)
- **Markdown:** Consider caching rendered HTML if slow

---

## ⚠️ Important Notes

### What NOT to Do:
- ❌ Don't write to git repositories (read-only)
- ❌ Don't modify TODO.md files (read-only)
- ❌ Don't modify EXTERNAL_RESOURCES.md (read-only)
- ❌ Don't use cloud services (local only, $0 cost)
- ❌ Don't skip error handling (projects may be broken/incomplete)

### What TO Do:
- ✅ Graceful fallbacks (git fails → file mtime)
- ✅ Defensive parsing (handle malformed TODO.md)
- ✅ Log errors (don't fail silently)
- ✅ Test on project-tracker itself (meta-tracking)
- ✅ Keep it fast (< 1s page load)

---

## 🚀 Getting Started

### Step 1: Read Documentation
1. Read `README.md` - Understand the vision
2. Read `TODO.md` - This is your detailed checklist
3. Read `TODO_FORMAT_STANDARD.md` - How to parse TODO files

### Step 2: Set Up Environment
1. Create virtual environment
2. Install dependencies
3. Test imports work

### Step 3: Start with Database
1. Create `scripts/db/schema.py`
2. Create database with tables
3. Test with sample data

### Step 4: Build CLI
1. Create `scripts/pt.py` with Typer
2. Implement `pt add` command (manual add)
3. Test adding project-tracker manually

### Step 5: Add Discovery
1. Implement project scanner
2. Implement git metadata extraction
3. Implement TODO parser
4. Test `pt scan` on projects directory

### Step 6: Build Dashboard
1. Create FastAPI app
2. Create HTML templates
3. Test at http://localhost:8000

### Step 7: Add TODO Viewer
1. Add markdown rendering
2. Create TODO viewer template
3. Test rendering project-tracker's TODO

### Step 8: Test & Polish
1. Test on 5+ real projects
2. Fix bugs discovered
3. Verify all key requirements work
4. Check project-tracker tracks itself

---

## 📦 Deliverables

When complete, you should have:
1. ✅ Working SQLite database with data
2. ✅ CLI tool (`pt`) installed and functional
3. ✅ Web dashboard running on localhost:8000
4. ✅ TODO.md viewer rendering correctly
5. ✅ project-tracker tracking itself (meta!)
6. ✅ All requirements from TODO.md satisfied
7. ✅ Documentation updated with usage instructions
8. ✅ Tests passing

---

## 🤔 Questions?

If anything is unclear:
1. Check `TODO.md` for detailed breakdown
2. Check `README.md` for vision and mockup
3. Check `TODO_FORMAT_STANDARD.md` for parsing guidance
4. Look at example TODOs in other projects

If still stuck, document the question in TODO.md and continue with what you can do.

---

## 🎯 Remember

**Primary goal:** Build dashboard that solves Erik's "spinning plates" problem.

**Key requirements:**
- Chronological sorting (newest first)
- AI agents tracking
- Cron jobs display
- TODO.md viewer
- Progress bars
- Self-tracking (meta!)

**Expected time:** 14-18 hours

**Cost:** $0 (all local)

**Success:** Erik uses dashboard daily to see project status at a glance.

---

**Ready to build? Start with TODO.md Phase 1! 🚀**

