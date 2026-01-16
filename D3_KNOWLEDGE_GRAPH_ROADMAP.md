# D3 Knowledge Graph - Feature Roadmap

> **Goal:** Add an interactive knowledge graph visualization to project-tracker that shows ALL files (code + docs) and their relationships across the entire ecosystem.

> **Why:** Obsidian only tracks `.md` files. We need a graph that tracks Python imports, TypeScript imports, Go imports, wiki-links, and file references - designed for an AI agent ecosystem, not human markdown reading.

---

## Overview

### What We're Building

A new `/graph` page in project-tracker that displays:
- **All files** in the ecosystem (not just markdown)
- **Relationships**: imports, wiki-links, references, project boundaries
- **Interactive D3.js visualization**: zoom, click, filter, explore
- **Color coding** by file type or project
- **Orphan detection** for files with no connections

### Architecture

```
project-tracker/
├── dashboard/
│   ├── app.py                    # Add: /graph route, /api/graph endpoint
│   ├── templates/
│   │   └── graph.html            # NEW: D3 visualization page
│   └── static/
│       ├── graph.js              # NEW: D3.js force-directed graph
│       └── graph.css             # NEW: Graph-specific styling
│
└── scripts/
    └── discovery/
        └── graph_builder.py      # NEW: Scans all files, builds graph JSON
```

### Tech Stack
- **Backend:** FastAPI (existing)
- **Frontend:** D3.js v7 (force-directed graph)
- **Data:** JSON graph format `{nodes: [], edges: []}`

---

## Phase 1: Graph Data Builder

**File:** `scripts/discovery/graph_builder.py`

### What It Does
Scans the entire ecosystem and builds a graph of files and their relationships.

### File Types to Scan
```python
SCAN_EXTENSIONS = {
    '.md': 'markdown',
    '.py': 'python',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.go': 'go',
    '.json': 'config',
    '.yaml': 'config',
    '.yml': 'config',
}
```

### Relationships to Detect

| Type | Pattern | Example |
|------|---------|---------|
| Wiki link | `[[target]]` | `[[DOPPLER_SECRETS_MANAGEMENT]]` |
| Markdown link | `[text](path.md)` | `[docs](./README.md)` |
| Python import | `from x import y` | `from scripts.discovery import graph_builder` |
| Python import | `import x` | `import json` |
| TS/JS import | `import { x } from 'y'` | `import { useState } from 'react'` |
| TS/JS import | `import x from 'y'` | `import App from './App'` |
| TS/JS require | `require('x')` | `const fs = require('fs')` |
| Go import | `import "x"` | `import "github.com/user/repo"` |
| File reference | `# See: path` or `// See: path` | `# See: docs/ARCHITECTURE.md` |

### Skip Patterns
```python
SKIP_DIRS = {
    'node_modules', 'venv', '.venv', '__pycache__',
    '.git', '.pytest_cache', 'dist', 'build', '.next',
    '_trash', '__trash__', 'trash'
}

SAFE_ZONES = {
    # Don't modify, but DO scan for graph
    'ai-journal', 'writing'
}
```

### Output Format
```json
{
  "generated_at": "2026-01-15T14:00:00Z",
  "stats": {
    "total_nodes": 1234,
    "total_edges": 5678,
    "orphan_count": 42,
    "projects_scanned": 36
  },
  "nodes": [
    {
      "id": "project-tracker/scripts/discovery/graph_builder.py",
      "name": "graph_builder.py",
      "type": "python",
      "project": "project-tracker",
      "path": "scripts/discovery/graph_builder.py",
      "size": 15,  // connection count (for node sizing)
      "is_orphan": false
    }
  ],
  "edges": [
    {
      "source": "project-tracker/scripts/discovery/graph_builder.py",
      "target": "project-tracker/scripts/discovery/project_scanner.py",
      "type": "python_import",
      "label": "from .project_scanner import discover_projects"
    }
  ]
}
```

### Acceptance Criteria
- [x] Scans all 36+ projects in ecosystem
- [x] Detects Python imports (relative and absolute)
- [x] Detects wiki-links `[[target]]`
- [x] Detects markdown links `[text](path)`
- [x] Outputs valid JSON graph
- [x] Skips node_modules, venv, .git, etc.
- [x] Runs in < 30 seconds
- [x] CLI: `python scripts/discovery/graph_builder.py --output data/graph.json`

---

## Phase 2: API Endpoint

**File:** `dashboard/app.py`

### New Routes

```python
@app.get("/graph", response_class=HTMLResponse)
async def graph_view(request: Request):
    """Render the graph visualization page."""
    return templates.TemplateResponse("graph.html", {"request": request})

@app.get("/api/graph")
async def get_graph_data(
    project: Optional[str] = None,      # Filter to single project
    file_types: Optional[str] = None,   # Comma-separated: "py,ts,md"
    include_orphans: bool = True,       # Show orphaned nodes
    min_connections: int = 0            # Filter by connection count
):
    """Return graph JSON for D3.js visualization."""
    graph_path = Path(__file__).parent.parent / "data" / "graph.json"
    if not graph_path.exists():
        return JSONResponse({"error": "Graph not built. Run: python scripts/discovery/graph_builder.py"}, status_code=404)

    graph = json.loads(graph_path.read_text())

    # Apply filters...

    return graph
```

### Acceptance Criteria
- [x] `/graph` renders the graph.html template
- [x] `/api/graph` returns full graph JSON
- [x] `/api/graph?project=trading-copilot` filters to one project
- [x] `/api/graph?file_types=py,ts` filters by extension
- [x] `/api/graph?include_orphans=false` hides orphans
- [x] Returns 404 with helpful message if graph.json missing

---

## Phase 3: D3.js Visualization

**Files:**
- `dashboard/templates/graph.html`
- `dashboard/static/graph.js`
- `dashboard/static/graph.css`

### Features

1. **Force-directed layout** - nodes repel, edges attract
2. **Project clustering** - nodes grouped by project (different force centers)
3. **Color coding by file type:**
   - Python: `#3572A5` (blue)
   - TypeScript: `#2b7489` (teal)
   - JavaScript: `#f1e05a` (yellow)
   - Markdown: `#083fa1` (dark blue)
   - Go: `#00ADD8` (cyan)
   - Config: `#6e6e6e` (gray)

4. **Node sizing** - bigger = more connections (hub nodes)
5. **Edge styling:**
   - Imports: solid line
   - Wiki-links: dashed line
   - File references: dotted line

6. **Interactions:**
   - **Hover**: highlight node + connected edges
   - **Click**: show node details panel (path, type, connections)
   - **Double-click**: filter to only this node's neighborhood
   - **Zoom/pan**: mouse wheel + drag
   - **Search**: filter nodes by name

7. **Controls panel:**
   - Project filter (dropdown)
   - File type toggles (checkboxes)
   - Show/hide orphans toggle
   - Reset view button
   - Stats display (node count, edge count, orphans)

### Acceptance Criteria
- [x] Graph renders with D3.js force simulation
- [x] Nodes colored by file type
- [x] Nodes sized by connection count
- [x] Edges show different styles by type
- [x] Hover highlights connected nodes
- [x] Click shows node details
- [x] Zoom and pan work
- [x] Project filter works
- [x] File type filter works
- [x] Orphan toggle works
- [x] Stats display accurate counts

---

## Phase 4: Integration & Polish

### Navigation
- Add "Graph" link to project-tracker nav bar
- On `/project/{name}` detail page, add "View in Graph" button

### Caching
- Graph rebuilds on `./pt scan`
- Add `--rebuild-graph` flag to scan command
- Store last-built timestamp in graph.json

### Performance
- For large graphs (>5000 nodes), implement:
  - Lazy loading (only load visible nodes)
  - Level-of-detail (collapse distant clusters)
  - WebGL renderer option (if D3 is too slow)

### Acceptance Criteria
- [x] "Graph" link in nav
- [x] "View in Graph" on project detail pages
- [x] Graph rebuilds with `./pt scan`
- [x] Performance acceptable with full ecosystem

---

## Phase 5: AI-Readable Analysis Layer

> **Purpose:** Give AI agents (Claude, Gemini, etc.) a way to understand the neural network without needing to see the visual graph.

### 5A: Graph Analysis Report

**File:** `data/graph_analysis.md` (generated alongside `graph.json`)

When `graph_builder.py` runs, also generate a markdown report:

```markdown
# Ecosystem Neural Network Analysis
Generated: 2026-01-15T14:30:00Z

## Vital Signs
- **Total Nodes:** 4,521 files
- **Total Edges:** 12,847 connections
- **Orphan Count:** 127 (2.8%)
- **Graph Density:** 0.0006 (sparse - healthy for a large ecosystem)
- **Projects Scanned:** 36

## Hub Nodes (Top 10 Most Connected)
| Rank | File | Connections | Type | Project |
|------|------|-------------|------|---------|
| 1 | CLAUDE.md | 89 | markdown | project-scaffolding |
| 2 | db_helpers.py | 67 | python | trading-copilot |
| 3 | TODO.md | 54 | markdown | (root) |
| ... | ... | ... | ... | ... |

## Cross-Project Bridges
Files referenced from multiple projects (knowledge hubs):
- `DOPPLER_SECRETS_MANAGEMENT.md` → referenced by 10 projects
- `CODE_REVIEW_ANTI_PATTERNS.md` → referenced by 8 projects
- `architecture_patterns.md` → referenced by 6 projects

## Project Dependency Matrix
Which projects depend on which (by import/reference count):
- `project-scaffolding` ← 22 projects depend on it
- `trading-copilot` ← 5 projects reference it
- `_tools/doc-auditor` ← 4 projects reference it

## Isolated Clusters (Low External Connectivity)
Projects with few connections to the rest of the ecosystem:
- `van-build` - 3 outbound links
- `plugin-find-names-chrome` - 0 outbound links
- `writing` - 2 outbound links (intentional - creative vault)

## Orphan Hotspots
Directories with the most unconnected files:
| Directory | Orphan Count | Total Files | Orphan % |
|-----------|--------------|-------------|----------|
| writing/ | 45 | 120 | 37.5% |
| ai-journal/entries/2025/ | 32 | 306 | 10.5% |
| _trash/ | 28 | 28 | 100% |

## File Type Distribution
| Type | Count | % of Total | Avg Connections |
|------|-------|------------|-----------------|
| markdown | 1,234 | 27.3% | 4.2 |
| python | 987 | 21.8% | 6.1 |
| typescript | 654 | 14.5% | 5.8 |
| javascript | 432 | 9.6% | 3.2 |
| config | 876 | 19.4% | 1.1 |
| go | 98 | 2.2% | 7.3 |

## Recent Changes (if tracking enabled)
- New nodes since last scan: 12
- New edges since last scan: 47
- Nodes removed: 3
- New orphans: 2
```

### 5B: Neural Network Snapshot in Ecosystem TODO

Auto-append a summary section to `/Users/eriksjaastad/projects/TODO.md`:

```markdown
## Neural Network Status (Auto-Updated)

**Last Scan:** Jan 15, 2026 2:30 PM
**Health:** GOOD (2.8% orphan rate)

**Quick Stats:**
- 4,521 nodes | 12,847 edges | 127 orphans
- Top Hub: `project-scaffolding/CLAUDE.md` (89 connections)
- Most Isolated: `van-build` (3 external links)
- Cross-project bridges: 15 files link 3+ projects

**View full analysis:** `project-tracker/data/graph_analysis.md`
**Interactive graph:** `./pt launch` → Graph tab
```

### Implementation

Modify `graph_builder.py` to:
1. Generate `graph_analysis.md` alongside `graph.json`
2. Optionally append snapshot to ecosystem TODO (flag: `--update-todo`)

```bash
# Generate both files
python scripts/discovery/graph_builder.py --output data/graph.json --analysis data/graph_analysis.md

# Also update ecosystem TODO
python scripts/discovery/graph_builder.py --output data/graph.json --update-todo /Users/eriksjaastad/projects/TODO.md
```

### Acceptance Criteria
- [x] `graph_analysis.md` generated on each scan
- [x] Contains: vital signs, hub nodes, cross-project bridges, orphan hotspots
- [x] Human AND AI readable (markdown tables, clear sections)
- [x] Optional: `--update-todo` appends snapshot to ecosystem TODO
- [x] Analysis generation adds < 2 seconds to scan time

---

## Implementation Order

1. **Phase 1** - `graph_builder.py` (data foundation) ✅ COMPLETE
2. **Phase 2** - API endpoints (serve the data) ✅ COMPLETE
3. **Phase 3** - D3 visualization (the fun part) ✅ COMPLETE
4. **Phase 4** - Integration (wire it all together) ✅ COMPLETE
5. **Phase 5** - AI-readable analysis layer ✅ COMPLETE

---

## Prompt: Phase 5 (AI-Readable Layer)

Use this prompt to have Gemini add the AI-readable analysis layer:

```
Enhance `scripts/discovery/graph_builder.py` to generate an AI-readable analysis report.

**Requirements:**

1. After generating `graph.json`, also generate `graph_analysis.md` in the same output directory

2. The analysis report should include these sections:
   - **Vital Signs:** total nodes, edges, orphan count, orphan %, graph density, projects scanned
   - **Hub Nodes (Top 10):** most connected files with connection count, type, project
   - **Cross-Project Bridges:** files referenced from 3+ different projects
   - **Project Dependency Matrix:** which projects are most depended upon
   - **Isolated Clusters:** projects with fewest external connections
   - **Orphan Hotspots:** directories with highest orphan counts
   - **File Type Distribution:** count and avg connections per file type

3. Add CLI flags:
   - `--analysis PATH` - where to write the analysis markdown (default: same dir as --output)
   - `--update-todo PATH` - optionally append a summary snapshot to the ecosystem TODO.md

4. The analysis must be:
   - Readable by AI agents (clear markdown, tables, no ambiguity)
   - Readable by humans (good formatting, explanatory headers)
   - Generated in < 2 seconds additional time

5. For `--update-todo`, find and replace the section between:
   `## Neural Network Status (Auto-Updated)` and the next `## ` header
   Or append if the section doesn't exist yet.

**Look at the roadmap for the exact output format:**
- `D3_KNOWLEDGE_GRAPH_ROADMAP.md` → Phase 5 section

**Test by running:**
```bash
python scripts/discovery/graph_builder.py --output data/graph.json --analysis data/graph_analysis.md
cat data/graph_analysis.md
```
```

---

## First Prompt: Phase 1 (Already Complete)

Use this prompt to start Phase 1 with Gemini or another AI:

```
I need you to create a new file: `scripts/discovery/graph_builder.py`

This script scans the entire projects ecosystem and builds a knowledge graph JSON file.

**Requirements:**

1. Scan from `/Users/eriksjaastad/projects/` root
2. Include these file types: .md, .py, .ts, .tsx, .js, .jsx, .go, .json, .yaml, .yml
3. Skip these directories: node_modules, venv, .venv, __pycache__, .git, .pytest_cache, dist, build, .next, _trash, __trash__
4. Detect these relationships:
   - Wiki links: [[target]] pattern in markdown
   - Markdown links: [text](path.md) pattern
   - Python imports: `from x import y` and `import x` statements
   - TypeScript/JS imports: `import { x } from 'y'` and `import x from 'y'` and `require('x')`
5. Output JSON with this structure:
   ```json
   {
     "generated_at": "ISO timestamp",
     "stats": {"total_nodes": N, "total_edges": N, "orphan_count": N},
     "nodes": [{"id": "full/path", "name": "filename", "type": "python", "project": "project-name", "size": connection_count, "is_orphan": bool}],
     "edges": [{"source": "id", "target": "id", "type": "python_import|wiki_link|markdown_link"}]
   }
   ```
6. CLI interface: `python graph_builder.py --root /path --output graph.json`
7. Should complete in < 30 seconds for the full ecosystem

Look at the existing `project_scanner.py` in the same directory for patterns on how we scan projects.

Start by reading:
- scripts/discovery/project_scanner.py (for scanning patterns)
- _tools/doc-auditor/audit_docs.py (for wiki-link detection patterns)

Then create graph_builder.py with tests.
```

---

## Future Ideas (Post-MVP)

- **Time-lapse**: show graph evolution over git history
- **Health overlay**: color nodes by test coverage or lint status
- **AI agent paths**: trace which files an agent touched in a session
- **Diff view**: highlight what changed since last scan
- **3D mode**: Three.js WebGL for massive graphs
- **Export**: PNG/SVG export for documentation

---

*Created: Jan 15, 2026*
*Author: Claude Code CLI (claude-code-cli-opus-4-5)*
