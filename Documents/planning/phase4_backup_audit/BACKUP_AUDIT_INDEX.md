# Phase 4: Backup Audit (rclone) - Prompts Index

**Feature:** Audit and surface "un-backed-up" data on the dashboard
**Created:** January 11, 2026
**Executor:** Floor Manager (via Ollama MCP)
**Worker Models:** qwen3:4b (primary), deepseek-r1:14b (reasoning)

---

## Context

From TODO.md:
> **Backup Audit (rclone):** Refine the dashboard to audit and surface "un-backed-up" data.

The project-tracker dashboard already has:
- Telemetry reader (`scripts/discovery/telemetry_reader.py`) - pattern to follow
- Cron health monitoring (`scripts/discovery/cron_health.py`)
- API endpoints via FastAPI (`dashboard/app.py`)

The ecosystem has:
- rclone configured with `gbackup` (Google Drive) and `r2_pose_factory` (Cloudflare R2) remotes
- No automated backup cron jobs yet (opportunity to surface this gap)

---

## Done Criteria (Overall Feature)

All must pass for feature complete:

- [ ] **B1: Discovery Module** - `scripts/discovery/backup_reader.py` exists and runs
- [ ] **B2: Backup Config Detection** - Reads rclone remotes and reports status
- [ ] **B3: Un-Backed-Up Detection** - Identifies critical data not in backup scope
- [ ] **B4: API Endpoint** - `/api/backup` returns backup audit data
- [ ] **B5: Dashboard Card** - Backup status visible on dashboard
- [ ] **B6: Verification** - All verification tests pass

---

## Prompt Execution Order

Execute prompts in sequence. Each builds on the previous.

| # | Prompt File | Description | Est. Time |
|---|-------------|-------------|-----------|
| 1 | `PROMPT_B1_BACKUP_READER_SKELETON.md` | Create backup_reader.py with basic structure | 5-10 min |
| 2 | `PROMPT_B2_RCLONE_CONFIG_PARSER.md` | Parse rclone config and detect remotes | 5-10 min |
| 3 | `PROMPT_B3_UNBACKED_DETECTION.md` | Detect critical paths not covered by backups | 5-10 min |
| 4 | `PROMPT_B4_API_ENDPOINT.md` | Add /api/backup endpoint to dashboard | 5-10 min |
| 5 | `PROMPT_B5_DASHBOARD_CARD.md` | Add backup status card to dashboard UI | 5-10 min |
| 6 | `PROMPT_B6_VERIFICATION.md` | Verification tests for all components | 5 min |

---

## Key Constraints (Apply to ALL Prompts)

These constraints must be included in every prompt:

```markdown
## CONSTRAINTS (READ FIRST)
- DO NOT hardcode paths - use `Path.home()` or environment variables
- DO NOT silent fail - always log errors with context
- DO NOT add features beyond the acceptance criteria
- COPY the code patterns from telemetry_reader.py verbatim
- TIMEOUT: Keep tasks atomic (5-10 min max)
```

---

## Reference Files

Floor Manager should provide these as context:

1. **Pattern to follow:** `scripts/discovery/telemetry_reader.py` (lines 1-50)
2. **Config location:** `~/.config/rclone/rclone.conf`
3. **Dashboard app:** `dashboard/app.py` (for API endpoint pattern)

---

## Escalation Protocol

If a Worker times out or fails:

1. **Strike 1:** Retry with same model
2. **Strike 2:** Switch model (qwen3:4b → deepseek-r1:14b)
3. **Strike 3:** HALT and report to Conductor

DO NOT manually implement failed Worker tasks.

---

## Progress Tracking

| Prompt | Status | Worker Model | Notes |
|--------|--------|--------------|-------|
| B1 | [ ] Pending | - | - |
| B2 | [ ] Pending | - | - |
| B3 | [ ] Pending | - | - |
| B4 | [ ] Pending | - | - |
| B5 | [ ] Pending | - | - |
| B6 | [ ] Pending | - | - |

**Overall Status:** [ ] Not Started / [ ] In Progress / [ ] Complete

---

**Hand to Floor Manager to begin execution.**
