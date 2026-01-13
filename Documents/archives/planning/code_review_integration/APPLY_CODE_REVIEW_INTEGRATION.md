# Apply Code Review Integration to project-tracker

**Task:** Update project-tracker files with code review and validation references from project-scaffolding
**Estimated Time:** 15-20 minutes total (5 changes)
**Worker Model:** qwen2.5-coder:7b (preferred) or deepseek-r1:14b

---

## Context

project-scaffolding just integrated code review infrastructure documentation into its templates. Now we need to apply those same changes to project-tracker's actual files so this project knows about and references the review system.

**What's being added:**
- References to validation scripts in project-scaffolding
- Code review workflow documentation
- Validation commands in Definition of Done

---

## Files to Update

Execute these changes in order:

### Change 1: Update AGENTS.md - Add Code Review to DoD

**File:** `AGENTS.md`

**old_string:**
```markdown
## 📋 Definition of Done (DoD)
- [ ] Code is documented with type hints.
- [ ] Technical changes are logged to `_obsidian/WARDEN_LOG.yaml`.
- [ ] `00_Index_*.md` is updated with recent activity.
```

**new_string:**
```markdown
## 📋 Definition of Done (DoD)
- [ ] Code is documented with type hints.
- [ ] Technical changes are logged to `_obsidian/WARDEN_LOG.yaml`.
- [ ] `00_Index_*.md` is updated with recent activity.
- [ ] Code validated (no hardcoded paths, no secrets exposed).
- [ ] Code review completed (if significant architectural changes).
```

**Then add after the ⚠️ Critical Constraints section:**

Find:
```markdown
## 📖 Reference Links
```

Add before it:
```markdown

**Code Review Standards:** See `$SCAFFOLDING/REVIEWS_AND_GOVERNANCE_PROTOCOL.md` for full review process.

## 📖 Reference Links
```

---

### Change 2: Update CLAUDE.md - Add Code Review Section

**File:** `CLAUDE.md`

Find the "## Validation Commands" section and add this new section AFTER it:

**Insert after "## Validation Commands":**
```markdown

---

## Code Review and Validation

### When to Request a Code Review

Request architectural review, security audit, or performance analysis when:
- Making significant architectural decisions
- Implementing security-critical code paths
- Before merging major features
- When unsure about design approach

### How to Request a Review

**Step 1: Create review request**
```bash
# Use the template
cp "$SCAFFOLDING/templates/CODE_REVIEW.md.template" ./CODE_REVIEW_REQUEST.md

# Edit CODE_REVIEW_REQUEST.md:
# - Fill out "Definition of Done" section
# - Describe what you want reviewed
# - Specify review focus (architecture/security/performance)
```

**Step 2: Run multi-AI review**
```bash
cd "$SCAFFOLDING"
source venv/bin/activate
python scaffold_cli.py review --type document --input /path/to/your/CODE_REVIEW_REQUEST.md --round 1
```

**Step 3: Review results**
- Reviews saved to: `$SCAFFOLDING/review_outputs/round_1/CODE_REVIEW_*.md`
- Copy relevant reviews to: `Documents/archives/reviews/`

### How to Validate Your Work

Run validation to check for common issues:

```bash
# Quick safety check (< 1 second)
python "$SCAFFOLDING/scripts/warden_audit.py" --root . --fast

# Full project validation
python "$SCAFFOLDING/scripts/validate_project.py" project-tracker
```

**What validation catches:**
- ✅ Hardcoded absolute paths (`[USER_HOME]/...`, `/home/...`)
- ✅ Exposed secrets (API keys like `sk-...`, `AIza...`)
- ✅ Missing required files (00_Index_*.md, AGENTS.md, etc.)
- ✅ Invalid project structure

**Best practice:** Validate before major commits or before requesting code reviews.

### Learn More

- **Full Protocol:** `$SCAFFOLDING/REVIEWS_AND_GOVERNANCE_PROTOCOL.md`
- **Pattern Docs:** `$SCAFFOLDING/patterns/code-review-standard.md`
- **Review Prompts:** `$SCAFFOLDING/prompts/active/document_review/`
```

---

### Change 3: Update .cursorrules - Add Validation

**File:** `.cursorrules`

**Find the Definition of Done section and update it:**

**old_string:**
```markdown
## 📋 Definition of Done (Project-Specific)

- [x] Code follows project coding standards (see below)
- [x] Changes logged to `WARDEN_LOG.yaml`
- [x] Documentation updated (if user-facing changes)
- [x] Tests pass: `pytest tests/`
- [x] **Index updated** (if new patterns, templates, or major components added)
```

**new_string:**
```markdown
## 📋 Definition of Done (Project-Specific)

- [x] Code follows project coding standards (see below)
- [x] Code validated (no hardcoded paths, no secrets exposed)
- [x] Changes logged to `WARDEN_LOG.yaml`
- [x] Documentation updated (if user-facing changes)
- [x] Tests pass: `pytest tests/`
- [x] **Index updated** (if new patterns, templates, or major components added)
```

**Then update Execution Commands section:**

**old_string:**
```markdown
## 🚀 Execution Commands

```bash
# Environment
source venv/bin/activate

# Run tests
pytest tests/

# Run main app
python pt scan
```
```

**new_string:**
```markdown
## 🚀 Execution Commands

```bash
# Environment
source venv/bin/activate

# Validate project (before commits)
python "$SCAFFOLDING/scripts/validate_project.py" project-tracker

# Run tests
pytest tests/

# Run main app
python pt scan
```
```

**Finally, update Related Files section:**

**old_string:**
```markdown
## 🔗 Related Files

- **Ecosystem Constitution:** `AGENTS.md`
- **Review Protocol:** `REVIEWS_AND_GOVERNANCE_PROTOCOL.md`
- **Project Index:** `[[00_Index_project-tracker]]`
- **Scaffolding Transfer Guide:** `Documents/SCAFFOLDING_TRANSFER_GUIDE.md`
```

**new_string:**
```markdown
## 🔗 Related Files

- **Ecosystem Constitution:** `AGENTS.md`
- **Review Protocol:** `$SCAFFOLDING/REVIEWS_AND_GOVERNANCE_PROTOCOL.md`
- **Code Review Pattern:** `$SCAFFOLDING/patterns/code-review-standard.md`
- **Project Index:** `[[00_Index_project-tracker]]`
- **Scaffolding Transfer Guide:** `Documents/SCAFFOLDING_TRANSFER_GUIDE.md`
```

---

### Change 4: Update QUICKSTART.md (if it has phases)

**File:** `QUICKSTART.md`

Check if this file has a phase-based structure. If it does, add a validation phase similar to what we did in project-scaffolding. If it's just a simple quickstart, skip this change.

---

## [ACCEPTANCE CRITERIA]

- [ ] AGENTS.md has validation and code review in DoD
- [ ] AGENTS.md references REVIEWS_AND_GOVERNANCE_PROTOCOL.md
- [ ] CLAUDE.md has "Code Review and Validation" section
- [ ] .cursorrules has validation in DoD
- [ ] .cursorrules has validation command in Execution Commands
- [ ] .cursorrules references code-review-standard.md
- [ ] All uses $SCAFFOLDING variable for paths

---

## Verification

After all changes, verify:

```bash
cd $PROJECTS_ROOT/project-tracker

# 1. Check AGENTS.md
grep "Code validated" AGENTS.md
grep "REVIEWS_AND_GOVERNANCE_PROTOCOL" AGENTS.md

# 2. Check CLAUDE.md
grep -n "Code Review and Validation" CLAUDE.md
grep "validate_project.py" CLAUDE.md

# 3. Check .cursorrules
grep "Code validated" .cursorrules
grep "validate_project.py" .cursorrules
grep "code-review-standard.md" .cursorrules

# All should return matches
```

---

## Execution Instructions for Floor Manager

**Use Ollama MCP:**
- Model: qwen2.5-coder:7b
- Timeout: 300000 (5 minutes per change)

**Execute changes 1-3 in order. For each change:**
1. Send the specific change to worker
2. Verify it applied correctly
3. Move to next change

**If any change hits 3 strikes:** HALT and report which change failed.

---

## Result

- [ ] PASS: All changes applied, verification succeeds
- [ ] FAIL: Describe which change failed and why

**When complete:** project-tracker will have full code review infrastructure documentation and know how to use the validation/review system from project-scaffolding.
