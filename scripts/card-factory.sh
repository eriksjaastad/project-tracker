#!/usr/bin/env bash
#
# card-factory.sh — Scan projects and generate Kanban cards
#
# Usage:
#   card-factory.sh                     # Scan all active projects
#   card-factory.sh --project <name>    # Scan a single project
#   card-factory.sh --dry-run           # Show what would be created
#   card-factory.sh --project <name> --dry-run
#

set -euo pipefail

PROJECT=""
DRY_RUN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project|-p)
      PROJECT="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="(dry run only — show what you would create but do NOT create anything)"
      shift
      ;;
    --all)
      PROJECT=""
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: card-factory.sh [--project <name>] [--dry-run]" >&2
      exit 1
      ;;
  esac
done

if [[ -n "$PROJECT" ]]; then
  PROMPT="Scan $PROJECT. $DRY_RUN Run the scan script, parse the output, and create cards for every finding. Do not ask questions or wait for confirmation. Create the cards now."
else
  PROMPT="Scan all active projects. $DRY_RUN Run the scan script on each project, parse the output, and create cards for every finding. Do not ask questions or wait for confirmation. Create the cards now."
fi

exec claude --agent card-factory -p "$PROMPT"
