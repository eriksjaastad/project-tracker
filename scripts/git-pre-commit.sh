#!/bin/bash
# Pre-commit hook to prevent hardcoded absolute paths

# Check if PROJECTS_ROOT is set
if [ -z "$PROJECTS_ROOT" ]; then
    # Heuristic: find the projects root by going up from current directory
    # until we find a directory containing 'project-scaffolding' or similar
    # For now, we'll try to guess or use the current parent
    export PROJECTS_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fi

echo "🛡️ Running DNA Integrity Scan..."

# Run the validation script on the current project
# Redirect output to see it in the terminal
python3 "./scripts/validate_project.py" project-tracker

RESULT=$?

if [ $RESULT -ne 0 ]; then
    echo "❌ COMMIT BLOCKED: DNA Defects (absolute paths) found."
    echo "   Run ./scripts/fix_portability.py or fix manually."
    exit 1
fi

echo "✅ DNA Scan Passed."
exit 0
