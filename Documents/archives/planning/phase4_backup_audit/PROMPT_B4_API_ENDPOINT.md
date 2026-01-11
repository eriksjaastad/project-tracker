# Prompt B4: API Endpoint

**Task:** Add `/api/backup` endpoint to the dashboard
**Estimated Time:** 5-10 minutes
**Worker Model:** qwen3:4b (preferred) or deepseek-r1:14b
**Depends On:** B3 (backup_reader must return valid data)

---

## CONSTRAINTS (READ FIRST)

- DO NOT modify existing endpoints - only add new one
- DO NOT add authentication - keep it simple like /api/telemetry
- DO NOT refactor the app - minimal changes only
- FOLLOW the exact pattern used by /api/telemetry endpoint
- OUTPUT using StrReplace to add the new endpoint

---

## Task Description

Add to `dashboard/app.py`:
1. Import the backup_reader module
2. Add `/api/backup` GET endpoint
3. Return backup status as JSON

---

## [ACCEPTANCE CRITERIA] (MANDATORY CHECKLIST)

- [x] **Import Added:** `from scripts.discovery.backup_reader import get_backup_status`
- [x] **Endpoint Exists:** `/api/backup` returns JSON response
- [x] **Returns Status:** Response includes status, remotes, message fields
- [x] **No Breaking Changes:** Existing endpoints still work
- [x] **Matches Pattern:** Follows same structure as /api/telemetry

---

## Context Bridge: Existing Pattern

Find the `/api/telemetry` endpoint in `dashboard/app.py` and follow its pattern:

```python
# Existing pattern (example):
@app.get("/api/telemetry")
async def get_telemetry():
    from scripts.discovery.telemetry_reader import get_telemetry_stats
    stats = get_telemetry_stats(days=30)
    return stats

# Add this new endpoint following the same pattern:
@app.get("/api/backup")
async def get_backup():
    from scripts.discovery.backup_reader import get_backup_status
    status = get_backup_status()
    return status
```

---

## Floor Manager Instructions

1. Read `dashboard/app.py` to find where `/api/telemetry` is defined
2. Find the import section at the top of the file
3. Add the new endpoint after the telemetry endpoint (or in the same section)
4. The import can be inline (inside the function) to match existing pattern

---

## Verification Command

After implementing, run:

```bash
cd /Users/eriksjaastad/projects/project-tracker

# Start dashboard in background
./pt launch --no-scan &
sleep 3

# Test the endpoint
curl -s http://localhost:8000/api/backup | python -c "
import sys, json
data = json.load(sys.stdin)
print('API Response:')
print(f'  Status: {data.get(\"status\", \"missing\")}')
print(f'  Remotes: {data.get(\"remotes\", [])}')
print(f'  Message: {data.get(\"message\", \"missing\")}')

assert 'status' in data, 'ERROR: Missing status field'
assert 'remotes' in data, 'ERROR: Missing remotes field'
print('OK - API endpoint working')
"

# Cleanup
pkill -f "uvicorn" || true
```

**Expected:** Returns JSON with backup status data

---

## Result

- [x] PASS: API endpoint returns valid JSON.
- [ ] FAIL: Describe error

**Hand back to Floor Manager when complete.**
