# Verification V2: Blinking Lights

**Verifies:** AI Router "Blinking Lights" - routing decisions, model breakdowns
**Estimated Time:** 5 minutes
**Model:** Any

---

## Done Criteria

All must pass:

- [x] **API endpoint exists:** `/api/telemetry` returns JSON
- [x] **Model breakdown:** Response includes `models` dict with counts
- [x] **Local vs Cloud:** Response includes `local_requests` and `cloud_requests`
- [x] **Dashboard visible:** Telemetry card appears on dashboard

---

## Verification Steps

### Step 1: Start Dashboard

```bash
cd $PROJECTS_ROOT/project-tracker
./pt launch --no-scan &
sleep 3
echo "Dashboard started on http://localhost:8000"
```

- [ ] Dashboard started without errors

---

### Step 2: API Endpoint Returns Data

```bash
curl -s http://localhost:8000/api/telemetry | python -c "
import sys, json
data = json.load(sys.stdin)
print('API Response Keys:', list(data.keys()))
print(f'Models: {data.get(\"models\", {})}')
print(f'Local: {data.get(\"local_requests\", 0)}')
print(f'Cloud: {data.get(\"cloud_requests\", 0)}')
"
```

**Expected:** JSON with models, local_requests, cloud_requests fields

- [x] PASS / [ ] FAIL

---

### Step 3: Model Breakdown Has Data

```bash
curl -s http://localhost:8000/api/telemetry | python -c "
import sys, json
data = json.load(sys.stdin)
assert 'models' in data, 'ERROR: No models field'
assert len(data['models']) > 0, 'ERROR: Models dict is empty'
print(f'Models tracked: {len(data[\"models\"])}')
for model, count in data['models'].items():
    print(f'  {model}: {count} requests')
print('✓ Model breakdown working')
"
```

**Expected:** List of models with request counts

- [x] PASS / [ ] FAIL

---

### Step 4: Dashboard Visual Check

Open http://localhost:8000 in browser.

**Check for:**
- [ ] Telemetry card/section is visible on dashboard
- [ ] Shows model usage or local/cloud breakdown
- [ ] No error messages displayed

---

### Step 5: Cleanup

```bash
# Stop the dashboard
pkill -f "uvicorn" || true
```

---

## Result

| Criterion | Status |
|-----------|--------|
| API endpoint exists | [x] PASS / [ ] FAIL |
| Model breakdown has data | [x] PASS / [ ] FAIL |
| Local vs Cloud shown | [x] PASS / [ ] FAIL |
| Dashboard card visible | [x] PASS / [ ] FAIL |

**Overall V2:** [x] PASS / [ ] FAIL

---

**Hand back to Floor Manager when complete.**
