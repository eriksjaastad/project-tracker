# Prompt 3b: Verify .cursorrules Alignment

**Estimated Time:** 10 minutes
**Model:** Any
**File to Review:** `.cursorrules`

---

## Objective

Verify that .cursorrules has all required sections and safety rules from the project-scaffolding standard.

---

## CONSTRAINTS (READ FIRST)

- DO NOT remove existing project-specific constraints
- DO NOT change commands that are working correctly
- PRESERVE custom rules that make sense for this project
- ONLY add missing safety rules or structural sections

---

## Required Sections Checklist

Compare .cursorrules against this checklist:

### Must Have:
- [ ] **Project Context** section (name, description, domain)
- [ ] **Tech Stack** section (language, framework, key dependencies)
- [ ] **Safety Rules** section with:
  - [ ] "Trash, Don't Delete" rule (uses `send2trash`)
  - [ ] "No Silent Failures" rule (always log exceptions)
- [ ] **Execution Commands** (run, test)
- [ ] **Project-Specific Constraints**

### Nice to Have:
- [ ] AI tier guidance (what to use local vs cloud for)
- [ ] File operation warnings (which files are dangerous)
- [ ] Link to AGENTS.md as source of truth

---

## Task

1. **Read** current `.cursorrules`

2. **Compare** against the checklist above

3. **Verify** safety rules are present and correct:
   ```markdown
   ## Safety Rules

   ### File Operations
   - **Trash, Don't Delete:** NEVER use `rm`, `os.remove`, `os.unlink`, or `shutil.rmtree`
   - ALWAYS use `send2trash` (Python) to move files to the system Trash.

   ### Error Handling
   - **No Silent Failures:** NEVER swallow exceptions without logging.
   ```

4. **Report** which sections are present/missing

5. **Add** any missing required sections

---

## Acceptance Criteria

- [ ] **Safety Rules:** Both trash and silent failure rules present
- [ ] **Trash Rule:** Says `send2trash` (NOT `_trash/` directory)
- [ ] **Commands:** Run and test commands are accurate
- [ ] **Structure:** Has clear section headers

---

## Verification

```bash
# Check for safety rules
grep -A2 "Trash, Don't Delete" .cursorrules
# Should show send2trash rule

grep -A2 "No Silent Failures" .cursorrules
# Should show logging requirement
```

---

**Hand back to Floor Manager when complete.**
