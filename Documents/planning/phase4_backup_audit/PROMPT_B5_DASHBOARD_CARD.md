# Prompt B5: Dashboard Card

**Task:** Add backup status card to the dashboard UI
**Estimated Time:** 5-10 minutes
**Worker Model:** qwen3:4b (preferred) or deepseek-r1:14b
**Depends On:** B4 (API endpoint must work)

---

## CONSTRAINTS (READ FIRST)

- DO NOT redesign the dashboard - add one card only
- DO NOT add JavaScript - use existing patterns (Jinja2 templates)
- DO NOT add new CSS files - use existing styles
- FOLLOW the exact pattern used by other dashboard cards
- OUTPUT using StrReplace to add to the template

---

## Task Description

Add to the dashboard template:
1. Fetch backup status from API (or pass from backend)
2. Display a card showing backup status
3. Use color coding (green/yellow/red) based on status
4. List configured remotes

---

## [ACCEPTANCE CRITERIA] (MANDATORY CHECKLIST)

- [ ] **Card Visible:** Backup status card appears on dashboard
- [ ] **Status Color:** Card uses appropriate color (green/yellow/red)
- [ ] **Remote List:** Shows configured backup remotes
- [ ] **Message Shown:** Displays status message
- [ ] **No Breaking Changes:** Other dashboard elements still work

---

## Context Bridge: Dashboard Structure

The dashboard uses Jinja2 templates. Check:
- `dashboard/templates/index.html` - Main dashboard template
- Look for how telemetry or cron health cards are rendered

Typical card pattern:

```html
<!-- Backup Status Card -->
<div class="card" style="border-left: 4px solid {{ backup_status.status_color }};">
    <h3>Backup Status</h3>
    <p class="status-{{ backup_status.status }}">
        {{ backup_status.message }}
    </p>
    {% if backup_status.remotes %}
    <div class="remote-list">
        <strong>Configured Remotes:</strong>
        <ul>
        {% for remote in backup_status.remotes %}
            <li>{{ remote }}</li>
        {% endfor %}
        </ul>
    </div>
    {% endif %}
    {% if backup_status.critical_unbacked %}
    <div class="warning">
        <strong>Needs Backup:</strong>
        <ul>
        {% for path in backup_status.critical_unbacked[:3] %}
            <li>{{ path }}</li>
        {% endfor %}
        {% if backup_status.critical_unbacked|length > 3 %}
            <li>... and {{ backup_status.critical_unbacked|length - 3 }} more</li>
        {% endif %}
        </ul>
    </div>
    {% endif %}
</div>
```

---

## Floor Manager Instructions

1. Read `dashboard/app.py` to find how data is passed to templates
2. Read `dashboard/templates/index.html` to find where cards are placed
3. Add `backup_status` to the template context in the route handler
4. Add the card HTML to the template

**Two-part edit required:**

**Part A: app.py** - Add backup_status to context:
```python
# In the route that renders index.html, add:
from scripts.discovery.backup_reader import get_backup_status
backup_status = get_backup_status()
# Pass to template: backup_status=backup_status
```

**Part B: index.html** - Add the card HTML where other status cards are

---

## Verification Command

After implementing, run:

```bash
cd /Users/eriksjaastad/projects/project-tracker

# Start dashboard
./pt launch --no-scan &
sleep 3

# Check if page loads and contains backup info
curl -s http://localhost:8000/ | grep -q "Backup Status" && echo "OK - Card found on page" || echo "ERROR - Card not found"

# Cleanup
pkill -f "uvicorn" || true
```

**Expected:** "Backup Status" text found on dashboard page

---

## Manual Verification

Open http://localhost:8000 in browser and check:
- [ ] Backup Status card is visible
- [ ] Shows correct status color
- [ ] Lists configured remotes (gbackup, r2_pose_factory)

---

## Result

- [ ] PASS: Dashboard card visible and working
- [ ] FAIL: Describe error

**Hand back to Floor Manager when complete.**
