#!/bin/bash
# maintenance.sh - Global Ecosystem Health & Networking
# Master script for the ecosystem. Runs WEEKLY via cron (Sundays 5 AM).
# Changed from daily to weekly on Jan 24, 2026 (librarian refactor session)

# Use environment variable, fall back to resolving from script location
PROJECT_ROOT="${PROJECTS_ROOT:-$HOME/projects}"
TRACKER_DIR="$PROJECT_ROOT/project-tracker"
LIBRARIAN="$TRACKER_DIR/scripts/discovery/librarian.py"
JOURNAL_SPECIALIST="$TRACKER_DIR/scripts/discovery/journal_specialist.py"
GRAPH_BUILDER="$TRACKER_DIR/scripts/discovery/graph_builder.py"
UV_RUN="$HOME/.local/bin/uv run"

echo "🤖 Starting Weekly Ecosystem Maintenance... $(date)"

# Step 1: Index ai-journal entries first (so new entries are tracked)
JOURNAL_DIR="$PROJECT_ROOT/ai-journal"
JOURNAL_INDEXER="$JOURNAL_DIR/ai_journal_audit_toolkit/build_journal_index.py"
if [ -f "$JOURNAL_INDEXER" ]; then
    echo "📓 Indexing AI Journal entries..."
    cd "$JOURNAL_DIR" && $UV_RUN "$JOURNAL_INDEXER" 2>/dev/null || echo "⚠️ Journal indexer skipped"
    cd "$PROJECT_ROOT"
fi

# Step 2: Network all projects
echo "📖 Running The Librarian (Networking all projects)..."
$UV_RUN "$LIBRARIAN" --all-projects

echo "🧠 Running Journal Specialist (Deep linking memories)..."
$UV_RUN "$JOURNAL_SPECIALIST"

echo "🕸️ Rebuilding Knowledge Graph..."
$UV_RUN "$GRAPH_BUILDER" --output "$TRACKER_DIR/data/graph.json"

echo "✅ Maintenance complete. Knowledge graph is now fully networked. $(date)"
