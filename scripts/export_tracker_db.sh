#!/usr/bin/env bash
# export_tracker_db.sh — Export tracker.db to SQL dump for Turso import
# Usage: bash scripts/export_tracker_db.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DB_PATH="$REPO_ROOT/tracker.db"
DUMP_PATH="$REPO_ROOT/tracker_export.sql"

if [[ ! -f "$DB_PATH" ]]; then
  echo "❌ tracker.db not found at $DB_PATH"
  exit 1
fi

echo "📦 Exporting $DB_PATH → $DUMP_PATH ..."
sqlite3 "$DB_PATH" .dump > "$DUMP_PATH"
ROW_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM tasks;")
echo "✅ Export complete — $ROW_COUNT rows in 'tasks' table"
echo "   Output: $DUMP_PATH"
echo ""
echo "Next steps:"
echo "  turso db create open-kanban"
echo "  turso db shell open-kanban < $DUMP_PATH"
