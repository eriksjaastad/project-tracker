# Prompt 1b: Update 00_Index Status Tag

**Estimated Time:** 5 minutes
**Model:** Any
**File to Modify:** `00_Index_project-tracker.md`

---

## Objective

Update the YAML frontmatter tags in the project index to reflect active development status.

---

## CONSTRAINTS (READ FIRST)

- DO NOT change the 3-sentence summary
- DO NOT remove existing tags (p/, type/, domain/, tech/)
- ONLY modify the status tag
- PRESERVE YAML frontmatter structure

---

## Task

1. **Open** `00_Index_project-tracker.md`

2. **Find** the YAML frontmatter tags section

3. **Update** the status tag:
   - If `#status/complete` exists, change to `#status/active`
   - If no status tag exists, add `#status/active`

4. **Verify** YAML frontmatter is still valid

---

## Acceptance Criteria

- [ ] **Tag exists:** `#status/active` is in the tags
- [ ] **No duplicates:** Only one status tag present
- [ ] **Valid YAML:** Frontmatter parses correctly
- [ ] **Preserved:** All other tags unchanged

---

## Verification

```bash
head -20 00_Index_project-tracker.md | grep status
# Should show: #status/active
```

---

**Hand back to Floor Manager when complete.**
