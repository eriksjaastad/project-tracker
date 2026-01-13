# CLAUDE.md - AI Collaboration Instructions

## 🛑 IMPORTANT: READ AGENTS.md FIRST
`AGENTS.md` is the universal source of truth for this project. Always consult it for project-specific rules, tech stack, and execution commands.

## 📚 Required Reading
1. **[[AGENTS.md]]** - Source of Truth for AI Agents (Read this first!)
2. **[[README.md]]** - Project overview and quick start
3. **[[TODO.md]]** - Project status and completed tasks
4. **[[00_Index_project-tracker]]** - Project index and metadata

## 📋 Project Summary
**What this project does:**
Centralized dashboard and CLI tool for tracking the status, health, and resource usage of all projects in the workspace. It auto-discovers projects and enforces documentation standards.

**Current status:**
Complete (MVP + Phase 4 enhancements). 

**Key constraints:**
- 100% Local (no cloud dependencies).
- $0 Monthly Cost.
- Mandatory `00_Index_*.md` files.

## 🛠 Coding Standards
- **Language:** Python 3.11+
- **Type Hints:** Mandatory for all public functions.
- **Error Handling:** No silent failures. Always log exceptions with context.
- **SQL Safety:** Use parameterized queries for all SQLite operations.
- **Logging:** Use the `logger.py` module for all logging.

## 🚀 Key Commands
- **Install Hooks:** `ln -sf ../../scripts/git-pre-commit.sh .git/hooks/pre-commit`
- **Launch Dashboard:** `./pt launch`
- **Full Project Scan:** `./pt scan`
- **List Projects:** `./pt list`
- **Run Tests:** `pytest tests/`

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
cp "./Documents/templates/CODE_REVIEW.md.template" ./CODE_REVIEW_REQUEST.md

# Edit CODE_REVIEW_REQUEST.md:
# - Fill out "Definition of Done" section
# - Describe what you want reviewed
# - Specify review focus (architecture/security/performance)
```

**Step 2: Run multi-AI review**
```bash
# cd "."
source venv/bin/activate
# ...
```

**Step 3: Review results**
- Reviews saved to: `./review_outputs/round_1/CODE_REVIEW_*.md`
- Copy relevant reviews to: `Documents/archives/reviews/`

### How to Validate Your Work

Run validation to check for common issues:

```bash
# Quick safety check (< 1 second)
python "./scripts/warden_audit.py" --root . --fast

# Full project validation
python "./scripts/validate_project.py" project-tracker
```

**What validation catches:**
- ✅ Hardcoded absolute paths (`[USER_HOME]/...`, `/home/...`)
- ✅ Exposed secrets (API keys like `sk-...`, `AIza...`)
- ✅ Missing required files (00_Index_*.md, AGENTS.md, etc.)
- ✅ Invalid project structure

**Best practice:** Validate before major commits or before requesting code reviews.

### Learn More

- **Full Protocol:** `./Documents/REVIEWS_AND_GOVERNANCE_PROTOCOL.md`
- **Pattern Docs:** `./Documents/patterns/code-review-standard.md`
- **Review Prompts:** `./prompts/active/document_review/`

---
*This file follows the [[project-scaffolding]] collaboration pattern.*
