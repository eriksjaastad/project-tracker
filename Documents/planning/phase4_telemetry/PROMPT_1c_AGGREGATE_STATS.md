# Worker Task 1c: Add Aggregation Functions

**Worker Model:** Qwen 2.5 Coder
**Objective:** Update `get_telemetry_stats()` to aggregate entries into useful stats.

---

## 🎯 [ACCEPTANCE CRITERIA]

- [x] **get_telemetry_stats() Updated:** Returns aggregated dict
- [x] **Model Counts:** Count of requests per model
- [x] **Provider Split:** Count of local vs cloud requests
- [x] **Avg Duration:** Average response time per provider
- [x] **Error Rate:** Percentage of requests with errors/timeouts
- [x] **Total Requests:** Overall count

---

## CONSTRAINTS (READ FIRST)

- USE the `_read_telemetry_entries()` function from previous task
- DO NOT add cost calculations yet (next task)
- RETURN a flat dict structure for easy JSON serialization

---

## Reference Code Snippet

```python
def get_telemetry_stats(days: int = 7) -> dict[str, Any]:
    """
    Get aggregated telemetry stats for the dashboard.

    Args:
        days: Number of days to look back (default 7)

    Returns:
        Dict with model usage, durations, costs, etc.
    """
    entries = _read_telemetry_entries(days)

    if not entries:
        return {
            "total_requests": 0,
            "local_requests": 0,
            "cloud_requests": 0,
            "local_pct": 0,
            "avg_duration_local_ms": 0,
            "avg_duration_cloud_ms": 0,
            "error_rate": 0,
            "models": {},
            "period_days": days
        }

    # Count by provider
    local_entries = [e for e in entries if e.get('provider') == 'local']
    cloud_entries = [e for e in entries if e.get('provider') != 'local']

    # Count by model
    model_counts: dict[str, int] = {}
    for e in entries:
        model = e.get('model', 'unknown')
        model_counts[model] = model_counts.get(model, 0) + 1

    # Average durations
    local_durations = [e.get('duration_ms', 0) for e in local_entries]
    cloud_durations = [e.get('duration_ms', 0) for e in cloud_entries]

    avg_local = sum(local_durations) / len(local_durations) if local_durations else 0
    avg_cloud = sum(cloud_durations) / len(cloud_durations) if cloud_durations else 0

    # Error rate
    errors = [e for e in entries if e.get('error') or e.get('timed_out')]
    error_rate = (len(errors) / len(entries) * 100) if entries else 0

    total = len(entries)
    local_count = len(local_entries)

    return {
        "total_requests": total,
        "local_requests": local_count,
        "cloud_requests": len(cloud_entries),
        "local_pct": round(local_count / total * 100, 1) if total else 0,
        "avg_duration_local_ms": round(avg_local, 0),
        "avg_duration_cloud_ms": round(avg_cloud, 0),
        "error_rate": round(error_rate, 1),
        "models": model_counts,
        "period_days": days
    }
```

---

## Verification

```bash
cd /Users/eriksjaastad/projects/project-tracker
python -c "
from scripts.discovery.telemetry_reader import get_telemetry_stats
stats = get_telemetry_stats(days=30)
print(f'Total requests: {stats[\"total_requests\"]}')
print(f'Local %: {stats[\"local_pct\"]}%')
print(f'Models: {stats[\"models\"]}')
"
# Expected: Stats with actual counts
```
