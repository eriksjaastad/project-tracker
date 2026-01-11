# Phase 4 Telemetry: Verification Prompts

**For Floor Manager Use**
**Date:** January 11, 2026
**Location:** `project-tracker/Documents/planning/phase4_verification/`

These prompts verify that Phase 4 implementation is complete before updating the main ecosystem TODO.md.

> **Why This Exists:** We don't check things off without proof they work.

---

## Verification Tasks

| Task | File | Est. | Verifies | Status |
|------|------|------|----------|--------|
| **V1** | `PROMPT_V1_TELEMETRY_READER.md` | 5 min | ai_router telemetry as scanned resource | [x] PASS |
| **V2** | `PROMPT_V2_BLINKING_LIGHTS.md` | 5 min | AI Router model breakdowns visible | [x] PASS |
| **V3** | `PROMPT_V3_COST_SAVINGS.md` | 5 min | Cost savings calculated and displayed | [x] PASS |
| **V4** | `PROMPT_V4_CRITICAL_ERRORS.md` | 5 min | [CRITICAL] error surfacing works | [x] PASS |
| **V5** | `PROMPT_V5_CRON_HEALTH.md` | 5 min | Cron health sentinel shows heartbeat | [x] PASS |

**Total Time:** ~25 minutes

---

## Floor Manager Instructions

1. **Run in order:** V1 → V2 → V3 → V4 → V5

2. **For each prompt:**
   - Run the verification commands
   - Check PASS/FAIL for each criterion
   - Mark status in this index when complete

3. **If ANY verification fails:**
   - Stop and report to Super Manager
   - Do NOT mark as complete in main TODO

4. **If ALL verifications pass:**
   - Mark all tasks [x] Done in this index
   - Report to Super Manager for main TODO update

---

## Summary Checklist

After all prompts complete, fill in this summary:

| Main TODO Item | Verification | Result |
|----------------|--------------|--------|
| Add `ai_router` telemetry directory as scanned resource | V1 | [x] PASS / [ ] FAIL |
| AI Router "Blinking Lights" | V2 | [x] PASS / [ ] FAIL |
| Cost Savings: Calculate and display | V3 | [x] PASS / [ ] FAIL |
| Critical Error Surfacing | V4 | [x] PASS / [ ] FAIL |
| Cron Health Sentinel | V5 | [x] PASS / [ ] FAIL |

---

## Sign-Off

- [x] **All 5 verifications passed**
- [x] **Dashboard loads without errors:** `./pt launch --no-scan`
- [x] **Super Manager notified:** Ready to update main TODO.md

---

**Hand this completed index back to Super Manager when all verifications pass.**
