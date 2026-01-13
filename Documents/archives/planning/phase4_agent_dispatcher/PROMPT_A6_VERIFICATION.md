# Prompt A6: Verification

**Verifies:** Agent Dispatcher UI - all components working together
**Estimated Time:** 5 minutes
**Model:** Any

---

## Done Criteria

All must pass:

- [x] **File exists:** `scripts/discovery/agent_registry.py`
- [x] **Agents listed:** `get_available_agents()` returns agents
- [x] **Executor works:** `run_agent_command()` runs commands
- [x] **API works:** Both `/api/agents` endpoints return data
- [x] **Dashboard shows UI:** Agent Dispatcher section visible
- [x] **Commands execute:** Clicking buttons runs commands and shows output

---

## Verification Steps

### Step 1: Registry File Exists

```bash
cd $PROJECTS_ROOT/project-tracker
ls -la scripts/discovery/agent_registry.py
```

**Expected:** File exists with reasonable size (>2KB)

- [x] PASS / [ ] FAIL

---

### Step 2: Agents Registered

```bash
python -c "
from scripts.discovery.agent_registry import get_available_agents
agents = get_available_agents()
print(f'Found {len(agents)} agents:')
for a in agents:
    print(f'  - {a.name}: {len(a.commands)} commands, available={a.available}')
assert len(agents) >= 2, 'ERROR: Should have at least 2 agents'
print('PASS: Agents registered')
"
```

**Expected:** At least audit-agent and pt registered

- [x] PASS / [ ] FAIL

---

### Step 3: Executor Works

```bash
python -c "
from scripts.discovery.agent_registry import run_agent_command

result = run_agent_command('pt', 'list')
print(f'Command: {result.command}')
print(f'Success: {result.success}')
print(f'Duration: {result.duration_ms}ms')
print(f'Output length: {len(result.output)} chars')

assert result.success or result.error, 'ERROR: No result data'
print('PASS: Executor works')
"
```

**Expected:** Command runs and returns result

- [x] PASS / [ ] FAIL

---

### Step 4: API Endpoints Work

```bash
./pt launch --no-scan &
sleep 3

# Test GET /api/agents
echo "Testing GET /api/agents:"
curl -s http://localhost:8000/api/agents | python -c "
import sys, json
data = json.load(sys.stdin)
agents = data.get('agents', [])
assert len(agents) >= 2, 'ERROR: Not enough agents'
print(f'OK: {len(agents)} agents returned')
"

# Test POST /api/agents/run
echo "Testing POST /api/agents/run:"
curl -s -X POST http://localhost:8000/api/agents/run \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "pt", "command_name": "list"}' | python -c "
import sys, json
data = json.load(sys.stdin)
assert 'success' in data, 'ERROR: Missing success field'
assert 'output' in data, 'ERROR: Missing output field'
print(f'OK: success={data[\"success\"]}, duration={data.get(\"duration_ms\")}ms')
"

pkill -f "uvicorn" || true
echo "PASS: API endpoints work"
```

**Expected:** Both endpoints return valid JSON

- [x] PASS / [ ] FAIL

---

### Step 5: Dashboard UI Visible

```bash
./pt launch --no-scan &
sleep 3

curl -s http://localhost:8000/ | grep -q "Agent Dispatcher" && echo "PASS: Section found" || echo "FAIL: Section not found"
curl -s http://localhost:8000/ | grep -q "cmd-btn" && echo "PASS: Buttons found" || echo "FAIL: Buttons not found"

pkill -f "uvicorn" || true
```

**Expected:** Agent Dispatcher section with command buttons

- [x] PASS / [ ] FAIL

---

### Step 6: Manual Click Test

Open http://localhost:8000 in browser:

1. Find "Agent Dispatcher" section
2. Click "list" button under "pt"
3. Verify output appears showing project list
4. Check that success/duration is shown

- [x] PASS / [ ] FAIL

---

## Result Summary

| Criterion | Status |
|-----------|--------|
| Registry file exists | [x] PASS / [ ] FAIL |
| Agents registered | [x] PASS / [ ] FAIL |
| Executor works | [x] PASS / [ ] FAIL |
| API endpoints work | [x] PASS / [ ] FAIL |
| Dashboard UI visible | [x] PASS / [ ] FAIL |
| Manual click test | [x] PASS / [ ] FAIL |

**Overall A6:** [x] PASS / [ ] FAIL

---

## If Any Step Fails

1. Note which step failed and the error message
2. Report back to Floor Manager
3. Floor Manager determines if retry or escalation needed

---

**Hand back to Floor Manager when complete.**
