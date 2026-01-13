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
| 1 | Read `Documents/PROJECT_KICKOFF_GUIDE.md` | ⚠️ Partial | Should review for any missed steps |
| 2 | Follow `Documents/PROJECT_STRUCTURE_STANDARDS.md` | ✅ Done | venv in root, scripts/, data/, Documents/ |
| 3 | Follow `Documents/CODE_QUALITY_STANDARDS.md` | ⚠️ AUDIT NEEDED | Need to verify 4 critical rules |
| 4 | Copy templates (.cursorrules, CLAUDE.md, etc.) | ✅ Done | Templates applied + safety injection |
| 5 | Plan using Tiered AI Sprint Planning | ✅ Done | Phase 4 prompts use tiered approach |
| 6 | Execute with appropriate models | 🔄 In Progress | Today's work uses local models |
| 7 | Track external resources in EXTERNAL_RESOURCES.md | ✅ Done | Listed: SQLite, FastAPI ($0/mo) |

### README Items Not Mentioned But Now Critical

These systems were built AFTER the README was written:

| System | Status in project-tracker | README Mentions? |
|--------|--------------------------|------------------|
| AGENTS.md hierarchy (4-tier) | ✅ Referenced | ❌ No |
| Global Rules Injection | ✅ Applied | ❌ No |
| Prompt pattern for local models | ✅ Using today | ❌ No |
| LOCAL_MODEL_LEARNINGS.md | ✅ Created | ❌ No |
| Warden audit system | ❌ Not integrated | ❌ No |
| Pre-commit hooks | ❌ Not set up | ❌ No |

### README Update Recommendations

The project-scaffolding README should be updated to include:

1. **AGENTS.md** - The 4-tier hierarchy (Conductor → Super Manager → Floor Manager → Workers)
2. **Prompt Pattern** - Micro-task prompts with acceptance criteria for local models
3. **LOCAL_MODEL_LEARNINGS.md** - Institutional memory for AI model behavior
4. **Global Rules Injection** - The update_cursorrules.py system
5. **Warden** - Security audit tool (warden_audit.py)
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
| `CLAUDE.md` | ✅ Done | References AGENTS.md |
| `00_Index_project-tracker.md` | ✅ Done | Exists and maintained |

### Action Items
- [x] Add universal constitution reference to AGENTS.md (done today)
- [ ] Verify .cursorrules has all critical constraints from template

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
- [x] Create Documents/README.md index
- [ ] Create guides/ with project-specific how-tos
- [ ] Create reference/ for LOCAL_MODEL_LEARNINGS
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
| **Read-Only Source** | ✅ Done | Reads TODO.md/README.md, doesn't modify |
| **Atomic Writes** | ⚠️ Unknown | Need to check database writes |
| **Move, Don't Modify** | N/A | Not applicable (no file moving) |
| **Trash, Don't Delete** | ✅ In .cursorrules | Rule documented |
| **Validate Before Write** | ⚠️ Unknown | Need to check database operations |

### Action Items
- [ ] Audit `scripts/db/` for atomic writes
- [ ] Verify send2trash is used if any deletions exist
- [ ] Add append-only logging for scan history (nice to have)

---

## 5. Templates Applied

### Status: PARTIAL

| Template | Status | Notes |
|----------|--------|-------|
| `.cursorrules` | ✅ Applied | From template + safety injection |
| `AGENTS.md` | ⚠️ Minimal | Missing hierarchy, updated today |
| `CLAUDE.md` | ✅ Applied | References scaffolding |
| `TODO.md` | ⚠️ Custom | Uses custom format, not standard |
| `README.md` | ✅ Done | Comprehensive |
| `00_Index_*.md` | ✅ Done | Follows template |

### Action Items
- [ ] Consider updating TODO.md to standard format
- [ ] Verify all templates are project-scaffolding aligned

---

## 6. Patterns to Apply

### Immediately Relevant

| Pattern | Priority | Why |
|---------|----------|-----|
| **Tiered AI Sprint Planning** | HIGH | project-tracker uses AI extensively |
| **Local AI Integration** | HIGH | Today's work adds AI Router integration |
| **SSOT via YAML** | MEDIUM | External resources tracking |
| **Learning Loop** | MEDIUM | Document AI model learnings |

### Already Applied

| Pattern | Evidence |
|---------|----------|
| **Layer-by-Layer Development** | Phase 0 → 1 → 2 → 3 → 4 structure |
| **Foundation Documents First** | AGENTS.md, CLAUDE.md exist |
| **API Key Management** | Uses project-specific .env |

### Not Applicable

| Pattern | Why |
|---------|-----|
| Discord Webhooks | No notifications needed yet |
| Automation Reliability | Not a cron job (manual launch) |

---

## 7. Scripts & Automation

### Status: NOT IMPLEMENTED

| Script | Status | Priority |
|--------|--------|----------|
| `pre_review_scan.sh` | ❌ Missing | HIGH - should gate commits |
| `validate_project.py` | ❌ Missing | MEDIUM - structure validation |
| `warden_audit.py` | ❌ Missing | LOW - has audit-agent instead |

### Action Items
- [ ] Create project-tracker specific pre_review_scan.sh
- [ ] Or: integrate with audit-agent (Go binary)

---

## 8. Reference Documents

### Status: NOT CREATED

| Document | Status | Priority |
|----------|--------|----------|
| `LOCAL_MODEL_LEARNINGS.md` | ❌ Missing | HIGH - we're using local models today |
| `PATTERN_ANALYSIS.md` | ❌ Missing | LOW - not extracting patterns |
| `CODE_REVIEW_ANTI_PATTERNS.md` | ❌ Missing | MEDIUM - should document issues |

### Action Items
- [ ] Create `Documents/reference/LOCAL_MODEL_LEARNINGS.md`
- [ ] Start documenting anti-patterns found during Phase 4

---

## 9. Prompt Pattern (For Today's Work)

### Status: ✅ IMPLEMENTED

| Component | Status | Location |
|-----------|--------|----------|
| PROMPTS_INDEX | ✅ Created | `Documents/planning/phase4_telemetry/` |
| Micro-task prompts | ✅ Created | 9 prompt files |
| Acceptance criteria | ✅ In prompts | Binary checklists |
| Constraints section | ✅ In prompts | DO NOT rules |
| Reference code | ✅ In prompts | Copy-paste snippets |

---

## 10. External Resources

### Status: UNKNOWN

| Item | Status | Action |
|------|--------|--------|
| Listed in EXTERNAL_RESOURCES.yaml | ⚠️ Unknown | Check if project-tracker is documented |
| API keys documented | ⚠️ Unknown | Does it use any external services? |

### Action Items
- [ ] Verify project-tracker is in EXTERNAL_RESOURCES.yaml
- [ ] Document any services used (likely none - it's local-only)

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

### During Phase 4 Work

1. Document any local model issues in LOCAL_MODEL_LEARNINGS.md
2. Note any anti-patterns discovered
3. Verify each prompt's acceptance criteria before signing off

### After Phase 4 Work

1. Archive completed prompts to `Documents/archives/planning/`
2. Update TODO.md with completion status
3. Document what worked/didn't work

---

## Gold Standard Checklist

### Foundation (Must Have)
- [x] `.cursorrules` with safety rules
- [x] `AGENTS.md` referencing universal constitution
- [x] `CLAUDE.md` with project context
- [x] `00_Index_*.md` maintained
- [ ] No hardcoded absolute paths
- [ ] No silent exception swallowing

### Documentation (Should Have)
- [x] `Documents/` structure created
- [x] `Documents/README.md` index
- [ ] `Documents/reference/LOCAL_MODEL_LEARNINGS.md`
- [ ] `Documents/guides/` with how-tos
- [x] Comprehensive README.md
- [x] TODO.md with status tracking

### Safety (Must Have for Production)
- [x] Read-only source data pattern
- [ ] Atomic writes for database
- [x] Trash, Don't Delete in rules
- [ ] Memory guards for large scans

### Automation (Nice to Have)
- [ ] Pre-review scan script
- [ ] CI integration
- [x] Prompt pattern for AI tasks

---

## Summary

**project-tracker is ~60% aligned with Gold Standard.**

**Strong Areas:**
- Core governance files exist
- Documentation structure started
- Prompt pattern implemented
- Index file maintained

**Gaps:**
- Code quality audit not done (Rules #1-4)
- Hardcoded paths exist
- Missing LOCAL_MODEL_LEARNINGS.md
- Documents/ structure incomplete

**Recommendation:** Create LOCAL_MODEL_LEARNINGS.md before starting prompts, then proceed with Phase 4 work while capturing learnings as we go.

---

*This guide will be updated as we progress through the canary test.*
