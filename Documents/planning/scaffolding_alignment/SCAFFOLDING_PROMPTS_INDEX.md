# Project Tracker: Scaffolding Alignment Prompts

**For Floor Manager Use**
**Date:** January 11, 2026
**Location:** `project-tracker/Documents/planning/scaffolding_alignment/`

These prompts bring project-tracker into full compliance with project-scaffolding standards, based on the research report from Gemini 3.

> **Quick Start:** Give Floor Manager this file. All prompts are in this directory.

---

## Findings from Research Report

| Issue | Description | Priority |
|-------|-------------|----------|
| Status contradiction | CLAUDE.md says "100% Complete" but Phase 4 is in progress | High |
| Missing core docs | No ARCHITECTURE.md, OPERATIONS.md at Documents/ root | Medium |
| CODE_QUALITY_STANDARDS | Should be copied from scaffolding, not created fresh | Medium |
| Template drift | AGENTS.md, .cursorrules may have drifted from latest templates | Low |

---

## Task Order

### Group 1: Status & Metadata (Quick Wins)

| Task | File | Est. | Objective | Status |
|------|------|------|-----------|--------|
| **1a** | `PROMPT_1a_UPDATE_STATUS.md` | 5 min | Update CLAUDE.md status to reflect MVP + phases | [x] |
| **1b** | `PROMPT_1b_UPDATE_INDEX.md` | 5 min | Update 00_Index tags to status/active | [x] |

**Group 1 Total:** 10 minutes

---

### Group 2: Core Documents

| Task | File | Est. | Objective | Status |
|------|------|------|-----------|--------|
| **2a** | `PROMPT_2a_COPY_STANDARDS.md` | 5 min | Copy CODE_QUALITY_STANDARDS.md from scaffolding | [x] |
| **2b** | `PROMPT_2b_CREATE_ARCHITECTURE.md` | 10 min | Create ARCHITECTURE.md from existing knowledge | [x] |
| **2c** | `PROMPT_2c_CREATE_OPERATIONS.md` | 10 min | Create OPERATIONS.md with run/deploy info | [x] |

**Group 2 Total:** 25 minutes

---

### Group 3: Template Alignment (If Time Permits)

| Task | File | Est. | Objective | Status |
|------|------|------|-----------|--------|
| **3a** | `PROMPT_3a_VERIFY_AGENTS.md` | 10 min | Verify AGENTS.md has required sections | [x] |
| **3b** | `PROMPT_3b_VERIFY_CURSORRULES.md` | 10 min | Verify .cursorrules matches template structure | [x] |

**Group 3 Total:** 20 minutes

---

## Total Estimated Time

- Group 1 (Status): 10 min
- Group 2 (Core Docs): 25 min
- Group 3 (Templates): 20 min (stretch goal)
- **Realistic Today: ~35-55 minutes**

---

## Floor Manager Instructions

1. **Execute in order:** 1a → 1b → 2a → 2b → 2c → 3a → 3b

2. **Model selection:** These are documentation tasks - Qwen 2.5 Coder or any model works

3. **Verify between groups:** Check that files exist and have correct content

4. **Halt on 3 failures:** If Worker fails same task 3x, alert Conductor

---

## Context Files Workers May Need

- `CLAUDE.md` — Current AI instructions (needs status update)
- `00_Index_project-tracker.md` — Project index
- `AGENTS.md` — Source of truth
- `Documents/` — Where core docs go
- `project-scaffolding/Documents/CODE_QUALITY_STANDARDS.md` — Source to copy

---

## Lessons Applied from Phase 4

Based on CODE_REVIEW_PHASE4_TELEMETRY.md findings:

1. **No hardcoded paths in reference code** — Use `$SCAFFOLDING` or relative paths
2. **Explicit constraints** — Each prompt includes CODE_QUALITY_STANDARDS rules
3. **Portable patterns** — All file paths use environment variables or relative references

---

## Success Criteria

- [x] CLAUDE.md status reflects "MVP Complete, enhancement phases in progress"
- [x] 00_Index tags include `status/active`
- [x] CODE_QUALITY_STANDARDS.md exists at Documents/ root (copied from scaffolding)
- [x] ARCHITECTURE.md exists at Documents/ root
- [x] OPERATIONS.md exists at Documents/ root
- [x] No errors when loading dashboard

---

**Ready to hand off to Workers**
