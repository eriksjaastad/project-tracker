# Prompt 2a: Copy CODE_QUALITY_STANDARDS.md

**Estimated Time:** 5 minutes
**Model:** Any
**Source:** `$SCAFFOLDING/Documents/CODE_QUALITY_STANDARDS.md`
**Destination:** `Documents/CODE_QUALITY_STANDARDS.md`

---

## Objective

Copy the universal CODE_QUALITY_STANDARDS.md from project-scaffolding to this project's Documents/ folder.

---

## CONSTRAINTS (READ FIRST)

- DO NOT modify the source file
- DO NOT create the file from scratch — COPY it
- DO NOT put it in a subdirectory — it goes at Documents/ root
- VERIFY the destination doesn't already exist before copying

---

## Task

1. **Check** if `Documents/CODE_QUALITY_STANDARDS.md` already exists
   - If yes, compare with source and only update if different
   - If no, proceed with copy

2. **Copy** from scaffolding:
   ```bash
   cp "$SCAFFOLDING/Documents/CODE_QUALITY_STANDARDS.md" ./Documents/
   ```

   Or if $SCAFFOLDING is not set:
   ```bash
   cp ~/projects/project-scaffolding/Documents/CODE_QUALITY_STANDARDS.md ./Documents/
   ```

3. **Verify** the file exists at `Documents/CODE_QUALITY_STANDARDS.md`

---

## Acceptance Criteria

- [ ] **Exists:** File is at `Documents/CODE_QUALITY_STANDARDS.md`
- [ ] **Complete:** File has all 7 rules (check for "Rule #7")
- [ ] **Location:** NOT in Documents/core/ or any subdirectory
- [ ] **Identical:** Matches source file from scaffolding

---

## Verification

```bash
ls -la Documents/CODE_QUALITY_STANDARDS.md
# Should exist

grep "Rule #7" Documents/CODE_QUALITY_STANDARDS.md
# Should show the type hints rule
```

---

**Hand back to Floor Manager when complete.**
