# Prompt A5: Output Display

**Task:** Implement JavaScript to run commands and display output
**Estimated Time:** 5-10 minutes
**Worker Model:** qwen3:4b (preferred) or deepseek-r1:14b
**Depends On:** A4 (UI structure must exist)

---

## CONSTRAINTS (READ FIRST)

- DO NOT use external JavaScript libraries - vanilla JS only
- DO NOT add WebSocket - simple fetch for MVP
- DO NOT add polling - one request, one response
- KEEP JavaScript minimal and readable
- OUTPUT using StrReplace to update the script section

---

## Task Description

Update the JavaScript in the dashboard template:
1. Implement `runAgentCommand()` to call the API
2. Show loading state while running
3. Display output in the output area
4. Handle errors gracefully

---

## [ACCEPTANCE CRITERIA] (MANDATORY CHECKLIST)

- [x] **Click Triggers API:** Button click calls POST /api/agents/run
- [x] **Loading State:** Shows "Running..." while waiting
- [x] **Output Displayed:** Command output appears in output area
- [x] **Success/Error Styled:** Different colors for success vs error
- [x] **Duration Shown:** Shows how long command took

---

## Context Bridge: JavaScript Implementation

Replace the placeholder script with:

```html
<script>
async function runAgentCommand(agentName, commandName, args = '') {
    const outputDiv = document.getElementById('command-output');
    const outputContent = document.getElementById('output-content');

    // Show output area with loading state
    outputDiv.classList.remove('hidden');
    outputContent.innerHTML = '<span style="color: #888;">Running ' + agentName + ' ' + commandName + '...</span>';

    try {
        const response = await fetch('/api/agents/run', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                agent_name: agentName,
                command_name: commandName,
                args: args
            })
        });

        const result = await response.json();

        // Build output display
        let html = '';

        // Header with status
        if (result.success) {
            html += '<span style="color: #4caf50;">SUCCESS</span>';
        } else {
            html += '<span style="color: #f44336;">FAILED</span>';
        }
        html += ' <span style="color: #888;">(' + result.duration_ms + 'ms)</span>\n';
        html += '<span style="color: #888;">Command: ' + escapeHtml(result.command) + '</span>\n\n';

        // Output
        if (result.output) {
            html += result.output;
        }

        // Error (if any)
        if (result.error) {
            html += '\n<span style="color: #f44336;">Error: ' + escapeHtml(result.error) + '</span>';
        }

        outputContent.innerHTML = html;

    } catch (error) {
        outputContent.innerHTML = '<span style="color: #f44336;">Request failed: ' + escapeHtml(error.message) + '</span>';
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
</script>
```

---

## Floor Manager Instructions

1. Read `dashboard/templates/index.html`
2. Find the existing `<script>` section with the placeholder `runAgentCommand`
3. Replace the entire script block with the new implementation above

---

## Verification Command

After implementing, run:

```bash
cd /Users/eriksjaastad/projects/project-tracker

# Start dashboard
./pt launch --no-scan &
sleep 3

# Check if the new JavaScript is present
curl -s http://localhost:8000/ | grep -q "fetch('/api/agents/run'" && echo "OK - JavaScript updated" || echo "FAIL - Old placeholder still there"

# Cleanup
pkill -f "uvicorn" || true
```

**Expected:** New fetch-based JavaScript found on page.

---

## Manual Verification

Open http://localhost:8000 in browser:
1. Find Agent Dispatcher section
2. Click a command button (e.g., "pt > list")
3. Verify output appears below
4. Verify success/error styling works

---

## Result

- [x] PASS: Commands execute and output displays
- [ ] FAIL: Describe error

**Hand back to Floor Manager when complete.**
