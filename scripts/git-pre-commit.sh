#!/bin/bash
# Pre-commit hook installed by governance system
# Runs governance checks on staged files

# Path to governance-check.sh (resolve from PROJECTS_ROOT or HOME)
GOVERNANCE_CHECK="${PROJECTS_ROOT:-$HOME/projects}/_tools/governance/governance-check.sh"

if [ ! -f "$GOVERNANCE_CHECK" ]; then
    echo "Error: governance-check.sh not found at $GOVERNANCE_CHECK" >&2
    exit 1
fi

# Run governance checks
exec "$GOVERNANCE_CHECK"
