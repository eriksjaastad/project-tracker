# Worker Task 3a: Add Critical Error Surfacing

**Worker Model:** Qwen 2.5 Coder
**Objective:** Surface critical errors (MCP failures, Cron failures) with [CRITICAL] flags.

---

## 🎯 [ACCEPTANCE CRITERIA]

- [x] **Check Telemetry Errors:** Count recent errors/timeouts from AI Router
- [x] **Critical Threshold:** Flag if error rate >10% or >5 errors in last 24h
- [x] **Add to Alerts:** Show in dashboard alerts section
- [x] **Visual Indicator:** Red [CRITICAL] badge

---

## CONSTRAINTS (READ FIRST)

- ADD to existing alerts system in dashboard (don't create new alert system)
- USE the telemetry stats already being fetched
- KEEP it simple - just count errors, flag if too many

---

## Reference: What Counts as Critical

1. **AI Router errors:** From telemetry (error != null or timed_out == true)
2. **High error rate:** >10% of requests failing
3. **Recent failures:** >5 errors in last 24 hours

---

## Reference Code Snippet

Add to telemetry_reader.py:

```python
def get_critical_errors(hours: int = 24) -> list[dict]:
    """
    Get critical errors from last N hours.
    Returns list of error entries for alerting.
    """
    entries = _read_telemetry_entries(days=1)  # Get last day

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    errors = []

    for e in entries:
        if not (e.get('error') or e.get('timed_out')):
            continue

        ts_str = e.get('timestamp', '')
        if ts_str:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            if ts.replace(tzinfo=None) >= cutoff:
                errors.append({
                    'model': e.get('model', 'unknown'),
                    'error': e.get('error') or 'Timeout',
                    'timestamp': ts_str
                })

    return errors
```

Add to dashboard JavaScript:

```javascript
// Check for critical errors
fetch('/api/telemetry?days=1')
    .then(response => response.json())
    .then(data => {
        if (data.error_rate > 10) {
            // Add critical alert
            const alertHtml = `
                <div class="alert alert-danger">
                    <span class="badge bg-danger">CRITICAL</span>
                    AI Router error rate: ${data.error_rate}% in last 24h
                </div>
            `;
            document.getElementById('alerts-container').insertAdjacentHTML('afterbegin', alertHtml);
        }
    });
```

---

## Verification

```bash
cd /Users/eriksjaastad/projects/project-tracker
python -c "
from scripts.discovery.telemetry_reader import get_critical_errors
errors = get_critical_errors(hours=24)
print(f'Critical errors in last 24h: {len(errors)}')
"
```
