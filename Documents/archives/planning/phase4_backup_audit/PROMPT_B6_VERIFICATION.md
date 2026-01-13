# Prompt B6: Verification

**Verifies:** Backup Audit feature - all components working together
**Estimated Time:** 5 minutes
**Model:** Any

---

## Done Criteria

All must pass:

- [x] **File exists:** `scripts/discovery/backup_reader.py`
- [x] **Config parsed:** `_parse_rclone_config()` returns remotes
- [x] **Status works:** `get_backup_status()` returns dict with all fields
- [x] **API works:** `/api/backup` returns JSON
- [x] **Dashboard shows card:** Backup status visible on page

---

## Verification Steps

### Step 1: File Exists

```bash
cd $PROJECTS_ROOT/project-tracker
ls -la scripts/discovery/backup_reader.py
```

**Expected:** File exists with reasonable size (>1KB)

- [x] PASS / [ ] FAIL

---

### Step 2: Config Parser Works

```bash
python -c "
from scripts.discovery.backup_reader import _parse_rclone_config
remotes = _parse_rclone_config()
print(f'Found {len(remotes)} remotes:')
for name in remotes:
    print(f'  - {name}')
assert len(remotes) > 0, 'ERROR: No remotes found'
print('PASS: Config parser works')
"
```

**Expected:** Lists remotes (gbackup, r2_pose_factory, s3)

- [x] PASS / [ ] FAIL

---

### Step 3: Status Function Works

```bash
python -c "
from scripts.discovery.backup_reader import get_backup_status
status = get_backup_status()

required_fields = ['status', 'status_color', 'message', 'remotes', 'remote_count']
for field in required_fields:
    assert field in status, f'ERROR: Missing field: {field}'

print(f'Status: {status["status"]}')
print(f'Color: {status["status_color"]}')
print(f'Message: {status["message"]}')
print(f'Remotes: {status["remotes"]}')
print('PASS: Status function works')
"
```

**Expected:** All fields present with valid values

- [x] PASS / [ ] FAIL

---

### Step 4: API Endpoint Works

```bash
./pt launch --no-scan &
sleep 3

curl -s http://localhost:8000/api/backup | python -c "
import sys, json
data = json.load(sys.stdin)
assert 'status' in data, 'ERROR: Missing status'
assert 'remotes' in data, 'ERROR: Missing remotes'
print(f'API Status: {data["status"]}')
print(f'API Remotes: {data["remotes"]}')
print('PASS: API endpoint works')
"

pkill -f "uvicorn" || true
```

**Expected:** JSON response with backup status

- [x] PASS / [ ] FAIL

---

### Step 5: Dashboard Card Visible

```bash
./pt launch --no-scan &
sleep 3

curl -s http://localhost:8000/ | grep -q "Backup" && echo "PASS: Backup mentioned on dashboard" || echo "FAIL: Backup not found"

pkill -f "uvicorn" || true
```

**Expected:** "Backup" text found on dashboard

- [x] PASS / [ ] FAIL

---

## Result Summary

| Criterion | Status |
|-----------|--------|
| Registry file exists | [x] PASS / [ ] FAIL |
| Config parser works | [x] PASS / [ ] FAIL |
| Status function works | [x] PASS / [ ] FAIL |
| API endpoint works | [x] PASS / [ ] FAIL |
| Dashboard card visible | [x] PASS / [ ] FAIL |
| Manual click test | [x] PASS / [ ] FAIL |

**Overall B6:** [x] PASS / [ ] FAIL

---

## If Any Step Fails

1. Note which step failed and the error message
2. Report back to Floor Manager
3. Floor Manager determines if retry or escalation needed

---

**Hand back to Floor Manager when complete.**
