# Worker Task 2a: Add Dashboard API Route

**Worker Model:** Qwen 2.5 Coder
**Objective:** Add `/api/telemetry` endpoint to `dashboard/app.py`.

---

## 🎯 [ACCEPTANCE CRITERIA]

- [x] **Import Added:** Import `get_telemetry_stats` from telemetry_reader
- [x] **Route Added:** `/api/telemetry` GET endpoint
- [x] **Returns JSON:** Stats dict from get_telemetry_stats()
- [x] **Days Parameter:** Optional `?days=N` query parameter (default 7)

---

## CONSTRAINTS (READ FIRST)

- ADD the import at the top with other imports
- ADD the route near other `/api/` routes in app.py
- DO NOT modify any existing routes
- USE FastAPI patterns already in the file

---

## Reference Code Snippet

Add this import near the top of `dashboard/app.py`:

```python
from scripts.discovery.telemetry_reader import get_telemetry_stats
```

Add this route (find the section with other API routes):

```python
@app.get("/api/telemetry")
async def api_telemetry(days: int = 7):
    """Get AI Router telemetry stats."""
    try:
        stats = get_telemetry_stats(days=days)
        return stats
    except Exception as e:
        logger.error(f"Error getting telemetry: {e}")
        return {"error": str(e), "total_requests": 0}
```

---

## Verification

```bash
cd $PROJECTS_ROOT/project-tracker

# Start dashboard
./pt launch --no-scan &

# Wait a moment, then test endpoint
sleep 3
curl http://localhost:8000/api/telemetry

# Expected: JSON with total_requests, local_pct, savings, etc.

# Kill dashboard
pkill -f "uvicorn"
```


## Related Documentation

- [[LOCAL_MODEL_LEARNINGS]] - local AI

