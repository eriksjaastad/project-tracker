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

- [x] **B1: Discovery Module** - `scripts/discovery/backup_reader.py` exists and runs
- [x] **B2: Backup Config Detection** - Reads rclone remotes and reports status
- [x] **B3: Un-Backed-Up Detection** - Identifies critical data not in backup scope
- [x] **B4: API Endpoint** - `/api/backup` returns backup audit data
- [x] **B5: Dashboard Card** - Backup status visible on dashboard
- [x] **B6: Verification** - All verification tests pass

---

## Prompt Execution Order

Execute prompts in sequence. Each builds on the previous.

| # | Prompt File | Description | Est. Time |
|---|-------------|-------------|-----------|
| 1a | `PROMPT_B1a_IMPORTS_CONFIG.md` | Create backup_reader.py skeleton (imports + config) | 3-5 min |
| 1b | `PROMPT_B1b_STUB_FUNCTIONS.md` | Add stub functions | 3-5 min |
| 2 | `PROMPT_B2_RCLONE_CONFIG_PARSER.md` | Parse rclone config and detect remotes | 5-10 min |
| 3a | `PROMPT_B3a_CRITICAL_PATHS.md` | Add CRITICAL_PATHS + get_unbacked_paths() | 3-5 min |
| 3b | `PROMPT_B3b_BACKUP_STATUS.md` | Implement get_backup_status() | 3-5 min |
| 4 | `PROMPT_B4_API_ENDPOINT.md` | Add /api/backup endpoint to dashboard | 5-10 min |
| 5 | `PROMPT_B5_DASHBOARD_CARD.md` | Add backup status card to dashboard UI | 5-10 min |
| 6 | `PROMPT_B6_VERIFICATION.md` | Verification tests for all components | 5 min |

> **Note:** B1 and B3 were split preemptively based on Agent Dispatcher A1 timeout learning.
> Context Bridge sections now kept under 30 lines per prompt.

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
| B1a | [x] Complete | FM Direct | - |
| B1b | [x] Complete | deepseek-r1 | FM Cleaned |
| B2 | [x] Complete | deepseek-r1 | FM Cleaned |
| B3a | [x] Complete | FM Direct | - |
| B3b | [x] Complete | FM Direct | - |
| B4 | [x] Complete | FM Direct | - |
| B5 | [x] Complete | FM Direct | - |
| B6 | [x] Complete | FM Direct | - |

**Overall Status:** [ ] Not Started / [ ] In Progress / [x] Complete

---

**Hand to Floor Manager to begin execution.**


## Related Documentation

- [Doppler Secrets Management](Documents/reference/DOPPLER_SECRETS_MANAGEMENT.md) - secrets management
- [Local Model Learnings](Documents/reference/LOCAL_MODEL_LEARNINGS.md) - local AI

