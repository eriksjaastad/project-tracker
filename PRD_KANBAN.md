# PRD: Kanban Feature for project-tracker

> **Type:** Feature PRD (adding to existing project)
> **Parent Project:** project-tracker
> **Created:** January 25, 2026
> **Last Updated:** January 27, 2026

---

## Overview

Replace scattered `TODO.md` files with a centralized Kanban system that becomes the **single source of truth** for all tasks across 20+ projects. Provides a visual board interface with drag-and-drop, plus a programmatic `add_task` hook for AI agents to create tasks from any project context.

---

## Goals

1. **Single source of truth** - Kanban DB replaces all TODO.md files
2. **Visual management** - Drag-and-drop status changes across 5 columns (Backlog, To Do, In Progress, Review, Done)
3. **Filtering and sorting** - By project, alphabetically, or by task count
4. **Programmatic access** - CLI (`./pt tasks`) and API for AI agents to create/update tasks from any context
5. **Dashboard integration** - Main dashboard reads from Kanban data
6. **Productivity insights** - Track completion trends over time (graphs showing "you got shit done this month" or "you bought a video game and nothing got done")
7. **Agent governance** - Review column as quality gate (agents move to Review, humans promote to Done)

---

## Non-Goals

- **No multi-user support** - Personal tool, not team collaboration
- **No external integrations** - Not connecting to Jira, Trello, GitHub Issues
- **No light theme** - Dark mode only, no theme toggle
- **No mobile app** - Desktop browser only (local-first)
- **No notifications/reminders** - Board shows state, doesn't push alerts
- **No TODO.md sync** - One-time migration, then Kanban is the only source

---

## Security

- **No authentication required** - Single user, local-first application
- **No sensitive data in tasks** - Task text should never contain API keys, passwords, SSNs, or credentials
- **Input validation** - Warn or block task text that looks like secrets (patterns: `sk-`, `api_key=`, social security formats, etc.)
- **No external data transmission** - All data stays in local SQLite

---

## Target Users

**Primary:** Erik - a developer managing 20+ projects who needs a unified view of all active work without hunting through individual TODO.md files.

---

## Problem Statement

With 20+ active projects, tasks are scattered across individual `TODO.md` files. There's no unified view, no programmatic access for AI agents, and no way to manage tasks without editing markdown files manually. Finding "what should I work on next?" requires opening multiple files and mentally aggregating state.

---

## Integration Context

**Reference:** `project-scaffolding/EXTERNAL_RESOURCES.yaml` - project-tracker entry

- **Existing infrastructure:** project-tracker already has SQLite (`tracker.db`) and FastAPI - Kanban extends these
- **External services needed:** None - 100% local (consistent with existing project-tracker)
- **Publishing destination:** localhost (Phase 1-3), Vercel (Phase 4+)
- **Notification channels:** None (explicitly a non-goal)

---

## Human Touchpoints

This is a direct-manipulation tool. The human (Erik) interacts with the board constantly:

- **Create tasks** - Via "Add Task" button on the board or CLI (`./pt tasks create`)
- **Move tasks** - Drag-and-drop between columns (Backlog → To Do → In Progress → Review → Done)
- **Edit tasks** - Click to expand, edit text inline
- **Filter view** - Toggle projects on/off via sidebar checkboxes
- **Review progress** - View productivity graphs to see completion trends
- **Approve agent work** - Review column acts as quality gate; only humans promote to Done

**Review Column Workflow:** AI agents complete work and move tasks to Review. Humans verify the work and promote to Done (or move back to In Progress if changes needed). This prevents agents from marking their own work as complete.

---

## Core Concept / Data Model

### Task Model

A task has:
- **Text** - The task description
- **Status** - One of: Backlog, To Do, In Progress, Review, Done
- **Project** - Which project it belongs to
- **Priority** - Optional: Critical, High, Medium, Low
- **Prompt** - Optional: Structured execution instructions for AI agents (Overview, Execution steps, Done criteria)
- **Timestamps** - created_at, updated_at, completed_at

### Migration Mapping (one-time import from TODO.md)
| TODO.md Syntax | Kanban Status |
|----------------|---------------|
| `- [ ] Task` (no priority) | Backlog |
| `- [ ] Task` (under priority header) | To Do |
| `- [~] Task` or `🔄` marker | In Progress |
| `- [x] Task` | Done |

### Data Flow
```
Kanban DB (SQLite - source of truth)
       ↑ write              ↓ read
add_task hook          Board UI + Dashboard
(from any agent)       (drag-and-drop updates)
```

### Add Task Hook
```python
add_task(
    project: str,      # e.g., "project-tracker"
    text: str,         # task description
    status: str = "Backlog",
    priority: str = None
) -> Task
```
Available as CLI command, Python function, or MCP tool for AI agents.

---

## Functional Requirements

### FR1: Task Storage
- SQLite table for tasks (extends existing `tracker.db`)
- CRUD operations: create, read, update, delete tasks
- Query by project, status, priority

### FR2: Task Management Interface
- **CLI:** `./pt tasks` - list, create, update, start, done commands (primary for AI agents)
- **REST API:** Full CRUD at `/api/tasks` endpoints
- **Dashboard UI:** "Add Task" button for manual entry from the board
- **Python function:** `DatabaseManager.add_task()` for internal use

### FR3: Kanban Board Display
- Display 5 columns: Backlog, To Do, In Progress, Review, Done
- Show task cards with: text (truncated), project label, priority indicator
- Color-code or badge tasks by source project
- "Delete Done" button to permanently remove all completed tasks

### FR4: Project Filtering
- Collapsible left sidebar with project list
- Checkbox per project to show/hide its tasks on the board
- "Select All" / "Deselect All" controls

### FR5: Project Sorting
- Sort project list alphabetically (A-Z, Z-A)
- Sort project list by open task count (most first, least first)

### FR6: URL Routing & Deep Links
- URLs must reflect current view state (no silent SPA navigation)
- Routes: `/dashboard`, `/kanban`, `/kanban/:project`, `/graph`, `/graph/:project`
- `/kanban/project-tracker` → board pre-filtered to project-tracker tasks
- `/graph/project-tracker` → graph filtered to project-tracker
- Browser back/forward must work
- Bookmarkable URLs (share a link, get the same view)

### FR7: Task Detail View
- Click task card to expand full text
- Show project name and timestamps
- Edit task text inline

### FR8: Dashboard Integration
- Add as new tab/view in existing project-tracker dashboard
- Navigation: [Dashboard] [Kanban] [Graph]
- Main dashboard reads task counts from Kanban DB

### FR9: Migration Tool
- One-time import from existing TODO.md files
- Parse using migration mapping (see Data Model)
- Delete TODO.md files after successful import

---

## Non-Functional Requirements

### NFR1: Performance
- Load all tasks in under 1 second (SQLite is fast)
- Drag-and-drop response under 200ms
- Hook writes under 100ms

### NFR2: Reliability
- SQLite with WAL mode for concurrent access
- Graceful handling of missing/invalid project names

### NFR3: Maintainability
- Follow existing project-tracker code patterns
- No new frameworks unless necessary
- Clear separation between parsing, UI, and write-back logic

---

## UX and UI Requirements

### Layout
```
┌──────────────────────────────────────────────────────────────────────────┐
│  project-tracker                                [Dashboard] [Kanban] [Graph] │
├──────────────────────────────────────────────────────────────────────────┤
│  Backlog   │   To Do    │ In Progress │   Review   │      Done           │
│            │            │             │            │                     │
│ ┌────────┐ │ ┌────────┐ │ ┌─────────┐ │ ┌────────┐ │  ┌────────┐        │
│ │ Task A │ │ │ Task B │ │ │ Task C  │ │ │ Task D │ │  │ Task E │        │
│ │ proj-1 │ │ │ proj-2 │ │ │ proj-1  │ │ │ proj-2 │ │  │ proj-1 │        │
│ └────────┘ │ └────────┘ │ └─────────┘ │ └────────┘ │  └────────┘        │
│            │            │             │            │                     │
│            │            │             │  ↑ Agent   │   ↑ Human          │
│            │            │             │  moves here│   approves here    │
│ 12 tasks   │ 8 tasks    │ 3 tasks     │ 2 tasks    │  47 done (7d keep) │
└──────────────────────────────────────────────────────────────────────────┘
```

**Review Column:** AI agents move completed work to Review. Humans verify and promote to Done.
Use "Delete Done" button to clear completed tasks when ready.

### Design Requirements
- **Dark theme only** - No light mode, no toggle
- **Minimal chrome** - Focus on task content, not UI decoration
- **Developer aesthetic** - Monospace fonts for task text, muted colors
- **Responsive columns** - Columns resize based on content, scrollable if overflow

### Design System (from image-workflow)

Inherit the established design system from `image-workflow/Documents/reference/WEB_STYLE_GUIDE.md`:

**Color Palette:**
```css
:root {
  color-scheme: dark;
  --bg: #101014;           /* Main background - deep navy */
  --surface: #181821;      /* Card/panel backgrounds */
  --surface-alt: #1f1f2c;  /* Alternative surface (sidebar) */
  --accent: #4f9dff;       /* Primary blue - links, active states */
  --accent-soft: rgba(79, 157, 255, 0.2);

  /* Status colors */
  --success: #51cf66;      /* Done column, completed tasks */
  --danger: #ff6b6b;       /* Blocked/overdue indicators */
  --warning: #ffd43b;      /* Priority indicators */
  --muted: #a0a3b1;        /* Secondary text, project labels */
}
```

**Spacing Scale:**
```css
--space-xs: 0.25rem;    /* 4px - tight padding */
--space-sm: 0.5rem;     /* 8px - card internal */
--space-md: 0.75rem;    /* 12px - card padding */
--space-lg: 1rem;       /* 16px - section gaps */
--space-xl: 1.5rem;     /* 24px - column gaps */
```

**Card Pattern:**
```css
.task-card {
  background: var(--surface);
  border-radius: 8px;
  padding: var(--space-md);
  border: 1px solid transparent;
  transition: border-color 0.2s ease;
}
.task-card:hover {
  border-color: var(--accent-soft);
}
```

**Sidebar Pattern:**
```css
.project-sidebar {
  width: 200px;
  background: var(--surface-alt);
  border-right: 1px solid rgba(255,255,255,0.1);
}
```

**Typography:**
- Task text: Monospace (system or `JetBrains Mono`)
- UI labels: System sans-serif
- Font sizes: 0.875rem (14px) for cards, 0.75rem (12px) for metadata

**Reference:** Full design system at `image-workflow/Documents/reference/WEB_STYLE_GUIDE.md`

### Task Card Design
- Compact by default (single line + project badge)
- Expandable on click for full text
- Visual priority indicator (color dot or border)
- Drag handle visible on hover

### Sidebar Behavior
- Collapsible via toggle button
- Remembers collapsed state across sessions
- Shows counts: total projects, total tasks, tasks per column

---

## Success Metrics

1. **Adoption:** No more TODO.md files - all task management through Kanban
2. **Speed:** Full board loads in under 1 second
3. **Hook usage:** AI agents successfully create tasks via add_task hook
4. **Migration:** 100% of existing TODO.md tasks imported
5. **Productivity tracking:** Can view completion trends over time (weekly/monthly graphs)

---

## MVP Scope

### MVP (Phase 1) - Core Board ✅
- [x] SQLite schema for tasks table
- [x] Display 5-column Kanban board (Backlog, To Do, In Progress, Review, Done)
- [x] Dark theme UI (design system from image-workflow)
- [x] Basic task cards (text + project label)
- [x] Drag-and-drop status updates
- [x] 90% width layout for better screen utilization
- [ ] Project sidebar with checkboxes to filter
- [ ] Sort projects alphabetically

### Phase 2 - Task Management ✅
- [x] "Add Task" button in dashboard UI
- [x] CLI: `./pt tasks` with create, update, start, done, show commands
- [x] REST API: Full CRUD at `/api/tasks`
- [x] Auto-detect project from current directory
- [ ] Migration tool to import from TODO.md files

### Phase 3 - Polish (In Progress)
- [x] Task detail modal with inline edit
- [x] Priority indicators (color-coded)
- [x] Delete Done button to clear completed tasks
- [x] Prompt field for AI agent execution instructions
- [x] History tracking for productivity graphs
- [ ] Sort by task count
- [ ] Search/filter tasks by text
- [ ] Keyboard shortcuts
- [ ] Productivity graphs visualization

### Future (Phase 4+)
- [ ] **Vercel deployment** - Host online for access anywhere
- [ ] Export view as markdown
- [ ] Task templates / quick-add presets
- [ ] Task linking/dependencies

---

## Constraints / Technical Stack

### Must Use
- **React** - Frontend (consistent with other projects)
- **FastAPI** - Backend API (existing project-tracker)
- **SQLite** - Task storage (extend existing `tracker.db`)
- **Vite** - Build tool (matches tax-organizer pattern)

### Must Follow
- Existing project-tracker code patterns
- Dark theme design language (image-workflow system)
- SQLite as single source of truth

### Environment
- Runs locally on macOS (Phase 1-3)
- Accessed via browser (localhost)
- Single user (no auth needed)
- Future: Vercel deployment for online access

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Migration data loss | Medium | High | Backup TODO.md files, verify import counts, manual review |
| Dashboard framework limitations | Unknown | High | Explore current framework first, pivot if needed |
| Hook adoption friction | Medium | Medium | Clear docs, examples in CLAUDE.md files |
| SQLite locking under load | Low | Low | WAL mode, single-user so minimal concern |

---

## Decisions Made

1. **Frontend:** React with Vite (consistent with tax-organizer, flo-fi, portfolio-ai)
2. **Drag-and-drop:** @dnd-kit/core - modern, accessible, well-maintained
3. **5 columns:** Added Review column as agent governance gate (Jan 27, 2026)
4. **Delete Done:** Manual cleanup button to remove completed tasks (Jan 27, 2026)
5. **CLI-first for agents:** `./pt tasks` over MCP for simplicity and discoverability

---

## Resolved Questions

1. **SQLite schema** - ✅ Tasks table with id, text, status, project_id, priority, prompt, timestamps. Indexes on status, project_id, completed_at.
2. **API endpoint design** - ✅ REST: GET/POST /api/tasks, GET/PATCH/DELETE /api/tasks/{id}
3. **Drag-and-drop library** - ✅ @dnd-kit/core (modern, accessible, maintained)
4. **Secret detection patterns** - ✅ Regex patterns for API keys, passwords, tokens in validation.py

## Open Questions

1. **Productivity graph implementation** - What metrics to track, how to visualize (chart library choice)
2. **Project sidebar** - Implement filtering by project checkboxes

---

*This is a Feature PRD following Erik's 13-section template. Kanban replaces TODO.md as the single source of truth for task management.*
