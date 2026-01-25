# Project Tracker Phase 4: Worker Task Prompts

**For Floor Manager Use**
**Date:** January 11, 2026
**Location:** `project-tracker/Documents/planning/phase4_telemetry/`

Hand off these prompts to Workers **in order** (each builds on the previous).

> **Quick Start:** Give Floor Manager this file. All prompts are in this same directory.

---

## Today's Focus: Telemetry & AI Router Integration

The 10 Phase 4 tasks are grouped into logical work streams. Today we focus on **Telemetry Integration** (Tasks 3-5 from TODO).

---

## Task Order

### Group 1: Telemetry Reader Foundation (Micro-Tasks)

| Task | File | Est. | Objective | Status |
|------|------|------|-----------|--------|
| **1a** | `PROMPT_1a_TELEMETRY_READER.md` | 5 min | Create telemetry reader module skeleton | ✅ Done |
| **1b** | `PROMPT_1b_PARSE_JSONL.md` | 5 min | Add JSONL parsing function | ✅ Done |
| **1c** | `PROMPT_1c_AGGREGATE_STATS.md` | 5 min | Add aggregation functions (counts, durations) | ✅ Done |
| **1d** | `PROMPT_1d_COST_CALCULATION.md` | 5 min | Add cost savings calculation | ✅ Done |

**Group 1 Total:** 20 minutes

---

### Group 2: Dashboard Integration (Micro-Tasks)

| Task | File | Est. | Objective | Status |
|------|------|------|-----------|--------|
| **2a** | `PROMPT_2a_DASHBOARD_ROUTE.md` | 5 min | Add /api/telemetry route to app.py | ✅ Done |
| **2b** | `PROMPT_2b_BLINKING_LIGHTS_HTML.md` | 10 min | Add telemetry card to dashboard template | ✅ Done |
| **2c** | `PROMPT_2c_COST_DISPLAY.md` | 5 min | Add cost savings display to UI | ✅ Done |

**Group 2 Total:** 20 minutes

---

### Group 3: Health Monitoring (If Time Permits)

| Task | File | Est. | Objective | Status |
|------|------|------|-----------|--------|
| **3a** | `PROMPT_3a_CRITICAL_ERRORS.md` | 10 min | Add [CRITICAL] error surfacing | ✅ Done |
| **3b** | `PROMPT_3b_CRON_HEARTBEAT.md` | 15 min | Add cron health sentinel | ✅ Done |

**Group 3 Total:** 25 minutes

---

### Deferred to Tomorrow or Later

These are larger architectural tasks:

- **Agent Dispatcher UI** — Needs design discussion first
- **Backup Audit (rclone)** — Needs to understand rclone log format
- **Flow (100% completion)** — UI/UX change, medium complexity
- **Eco-System Org Chart** — Visualization project, needs design

---

## Total Estimated Time

- Group 1 (Telemetry Reader): 20 min
- Group 2 (Dashboard): 20 min
- Group 3 (Health): 25 min (stretch goal)
- **Realistic Today: ~40-65 minutes**

---

## Floor Manager Instructions

1. **Verify AI Router telemetry exists first:**
   ```bash
   head -3 $PROJECTS_ROOT/_tools/ai_router/logs/telemetry.jsonl
   ```

2. **Use micro-tasks sequentially:** 1a → 1b → 1c → 1d → 2a → 2b → 2c

3. **Model selection:** Prefer Qwen 2.5 Coder for code generation

4. **Verify between tasks:** Run the dashboard after Groups 1 and 2

5. **Halt on 3 failures:** If Worker fails same task 3x, alert Conductor

---

## Context Files Workers May Need

- `dashboard/app.py` — Main FastAPI application
- `scripts/discovery/` — Where discovery modules live
- `dashboard/templates/index.html` — Dashboard template
- `$PROJECTS_ROOT/_tools/ai_router/logs/telemetry.jsonl` — Data source

---

## Telemetry JSONL Format (Reference)

```json
{
  "provider": "local",
  "model": "llama3.2:3b",
  "tier": "local",
  "duration_ms": 11246,
  "timed_out": false,
  "error": null,
  "timestamp": "2026-01-05T09:23:14.918438Z",
  "prompt_len": 19046
}
```

Key fields for "Blinking Lights":
- `provider`: "local" vs "openai" (for cloud)
- `model`: Which model was used
- `tier`: "local", "cheap", "smart"
- `duration_ms`: Response time
- `timed_out`: Did it fail?
- `error`: Error message if failed

---

## Final Verification (After Groups 1-2)

```bash
# 1. Test telemetry reader works
cd $PROJECTS_ROOT/project-tracker
python -c "from scripts.discovery.telemetry_reader import get_telemetry_stats; print(get_telemetry_stats())"
# Expected: Dict with model counts, durations, etc.

# 2. Test dashboard launches
./pt launch --no-scan
# Expected: Dashboard shows telemetry card

# 3. Test API endpoint
curl http://localhost:8000/api/telemetry
# Expected: JSON response with stats
```

---

## Success Criteria for Today

- [x] Telemetry reader module exists at `scripts/discovery/telemetry_reader.py`
- [x] Dashboard shows AI Router stats (model usage, local vs cloud)
- [x] Cost savings estimate displayed
- [x] No errors when loading dashboard

---

**Ready to hand off to Workers**


## Related Documentation

- [Local Model Learnings](Documents/reference/LOCAL_MODEL_LEARNINGS.md) - local AI

