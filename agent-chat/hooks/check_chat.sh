#!/usr/bin/env bash
#
# check_chat.sh — Claude Code PreToolUse hook
#
# Polls the hosted Agent Chat API for new messages.
# Outputs new messages to stdout so Claude Code injects them into context.
# Stores the last-seen timestamp in ~/.claude/chat_cursor to avoid re-reading.
#
# Environment:
#   AGENT_CHAT_URL     — API base URL (default: https://chat.synthinsightlabs.com)
#   AGENT_CHAT_API_KEY — API key for authentication
#   AGENT_CHAT_SENDER  — This agent's sender name (for filtering out own messages)

set -euo pipefail

# Source config if available
[[ -f "$HOME/.claude/agent-chat.env" ]] && source "$HOME/.claude/agent-chat.env"

CHAT_URL="${AGENT_CHAT_URL:-https://agent-chat-90116449356.us-central1.run.app}"
API_KEY="${AGENT_CHAT_API_KEY:-}"
SENDER="${AGENT_CHAT_SENDER:-}"
CURSOR_FILE="$HOME/.claude/chat_cursor"

# No API key = skip
[[ -n "$API_KEY" ]] || exit 0

# Throttle: only check every 30 seconds
THROTTLE_FILE="$HOME/.claude/chat_throttle"
if [[ -f "$THROTTLE_FILE" ]]; then
    last_check=$(cat "$THROTTLE_FILE")
    now=$(date +%s)
    if (( now - last_check < 30 )); then
        exit 0
    fi
fi
date +%s > "$THROTTLE_FILE.tmp" && mv "$THROTTLE_FILE.tmp" "$THROTTLE_FILE"

# Read last cursor
since=""
if [[ -f "$CURSOR_FILE" ]]; then
    since="$(cat "$CURSOR_FILE")"
fi

# Build URL — filter for messages visible to this agent
url="$CHAT_URL/messages?limit=20"
if [[ -n "$SENDER" ]]; then
    url+="&for=$(printf '%s' "$SENDER" | sed 's/ /%20/g')"
fi
if [[ -n "$since" ]]; then
    url+="&since=$(printf '%s' "$since" | sed 's/ /%20/g; s/:/%3A/g; s/+/%2B/g')"
fi

# Fetch messages
response="$(curl -s -f -H "X-API-Key: $API_KEY" "$url" 2>/dev/null)" || exit 0

# Parse with jq if available
if ! command -v jq &>/dev/null; then
    exit 0
fi

count="$(echo "$response" | jq '.messages | length')"
[[ "$count" -gt 0 ]] || exit 0

# Filter out own messages if sender is set
if [[ -n "$SENDER" ]]; then
    messages="$(echo "$response" | jq --arg s "$SENDER" '[.messages[] | select(.sender != $s)]')"
    count="$(echo "$messages" | jq 'length')"
    [[ "$count" -gt 0 ]] || exit 0
else
    messages="$(echo "$response" | jq '.messages')"
fi

# Update cursor to latest timestamp
last_ts="$(echo "$response" | jq -r '.messages[-1].ts')"
echo "$last_ts" > "$CURSOR_FILE.tmp" && mv "$CURSOR_FILE.tmp" "$CURSOR_FILE"

# Build output
output="=== AGENT CHAT: $count new message(s) ==="
output+=$'\n'

while IFS= read -r line; do
    sender="$(echo "$line" | jq -r '.sender')"
    body="$(echo "$line" | jq -r '.body')"
    ts="$(echo "$line" | jq -r '.ts')"
    priority="$(echo "$line" | jq -r '.priority')"
    recipient="$(echo "$line" | jq -r '.recipient // empty')"
    reply_to="$(echo "$line" | jq -r '.reply_to // empty')"
    msg_id="$(echo "$line" | jq -r '.id')"
    prefix=""
    [[ "$priority" == "urgent" ]] && prefix="[URGENT] "
    [[ "$priority" == "high" ]] && prefix="[HIGH] "
    header="${prefix}${sender}"
    [[ -n "$recipient" ]] && header+=" @${recipient}"
    [[ -n "$reply_to" ]] && header+=" (reply to #${reply_to})"
    output+=$'\n'"--- ${header} (#${msg_id}, ${ts}) ---"$'\n'
    output+="$body"
    output+=$'\n'
done < <(echo "$messages" | jq -c '.[]')

# Output Claude Code hook JSON
jq -n --arg ctx "$output" \
    '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":$ctx}}'
