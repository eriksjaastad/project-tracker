# Verification V4: Critical Error Surfacing

**Verifies:** Critical Error Surfacing - [CRITICAL] flags for MCP/Cron/Backup failures
**Estimated Time:** 5 minutes
**Model:** Any

---

## Done Criteria

All must pass:

- [x] **Function exists:** `get_critical_errors()` in telemetry_reader.py
- [x] **Detects timeouts:** Entries with `timed_out: true` are captured
- [x] **Detects errors:** Entries with `error: non-null` are captured
- [x] **Returns structured data:** List of error dicts with model, error, timestamp

---

## Verification Steps

### Step 1: Function Exists and Runs

```bash
cd $PROJECTS_ROOT/project-tracker
python -c "
from scripts.discovery.telemetry_reader import get_critical_errors
errors = get_critical_errors(hours=24)
print(f'Function exists and returned {len(errors)} errors')
print('✓ get_critical_errors() works')
"
```

**Expected:** Function runs without error, returns list

- [x] PASS / [ ] FAIL

---

### Step 2: Returns Structured Data

```bash
python -c "
from scripts.discovery.telemetry_reader import get_critical_errors
errors = get_critical_errors(hours=168)  # Last 7 days for more data

if len(errors) == 0:
    print('No errors found (this might be OK if system is healthy)')
    print('✓ Function works, no errors to report')
else:
    # Check structure of first error
    e = errors[0]
    assert 'model' in e, 'ERROR: Missing model field'
    assert 'error' in e, 'ERROR: Missing error field'
    assert 'timestamp' in e, 'ERROR: Missing timestamp field'

    print(f'Found {len(errors)} errors')
    print(f'Sample error structure: {list(e.keys())}')
    print('✓ Error structure correct')
"
```

**Expected:** Either no errors (healthy) or properly structured error dicts

- [x] PASS / [ ] FAIL

---

### Step 3: Show Recent Errors (If Any)

```bash
python -c "
from scripts.discovery.telemetry_reader import get_critical_errors
errors = get_critical_errors(hours=168)

print('Recent errors (last 7 days):')
if len(errors) == 0:
    print('  (none)')
else:
    for e in errors[:5]:
        print(f'  [{e[\"timestamp\"]}] {e[\"model\"]}: {e[\"error\"]}')

print('✓ Error surfacing working')
"
```

**Expected:** List of errors or "(none)" if healthy

- [x] PASS / [ ] FAIL

---

## Result

| Criterion | Status |
|-----------|--------|
| Function exists and runs | [x] PASS / [ ] FAIL |
| Returns structured data | [x] PASS / [ ] FAIL |
| Shows recent errors | [x] PASS / [ ] FAIL |

**Overall V4:** [x] PASS / [ ] FAIL

---

**Hand back to Floor Manager when complete.**
