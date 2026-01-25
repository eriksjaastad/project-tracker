# Worker Task 2b: Add Telemetry Card to Dashboard

**Worker Model:** Qwen 2.5 Coder
**Objective:** Add "AI Router" stats card to the dashboard template.

---

## 🎯 [ACCEPTANCE CRITERIA]

- [x] **Card Added:** New card in dashboard showing AI Router stats
- [x] **Shows Stats:** Total requests, Local %, Avg duration
- [x] **Visual Indicator:** Color-coded local percentage (green if >80%)
- [x] **JavaScript:** Fetches from /api/telemetry on page load

---

## CONSTRAINTS (READ FIRST)

- FIND the existing card pattern in `dashboard/templates/index.html`
- MATCH the existing styling (Bootstrap/CSS classes used)
- ADD JavaScript at the bottom with other scripts
- DO NOT modify existing cards

---

## Reference Code Snippet

Add this card HTML (find where other metric cards are):

```html
<!-- AI Router Telemetry Card -->
<div class="col-md-3">
    <div class="card">
        <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">AI Router (7 days)</h6>
            <div id="telemetry-stats">
                <p class="mb-1">
                    <strong>Requests:</strong> <span id="telemetry-total">--</span>
                </p>
                <p class="mb-1">
                    <strong>Local:</strong> <span id="telemetry-local-pct">--</span>%
                    <span id="telemetry-local-indicator"></span>
                </p>
                <p class="mb-1">
                    <strong>Avg Local:</strong> <span id="telemetry-avg-local">--</span>ms
                </p>
                <p class="mb-0">
                    <strong>Savings:</strong> $<span id="telemetry-savings">--</span>
                </p>
            </div>
        </div>
    </div>
</div>
```

Add this JavaScript (at bottom with other scripts):

```html
<script>
// Load AI Router telemetry
fetch('/api/telemetry')
    .then(response => response.json())
    .then(data => {
        document.getElementById('telemetry-total').textContent = data.total_requests || 0;
        document.getElementById('telemetry-local-pct').textContent = data.local_pct || 0;
        document.getElementById('telemetry-avg-local').textContent = data.avg_duration_local_ms || 0;
        document.getElementById('telemetry-savings').textContent = data.savings || '0.00';

        // Color indicator for local percentage
        const indicator = document.getElementById('telemetry-local-indicator');
        if (data.local_pct >= 80) {
            indicator.innerHTML = '<span class="badge bg-success">Good</span>';
        } else if (data.local_pct >= 50) {
            indicator.innerHTML = '<span class="badge bg-warning">OK</span>';
        } else {
            indicator.innerHTML = '<span class="badge bg-danger">Low</span>';
        }
    })
    .catch(err => {
        console.error('Failed to load telemetry:', err);
        document.getElementById('telemetry-stats').innerHTML = '<em>Telemetry unavailable</em>';
    });
</script>
```

---

## Verification

```bash
cd $PROJECTS_ROOT/project-tracker
./pt launch --no-scan

# Open browser to http://localhost:8000
# Expected: See "AI Router (7 days)" card with stats
```


## Related Documentation

- [Local Model Learnings](Documents/reference/LOCAL_MODEL_LEARNINGS.md) - local AI

