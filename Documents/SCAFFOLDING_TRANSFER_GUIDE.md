# Scaffolding Transfer Guide: project-tracker

> **Purpose:** Checklist and guide for incorporating project-scaffolding systems into project-tracker
> **Created:** January 11, 2026
> **Goal:** Bring project-tracker to Gold Standard compliance

---

## Quick Start Checklist (From README)

Based on `project-scaffolding/README.md` "Quick Start" section:

### Starting a New Project (Adapted for Existing Project)

| Step | README Instruction | Status | Notes |
|------|-------------------|--------|-------|
| 1 | Read [[PROJECT_KICKOFF_GUIDE]] | ⚠️ Partial | Should review for any missed steps |
| 2 | Follow [[PROJECT_STRUCTURE_STANDARDS]] | ✅ Done | venv in root, scripts/, data/, Documents/ |
| 3 | Follow [[CODE_QUALITY_STANDARDS]] | ⚠️ AUDIT NEEDED | Need to verify 4 critical rules |
| 4 | Copy templates (.cursorrules, CLAUDE.md, etc.) | ✅ Done | Templates applied + safety injection |
| 5 | Plan using [[TIERED_AI_SPRINT_PLANNING]] | ✅ Done | Phase 4 prompts use tiered approach |
| 6 | Execute with appropriate models | 🔄 In Progress | Today's work uses local models |
| 7 | Track external resources in [[EXTERNAL_RESOURCES]] | ✅ Done | Listed: SQLite, FastAPI ($0/mo) |

### README Items Not Mentioned But Now Critical

These systems were built AFTER the README was written:

| System | Status in project-tracker | README Mentions? |
|--------|--------------------------|------------------|
| [[AGENTS_CONSTITUTION]] (4-tier) | ✅ Referenced | ❌ No |
| Global Rules Injection | ✅ Applied | ❌ No |
| Prompt pattern for local models | ✅ Using today | ❌ No |
| [[LOCAL_MODEL_LEARNINGS]] | ✅ Created | ❌ No |
| Warden audit system | ❌ Not integrated | ❌ No |
| Pre-commit hooks | ❌ Not set up | ❌ No |

### README Update Recommendations

The project-scaffolding README should be updated to include:

1. **[[AGENTS_CONSTITUTION]]** - The 4-tier hierarchy (Conductor → Super Manager → Floor Manager → Workers)
2. **Prompt Pattern** - Micro-task prompts with acceptance criteria for local models
3. **[[LOCAL_MODEL_LEARNINGS]]** - Institutional memory for AI model behavior
4. **Global Rules Injection** - The update_cursorrules.py system
5. **[[WARDEN_AUDIT]]** - Security audit tool (warden_audit.py)
6. **Timeline Update** - Current dates (we're past "Month 6" in the timeline)

---

## Executive Summary

Project-scaffolding has evolved into an ecosystem constitution with **13+ patterns, 12+ templates, 4 critical code quality rules, and 6 safety systems**. This guide tracks what project-tracker has incorporated vs. what still needs work.

---

## 1. Core Governance Files

### Status: PARTIAL

| File | Status | Notes |
|------|--------|-------|
| `.cursorrules` | ✅ Done | Safety rules injected (Jan 10) |
| `AGENTS.md` | ⚠️ Minimal | Has tech stack but missing hierarchy reference |
| `CLAUDE.md` | ✅ Done | References [[AGENTS_CONSTITUTION]] |
| `00_Index_project-tracker.md` | ✅ Done | Exists and maintained |

---

## 2. Documents Structure ("Active OS" Pattern)

### Status: NEW - Just Created

| Directory | Status | Purpose |
|-----------|--------|---------|
| `Documents/` | ✅ Created | Root |
| `Documents/README.md` | ✅ Created | Index |
| `Documents/planning/` | ✅ Created | Active work planning |
| `Documents/guides/` | ❌ Missing | How-to documents |
| `Documents/reference/` | ❌ Missing | Knowledge base |
| `Documents/archives/` | ❌ Missing | Historical data |

### Action Items
- [x] Create Documents/ directory structure
- [x] Create [[Documents_README_Index]]
- [ ] Create guides/ with project-specific how-tos
- [ ] Create reference/ for [[LOCAL_MODEL_LEARNINGS]]
- [ ] Create archives/ for completed work

---

## 3. Code Quality Standards (4 Critical Rules)

### Status: NEEDS AUDIT

| Rule | Status | Evidence |
|------|--------|----------|
| **#0: Index File Required** | ✅ Done | `00_Index_project-tracker.md` exists |
| **#1: No Silent Failures** | ⚠️ Unknown | Need to audit all Python files |
| **#2: Subprocess Integrity** | ⚠️ Unknown | Need to check `check=True` + `timeout` |
| **#3: Memory Guards** | ⚠️ Unknown | Does pt scan handle 100+ projects? |
| **#4: Path Safety** | ⚠️ Known Issue | Has absolute paths in .cursorrules |

### Action Items
- [ ] Audit all Python files for `except: pass` (Rule #1)
- [ ] Audit all `subprocess.run()` calls (Rule #2)
- [ ] Check pt scan for memory guards with large project counts (Rule #3)
- [ ] Remove hardcoded `$HOME/` paths (Rule #4)

---

## 4. Safety Systems (6 Proven Patterns)

### Status: PARTIAL

| Pattern | Status | Evidence |
|---------|--------|----------|
| **Append-Only Archives** | ❌ Not Implemented | No append-only logs |
| **Read-Only Source** | ✅ Done | Reads [[TODO]]/README.md, doesn't modify |
| **Atomic Writes** | ⚠️ Unknown | Need to check database writes |
| **Move, Don't Modify** | N/A | Not applicable (no file moving) |
| **Trash, Don't Delete** | ✅ In .cursorrules | Rule documented |
| **Validate Before Write** | ⚠️ Unknown | Need to check database operations |

---

## Priority Action Items for Today

### Before Starting Phase 4 Work

1. **[HIGH]** Create `Documents/reference/LOCAL_MODEL_LEARNINGS.md`
   - We're about to use local models
   - Need somewhere to capture learnings

2. **[MEDIUM]** Audit for hardcoded paths
   - .cursorrules has `$PROJECTS_ROOT`
   - Should use environment variable or relative paths

3. **[LOW]** Complete Documents/ structure
   - Add guides/, reference/, archives/

---

## Gold Standard Checklist

### Foundation (Must Have)
- [x] `.cursorrules` with safety rules
- [x] `AGENTS.md` referencing [[AGENTS_CONSTITUTION]]
- [x] `CLAUDE.md` with project context
- [x] `00_Index_*.md` maintained
- [ ] No hardcoded absolute paths
- [ ] No silent exception swallowing

### Documentation (Should Have)
- [x] `Documents/` structure created
- [x] `Documents/README.md` index
- [ ] `Documents/reference/LOCAL_MODEL_LEARNINGS.md`
- [ ] `Documents/guides/` with how-tos
- [x] Comprehensive [[README]]
- [x] [[TODO]] with status tracking

---

*This guide will be updated as we progress through the canary test.*
*See also: [[PROJECT_STRUCTURE_STANDARDS]] and [[CODE_QUALITY_STANDARDS]].*

## Related Documentation

- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[database_setup]] - database
- [[prompt_engineering_guide]] - prompt engineering
- [[adult_business_compliance]] - adult industry
- [[ai_model_comparison]] - AI models
- [[security_patterns]] - security
- [[project-scaffolding/README]] - Project Scaffolding
- [[project-tracker/README]] - Project Tracker
