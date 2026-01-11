# Integration Strategy: Project Tracker ↔ Project Scaffolding

**Date:** December 22, 2025, 11:15 AM  
**Author:** Claude Sonnet 4.5  
**Context:** First AI-initiated project thoughts

---

## The Relationship

These are **complementary meta-tools** operating at different stages:

```
PROJECT LIFECYCLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 project-scaffolding          🎯 project-tracker
   "How to BUILD projects"         "What IS running"
          ↓                               ↓
   [Templates]                      [Registry]
   [Patterns]                       [Status]
   [Safety]                         [Visibility]
          ↓                               ↓
    NEW PROJECT  ─────────────────→  TRACKED PROJECT
          ↓                               ↓
    [Development]                    [Monitoring]
          ↓                               ↓
    [Production]  ←────────────────  [Context Switch]
```

---

## What Each Project Does

### Project Scaffolding (The Blueprint)

**Purpose:** Make projects consistent, safe, and fast to start

**Provides:**
- Templates (Documents/, .cursorrules, CLAUDE.md)
- Patterns (safety systems, tiered sprint planning, etc.)
- Kickoff guides (how to start a new project)
- External resources tracking (EXTERNAL_RESOURCES.md)

**Audience:** You, when starting new projects OR extracting patterns

**Use case:** "I'm starting a new project, what structure should it have?"

---

### Project Tracker (The Dashboard)

**Purpose:** Prevent spinning-plates chaos, provide visibility

**Provides:**
- Project registry (what exists, what's active)
- Status tracking (active/dev/paused/stalled)
- Cron job visibility (what's running when)
- Service dependency lookup (which project uses what)
- Context switching helper (remind me what this project does)

**Audience:** You, when switching between projects OR checking status

**Use case:** "I'm opening Cursor, which project am I in? What's running? What should I remember?"

---

## How They Work Together

### Flow 1: Starting a New Project

```
1. Use project-scaffolding templates
   ↓
2. Copy Documents/, .cursorrules, CLAUDE.md
   ↓
3. Customize for your project
   ↓
4. Register in project-tracker
   ↓
5. Start building
   ↓
6. Tracker monitors status automatically
```

### Flow 2: Working on Existing Project

```
1. Open project-tracker dashboard
   ↓
2. See: "image-workflow - Last work: 2 days ago"
   ↓
3. Click/switch to image-workflow
   ↓
4. Tracker shows context:
   - Cron jobs running
   - Services used
   - Recent files
   - Safety reminders
   ↓
5. Start work with full context
```

### Flow 3: Adding External Service

```
1. Project needs OpenAI
   ↓
2. Update project-scaffolding/EXTERNAL_RESOURCES.md
   (per Cursor user rule)
   ↓
3. Project-tracker reads EXTERNAL_RESOURCES.md
   ↓
4. Tracker now shows:
   "image-workflow uses: OpenAI, rclone"
   ↓
5. Next time: "Which project uses OpenAI?" 
   → Tracker answers instantly
```

### Flow 4: Extracting Patterns

```
1. Build something in a project (e.g., run tracking in agent_os)
   ↓
2. Works well across 2-3 projects
   ↓
3. Extract to project-scaffolding/patterns/
   ↓
4. Document in scaffolding
   ↓
5. Future projects use the pattern
   ↓
6. Tracker shows which projects use which patterns
```

---

## Shared Data & Single Sources of Truth

### EXTERNAL_RESOURCES.md

**Lives in:** project-scaffolding  
**Read by:** project-tracker (for service dependencies)  
**Updated by:** Any project (via Cursor user rule)

**Why here?** Scaffolding is the "how to manage projects" authority. Resources are part of management.

**How tracker uses it:**
```python
# project-tracker reads this
resources = parse_external_resources_md()
# Shows: "Trading: Railway, Postgres, Discord"
```

---

### Project Metadata

**Lives in:** Each project (README.md, .cursorrules, CLAUDE.md)  
**Read by:** project-tracker (for status, description, phase)  
**Created from:** project-scaffolding templates

**Why?** Each project owns its metadata, tracker aggregates it.

---

### Patterns

**Lives in:** project-scaffolding/patterns/  
**Used by:** All projects  
**Tracked by:** project-tracker ("Which projects use tiered sprint planning?")

**Why?** Patterns are reusable knowledge. Scaffolding is the knowledge repository.

---

## What Goes Where?

### In Project Scaffolding

✅ **Templates** - Starting points for new projects  
✅ **Patterns** - Reusable architectural patterns  
✅ **Guides** - How to start projects, kickoff workflows  
✅ **External Resources** - Single source of truth for services  
✅ **Philosophy** - Development principles  

❌ **Project status** - That's tracker's job  
❌ **Cron job registry** - That's tracker's job  
❌ **Active project list** - That's tracker's job  

---

### In Project Tracker

✅ **Project registry** - What exists, where it lives  
✅ **Status tracking** - Active/dev/paused/stalled  
✅ **Cron jobs** - What's scheduled, when, where  
✅ **Last modified** - When was work done  
✅ **Context switching** - Quick project summaries  

❌ **Templates** - That's scaffolding's job  
❌ **Patterns** - That's scaffolding's job  
❌ **How to build** - That's scaffolding's job  

---

## Technical Integration Points

### 1. Tracker Reads Scaffolding's EXTERNAL_RESOURCES.md

```python
# project-tracker/src/integrations/scaffolding.py

def get_service_dependencies(project_name: str) -> list[str]:
    """Read EXTERNAL_RESOURCES.md from scaffolding."""
    path = Path("../project-scaffolding/EXTERNAL_RESOURCES.md")
    resources = parse_resources(path.read_text())
    return resources.get(project_name, [])
```

**Why?** Single source of truth. Tracker doesn't duplicate service data.

---

### 2. Tracker Checks for Scaffolding Templates

```python
# When registering new project
def check_scaffolding_compliance(project_path: Path) -> dict:
    """Check if project uses scaffolding templates."""
    return {
        "has_documents_dir": (project_path / "Documents").exists(),
        "has_claude_md": (project_path / "CLAUDE.md").exists(),
        "has_cursorrules": (project_path / ".cursorrules").exists(),
        "scaffolded": all([...]),
    }
```

**Why?** Show which projects follow scaffolding patterns. Identify projects that need structure.

---

### 3. Scaffolding Suggests Tracker Registration

```markdown
<!-- In project-scaffolding/docs/PROJECT_KICKOFF_GUIDE.md -->

### Step 4: Register in Project Tracker

After copying templates, register your project:

```bash
cd ../project-tracker
python tracker.py register my-new-project \
  --status dev \
  --description "My new project" \
  --phase "Layer 1"
```

This ensures the project appears in status dashboards.
```

**Why?** Make registration part of the kickoff workflow.

---

### 4. Tracker Shows Pattern Usage

```
📊 PATTERN USAGE ACROSS PROJECTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tiered Sprint Planning:
  • Trading Co-Pilot ✓
  • Hologram ✓
  • land (planned)

Safety Systems (append-only):
  • image-workflow ✓ (battle-tested)
  • Cortana ✓

Documents/ Structure:
  • image-workflow ✓
  • Trading Co-Pilot ✓
  • project-scaffolding ✓
```

**Why?** Shows pattern adoption. Identifies projects that could benefit from patterns.

---

## User Workflows (Real Scenarios)

### Scenario 1: "Which Project Uses Cloudflare?"

**Without these tools:**
1. Grep through projects manually
2. Check billing emails
3. Ask AI to search
4. Guess based on memory

**With these tools:**
1. Open project-tracker dashboard
2. See: "3D Pose Factory - Cloudflare R2 ($0/mo)"
3. Done.

**Which tool answers it?** Tracker (reading scaffolding's EXTERNAL_RESOURCES.md)

---

### Scenario 2: "Starting a New Email Monitoring Project"

**Without these tools:**
1. Create directory
2. Guess at structure
3. Forget to add .gitignore
4. Forget to document services
5. Build from scratch

**With these tools:**
1. `cd project-scaffolding`
2. Copy templates
3. Customize for email monitoring
4. Register in tracker
5. Start building (structure already there)

**Which tool helps?** Scaffolding (templates), Tracker (registration)

---

### Scenario 3: "I Haven't Worked on 'land' in 2 Months"

**Without these tools:**
1. Don't realize it's stalled
2. Eventually notice
3. "What was I doing?"
4. Re-read everything
5. Lost context

**With these tools:**
1. Tracker dashboard shows: "⚠️ land - Stalled 60+ days"
2. Alerts you proactively
3. Click → See last work, blockers, context
4. Resume with context intact

**Which tool helps?** Tracker (monitoring, alerts)

---

### Scenario 4: "Switching from Trading to image-workflow"

**Without these tools:**
1. Close Cursor window (Trading)
2. Open new Cursor window (image-workflow)
3. "Wait, what was I doing here?"
4. "What's running? Any cron jobs?"
5. "What services does this use?"
6. Spend 5 minutes re-orienting

**With these tools:**
1. `pt switch image-workflow`
2. See: Status, cron jobs, services, recent files, safety reminders
3. Start work immediately

**Which tool helps?** Tracker (context switching helper)

---

## The Meta-Level Game

Both projects operate at **Level 2** (building projects themselves):

```
LEVEL 1: Domain Projects
━━━━━━━━━━━━━━━━━━━━━━━
• image-workflow (image processing)
• Trading Co-Pilot (trading signals)
• Cortana (personal AI)
• land (property monitoring)

LEVEL 2: Meta-Projects
━━━━━━━━━━━━━━━━━━━━━━━
• project-scaffolding (how to build)
• project-tracker (what is running)

LEVEL 3: Meta-Meta (?)
━━━━━━━━━━━━━━━━━━━━━━━
• This document? 🤔
```

**Scaffolding** makes Level 1 projects **better**.  
**Tracker** makes Level 1 projects **manageable**.

Together they make **scale possible**.

---

## Success Criteria for Integration

**After 1 week:**
- [ ] Tracker can read EXTERNAL_RESOURCES.md from scaffolding
- [ ] Tracker shows which projects use scaffolding templates
- [ ] Kickoff guide mentions tracker registration

**After 1 month:**
- [ ] New projects start with scaffolding → register in tracker
- [ ] Pattern usage visible across projects
- [ ] Service lookups work: "Which uses X?" → instant answer

**After 3 months:**
- [ ] Both tools are daily-use
- [ ] Patterns flow: project → scaffolding → other projects
- [ ] Chaos measurably reduced

---

## Open Questions

**For Erik:**
1. Should tracker auto-detect scaffolded projects or require manual registration?
2. Should scaffolding kickoff guide auto-register in tracker (via script)?
3. Should patterns include "adoption status" (which projects use them)?
4. Should there be a "scaffolding health score" per project?

**Technical:**
1. How often should tracker re-scan projects? (Daily? On-demand? Real-time?)
2. Should tracker write back to projects (e.g., update last_modified)?
3. Should scaffolding include tracker as a recommended tool in templates?
4. Should patterns include "tracker-compatible metadata"?

---

## Implementation Priority

### Phase 0 (This Week) - Prove Value
1. Build basic tracker (SQLite + CLI)
2. Manually register 3-4 projects
3. Read EXTERNAL_RESOURCES.md for service deps
4. Show it works

### Phase 1 (Week 2) - Integration
1. Tracker checks for scaffolding compliance
2. Update scaffolding kickoff guide with tracker registration
3. Show pattern usage across projects

### Phase 2 (Week 3+) - Automation
1. Auto-detect scaffolded projects
2. Suggest missing templates
3. Alert on stale projects
4. Context switching helper

---

## Key Insight

**Scaffolding is the BLUEPRINT.**  
**Tracker is the DASHBOARD.**

Blueprints tell you how to build.  
Dashboards show you what's running.

You need both.

Scaffolding without Tracker = Good structure, poor visibility.  
Tracker without Scaffolding = Good visibility, inconsistent structure.

Together = Organized, visible, scalable project ecosystem.

---

## Final Thought

This is the first AI-initiated project. The fact that I'm writing this integration doc before any code exists is wild.

We're not just building projects. We're building the system that builds projects. And now we're building the system that tracks the projects that the system builds.

**The meta-level game continues.**

And it's working.

---

**Written by Claude Sonnet 4.5, December 22, 2025, 11:15 AM**  
**First thoughts on first AI-initiated project**

*Let's see where this goes.* 🚀

