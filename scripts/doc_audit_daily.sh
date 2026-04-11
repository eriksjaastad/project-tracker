#!/bin/bash
# doc_audit_daily.sh - Daily documentation maintenance
# Run by launchd at 3 AM

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/doc_audit_$(date +%Y%m%d).log"

# Ensure log directory exists
mkdir -p "$PROJECT_DIR/logs"

echo "=== Doc Audit Daily Run: $(date) ===" >> "$LOG_FILE"

cd "$PROJECT_DIR"

# Activate virtual environment
source venv/bin/activate

# 1. Rebuild atlas to catch any new/changed documents
echo "[$(date +%H:%M:%S)] Rebuilding Semantic Atlas..." >> "$LOG_FILE"
python scripts/doc_audit_v2.py atlas --build --auto >> "$LOG_FILE" 2>&1 || true

# 2. Regenerate embeddings
echo "[$(date +%H:%M:%S)] Updating embeddings..." >> "$LOG_FILE"
python scripts/doc_audit_v2.py embeddings --generate >> "$LOG_FILE" 2>&1 || true

# 3. Find new clusters
echo "[$(date +%H:%M:%S)] Finding similarity clusters..." >> "$LOG_FILE"
python scripts/doc_audit_v2.py embeddings --cluster >> "$LOG_FILE" 2>&1 || true

# 4. Run audit on all projects (will skip already-audited ones)
echo "[$(date +%H:%M:%S)] Running audit pass..." >> "$LOG_FILE"
python scripts/doc_audit_v2.py audit --auto >> "$LOG_FILE" 2>&1 || true

# 5. Generate status report
echo "[$(date +%H:%M:%S)] Generating status report..." >> "$LOG_FILE"
python scripts/doc_audit_v2.py status >> "$LOG_FILE" 2>&1

echo "[$(date +%H:%M:%S)] Daily run complete." >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Cleanup old logs (keep 30 days)
find "$PROJECT_DIR/logs" -name "doc_audit_*.log" -mtime +30 -delete 2>/dev/null || true
