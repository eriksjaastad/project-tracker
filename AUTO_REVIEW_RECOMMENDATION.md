# Auto-Review Function: Recommendation

## RECOMMENDATION: REMOVE

Remove `scripts/utils/hooks.py` entirely. It is dead code with no path to useful resurrection.

---

## Current State

- **File:** `/Users/eriksjaastad/projects/project-tracker/scripts/utils/hooks.py`
- **Contents:** A single deprecated flag (`AUTO_REVIEW_ENABLED = False`) and a docstring explaining why it was disabled
- **Disabled since:** 2026-02-15
- **Imports/references anywhere in codebase:** None
- **Tests:** None
- **Active functionality:** None

---

## Pros of Keeping

- Preserves a placeholder if status-change hooks are needed later
- Low carrying cost (11 lines, no runtime impact)

## Cons of Keeping

- Dead code creates false signals during codebase searches
- Suggests a hooks system exists when it does not
- The "stub for future use" rationale has not materialized in over a month
- No tests, no imports, no consumers -- it is pure noise
- Anyone reading the codebase must spend time understanding why it exists and whether it matters

---

## Rationale

The original auto-review feature used local models (Ollama) to review code on status changes. Per the file's own docstring, this was removed because local models "rubber-stamped PASS without reading code." Code reviews are now handled by Claude through the Agent Hub workflow (`/judge` skill, Architect sign-off).

The file was kept as a stub "in case we need status-change hooks for other purposes." That need has not emerged. If status-change hooks are needed in the future, they should be designed from scratch based on actual requirements rather than grown from an unrelated stub. The git history preserves the original implementation if anyone needs to reference it.

Nothing in the codebase imports `hooks.py` or reads `AUTO_REVIEW_ENABLED`. Removing it has zero functional impact.

---

## Next Steps

1. **Delete the file:** `trash scripts/utils/hooks.py`
2. **Mark task #4954 as done** after removal
3. **No replacement needed:** The review workflow is already handled by the Agent Hub pipeline (Architect as Judge, Claude-based code review)
4. **If status-change hooks are needed later:** Design them as a new feature with clear requirements, not by resurrecting this stub
