#!/bin/bash
# maintenance.sh - Global Ecosystem Health & Networking
# Master script for the ecosystem. Runs DAILY via LaunchAgent.
# Changed from monthly to daily on Jan 16, 2026 (ham-induced insomnia session)

# Use environment variable, fall back to resolving from script location
PROJECT_ROOT="${PROJECTS_ROOT:-.}"
TRACKER_DIR="$PROJECT_ROOT/project-tracker"
LIBRARIAN="$TRACKER_DIR/scripts/discovery/librarian.py"
JOURNAL_SPECIALIST="$TRACKER_DIR/scripts/discovery/journal_specialist.py"
GRAPH_BUILDER="$TRACKER_DIR/scripts/discovery/graph_builder.py"

echo "🤖 Starting Daily Ecosystem Maintenance... $(date)"

# Step 1: Index ai-journal entries first (so new entries are tracked)
JOURNAL_DIR="$PROJECT_ROOT/ai-journal"
JOURNAL_INDEXER="$JOURNAL_DIR/ai_journal_audit_toolkit/build_journal_index.py"
if [ -f "$JOURNAL_INDEXER" ]; then
    echo "📓 Indexing AI Journal entries..."
    cd "$JOURNAL_DIR" && source venv/bin/activate && python3 "$JOURNAL_INDEXER" 2>/dev/null || echo "⚠️ Journal indexer skipped (no venv or config)"
    cd "$PROJECT_ROOT"
fi

# Step 2: Network all projects
echo "📖 Running The Librarian (Networking all projects)..."
python3 "$LIBRARIAN" --all-projects

echo "🧠 Running Journal Specialist (Deep linking memories)..."
python3 "$JOURNAL_SPECIALIST"

echo "🕸️ Rebuilding Knowledge Graph..."
python3 "$GRAPH_BUILDER" --output "$TRACKER_DIR/data/graph.json"

echo "✅ Maintenance complete. Knowledge graph is now fully networked. $(date)"
