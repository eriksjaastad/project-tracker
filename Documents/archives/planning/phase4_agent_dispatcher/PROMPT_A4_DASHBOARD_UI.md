# Prompt A4: Dashboard UI

**Task:** Add Agent Dispatcher section to dashboard with trigger buttons
**Estimated Time:** 5-10 minutes
**Worker Model:** qwen3:4b (preferred) or deepseek-r1:14b
**Depends On:** A3 (API endpoints must work)

---

## CONSTRAINTS (READ FIRST)

- DO NOT add complex JavaScript frameworks - vanilla JS only
- DO NOT redesign the dashboard - add one section only
- DO NOT add real-time updates - simple request/response for MVP
- FOLLOW existing template patterns in index.html
- OUTPUT using StrReplace to modify template

---

## Task Description

Add to dashboard template:
1. Agent Dispatcher section with list of agents
2. Trigger buttons for each command
3. Basic styling matching existing cards

---

## [ACCEPTANCE CRITERIA] (MANDATORY CHECKLIST)

- [x] **Section Visible:** Agent Dispatcher section appears on dashboard
- [x] **Agents Listed:** Shows all available agents with status
- [x] **Command Buttons:** Each command has a clickable button
- [x] **Unavailable Grayed:** Agents without binary are visually disabled
- [x] **No Breaking Changes:** Rest of dashboard still works

---

## Context Bridge: Template Pattern

Add this section to `dashboard/templates/index.html`:

```html
<!-- Agent Dispatcher Section -->
<div class="card agent-dispatcher">
    <h2>Agent Dispatcher</h2>
    <p class="subtitle">Manually trigger agent commands</p>

    <div id="agents-list">
        {% for agent in agents %}
        <div class="agent-card {% if not agent.available %}disabled{% endif %}">
            <div class="agent-header">
                <strong>{{ agent.name }}</strong>
                {% if agent.available %}
                    <span class="status-badge green">Ready</span>
                {% else %}
                    <span class="status-badge red">Not Found</span>
                {% endif %}
            </div>
            <p class="agent-description">{{ agent.description }}</p>

            {% if agent.available %}
            <div class="command-buttons">
                {% for cmd in agent.commands %}
                <button
                    class="cmd-btn"
                    onclick="runAgentCommand('{{ agent.name }}', '{{ cmd.name }}')"
                    title="{{ cmd.description }}"
                >
                    {{ cmd.name }}
                </button>
                {% endfor %}
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>

    <!-- Output area (filled by A5) -->
    <div id="command-output" class="hidden">
        <h3>Command Output</h3>
        <pre id="output-content"></pre>
    </div>
</div>

<style>
.agent-dispatcher {
    margin-top: 20px;
}
.agent-card {
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 12px;
    margin-bottom: 10px;
}
.agent-card.disabled {
    opacity: 0.5;
}
.agent-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.status-badge {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
}
.status-badge.green { background: #d4edda; color: #155724; }
.status-badge.red { background: #f8d7da; color: #721c24; }
.agent-description {
    color: #666;
    font-size: 14px;
    margin: 8px 0;
}
.command-buttons {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
.cmd-btn {
    padding: 6px 12px;
    border: 1px solid #007bff;
    background: white;
    color: #007bff;
    border-radius: 4px;
    cursor: pointer;
}
.cmd-btn:hover {
    background: #007bff;
    color: white;
}
#command-output {
    margin-top: 20px;
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 12px;
    border-radius: 4px;
}
#command-output.hidden {
    display: none;
}
#output-content {
    max-height: 300px;
    overflow-y: auto;
    white-space: pre-wrap;
    font-family: monospace;
    font-size: 13px;
}
</style>

<script>
// Placeholder - implemented in A5
function runAgentCommand(agentName, commandName) {
    console.log('Running:', agentName, commandName);
    alert('Command execution will be added in next prompt');
}
</script>
```

---

## Floor Manager Instructions

1. Read `dashboard/app.py` to find the route that renders `index.html`
2. Add `agents` to the template context:
   ```python
   from scripts.discovery.agent_registry import get_available_agents
   agents = get_available_agents()
   # Convert to dicts for template
   agents_data = [
       {
           "name": a.name,
           "description": a.description,
           "available": a.available,
           "commands": [{"name": c.name, "description": c.description} for c in a.commands]
       }
       for a in agents
   ]
   # Pass agents=agents_data to template
   ```

3. Read `dashboard/templates/index.html` to find where to add the section
4. Add the HTML/CSS/JS above

---

## Verification Command

After implementing, run:

```bash
cd $PROJECTS_ROOT/project-tracker

# Start dashboard
./pt launch --no-scan &
sleep 3

# Check if Agent Dispatcher section exists
curl -s http://localhost:8000/ | grep -q "Agent Dispatcher" && echo "OK - Section found" || echo "FAIL - Section not found"

# Cleanup
pkill -f "uvicorn" || true
```

**Expected:** "Agent Dispatcher" text found on page.

---

## Result

- [x] PASS: Agent Dispatcher section visible
- [ ] FAIL: Describe error

**Hand back to Floor Manager when complete.**
