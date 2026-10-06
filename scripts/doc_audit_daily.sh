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

# Model calls go through OpenRouter; the key comes from Doppler (#7973).
# doppler and uv come from PATH; under launchd, set PATH in the plist.
for tool in doppler uv; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "[$(date +%H:%M:%S)] FAILED: $tool not found on PATH ($PATH)" >> "$LOG_FILE"
        echo "doc audit: $tool not found on PATH (log: $LOG_FILE)" >&2
        exit 1
    fi
done

run_step() {
    local label="$1"; shift
    echo "[$(date +%H:%M:%S)] $label..." >> "$LOG_FILE"
    if ! doppler run --project project-tracker --config dev -- \
            uv run scripts/doc_audit_v2.py "$@" >> "$LOG_FILE" 2>&1; then
        echo "[$(date +%H:%M:%S)] FAILED: $label (see output above)" >> "$LOG_FILE"
        FAILED_STEPS+=("$label")
    fi
}

# Each step still runs after an earlier failure (later steps skip work that is
# already done), but any failure makes the whole run exit nonzero.
# atlas --compile is not run here (unchanged from before #7973); keeping the
# cached batches, atlas and clusters fresh is #7975.
FAILED_STEPS=()
run_step "Rebuilding Semantic Atlas" atlas --build --auto
run_step "Updating embeddings" embeddings --generate
run_step "Finding similarity clusters" embeddings --cluster
run_step "Running audit pass" audit --auto
run_step "Generating status report" status

echo "[$(date +%H:%M:%S)] Daily run complete." >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Cleanup old logs (keep 30 days)
find "$PROJECT_DIR/logs" -name "doc_audit_*.log" -mtime +30 -delete 2>/dev/null || true

if [ "${#FAILED_STEPS[@]}" -gt 0 ]; then
    failed_list=""
    for step in "${FAILED_STEPS[@]}"; do failed_list="${failed_list:+$failed_list; }$step"; done
    echo "doc audit: ${#FAILED_STEPS[@]} step(s) failed: $failed_list (log: $LOG_FILE)" >&2
    exit 1
fi
