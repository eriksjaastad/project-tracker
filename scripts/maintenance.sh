#!/bin/bash
# maintenance.sh - Global Ecosystem Health & Networking
# Master script for the ecosystem. Runs monthly via cron.

PROJECT_ROOT="/Users/eriksjaastad/projects"
TRACKER_DIR="$PROJECT_ROOT/project-tracker"
LIBRARIAN="$TRACKER_DIR/scripts/discovery/librarian.py"
JOURNAL_SPECIALIST="$TRACKER_DIR/scripts/discovery/journal_specialist.py"

echo "🤖 Starting Ecosystem Maintenance..."

echo "📖 Running The Librarian (Networking all projects)..."
python3 "$LIBRARIAN" --all-projects

echo "🧠 Running Journal Specialist (Deep linking memories)..."
python3 "$JOURNAL_SPECIALIST"

echo "✅ Maintenance complete. Knowledge graph is now fully networked."
