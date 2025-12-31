# Dashboard Project - Discussion Summary

**Date:** December 30, 2025  
**Context:** Erik wants to shift focus to project dashboard development

---

## What We Just Accomplished ✅

### 1. Created Comprehensive Dashboard TODO
**File:** `/Users/eriksjaastad/projects/project-tracker/TODO.md`

**Content (430+ lines):**
- Complete project status and current state
- Detailed phase breakdown (Phase 0: TODO standardization, MVP, enhancements)
- All requirements Erik mentioned:
  - ✅ Chronological sorting (newest work first)
  - ✅ AI agents tracking (which AI helping with what)
  - ✅ Cron jobs display
  - ✅ Services used
  - ✅ TODO.md viewer with markdown rendering
  - ✅ Progress bars based on completion %
  - ✅ Dashboard tracks itself (meta!)
- Time estimates (28-38 hours total)
- Cost estimates ($0 - all local)
- Integration points with other projects

### 2. Created TODO Standard Template
**File:** `/Users/eriksjaastad/projects/project-scaffolding/templates/TODO.md.template`

**Features:**
- Required sections: Header, Current State, Completed, Pending, Success Criteria, Notes
- Optional sections: Change Log, Technical Stack, Integration Learnings
- NEW metadata sections:
  - AI Agents in Use (tracks which AI helping with what)
  - Cron Jobs / Automation (scheduled tasks)
  - External Services Used
- Comprehensive guidance comments for AI sessions
- Flexible (scales from simple to complex projects)
- Examples and placeholders throughout

### 3. Documented Format Standard
**File:** `/Users/eriksjaastad/projects/project-scaffolding/docs/TODO_FORMAT_STANDARD.md`

**Content (650+ lines):**
- Analysis of 4 real projects' TODO formats
- What works well (Cortana's layering, YouTube's staging, etc.)
- Required vs optional sections
- Priority system (🔴 🟡 🔵 🟢)
- Task organization patterns (phase-based, sprint-based, stage-based)
- AI session guidance (how to read, update, handoff)
- Flexibility guidelines (simple vs complex projects)
- Dashboard integration details
- Examples from real projects
- Success metrics

---

## TODO Format Analysis

### Projects Analyzed
1. **Cortana Personal AI** (660 lines) - ✅ Excellent structure
2. **analyze-youtube-videos** (400 lines) - ✅ Good stage breakdown
3. **actionable-ai-intel** (350 lines) - ✅ Clear blockers
4. **project-scaffolding** (107 lines) - ✅ Minimal but clear

### Common Patterns Found
- Header with status, phase, last updated
- Current State (what works, what's missing, blockers)
- Completed tasks (with dates, kept for progress)
- Pending tasks (prioritized)
- Success criteria
- Notes (costs, time, related projects)

### What Varies
- Length (107 to 660 lines)
- Organization (layers vs phases vs sprints vs stages)
- Detail level
- AI agent tracking (inconsistent)

### Recommended Standard
**Required:**
- Header, Current State, Completed, Pending, Success Criteria

**Optional:**
- AI Agents, Cron Jobs, Services, Cost/Time, Related Docs, Change Log

**New Additions:**
- AI Agents section (which AI, what role)
- Cron Jobs section (schedule, command, status)
- Standardized priority emojis (🔴 🟡 🔵 🟢)

---

## Dashboard Requirements (Erik's Request)

### Core Features
1. **Chronological sorting** - Projects by last modified (newest first)
2. **AI agents display** - Which AI working on what
3. **Cron jobs indicator** - ⏰ for scheduled tasks
4. **Services used** - From EXTERNAL_RESOURCES.md
5. **TODO.md viewer** - Click to view rendered markdown
6. **Progress bars** - Based on TODO completion %
7. **Self-tracking** - Dashboard tracks itself (meta!)

### Technical Approach
**Backend:**
- SQLite database (local, no server)
- Python CLI tool (Typer framework)
- Auto-discovery (scan projects directory)
- Git integration (last modified timestamp)

**Web Dashboard:**
- FastAPI (lightweight, fast)
- Simple HTML/CSS (no frameworks)
- Markdown renderer for TODO.md
- Auto-refresh (60 seconds)

**Data Extracted:**
- Project metadata (name, path, status, phase)
- Timestamps (created, last modified)
- AI agents (from TODO.md, CLAUDE.md, .cursorrules)
- Cron jobs (from crontab, launchd plists)
- Services (from EXTERNAL_RESOURCES.md)
- Progress (calculated from TODO checkboxes)

---

## Implementation Plan

### Phase 0: TODO Standardization (2-3 hours)
✅ **DONE:**
- [x] Analyze existing TODO formats
- [x] Create standard template
- [x] Document format rationale

**REMAINING:**
- [ ] Get Erik's approval on format
- [ ] Test template on 1-2 projects
- [ ] Refine based on feedback

### Phase 1: Dashboard MVP (14-18 hours)
- [ ] SQLite database with schema
- [ ] CLI tool (add, list, scan, update)
- [ ] Auto-discovery (scan projects, git metadata)
- [ ] Cron job detection (crontab, launchd)
- [ ] Service dependency parsing (EXTERNAL_RESOURCES.md)
- [ ] AI agent detection (TODO.md, CLAUDE.md)
- [ ] Web dashboard (FastAPI + HTML)
- [ ] TODO.md markdown viewer
- [ ] Progress bars
- [ ] Testing on real projects

### Phase 2: Polish (6-8 hours)
- [ ] Daily automation (refresh data)
- [ ] Enhanced metadata extraction
- [ ] Search/filter/grouping
- [ ] UI enhancements

### Phase 3: Advanced (6-9 hours)
- [ ] Context switching helper
- [ ] Git commit tracking
- [ ] Cost tracking integration
- [ ] Cursor integration

**Total Time:** 28-38 hours over 2-3 weeks

---

## Dashboard Data Model

### Tables
```sql
-- Core project data
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL,
    description TEXT,
    phase TEXT,
    last_modified TEXT,
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
    agent_name TEXT NOT NULL,
    role TEXT,
    notes TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Activity log
CREATE TABLE work_log (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT,
    details TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
```

---

## Key Design Decisions

### 1. TODO Standardization FIRST
**Why:** Dashboard needs consistent data structure to extract metadata

**Order:**
1. Create standard template ✅
2. Document rationale ✅
3. Get Erik's approval (NEXT)
4. Test on 2-3 projects
5. THEN build dashboard to consume standardized data

### 2. Local-First Architecture
**Why:** No cloud costs, no external dependencies, fast, private

**Stack:**
- SQLite (not Postgres/MySQL)
- FastAPI (not cloud-hosted)
- Local file scanning (not API)
- Git metadata (already local)

### 3. Chronological Sorting Priority
**Key Requirement:** Sort by last modified, not creation date

**Why:**
- Erik works on many projects simultaneously
- Needs to see "what was I just working on?"
- Creation date irrelevant for active work

**Implementation:**
- Extract git last commit date
- Fall back to file modification time
- Update on every scan

### 4. AI Agent Tracking
**New Feature:** Track which AI helping with what

**Why:**
- Multiple AIs in use (Claude, Cursor, ChatGPT, etc.)
- Need visibility into which AI working on which project
- Helps with context switching

**Data sources:**
- TODO.md "AI Agents in Use" section
- CLAUDE.md mentions
- .cursorrules references
- Manual CLI adds

### 5. Meta-Tracking
**Requirement:** Dashboard must track itself

**Why:**
- Dogfooding (use what we build)
- Test case for auto-discovery
- Shows dashboard in action

**Implementation:**
- project-tracker/ appears in project list
- Status: Active Development
- AI agent: Claude Sonnet 4.5 (PM + Implementation)
- Last modified: updates as work happens

---

## Questions for Erik

Before proceeding with dashboard implementation:

### 1. TODO Format Approval
**Does the standard format work for you?**
- Required sections: Header, Current State, Completed, Pending, Success Criteria, Notes
- Optional sections: Change Log, Technical Stack, etc.
- New metadata: AI Agents, Cron Jobs, Services
- 4-level priority system (🔴 🟡 🔵 🟢)

**Or need changes?**

### 2. Dashboard MVP Scope
**Are these the right MVP features?**
- Project list (sorted by last modified)
- Status badges
- AI agents display
- Cron jobs indicator
- Services used
- Click → view TODO.md
- Progress bars

**Or need different priorities?**

### 3. Implementation Timeline
**Should we:**
- **Option A:** Build dashboard now (14-18 hours) - Full implementation
- **Option B:** Test TODO format first (2-3 hours) - Validate before building
- **Option C:** Minimal prototype (4-6 hours) - Prove concept quickly

**Which path?**

### 4. Other Projects Status
**What about:**
- **YouTube analysis** - Paused? (was testing skills library)
- **Actionable AI Intel** - Paused? (was waiting for Discord webhook)
- **Agent skills library** - Complete for now?

**Any of these need attention first?**

---

## Files Created

1. `/Users/eriksjaastad/projects/project-tracker/TODO.md` (430+ lines)
2. `/Users/eriksjaastad/projects/project-scaffolding/templates/TODO.md.template` (250+ lines)
3. `/Users/eriksjaastad/projects/project-scaffolding/docs/TODO_FORMAT_STANDARD.md` (650+ lines)

**Total:** 1,330+ lines of documentation and templates

---

## Next Steps (Waiting on Erik)

### Immediate
1. **Review TODO format standard** - Does it work for your workflow?
2. **Approve or request changes** - Any sections missing or unnecessary?
3. **Decide implementation path** - Build dashboard now, test format first, or quick prototype?
4. **Clarify project priorities** - Focus on dashboard only, or balance with other projects?

### After Approval
1. Test TODO template on 1-2 existing projects
2. Refine based on real usage
3. Build dashboard MVP (if approved)
4. Test dashboard on Erik's projects
5. Iterate based on feedback

---

## Success Criteria

**TODO standardization successful if:**
- Erik can glance at any TODO and know project state
- AI sessions can orient in < 2 minutes
- Dashboard can extract all needed metadata
- Handoffs between sessions are smooth

**Dashboard MVP successful if:**
- Shows all projects sorted by last work
- Displays AI agents, cron jobs, services
- TODO.md viewer works correctly
- Progress bars reflect real completion
- Erik uses it daily for 1 week

---

**Ready for discussion! What do you think? 🎯**

