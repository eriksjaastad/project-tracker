# PRD: Kanban Feature for project-tracker

> **Type:** Feature PRD (adding to existing project)
> **Parent Project:** project-tracker
> **Created:** January 25, 2026

---

## Overview

Add a Kanban board view to the existing project-tracker dashboard that aggregates tasks from all `TODO.md` files across 20+ projects into a unified, visual interface with drag-and-drop status updates.

---

## Goals

1. Provide a single view of all tasks across all projects
2. Enable visual status management via drag-and-drop
3. Allow filtering and sorting by project
4. Write status changes back to source TODO.md files
5. Integrate seamlessly with existing project-tracker dashboard

---

## Non-Goals

- **No multi-user support** - Personal tool, not team collaboration
- **No external integrations** - Not connecting to Jira, Trello, GitHub Issues
- **No light theme** - Dark mode only, no theme toggle
- **No mobile app** - Desktop browser only
- **No task creation from board** - Tasks created by editing TODO.md; board is view layer
- **No notifications/reminders** - Board shows state, doesn't push alerts

---

## Target Users

**Primary:** Erik - a developer managing 20+ projects who needs a unified view of all active work without hunting through individual TODO.md files.

---

## Problem Statement

With 20+ active projects, tasks are scattered across individual `TODO.md` files. There's no unified view to see what's in progress across the entire ecosystem. Finding "what should I work on next?" requires opening multiple files and mentally aggregating state.

---

## Core Concept / Data Model

### Task Model
```
Task {
  id: string (hash of project + task text)
  text: string (task description)
  status: enum [Backlog, ToDo, InProgress, Done]
  project: string (source project name)
  source_file: path (TODO.md location)
  line_number: int (for write-back)
  priority: optional string (Critical, High, etc.)
}
```

### Status Mapping from TODO.md
| Kanban Column | TODO.md Syntax |
|---------------|----------------|
| **Backlog** | `- [ ] Task` (no priority section) |
| **To Do** | `- [ ] Task` (under priority header like `### 🔴 CRITICAL`) |
| **In Progress** | `- [~] Task` or `- [ ] 🔄 Task` |
| **Done** | `- [x] Task` |

### Data Flow
```
TODO.md files (source of truth)
       ↓ [parse on load]
   In-memory task list
       ↓ [render]
   Kanban Board UI
       ↓ [drag action]
   Write back to TODO.md (update checkbox/marker)
```

---

## Functional Requirements

### FR1: Task Aggregation
- Parse all `TODO.md` files from projects in `$PROJECTS_ROOT`
- Extract task text, status, and priority from markdown syntax
- Associate each task with its source project

### FR2: Kanban Board Display
- Display 4 columns: Backlog, To Do, In Progress, Done
- Show task cards with: text (truncated), project label, priority indicator
- Color-code or badge tasks by source project

### FR3: Project Filtering
- Collapsible left sidebar with project list
- Checkbox per project to show/hide its tasks on the board
- "Select All" / "Deselect All" controls

### FR4: Project Sorting
- Sort project list alphabetically (A-Z, Z-A)
- Sort project list by open task count (most first, least first)

### FR5: Drag-and-Drop Status Update
- Drag task card between columns to change status
- On drop, write change back to source TODO.md file
- Update the checkbox marker (`[ ]` → `[x]`, etc.)

### FR6: Task Detail View
- Click task card to expand full text
- Show source file path and project name
- Link to open TODO.md in editor (optional)

### FR7: Dashboard Integration
- Add as new tab/view in existing project-tracker dashboard
- Navigation: [Dashboard] [Kanban] [Graph]

---

## Non-Functional Requirements

### NFR1: Performance
- Load all tasks from 20+ projects in under 3 seconds
- Drag-and-drop response under 200ms
- Write-back to TODO.md under 500ms

### NFR2: Reliability
- Handle malformed TODO.md gracefully (skip unparseable tasks, log warning)
- Handle concurrent edit conflicts (warn user, don't overwrite external changes)

### NFR3: Maintainability
- Follow existing project-tracker code patterns
- No new frameworks unless necessary
- Clear separation between parsing, UI, and write-back logic

---

## UX and UI Requirements

### Layout
```
┌─────────────────────────────────────────────────────────────┐
│  project-tracker                         [Dashboard] [Kanban] [Graph] │
├──────────┬──────────────────────────────────────────────────┤
│ Projects │                                                   │
│ ──────── │   Backlog    │   To Do    │ In Progress │  Done  │
│ [Sort ▼] │              │            │             │        │
│          │  ┌─────────┐ │ ┌────────┐ │ ┌─────────┐ │        │
│ ☑ proj-1 │  │ Task A  │ │ │ Task B │ │ │ Task C  │ │        │
│ ☑ proj-2 │  │ proj-1  │ │ │ proj-2 │ │ │ proj-1  │ │        │
│ ☐ proj-3 │  └─────────┘ │ └────────┘ │ └─────────┘ │        │
│ ...      │              │            │             │        │
│          │              │            │             │        │
│ [≡ Hide] │ 12 tasks     │ 8 tasks    │ 3 tasks     │ 47 done│
└──────────┴──────────────────────────────────────────────────┘
```

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

1. **Adoption:** Erik uses Kanban view instead of opening TODO.md files directly
2. **Speed:** Full board loads in under 3 seconds with 20+ projects
3. **Accuracy:** Status changes persist correctly to TODO.md files
4. **Coverage:** Successfully parses 95%+ of tasks from existing TODO.md files

---

## MVP Scope

### MVP (Phase 1)
- [ ] Parse TODO.md files from all projects
- [ ] Display 4-column Kanban board
- [ ] Project sidebar with checkboxes to filter
- [ ] Sort projects alphabetically
- [ ] Dark theme UI
- [ ] Basic task cards (text + project label)

### Post-MVP (Phase 2)
- [ ] Drag-and-drop with write-back to TODO.md
- [ ] Sort by task count
- [ ] Task detail expansion
- [ ] Priority indicators
- [ ] Collapsible sidebar with state persistence

### Future (Phase 3+)
- [ ] Search/filter tasks by text
- [ ] Keyboard shortcuts
- [ ] Export view as markdown

---

## Constraints / Technical Stack

### Must Use
- **Python** - Existing project-tracker is Python
- **Existing dashboard framework** - Whatever project-tracker currently uses
- **SQLite** - Can extend `tracker.db` if needed for caching
- **No new major dependencies** - Prefer stdlib + existing deps

### Must Follow
- Existing project-tracker code patterns
- TODO.md format already used across projects
- Dark theme design language

### Environment
- Runs locally on macOS
- Accessed via browser (localhost)
- Single user (no auth needed)

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| TODO.md format inconsistency | High | Medium | Define canonical format, handle variations gracefully |
| Write-back corrupts TODO.md | Medium | High | Backup before write, atomic updates, test thoroughly |
| Performance with many tasks | Medium | Medium | Lazy loading, virtualized list if needed |
| Dashboard framework limitations | Unknown | High | Explore current framework first, pivot if needed |
| Concurrent edit conflicts | Low | Medium | Detect external changes, warn user, don't overwrite |

---

## Open Questions

1. **What framework does project-tracker dashboard currently use?** (Streamlit? Flask? Plain HTML?)
2. **Is there an existing task parser?** Does project-tracker already extract individual tasks or just completion %?
3. **Standard for "in progress"?** Need to pick/document the `[~]` or `🔄` convention.

---

*This is a Feature PRD following Erik's 13-section template. Scoped to the Kanban feature only - does not document existing project-tracker functionality.*
