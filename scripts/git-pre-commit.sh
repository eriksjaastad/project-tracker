#!/bin/bash
# Pre-commit hook to prevent hardcoded absolute paths

# Get the project root
# When run as a hook, $0 is .git/hooks/pre-commit, so we go up 2 levels
# When run directly, $0 is scripts/git-pre-commit.sh, so we go up 1 level
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ "$SCRIPT_DIR" == *".git/hooks"* ]]; then
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
else
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# Check if PROJECTS_ROOT is set, otherwise set it to parent of project
if [ -z "$PROJECTS_ROOT" ]; then
    # For standalone projects, PROJECTS_ROOT is the parent directory
    export PROJECTS_ROOT="$(dirname "$PROJECT_ROOT")"
fi

echo "🛡️ Running DNA Integrity Scan..."

# Run warden audit instead of validate_project.py for standalone operation
python3 "$PROJECT_ROOT/scripts/warden_audit.py" --root "$PROJECT_ROOT" --fast

RESULT=$?

if [ $RESULT -ne 0 ]; then
    echo "❌ COMMIT BLOCKED: DNA Defects (absolute paths) found."
    echo "   Run ./scripts/fix_portability.py or fix manually."
    exit 1
fi

echo "✅ DNA Scan Passed."
exit 0
