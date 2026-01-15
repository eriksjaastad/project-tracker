# Prompt 3a: Verify AGENTS.md Alignment

**Estimated Time:** 10 minutes
**Model:** Any
**File to Review:** `AGENTS.md`

---

## Objective

Verify that AGENTS.md has all required sections from the project-scaffolding template and update if needed.

---

## CONSTRAINTS (READ FIRST)

- DO NOT delete existing project-specific content
- DO NOT change tech stack or commands that are correct
- PRESERVE any custom constraints
- ONLY add missing sections or fix structural issues
- REFERENCE the universal constitution in project-scaffolding

---

## Required Sections Checklist

Compare AGENTS.md against this checklist:

### Must Have:
- [ ] **Header** with project name and brief description
- [ ] **Reference** to universal constitution (`project-scaffolding/AGENTS.md`)
- [ ] **Tech Stack** section (language, frameworks, database)
- [ ] **Execution Commands** (run, test, build)
- [ ] **Project-Specific Constraints** section
- [ ] **Definition of Done** checklist

### Nice to Have:
- [ ] Link to CLAUDE.md for working instructions
- [ ] Link to .cursorrules
- [ ] Current phase/status indicator

---

## Task

1. **Read** current `AGENTS.md`

2. **Compare** against the checklist above

3. **Report** which sections are present/missing

4. **Add** any missing required sections (use existing content where possible)

5. **Verify** the file references the universal constitution:
   ```markdown
   > **Universal Constitution:** See `project-scaffolding/AGENTS.md` for hierarchy, workflow, and universal safety rules.
   ```

---

## Acceptance Criteria

- [ ] **Complete:** All "Must Have" sections present
- [ ] **Reference:** Points to universal constitution
- [ ] **Accurate:** Tech stack and commands are correct
- [ ] **Preserved:** Existing custom content retained

---

## Verification

```bash
# Check for key sections
grep -E "(Tech Stack|Execution|Constraints|Definition of Done)" AGENTS.md
# Should find all four
```

---

**Hand back to Floor Manager when complete.**


## Related Documentation

- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

