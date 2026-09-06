#!/usr/bin/env bash
#
# check_chat.sh — Claude Code PreToolUse hook
#
# Polls the hosted Agent Chat API for new messages.
# Outputs new messages to stdout so Claude Code injects them into context.
# Stores the last-seen timestamp in ~/.claude/chat_cursor.<address> to avoid
# re-reading. The cursor is PER ADDRESS: several floor managers share one
# laptop, and a single shared cursor let one session's poll skip past mail
# addressed to another.
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
LEGACY_CURSOR_FILE="$HOME/.claude/chat_cursor"
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

# The cursor is scoped to the address we poll for, because the response is
# too: the request carries `?for=$SENDER`, so advancing one machine-global
# file marks mail as seen that this poll could never have returned. That is
# not hypothetical — the shared cursor sat at 2026-08-30T17:36:50, the exact
# timestamp of board message #94, a DM addressed to `ai-memory`, parked there
# by a `for=project-tracker` poll that never saw it. The addressee never got
# the message.
#
# Sanitize before the address reaches a path: it can contain `@`
# (`project-tracker@laptop`) and, if it is ever mis-derived, a separator.
#
# Percent-encode every character outside [A-Za-z0-9_-] rather than folding
# them to `_`. Folding is lossy — `a/b` and `a_b` would land on one file and
# steal each other's position, which is the bug this card exists to kill,
# re-introduced at a smaller scale. Encoding is injective (`%` is itself
# encoded), so distinct addresses cannot collide, and it needs no hash and no
# external binary in a hook that already has to degrade gracefully when `jq`
# is missing. It also leaves the address readable in the filename. No `/` and
# no `.` can appear in the output, so traversal and dot-runs are impossible by
# construction rather than by patching them out afterwards.
#
# The exact guarantee: injective over addresses of 64 bytes or fewer. Longer
# ones are truncated BEFORE encoding, so two addresses sharing a 64-byte
# prefix would still share a cursor. An address is `<project>` or
# `<project>@<machine>` — nothing close to the bound — and the bound is what
# keeps the filename inside NAME_MAX at the 3x worst case, so it stays.
#
# `LC_ALL=C` is not decoration. Under a UTF-8 locale bash matches `[A-Za-z]`
# by collation, so `ü` passes the allowlist untouched and the safe set is
# whatever the ambient locale says it is. C forces the loop to walk bytes
# against a fixed ASCII set, so the output is the same everywhere.
cursor_slug() {
    local LC_ALL=C
    local raw="${1:0:64}" out="" i ch code enc
    for (( i = 0; i < ${#raw}; i++ )); do
        ch="${raw:i:1}"
        case "$ch" in
            [A-Za-z0-9_-]) out+="$ch" ;;
            *)  printf -v code '%d' "'$ch"
                printf -v enc '%%%02X' "$(( code & 0xFF ))"
                out+="$enc" ;;
        esac
    done
    printf '%s' "$out"
}

# A seed is only worth taking if it is actually a position. An empty legacy
# file (a stray `touch`, a create that never got populated) would seed an
# empty cursor and the next poll would go out with no `since` at all — the
# unbounded replay the migration exists to prevent. A corrupt one is worse:
# `since=<garbage>` reaches the API, which may reject it or return nothing,
# turning a delivery bug into a silent one. Neither is trusted.
#
# The pattern is anchored at BOTH ends. Matching only a prefix let
# `2026-08-30T17:36:50 garbage` through — and paired with a strip that deleted
# interior whitespace it did worse than pass: it MANUFACTURED
# `2026-08-30T17:36:50garbage` out of a line that was never valid, then sent
# it as `since=`. Validate the whole line; never edit a line into validity.
#
# The shapes accepted are the two the server actually emits: SQLite's
# `strftime('%Y-%m-%dT%H:%M:%fZ')` (fractional seconds, `Z`) and Postgres
# TIMESTAMPTZ through `.isoformat()` (microseconds, `+00:00`) — see
# agent-chat/server/db.py. Anything else is not a position this API issued.
looks_like_cursor() {
    local LC_ALL=C
    local re='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}(:?[0-9]{2})?)?$'
    [[ "$1" =~ $re ]]
}

# Trim the ends only. Removing whitespace from the middle of a line can turn
# an invalid seed into a valid-looking one, which is how the prefix bug above
# got its teeth.
trim_ends() {
    local LC_ALL=C s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

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

# Resolve this address's cursor. Deferred until after the key check and the
# throttle so a skipped poll leaves no trace on disk.
if [[ -n "$SENDER" ]]; then
    CURSOR_FILE="$HOME/.claude/chat_cursor.$(cursor_slug "$SENDER")"
    # One-time migration off the shared cursor. Without the seed the first
    # per-address poll would carry no `since` and replay the whole board into
    # this session's context. Only a legacy file that is non-empty AND holds a
    # timestamp is trusted; anything else is ignored and this address starts
    # clean rather than migrating garbage forward.
    if [[ ! -f "$CURSOR_FILE" && -s "$LEGACY_CURSOR_FILE" ]]; then
        legacy_seed=""
        IFS= read -r legacy_seed < "$LEGACY_CURSOR_FILE" 2>/dev/null || true
        legacy_seed="$(trim_ends "$legacy_seed")"
        if looks_like_cursor "$legacy_seed"; then
            { printf '%s\n' "$legacy_seed" > "$CURSOR_FILE.tmp" \
                && mv "$CURSOR_FILE.tmp" "$CURSOR_FILE"; } 2>/dev/null || true
        fi
    fi
else
    # No address means no `?for=` filter, so the legacy global cursor still
    # describes exactly what was fetched.
    CURSOR_FILE="$LEGACY_CURSOR_FILE"
fi

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
    # The qualifier is cached at SessionStart; nothing exports
    # AGENT_CHAT_MACHINE by default, so reading only the env var meant
    # qualified DMs were never requested and never arrived.
    MACHINE="${AGENT_CHAT_MACHINE:-}"
    if [[ -z "$MACHINE" && -f "$IDENTITY_DIR/machine.txt" ]]; then
        MACHINE="$(<"$IDENTITY_DIR/machine.txt")"
        MACHINE="${MACHINE//[$'\t\r\n ']/}"
    fi
    if [[ -n "$MACHINE" ]]; then
        url+="&for_machine=$(printf '%s' "$MACHINE" | sed 's/ /%20/g')"
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
