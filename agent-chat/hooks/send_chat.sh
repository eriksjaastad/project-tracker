#!/usr/bin/env bash
#
# send_chat.sh — Send a message to Agent Chat from the command line.
#
# Usage: send_chat.sh <sender> <message>
# Example: send_chat.sh claude-architect "SIW email infrastructure is live."
#
# Environment:
#   AGENT_CHAT_URL     — API base URL (default: https://chat.synthinsightlabs.com)
#   AGENT_CHAT_API_KEY — API key for authentication

set -euo pipefail

CHAT_URL="${AGENT_CHAT_URL:-https://chat.synthinsightlabs.com}"
API_KEY="${AGENT_CHAT_API_KEY:-}"

if [[ $# -lt 2 ]]; then
    echo "Usage: send_chat.sh <sender> <message>" >&2
    exit 1
fi

sender="$1"
shift
body="$*"

curl -s -f -X POST "$CHAT_URL/send" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "$(jq -n --arg s "$sender" --arg b "$body" '{sender: $s, body: $b, priority: "normal"}')" \
    >/dev/null

echo "Sent."
