#!/usr/bin/env bash
# Local checks for project-tracker (#7828): the pytest and frontend jobs of
# .github/workflows/tests.yml.
#
# The shared pre-push (claude-user-config hooks/git-local-checks.py) runs this
# in a fresh worktree of the pushed commit, with LOCAL_CHECKS_SHA and
# LOCAL_CHECKS_BASE set, and bounds the whole run (LOCAL_CHECKS_TIMEOUT,
# default 30 minutes). Run it by hand from a checkout to check that checkout's
# HEAD; with no base, every check runs.
#
# pytest runs in its own environment under ~/.cache/local-checks, never the
# repo's .venv. The frontend job runs in a throwaway export of dashboard/
# against a clone of installed node_modules (this checkout's, else the main
# checkout's), and never installs packages: Erik's shell blocks unaudited
# npm ci/install as a supply-chain risk. What npm ci would reject fails here
# too: package.json out of step with package-lock.json, or installed packages
# that differ from the lockfile. The message says how to install deliberately.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
sha="$(git rev-parse HEAD)"
if [ -n "${LOCAL_CHECKS_SHA:-}" ] && [ "$sha" != "$(git rev-parse "$LOCAL_CHECKS_SHA^{commit}")" ]; then
    echo "local checks: this checkout is at $sha, not the pushed $LOCAL_CHECKS_SHA" >&2
    exit 2
fi
venv="$HOME/.cache/local-checks/project-tracker/venv"

# True when any given path changed since LOCAL_CHECKS_BASE; always true without
# one. If the diff itself fails, say so and treat every path as changed, so a
# broken diff runs the gated suites instead of silently skipping them.
changed() {
    [ -z "${LOCAL_CHECKS_BASE:-}" ] && return 0
    local paths
    if ! paths="$(git diff --name-only "$LOCAL_CHECKS_BASE" "$sha" -- "$@")"; then
        echo "local checks: cannot diff $LOCAL_CHECKS_BASE..$sha; running the gated checks" >&2
        return 0
    fi
    [ -n "$paths" ]
}

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

py() { UV_PROJECT_ENVIRONMENT="$venv" "$UV" "$@"; }

# Copy installed node_modules into the checkout under test. An APFS clone
# (cp -c) is near-instant and shares disk blocks; a symlink would let build
# caches land in the live checkout.
clone_tree() {
    cp -cR "$1" "$2" 2>/dev/null || cp -R "$1" "$2"
}

# Exit 0 when node_modules ($1) holds what package-lock.json in $2 pins and the
# lockfile agrees with package.json in $2, as npm ci requires; else say why.
installed_matches_lock() {
    node -e '
        const fs = require("fs"), path = require("path");
        const read = f => JSON.parse(fs.readFileSync(path.resolve(f), "utf8"));
        let installed, lock, manifest;
        try {
            installed = read(process.argv[1]).packages || {};
            lock = read(process.argv[2]).packages || {};
            manifest = read(process.argv[3]);
        } catch (err) {
            console.log(`cannot compare installed packages with the lockfile: ${err.message}`);
            process.exit(2);
        }
        const bad = [];
        const sorted = o => JSON.stringify(Object.keys(o || {}).sort().map(k => [k, o[k]]));
        for (const field of ["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"]) {
            if (sorted(manifest[field]) !== sorted((lock[""] || {})[field])) {
                bad.push(`package.json ${field} does not match package-lock.json`);
            }
        }
        for (const [key, want] of Object.entries(lock)) {
            if (!key.startsWith("node_modules/")) continue;
            const have = installed[key];
            if (!have) { if (!want.optional) bad.push(`${key} missing`); continue; }
            if (have.version !== want.version) bad.push(`${key} ${have.version} != ${want.version}`);
        }
        for (const key of Object.keys(installed)) if (!(key in lock)) bad.push(`${key} not in lockfile`);
        if (bad.length) { console.log(bad.slice(0, 10).join("\n")); process.exit(1); }
    ' "$1/.package-lock.json" "$2/package-lock.json" "$2/package.json"
}

if check "sync test dependencies" py sync -q --extra test --python 3.13; then
    step "pytest" py run --no-sync --python 3.13 python -m pytest tests/ -q -p no:cacheprovider
fi

if changed dashboard/ .github/workflows/tests.yml; then
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    git archive "$sha" dashboard | tar -x -C "$tmp"
    frontend="$tmp/dashboard/frontend"
    modules="$(pwd -P)/dashboard/frontend/node_modules"
    if [ ! -f "$modules/.package-lock.json" ]; then
        main_root="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
        modules="$main_root/dashboard/frontend/node_modules"
    fi
    want="$(cat "$frontend/.nvmrc")"
    have="$(node --version | sed 's/^v//; s/\..*//')"
    if [ "$have" != "${want%%.*}" ]; then
        echo "WARNING: CI used Node $want (.nvmrc); this machine runs Node $have"
    fi
    if [ ! -f "$modules/.package-lock.json" ]; then
        echo "frontend: no installed packages at $modules"
        echo "  install them deliberately: cd $(dirname "$modules") && command npm ci"
        failed+=("frontend dependencies")
    elif ! installed_matches_lock "$modules" "$frontend"; then
        echo "frontend: the installed packages or package.json do not match this commit's package-lock.json (details above)"
        echo "  review the change, then install deliberately: cd $(dirname "$modules") && command npm ci"
        failed+=("frontend dependencies")
    else
        clone_tree "$modules" "$frontend/node_modules"
        npm_in() { (cd "$frontend" && npm "$@"); }
        step "frontend lint" npm_in run lint
        step "frontend test" npm_in run test
        step "frontend build" npm_in run build
    fi
fi

if [ "${#failed[@]}" -gt 0 ]; then
    printf 'local checks FAILED: %s\n' "${failed[@]}"
    exit 1
fi
echo "local checks passed"
