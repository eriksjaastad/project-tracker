# Verification V1: Telemetry Reader

**Verifies:** Add `ai_router` telemetry directory as scanned resource
**Estimated Time:** 5 minutes
**Model:** Any

---

## Done Criteria

All must pass:

- [x] **File exists:** `scripts/discovery/telemetry_reader.py`
- [x] **Reads from AI Router:** Path points to telemetry.jsonl
- [x] **Returns data:** `get_telemetry_stats()` returns dict with actual data
- [x] **Has entries:** `total_requests` > 0

---

## Verification Steps

### Step 1: File Exists

```bash
cd $PROJECTS_ROOT/project-tracker
ls -la scripts/discovery/telemetry_reader.py
```

**Expected:** File exists with reasonable size (>1KB)

- [x] PASS / [ ] FAIL

---

### Step 2: Function Returns Data

```bash
python -c "
from scripts.discovery.telemetry_reader import get_telemetry_stats
stats = get_telemetry_stats(days=30)
print(f'Total requests: {stats[\"total_requests\"]}')
print(f'Local requests: {stats[\"local_requests\"]}')
print(f'Models used: {list(stats[\"models\"].keys())}')
"
```

**Expected:** Numbers > 0, list of model names

- [x] PASS / [ ] FAIL

---

### Step 3: Data is Real (Not Zeros)

```bash
python -c "
from scripts.discovery.telemetry_reader import get_telemetry_stats
stats = get_telemetry_stats(days=30)
assert stats['total_requests'] > 0, 'ERROR: No telemetry data'
assert len(stats['models']) > 0, 'ERROR: No models recorded'
print('✓ Telemetry reader has real data')
"
```

**Expected:** No assertion errors, success message

- [x] PASS / [ ] FAIL

---

## Result

| Criterion | Status |
|-----------|--------|
| File exists | [x] PASS / [ ] FAIL |
| Function returns data | [x] PASS / [ ] FAIL |
| Data is real (not zeros) | [x] PASS / [ ] FAIL |

**Overall V1:** [x] PASS / [ ] FAIL

---

**Hand back to Floor Manager when complete.**
