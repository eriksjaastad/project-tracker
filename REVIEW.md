# Code Review Process for Project Tracker

This document outlines the code review process for the Project Tracker application. It aims to ensure code quality, maintainability, and adherence to project standards.

## 1. Purpose

The primary goals of code review are to:

*   Identify potential bugs and security vulnerabilities.
*   Ensure code conforms to coding standards and best practices.
*   Improve code readability and maintainability.
*   Share knowledge and promote collaboration among team members.
*   Verify that the code fulfills the requirements.

## 2. When to Request a Code Review

A code review should be requested when:

*   A new feature is implemented.
*   A bug is fixed.
*   Significant changes are made to existing code.
*   A refactoring effort is completed.
*   Any code that will be merged into the main branch.

## 3. How to Request a Code Review

1.  **Create a Pull Request (PR):**  Submit your changes as a pull request to the appropriate branch (usually `main` or `develop`).
2.  **Assign Reviewers:**  Assign one or more appropriate reviewers to the PR. Consider the expertise of the reviewers and the area of the codebase affected by the changes.  For critical components, consult with the Senior Principal Engineer or designated code owner.
3.  **Provide Context:** In the PR description, clearly explain the purpose of the changes, the approach taken, and any potential areas of concern.  Include links to relevant issues or documentation.
4.  **Self-Review:** Before requesting a review, perform a self-review of your code to catch any obvious errors or inconsistencies.

## 4. The Review Process

1.  **Reviewer Assignment:**  The assigned reviewer(s) will receive a notification.
2.  **Code Examination:**  Reviewers will carefully examine the code, paying attention to:
    *   Correctness and functionality
    *   Code style and readability
    *   Error handling and security
    *   Performance and efficiency
    *   Test coverage
    *   Adherence to project standards
3.  **Providing Feedback:** Reviewers will provide feedback directly on the PR, using comments to highlight areas for improvement. Be specific and constructive in your feedback.
4.  **Addressing Feedback:** The author of the PR will address the feedback by:
    *   Making the requested changes.
    *   Responding to comments with explanations or justifications.
    *   Asking clarifying questions if needed.
5.  **Iteration:** The review process may involve multiple iterations until the reviewer(s) are satisfied with the changes.
6.  **Approval:** Once the reviewer(s) are satisfied, they will approve the PR.
7.  **Merging:** After all required approvals are obtained, the PR can be merged into the target branch.

## 5. Review Guidelines

*   **Be Timely:**  Review code promptly to avoid blocking other developers.
*   **Be Constructive:**  Focus on providing helpful and actionable feedback.
*   **Be Specific:**  Clearly identify the areas that need improvement and explain why.
*   **Be Respectful:**  Maintain a professional and respectful tone in all communications.
*   **Automated Checks:** Ensure all automated checks (linting, testing, static analysis) pass before requesting a review.
*   **Small PRs:** Keep pull requests reasonably sized to facilitate easier review.  Large PRs should be broken down into smaller, more manageable chunks.

## 6. Example Review Document (Phase 3 Audit Agent Integration)

```markdown
# Code Review: Phase 3 Audit Agent Integration

**Review Date:** 2026-01-02 22:47:44 UTC
**Reviewer:** Senior Principal Engineer
**Scope:** Full Phase 3 implementation (Prerequisites, Core Integration, UI/UX)

---

## 1. The Engineering Verdict

**[Production Ready]**

All three phases complete. Provider pattern works, health scores display, parallel execution implemented, UI polish applied. One missing script tag fixed in final pass.

---

## 2. Phase 3 Summary

### Prerequisites ✅
- Provider pattern (`AuditProvider` / `LegacyProvider`) implemented
- Binary detection with graceful fallback
- Database schema extended with health columns
- Input validation on health scores (0-100, A-F)

### Core Integration ✅
- `audit health` integration with ThreadPoolExecutor (8 workers)
- `audit check` integration for frontmatter validation
- `audit tasks` NDJSON parsing implemented (full pipeline deferred)
- Parallel alert detection
- Binary output validation before DB write

### UI/UX ✅
- Warning banner when audit-agent missing
- Fix Frontmatter button on project detail view
- Activity feed from WARDEN_LOG.yaml
- Health badge display on project cards

---

## 3. Issues Resolved

| Issue | Resolution |
|-------|------------|
| Double `PathLib` import | Removed, using `Path` consistently |
| Unvalidated binary output | Added score/grade validation in `get_health()` |
| Sequential frontmatter checks | Parallelized with ThreadPoolExecutor |
| Import pattern inconsistency | Fixed to relative imports |
| Missing script.js in detail page | Added `<script>` tag |

---

## 4. Definition of Done - Final Checklist

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Provider pattern with fallback | ✅ |
| 2 | Binary detection and logging | ✅ |
| 3 | Health scores in database | ✅ |
| 4 | Parallel health scanning | ✅ |
| 5 | Health badge on dashboard | ✅ |
| 6 | Parallel frontmatter validation | ✅ |
| 7 | Warning banner for missing binary | ✅ |
| 8 | Fix Frontmatter button | ✅ |
| 9 | Activity feed display | ✅ |

---

## 5. Remaining Work (Future Phases)

- **Fast Tasks Pipeline:** `get_tasks()` implemented but not wired into scan (documented deferral)
- **Progress Bar:** Could show incremental progress during parallel scans (nice-to-have)
- **Provider Caching:** `get_provider()` called multiple times per request (optimization)

---

**Phase 3: Audit Agent Integration is COMPLETE.**

*Ship it.*

## Related Documentation

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[dashboard_architecture]] - dashboard/UI
- [[database_schema]] - database design
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[performance_optimization]] - performance
- [[audit-agent/README]] - Audit Agent
