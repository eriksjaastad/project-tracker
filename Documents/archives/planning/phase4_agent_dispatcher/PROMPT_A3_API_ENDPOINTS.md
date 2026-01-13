# Prompt A3: API Endpoints

**Task:** Add /api/agents endpoints to list and run agents
**Estimated Time:** 5-10 minutes
**Worker Model:** qwen3:4b (preferred) or deepseek-r1:14b
**Depends On:** A2 (executor must work)

---

## CONSTRAINTS (READ FIRST)

- DO NOT add authentication - local use only
- DO NOT modify existing endpoints - add new ones only
- DO NOT use WebSockets - keep it simple with REST
- FOLLOW existing API patterns in app.py
- OUTPUT using StrReplace to add endpoints

---

## Task Description

Add to `dashboard/app.py`:
1. `GET /api/agents` - List all available agents and their commands
2. `POST /api/agents/run` - Execute an agent command

---

## [ACCEPTANCE CRITERIA] (MANDATORY CHECKLIST)

- [x] **GET /api/agents Works:** Returns list of agents with commands
- [x] **POST /api/agents/run Works:** Executes command and returns result
- [x] **Request Body Validated:** Checks for agent_name, command_name
- [x] **Returns Structured Data:** Success, output, error, duration
- [x] **No Breaking Changes:** Existing endpoints still work

---

## Context Bridge: API Pattern

Follow the existing pattern in `dashboard/app.py`:

```python
# Add these imports at the top of app.py
from scripts.discovery.agent_registry import (
    get_available_agents,
    run_agent_command,
    Agent,
    AgentCommand,
    CommandResult
)
from pydantic import BaseModel
from typing import Optional


# Pydantic model for run request
class AgentRunRequest(BaseModel):
    agent_name: str
    command_name: str
    args: Optional[str] = ""


# GET /api/agents - List all agents
@app.get("/api/agents")
async def list_agents():
    """Return list of available agents and their commands."""
    agents = get_available_agents()
    return {
        "agents": [
            {
                "name": a.name,
                "description": a.description,
                "available": a.available,
                "commands": [
                    {
                        "name": c.name,
                        "description": c.description,
                        "args_template": c.args_template,
                        "dangerous": c.dangerous
                    }
                    for c in a.commands
                ]
            }
            for a in agents
        ]
    }


# POST /api/agents/run - Execute agent command
@app.post("/api/agents/run")
async def run_agent(request: AgentRunRequest):
    """Execute an agent command and return result."""
    result = run_agent_command(
        request.agent_name,
        request.command_name,
        request.args or ""
    )

    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "return_code": result.return_code,
        "duration_ms": result.duration_ms,
        "command": result.command
    }
```

---

## Floor Manager Instructions

1. Read `dashboard/app.py` to find the import section
2. Add the new imports
3. Add the Pydantic model class
4. Add both endpoint functions after existing API endpoints

---

## Verification Command

After implementing, run:

```bash
cd $PROJECTS_ROOT/project-tracker

# Start dashboard
./pt launch --no-scan &
sleep 3

# Test GET /api/agents
echo "Testing GET /api/agents:"
curl -s http://localhost:8000/api/agents | python -c "
import sys, json
data = json.load(sys.stdin)
agents = data.get('agents', [])
print(f'Found {len(agents)} agents')
for a in agents:
    print(f'  - {a[\"name\"]}: {len(a[\"commands\"])} commands')
"

# Test POST /api/agents/run
echo ""
echo "Testing POST /api/agents/run:"
curl -s -X POST http://localhost:8000/api/agents/run \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "pt", "command_name": "list"}' | python -c "
import sys, json
data = json.load(sys.stdin)
print(f'Success: {data.get(\"success\")}')
print(f'Duration: {data.get(\"duration_ms\")}ms')
"

# Cleanup
pkill -f "uvicorn" || true
echo "OK - API endpoints working"
```

**Expected:** Both endpoints return valid JSON.

---

## Result

- [x] PASS: API endpoints work correctly
- [ ] FAIL: Describe error

**Hand back to Floor Manager when complete.**
