/**
 * Shared acceptance-criteria checklist rule (#7608).
 *
 * Every new Kanban card must state how its own completion will be
 * verified, as a Markdown checklist line. This mirrors
 * ACCEPTANCE_CRITERION_RE in scripts/utils/validation.py exactly: at
 * least one "- [ ] <text>" or "- [x] <text>" line, with real text after
 * the checkbox. A heading alone (e.g. "## Acceptance Criteria") does not
 * count. Keep this regex in sync with the Python one if either changes.
 *
 * This is a client-side convenience so TaskForm can block submit and show
 * an inline error before round-tripping to the server. It is NOT the
 * enforcement boundary -- DatabaseManager.create_card() (backend_manager.py)
 * is, and the server rejects the same way regardless of what the client
 * checks.
 */
const ACCEPTANCE_CRITERION_RE = /^[ \t]*-[ \t]*\[[ xX]\][ \t]+\S/m;

/** True when `notes` contains at least one concrete acceptance-criterion line. */
export function hasAcceptanceCriteria(notes: string | null | undefined): boolean {
  if (!notes || !notes.trim()) {
    return false;
  }
  return ACCEPTANCE_CRITERION_RE.test(notes);
}

/** Prefilled starting point for a new card's acceptance-criteria field. */
export const ACCEPTANCE_CRITERIA_TEMPLATE = '- [ ] ';

/** Client-side copy of the same rule the server enforces; shown inline. */
export const ACCEPTANCE_CRITERIA_HINT =
  "Acceptance criteria required: add at least one '- [ ] <how completion is verified>' " +
  "checklist line. A heading alone (e.g. '## Acceptance Criteria') does not count.";
