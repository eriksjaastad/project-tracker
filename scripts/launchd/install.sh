#!/bin/bash
#
# Install / uninstall the Phase 2 sync LaunchAgents on the current machine.
#
# The .plist.in templates in this directory hold @PT_HOME@, @UV_BIN@,
# and @PEER_HOST@ placeholders instead of hardcoded paths. This script
# substitutes them from the local environment and writes rendered
# .plist files to ~/Library/LaunchAgents/ before loading each with
# launchctl.
#
# Usage:
#   scripts/launchd/install.sh install   <peer-host>
#   scripts/launchd/install.sh uninstall
#   scripts/launchd/install.sh status
#   scripts/launchd/install.sh --help
#
# Example (laptop):    scripts/launchd/install.sh install eriks-mac-mini
# Example (Mac Mini):  scripts/launchd/install.sh install macbook-pro
#
# Each machine's <peer-host> is the OTHER machine's tailnet hostname
# (MagicDNS resolves plain names). See ~/projects/CLAUDE.md for the
# Tailscale CLI reference and tailnet overview.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PT_HOME="$(cd "$SCRIPT_DIR/../.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

AGENTS=(com.pt.tailscale-up com.pt.sync-daemon)

usage() {
    grep '^#' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

find_uv() {
    # Prefer the per-user install location, fall back to whatever's on PATH.
    if [[ -x "$HOME/.local/bin/uv" ]]; then
        echo "$HOME/.local/bin/uv"
        return
    fi
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return
    fi
    echo "install.sh: cannot find 'uv' binary — install uv first." >&2
    exit 2
}

render_and_install() {
    local peer_host="$1"
    local uv_bin
    uv_bin="$(find_uv)"

    mkdir -p "$LAUNCH_AGENTS_DIR" "$PT_HOME/logs"

    for agent in "${AGENTS[@]}"; do
        local src="$SCRIPT_DIR/${agent}.plist.in"
        local dst="$LAUNCH_AGENTS_DIR/${agent}.plist"
        if [[ ! -f "$src" ]]; then
            echo "install.sh: template missing: $src" >&2
            exit 2
        fi
        # sed with | delimiter so paths with slashes don't need escaping.
        sed \
            -e "s|@PT_HOME@|$PT_HOME|g" \
            -e "s|@UV_BIN@|$uv_bin|g" \
            -e "s|@PEER_HOST@|$peer_host|g" \
            "$src" > "$dst"

        # Fail loudly if any placeholder leaked through (catches typos
        # in the template or in this script). Use grep -E (ERE) so `+`
        # means "one or more" on BSD grep too; BSD's BRE would treat
        # `\+` as a literal backslash-plus and the guard would silently
        # pass on macOS.
        if grep -qE '@[A-Z_]+@' "$dst"; then
            echo "install.sh: unsubstituted placeholder in $dst:" >&2
            grep -nE '@[A-Z_]+@' "$dst" >&2
            exit 2
        fi

        # Reload on top of any prior install (idempotent).
        launchctl unload "$dst" 2>/dev/null || true
        launchctl load "$dst"
        echo "loaded: $dst"
    done

    echo ""
    echo "Done. Sync daemon will run on next round (ThrottleInterval=30s)."
    echo "Check status:   scripts/launchd/install.sh status"
    echo "Tail logs:      tail -f $PT_HOME/logs/sync-daemon.err"
}

uninstall_agents() {
    for agent in "${AGENTS[@]}"; do
        local dst="$LAUNCH_AGENTS_DIR/${agent}.plist"
        if [[ -f "$dst" ]]; then
            launchctl unload "$dst" 2>/dev/null || true
            rm -f "$dst"
            echo "removed: $dst"
        else
            echo "skipped (not installed): $dst"
        fi
    done
}

status_agents() {
    for agent in "${AGENTS[@]}"; do
        local dst="$LAUNCH_AGENTS_DIR/${agent}.plist"
        if [[ -f "$dst" ]]; then
            echo "installed: $dst"
            launchctl list | awk -v label="$agent" '$3 == label { print "  launchctl: pid="$1" exit="$2" label="$3 }'
        else
            echo "not installed: $dst"
        fi
    done
}

main() {
    local cmd="${1:-}"
    case "$cmd" in
        install)
            local peer="${2:-}"
            if [[ -z "$peer" ]]; then
                echo "install: <peer-host> argument required" >&2
                echo "Usage: $0 install <peer-host>" >&2
                exit 2
            fi
            render_and_install "$peer"
            ;;
        uninstall)
            uninstall_agents
            ;;
        status)
            status_agents
            ;;
        -h|--help|help|"")
            usage
            ;;
        *)
            echo "unknown command: $cmd" >&2
            usage
            ;;
    esac
}

main "$@"
