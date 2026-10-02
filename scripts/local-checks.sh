#!/usr/bin/env bash
# Local checks for project-tracker (#7828): the pytest and frontend jobs of
# .github/workflows/tests.yml.
#
# Only the shared runner (claude-user-config hooks/git-local-checks.py) runs
# this: on every push, and by hand with `~/.claude/hooks/git-local-checks.py
# --head`. It checks the commit out in a fresh worktree, sets the
# LOCAL_CHECKS_* variables and bounds the run. Every check runs on every push.
#
# pytest syncs its own environment inside this throwaway worktree. The frontend
# job runs in a throwaway export of dashboard/, with its packages installed by
# npm ci from the local npm cache only (see npm_ci_offline): exactly the
# locked packages, no network, no install scripts.
set -euo pipefail

if [ "${LOCAL_CHECKS_CLEAN:-}" != 1 ]; then
    echo "local checks: run them with the shared runner, which checks HEAD in a fresh worktree:" >&2
    echo "  ~/.claude/hooks/git-local-checks.py --head" >&2
    exit 2
fi
cd "$(git rev-parse --show-toplevel)"
sha="$(git rev-parse HEAD)"
if [ "$sha" != "$(git rev-parse "${LOCAL_CHECKS_SHA}^{commit}")" ]; then
    echo "local checks: this checkout is at $sha, not $LOCAL_CHECKS_SHA" >&2
    exit 2
fi
echo "local checks: $sha in $(pwd -P)"

UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

# Run one named check, record a failure, and return its status.
failed=()
check() {
    local name="$1" status=0
    shift
    echo "== $name"
    "$@" || status=$?
    if [ "$status" -ne 0 ]; then
        failed+=("$name")
    fi
    return "$status"
}
# A check nothing else depends on: its failure is recorded, and the run goes on.
step() { check "$@" || true; }

# npm_ci_offline DIR: install exactly what DIR's package-lock.json pins, as
# CI's npm ci did, but only from the local npm cache. --offline never touches
# the network: every tarball comes from the cache, checked against the
# lockfile's integrity hash. --ignore-scripts runs no package code at install.
# That keeps the intent of Erik's npm guard (no fresh downloads, no
# install-time package code) while testing exactly the locked packages, not a
# developer's node_modules. A tarball missing from the cache fails the check
# with its name; there is no network fallback. Decided by the Architect for
# Erik, 2026-10-02 (agent-runtime-config #7828).
npm_ci_offline() {
    local out status=0 missing
    out="$(cd "$1" && npm ci --offline --ignore-scripts --no-audit --no-fund 2>&1)" || status=$?
    if [ "$status" -eq 0 ]; then
        return 0
    fi
    printf '%s\n' "$out" | tail -n 25
    missing="$(printf '%s\n' "$out" \
        | sed -n 's|.*request to https\{0,1\}://[^/]*/\([^ ]*\) failed.*|\1|p' \
        | sed -e 's|%2[fF]|/|g' -e 's|^\(.*\)/-/.*-\([0-9][^/]*\)\.tgz$|\1@\2|' | sort -u)"
    if [ -n "$missing" ]; then
        echo "not in the local npm cache (no network fallback):"
        printf '  %s\n' $missing
        echo "  fetch them deliberately, after review, in a real checkout: command npm ci"
    fi
    return "$status"
}

if check "sync test dependencies" "$UV" sync -q --extra test --python 3.13; then
    step "pytest" "$UV" run --no-sync --python 3.13 python -m pytest tests/ -q -p no:cacheprovider
fi

# The frontend job runs on every push, as tests.yml ran it on every PR.
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git archive "$sha" dashboard | tar -x -C "$tmp"
frontend="$tmp/dashboard/frontend"
want="$(cat "$frontend/.nvmrc")"
have="$(node --version | sed 's/^v//; s/\..*//')"
if [ "$have" != "${want%%.*}" ]; then
    echo "WARNING: CI used Node $want (.nvmrc); this machine runs Node $have"
fi
if check "frontend dependencies (npm ci, offline, no scripts)" npm_ci_offline "$frontend"; then
    npm_in() { (cd "$frontend" && npm "$@"); }
    step "frontend lint" npm_in run lint
    step "frontend test" npm_in run test
    step "frontend build" npm_in run build
fi

if [ "${#failed[@]}" -gt 0 ]; then
    printf 'local checks FAILED: %s\n' "${failed[@]}"
    exit 1
fi
echo "local checks passed"
