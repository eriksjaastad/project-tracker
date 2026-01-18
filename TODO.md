---
tags:
  - p/project-tracker
  - type/documentation/todo
  - domain/project-management
status: #status/incomplete
created: 2025-12-22
---

# project-tracker - TODO

**Last Updated:** January 14, 2026
**Project Status:** Active (Phase 5 pending)
**Current Phase:** Phase 5: Index Auto-Sync
**Type:** Infrastructure
**Index:** [[00_Index_project-tracker]]

---

### 🧠 Session Trace Visualization (Future Exploration)

**Idea:** Layer execution traces onto the knowledge graph to show how work flows across projects.

**The Vision:**
- Capture session traces (files read, files modified, in sequence)
- Overlay traces on graph.json visualization - nodes light up in order of access
- Over time, see patterns: "Every time we touch budget code, we also touch these 4 files"
- Stack traces across projects, not just within a single codebase

**Building Blocks Already In Place:**
- `graph.json` - static relationships between files (2,150+ nodes, 7,165+ edges)
- `librarian-mcp` - MCP server that queries the graph
- `agent-hub` audit logs (Phase 5) - NDJSON event logs with timestamps
- D3 visualization - already renders the graph dynamically

**Open Questions:**
- [ ] How expensive is continuous trace logging? (Don't want to slow everything down for a cool map)
- [ ] Where to store session traces? (Separate SQLite table? NDJSON files?)
- [ ] How to correlate agent-hub audit logs with file operations?
- [ ] What's the minimum viable version? (Maybe just "files touched this session" highlighted on graph)

**Why This Matters:**
The Librarian becomes not just a search engine but a historian. Institutional knowledge extracted automatically from execution patterns.

---

### 🧠 Adaptive Memory / Learned Importance (Librarian Enhancement)

**Idea:** The Librarian gets smarter the more it's used. Frequently asked questions become instant answers.

**The Vision:**
```
Query frequency → Memory proximity

Asked once:      "Hmm, might be relevant"     → Compute, maybe note it
Asked 3x:        "People care about this"     → Cache the answer
Asked 10x:       "This is important"          → Pre-compute, instant retrieval
Asked 100x:      "Core knowledge"             → Part of identity
```

Like how a brain works - you don't remember every conversation, but if someone asks you the same thing repeatedly, it becomes instant recall. The Librarian builds its own "muscle memory" for the ecosystem.

**Technical Implementation (Draft):**
- SQLite table: `query_hash`, `query_text`, `answer`, `ask_count`, `last_asked`, `first_asked`
- Semantic hashing so "where is auth?" and "where is authentication handled?" hit the same memory
- Hot queries get pre-computed answers, cold queries get computed fresh
- The "distance" of the memory = retrieval speed (L1/L2/L3 cache metaphor)

**The Local Model Angle:**
Wrap a small local model around the Librarian that:
1. Receives the question
2. Checks its memory ("Have I seen this pattern?")
3. If hot → instant answer from cache
4. If cold → goes out, computes, returns, and *decides* whether to remember based on patterns

**Research Needed:**
- [ ] Look into existing math/algorithms for adaptive caching with learned importance
- [ ] Semantic similarity hashing (so similar questions hit same memory)
- [ ] How LLMs handle memory/retrieval - any applicable patterns?
- [ ] Threshold tuning: How many asks before something becomes "important"?

**Current State:**
- librarian-mcp exists but is stateless (computes fresh every time, forgets everything)
- No local model yet - just Python code routing to database/graph queries
- Embeddings directory exists but is empty

**The Goal:**
The Librarian gets smarter and faster the more it's used. Persistent memories "within arm's reach."

*Added: 2026-01-18 by Claude (Super Manager) - Erik's vision for intelligent adaptive memory*

---

*Added: 2026-01-18 by Claude (Super Manager) after discussing knowledge graph evolution with Erik*

---

### 🚨 Governance & Portability (Code Review v2) [complete]
- [x] **Ship Blockers:**
    - [x] Fix hardcoded paths in `agent_registry.py`.
    - [x] Install pre-commit hook (`scripts/git-pre-commit.sh` linked to `.git/hooks/pre-commit`).
- [x] **Recommended Fixes:**
    - [x] Add timeouts to `subprocess.run` calls in `dashboard/app.py`.
    - [x] Update `warden_audit.py` to detect `Path.home()` patterns.
    - [x] Expand test coverage (added `tests/test_discovery.py` and `tests/MISSING_TESTS.md`).

## 📍 Current State

### What's Working ✅
- ✅ **Knowledge Graph Transformation:** Achieved 0% orphan rate.
- ✅ **Interconnected Nervous System:** Every file in the ecosystem is now linked via indices, imports, or references.
- ✅ **D3 Visualization:** Dynamic knowledge graph with path highlighting and real-time physics.
- ✅ **MVP Complete!** Full implementation working (Dec 30, 2025)
- ✅ **Database:** SQLite with all tables (projects, cron_jobs, services, AI agents, indexing)
- ✅ **CLI Tool:** `pt` command with scan, list, launch, etc.
- ✅ **Web Dashboard:** FastAPI serving at localhost:8000
- ✅ **Auto-discovery:** Scans all projects successfully
- ✅ **TODO Viewer:** Renders markdown with full formatting
- ✅ **Progress Bars:** Calculates completion % from checkboxes
- ✅ **Sorting:** Newest work first (chronological)
- ✅ **Indexing System:** tracks 00_Index_*.md compliance (Critical Rule #0)
- ✅ **Alerts:** Stalled, Blocked, Missing Index, Cron failures
- ✅ **Meta-tracking:** Dashboard tracks itself!

### In Progress 🔄
- **Adoption** - Erik using dashboard daily
- **Audit Agent Integration** - Porting scanners to Go CLI (v1.0.0)
- **AI Router Telemetry** - Surface model usage & escalation stats in Dashboard

### What's Missing ❌
- **Index Auto-Sync** - See Phase 5 below (CRITICAL)

---

## 🛠️ Knowledge Graph Hardening (Jan 16, 2026) [complete]
- [x] **Orphan Elimination:** Reduced orphan rate from 5.8% to 0%.
- [x] **Project Connectivity:** Linked 116+ orphan files into their respective project indices.
- [x] **Hotspot Resolution:**
    - [x] **__Knowledge:** Linked masterclass notes and research papers.
    - [x] **Integrity Warden:** Created README and linked all maintenance scripts.
    - [x] **Flo-Fi:** Connected TypeScript definitions and financial configs.
    - [x] **SSH Agent:** Linked host configs and agent logic.
    - [x] **Writing:** Connected creative drafts and governance protocols.
    - [x] **Agent Skills Library:** Linked usage logs and lifecycle playbooks.
- [x] **Special Character Fixes:** Renamed and linked files with `[` and `]` to ensure graph compatibility.
- [x] **Journal Synchronization:** Updated 2026 journal index with latest entries.

**Final Stats:** 2149 nodes | 7138 edges | 0 orphans

---

## 📋 Current Tasks

### Phase 5: Index Auto-Sync (PENDING)

**Problem:** The `00_Index_*.md` files are the Source of Truth for the dashboard, but they require manual updates. Floor Managers forget to update them when they get busy doing actual work. This causes "Dashboard Drift" where projects appear stale even when active.

**Solution:** Project-tracker should WRITE to index files, not just READ them.

**Requirements:**
- [ ] **Trigger on launch** - NOT a cron job. Runs when `pt launch` or `pt scan` is called.
- [ ] **Auto-update "Recent Activity"** - Pull from git log and write to index file.
- [ ] **Detect drift** - Compare git activity timestamp vs index file mtime.
- [ ] **Preserve manual content** - Don't clobber description, components, or other human-written sections.
- [ ] **Atomic writes** - Use temp-file-and-rename pattern for safety.

**Implementation Notes:**
- Consider using `git log --pretty=format:"%ad %s" --date=short` to get recent activity.
- Implement a diffing algorithm to identify changes between the current index file and the auto-generated content. This will help preserve manual content.
- Use a configuration file to specify which sections of the index file should be auto-updated and which should be left untouched.
- Implement a dry-run mode to preview the changes before writing them to the index file.

**Sub-Tasks:**
- [ ] Implement git log parsing.
- [ ] Develop diffing algorithm.
- [ ] Create configuration file format.
- [ ] Implement atomic write functionality.
- [ ] Add dry-run mode.
- [ ] Write tests for index auto-sync.
- [ ] Integrate with `pt launch` and `pt scan`.

### Future Considerations

- **Slack Integration:** Send notifications to Slack channels when projects are stalled or blocked.
- **Automated Dependency Updates:** Automatically update dependencies in project files.
- **AI-Powered Task Prioritization:** Use AI to prioritize tasks based on urgency and importance.
- **Cross-Project Dependency Tracking:** Track dependencies between different projects in the ecosystem.
