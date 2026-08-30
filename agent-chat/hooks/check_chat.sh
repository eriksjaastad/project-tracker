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
#   AGENT_CHAT_SENDER  — Fallback sender name. The real address comes from this
#                        session's frozen identity (see agent-chat/identity.py);
#                        this env var is machine-global and cannot distinguish
#                        concurrent floor managers, so it is a fallback only.
#
# Failures are appended to ~/.claude/open-brain/agent_chat_drops.log. This hook
# must never block Claude, but it must not fail silently either: DMs were
# dropped here for five weeks and nothing reported it.

set -euo pipefail

# Source config if available
[[ -f "$HOME/.claude/agent-chat.env" ]] && source "$HOME/.claude/agent-chat.env"

CHAT_URL="${AGENT_CHAT_URL:-https://agent-chat-90116449356.us-central1.run.app}"
API_KEY="${AGENT_CHAT_API_KEY:-}"
CURSOR_FILE="$HOME/.claude/chat_cursor"
DROP_LOG="$HOME/.claude/open-brain/agent_chat_drops.log"

# Record why a poll produced nothing. Best-effort; never fails the hook.
drop() {
    mkdir -p "$(dirname "$DROP_LOG")" 2>/dev/null || return 0
    printf '%s\tcheck_chat\t%s\t%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${2:-}" >> "$DROP_LOG" 2>/dev/null || true
}

# Address resolution order:
#   1. This session's frozen identity, written once at SessionStart.
#   2. AGENT_CHAT_SENDER, for sessions that predate identity binding.
# Never re-derived from the current directory — that is the cwd bug.
SENDER=""
SESSION_ID="${CLAUDE_CODE_SESSION_ID:-}"
IDENTITY_DIR="${AGENT_CHAT_STATE_DIR:-$HOME/.claude/state/agent_chat/identity}"
if [[ -n "$SESSION_ID" && -f "$IDENTITY_DIR/${SESSION_ID}.txt" ]]; then
    SENDER="$(<"$IDENTITY_DIR/${SESSION_ID}.txt")"
    SENDER="${SENDER//[$'\t\r\n ']/}"
fi
[[ -n "$SENDER" ]] || SENDER="${AGENT_CHAT_SENDER:-}"

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
    # Always request the BARE project address: older server deployments match
    # `recipient` by exact string, and the bare form is the common case.
    url+="&for=$(printf '%s' "$SENDER" | sed 's/ /%20/g')"
    # `for_machine` additionally matches `<project>@<machine>`. Servers that
    # predate it ignore the param, so bare addressing keeps working either way.
    if [[ -n "${AGENT_CHAT_MACHINE:-}" ]]; then
        url+="&for_machine=$(printf '%s' "$AGENT_CHAT_MACHINE" | sed 's/ /%20/g')"
    fi
fi
if [[ -n "$since" ]]; then
    url+="&since=$(printf '%s' "$since" | sed 's/ /%20/g; s/:/%3A/g; s/+/%2B/g')"
fi

# Fetch messages
if ! response="$(curl -s -f -H "X-API-Key: $API_KEY" "$url" 2>/dev/null)"; then
    drop "curl_failed" "$CHAT_URL"
    exit 0
fi

# Parse with jq if available
if ! command -v jq &>/dev/null; then
    drop "jq_missing"
    exit 0
fi

count="$(echo "$response" | jq '.messages | length')"
[[ "$count" -gt 0 ]] || exit 0

# Drop only our OWN messages. The recipient clause that used to live here
# discarded every direct message, deferring them to a "router daemon" that was
# never written — so DMs were silently dropped from 2026-07-23 onward. The
# server already scopes the response via ?for=$SENDER, so what arrives is
# broadcasts plus DMs addressed to us; the only thing left to filter is the
# echo of our own traffic.
#
# The self-filter is only correct because identity is now per-session. While
# every agent shared AGENT_CHAT_SENDER=claude-architect it also ate genuine
# peer messages, since under that config they really were "our own".
if [[ -n "$SENDER" ]]; then
    messages="$(echo "$response" | jq --arg s "$SENDER" '[.messages[] | select(.sender != $s)]')"
else
    # No address. The request carried no ?for= filter, so `response` holds
    # every agent's mail — narrow to broadcasts here. Showing it unfiltered
    # would inject other agents' private messages into this session, which is
    # a wider leak than the silence this card set out to fix.
    drop "no_identity" "broadcasts only; run agent-chat/install-hooks.sh"
    messages="$(echo "$response" | jq '[.messages[] | select(.recipient == null or .recipient == "")]')"
fi
count="$(echo "$messages" | jq 'length')"
[[ "$count" -gt 0 ]] || exit 0

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
