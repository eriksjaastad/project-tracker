# Worker Task 2c: Enhance Cost Display

**Worker Model:** Qwen 2.5 Coder
**Objective:** Add detailed cost breakdown and model usage to the telemetry card.

---

## 🎯 [ACCEPTANCE CRITERIA]

- [x] **Model Breakdown:** Show top 3 most-used models
- [x] **Cost Comparison:** Show "Would have cost" vs "Actual cost"
- [x] **Savings Highlight:** Make savings visually prominent
- [x] **Error Rate:** Show if error rate is concerning (>5%)

---

## CONSTRAINTS (READ FIRST)

- MODIFY the existing telemetry card (don't create new card)
- KEEP the card compact (don't make it huge)
- USE existing CSS classes from Bootstrap

---

## Reference Code Snippet

Update the telemetry card body:

```html
<!-- AI Router Telemetry Card - Enhanced -->
<div class="col-md-4">
    <div class="card">
        <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">AI Router (7 days)</h6>
            <div id="telemetry-stats">
                <div class="row mb-2">
                    <div class="col-6">
                        <small class="text-muted">Requests</small><br>
                        <strong id="telemetry-total">--</strong>
                    </div>
                    <div class="col-6">
                        <small class="text-muted">Local</small><br>
                        <strong id="telemetry-local-pct">--</strong>%
                        <span id="telemetry-local-indicator"></span>
                    </div>
                </div>
                <div class="row mb-2">
                    <div class="col-6">
                        <small class="text-muted">Est. Cloud</small><br>
                        <span class="text-muted">$<span id="telemetry-cloud-cost">--</span></span>
                    </div>
                    <div class="col-6">
                        <small class="text-muted">Actual</small><br>
                        <span class="text-success">$<span id="telemetry-actual-cost">--</span></span>
                    </div>
                </div>
                <div class="alert alert-success py-1 px-2 mb-2" id="telemetry-savings-box">
                    <small><strong>Saved: $<span id="telemetry-savings">--</span></strong>
                    (<span id="telemetry-savings-pct">--</span>%)</small>
                </div>
                <div id="telemetry-models">
                    <small class="text-muted">Top Models:</small>
                    <div id="model-list" style="font-size: 0.85em;"></div>
                </div>
                <div id="telemetry-error-warning" class="text-danger mt-1" style="display:none;">
                    <small>⚠️ Error rate: <span id="telemetry-error-rate">--</span>%</small>
                </div>
            </div>
        </div>
    </div>
</div>
```

Update the JavaScript:

```html
<script>
fetch('/api/telemetry')
    .then(response => response.json())
    .then(data => {
        document.getElementById('telemetry-total').textContent = data.total_requests || 0;
        document.getElementById('telemetry-local-pct').textContent = data.local_pct || 0;
        document.getElementById('telemetry-cloud-cost').textContent = data.estimated_cloud_cost || '0.00';
        document.getElementById('telemetry-actual-cost').textContent = data.actual_cost || '0.00';
        document.getElementById('telemetry-savings').textContent = data.savings || '0.00';
        document.getElementById('telemetry-savings-pct').textContent = data.savings_pct || 0;

        // Local percentage indicator
        const indicator = document.getElementById('telemetry-local-indicator');
        if (data.local_pct >= 80) {
            indicator.innerHTML = '<span class="badge bg-success">Good</span>';
        } else if (data.local_pct >= 50) {
            indicator.innerHTML = '<span class="badge bg-warning">OK</span>';
        } else {
            indicator.innerHTML = '<span class="badge bg-danger">Low</span>';
        }

        // Model list (top 3)
        if (data.models) {
            const sorted = Object.entries(data.models)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 3);
            const modelHtml = sorted.map(([model, count]) =>
                `<div>${model}: ${count}</div>`
            ).join('');
            document.getElementById('model-list').innerHTML = modelHtml || '<em>No data</em>';
        }

        // Error rate warning
        if (data.error_rate > 5) {
            document.getElementById('telemetry-error-warning').style.display = 'block';
            document.getElementById('telemetry-error-rate').textContent = data.error_rate;
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
# Expected:
# - See enhanced telemetry card
# - Shows savings in green
# - Shows top 3 models used
# - Error warning appears if rate >5%
```
