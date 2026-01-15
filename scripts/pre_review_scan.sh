#!/bin/bash
# pre_review_scan.sh - Run before code reviews or commits
# Usage: ./scripts/pre_review_scan.sh

set -e  # Exit on first error

echo "=== Pre-Review Scan ==="
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Ensure PROJECTS_ROOT is set for validate_project.py
if [ -z "$PROJECTS_ROOT" ]; then
    export PROJECTS_ROOT="$(dirname "$PROJECT_ROOT")"
fi

echo "1. Running Warden Security Audit (fast mode)..."
python3 ./scripts/warden_audit.py --root "$(pwd)" --fast
WARDEN_EXIT=$?

echo ""
echo "2. Running Project Validation..."
python3 ./scripts/validate_project.py project-tracker
VALIDATE_EXIT=$?

echo ""
echo "=== Scan Complete ==="

if [ $WARDEN_EXIT -ne 0 ] || [ $VALIDATE_EXIT -ne 0 ]; then
    echo "FAILED: One or more checks failed"
    exit 1
else
    echo "PASSED: All checks passed"
    exit 0
fi
