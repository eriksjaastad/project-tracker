# Verification V3: Cost Savings

**Verifies:** Cost Savings - Calculate and display estimated savings
**Estimated Time:** 5 minutes
**Model:** Any

---

## Done Criteria

All must pass:

- [x] **Savings calculated:** `get_telemetry_stats()` returns `savings` field
- [x] **Percentage calculated:** Returns `savings_pct` field
- [x] **Estimated cost:** Returns `estimated_cloud_cost` field
- [x] **Actual cost:** Returns `actual_cost` field
- [x] **API includes savings:** `/api/telemetry` response has savings data

---

## Verification Steps

### Step 1: Savings Fields Exist

```bash
cd $PROJECTS_ROOT/project-tracker
python -c "
from scripts.discovery.telemetry_reader import get_telemetry_stats
stats = get_telemetry_stats(days=30)

required_fields = ['savings', 'savings_pct', 'estimated_cloud_cost', 'actual_cost']
for field in required_fields:
    assert field in stats, f'ERROR: Missing field: {field}'
    print(f'{field}: {stats[field]}')

print('✓ All savings fields present')
"
```

**Expected:** All 4 fields present with numeric values

- [x] PASS / [ ] FAIL

---

### Step 2: Savings Math Makes Sense

```bash
python -c "
from scripts.discovery.telemetry_reader import get_telemetry_stats
stats = get_telemetry_stats(days=30)

est = stats['estimated_cloud_cost']
actual = stats['actual_cost']
savings = stats['savings']

# Savings should equal estimated - actual
calculated = round(est - actual, 2)
print(f'Estimated cloud cost: \${est}')
print(f'Actual cost: \${actual}')
print(f'Savings: \${savings}')
print(f'Calculated (est - actual): \${calculated}')

# Allow small floating point difference
assert abs(savings - calculated) < 0.01, f'ERROR: Savings math wrong'
print('✓ Savings calculation correct')
"
```

**Expected:** savings = estimated_cloud_cost - actual_cost

- [x] PASS / [ ] FAIL

---

### Step 3: API Includes Savings

```bash
./pt launch --no-scan &
sleep 3

curl -s http://localhost:8000/api/telemetry | python -c "
import sys, json
data = json.load(sys.stdin)

assert 'savings' in data, 'ERROR: API missing savings'
assert 'savings_pct' in data, 'ERROR: API missing savings_pct'

print(f'API Savings: \${data[\"savings\"]} ({data[\"savings_pct\"]}%)')
print('✓ Savings in API response')
"

pkill -f "uvicorn" || true
```

**Expected:** Savings data in API response

- [x] PASS / [ ] FAIL

---

## Result

| Criterion | Status |
|-----------|--------|
| Savings fields exist | [x] PASS / [ ] FAIL |
| Savings math correct | [x] PASS / [ ] FAIL |
| API includes savings | [x] PASS / [ ] FAIL |

**Overall V3:** [x] PASS / [ ] FAIL

---

**Hand back to Floor Manager when complete.**
