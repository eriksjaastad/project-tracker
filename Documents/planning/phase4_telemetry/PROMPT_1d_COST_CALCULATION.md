# Worker Task 1d: Add Cost Savings Calculation

**Worker Model:** Qwen 2.5 Coder
**Objective:** Add cost estimation to show savings from local model usage.

---

## 🎯 [ACCEPTANCE CRITERIA]

- [x] **Cost Constants:** Add estimated costs per request by tier
- [x] **Estimated Cloud Cost:** What it would have cost if all requests were cloud
- [x] **Actual Cost:** Estimated actual cost (local = $0)
- [x] **Savings:** Difference between estimated and actual
- [x] **Add to Stats:** Include cost fields in get_telemetry_stats() return

---

## CONSTRAINTS (READ FIRST)

- USE rough estimates (exact pricing not critical)
- LOCAL requests cost $0
- CLOUD "cheap" tier ~$0.002 per request (GPT-4o-mini)
- CLOUD "smart" tier ~$0.01 per request (GPT-4o)
- DO NOT overcomplicate - rough estimates are fine

---

## Reference Code Snippet

Add these constants at the top of the file:

```python
# Rough cost estimates per request (USD)
COST_PER_REQUEST = {
    "local": 0.0,
    "cheap": 0.002,   # GPT-4o-mini estimate
    "smart": 0.01,    # GPT-4o estimate
}
```

Update `get_telemetry_stats()` to add cost calculations at the end:

```python
    # Cost calculations
    actual_cost = 0.0
    estimated_cloud_cost = 0.0

    for e in entries:
        tier = e.get('tier', 'local')
        # Actual cost
        actual_cost += COST_PER_REQUEST.get(tier, 0.0)
        # What it would cost if we used cloud for everything
        estimated_cloud_cost += COST_PER_REQUEST.get('cheap', 0.002)

    savings = estimated_cloud_cost - actual_cost

    # Add to return dict (before the final return statement)
    return {
        # ... existing fields ...
        "estimated_cloud_cost": round(estimated_cloud_cost, 2),
        "actual_cost": round(actual_cost, 2),
        "savings": round(savings, 2),
        "savings_pct": round(savings / estimated_cloud_cost * 100, 1) if estimated_cloud_cost > 0 else 0,
    }
```

---

## Verification

```bash
cd /Users/eriksjaastad/projects/project-tracker
python -c "
from scripts.discovery.telemetry_reader import get_telemetry_stats
stats = get_telemetry_stats(days=30)
print(f'Estimated cloud cost: \${stats[\"estimated_cloud_cost\"]}')
print(f'Actual cost: \${stats[\"actual_cost\"]}')
print(f'Savings: \${stats[\"savings\"]} ({stats[\"savings_pct\"]}%)')
"
# Expected: Savings showing local model value
```
