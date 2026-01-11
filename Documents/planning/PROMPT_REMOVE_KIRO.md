# Prompt: Remove Kiro from Project Tracker

**Estimated Time:** 10 minutes
**Model:** Any
**Priority:** Cleanup task

---

## Objective

Remove all Kiro IDE integration files and references from project-tracker. Kiro integration was abandoned and these files are no longer needed.

---

## CONSTRAINTS (READ FIRST)

- DO NOT modify any files in `Documents/archives/`
- DO NOT modify any files in trash directories
- USE `send2trash` to remove the `.kiro` directory (move to system Trash)
- VERIFY files exist before attempting to remove

---

## Task

### Step 1: Remove .kiro Directory

The `.kiro` directory exists at the project root:

```
project-tracker/.kiro/
├── README.md
├── specs/
└── steering/
    └── structure.md
```

**Action:** Move entire `.kiro` directory to system Trash:

```bash
# Using Python send2trash
python -c "from send2trash import send2trash; send2trash('.kiro')"

# Or verify it's gone
ls -la .kiro 2>&1 | grep -q "No such file" && echo "✓ .kiro removed"
```

### Step 2: Search for Remaining References

Search for any file references to Kiro (excluding archives):

```bash
grep -r "[Kk]iro" . --include="*.md" --include="*.py" --include="*.yaml" | grep -v archive | grep -v trash
```

If any are found, evaluate whether they should be:
- Removed entirely (if the line is only about Kiro)
- Updated (if Kiro is mentioned alongside other tools)

### Step 3: Verify Cleanup

```bash
# Confirm .kiro is gone
ls -la .kiro 2>&1

# Confirm no remaining references (excluding archives)
grep -r "[Kk]iro" . --include="*.md" | grep -v archive | grep -v trash | wc -l
# Should be 0
```

---

## Acceptance Criteria

- [x] **Removed:** `.kiro` directory no longer exists in project root
- [x] **Clean:** No active file references to Kiro (archives exempt)
- [x] **Safe:** Used send2trash, files are recoverable if needed
- [x] **Verified:** grep search returns 0 results

---

## Context

Kiro was an AI IDE that we briefly experimented with. The `.kiro` directory contained:
- `steering/` - Project structure hints for Kiro AI
- `specs/` - Feature specifications in Kiro format
- `README.md` - Kiro onboarding docs

None of this is needed anymore. Our AI collaboration now uses:
- `AGENTS.md` - Source of truth
- `CLAUDE.md` - Working instructions
- `.cursorrules` - Cursor IDE rules
- `Documents/` - Structured documentation

---

**Hand back to Floor Manager when complete.**
