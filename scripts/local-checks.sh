#!/usr/bin/env bash
# Local checks for project-tracker (#7828): the pytest and frontend jobs of
# .github/workflows/tests.yml. The shared pre-push runs this with
# LOCAL_CHECKS_SHA/LOCAL_CHECKS_BASE set (claude-user-config
# hooks/git-local-checks.py); run it by hand from the repo root to run
# everything.
#
# pytest runs in its own environment under ~/.cache/local-checks, never the
# repo's .venv. The frontend jobs run in a throwaway export of dashboard/ from
# the commit, against a clone of the node_modules installed in the main checkout.
# They never install packages: Erik's shell blocks unaudited npm ci/install as
# a supply-chain risk. When the installed packages do not match the commit's
# package-lock.json, the check fails and says how to install deliberately.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
sha="${LOCAL_CHECKS_SHA:-HEAD}"
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

# Every step runs even after a failure, so one run reports every broken gate.
failed=()
step() {
    local name="$1"
    shift
    echo "== $name"
    if ! "$@"; then
        failed+=("$name")
    fi
}

py() { UV_PROJECT_ENVIRONMENT="$venv" "$UV" "$@"; }

if step "sync test dependencies" py sync -q --extra test --python 3.13; then
    step "pytest" py run --no-sync --python 3.13 python -m pytest tests/ -q -p no:cacheprovider
fi

# Copy the installed node_modules into the checkout under test. An APFS clone
# (cp -c) is near-instant and shares disk blocks; a symlink is not enough,
# because Next.js (Turbopack) will not resolve packages outside its root, and
# build caches must not land in the live checkout.
clone_tree() {
    cp -cR "$1" "$2" 2>/dev/null || cp -R "$1" "$2"
}

# True when node_modules ($1) holds what the package-lock.json ($2) pins.
installed_matches_lock() {
    node -e '
        const fs = require("fs"), path = require("path");
        const read = f => JSON.parse(fs.readFileSync(path.resolve(f), "utf8")).packages || {};
        let installed, lock;
        try {
            installed = read(process.argv[1]);
            lock = read(process.argv[2]);
        } catch (err) {
            console.log(`cannot compare installed packages with the lockfile: ${err.message}`);
            process.exit(2);
        }
        const bad = [];
        for (const [key, want] of Object.entries(lock)) {
            if (!key.startsWith("node_modules/")) continue;
            const have = installed[key];
            if (!have) { if (!want.optional) bad.push(`${key} missing`); continue; }
            if (have.version !== want.version) bad.push(`${key} ${have.version} != ${want.version}`);
        }
        for (const key of Object.keys(installed)) if (!(key in lock)) bad.push(`${key} not in lockfile`);
        if (bad.length) { console.log(bad.slice(0, 10).join("\n")); process.exit(1); }
    ' "$1/.package-lock.json" "$2"
}

if changed dashboard/; then
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    git archive "$sha" dashboard | tar -x -C "$tmp"
    frontend="$tmp/dashboard/frontend"
    main_root="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
    modules="$main_root/dashboard/frontend/node_modules"
    want="$(cat "$frontend/.nvmrc")"
    have="$(node --version | sed 's/^v//; s/\..*//')"
    if [ "$have" != "${want%%.*}" ]; then
        echo "WARNING: CI used Node $want (.nvmrc); this machine runs Node $have"
    fi
    if [ ! -f "$modules/.package-lock.json" ]; then
        echo "frontend: no installed packages at $modules"
        echo "  install them deliberately: cd $main_root/dashboard/frontend && command npm ci"
        failed+=("frontend dependencies")
    elif ! installed_matches_lock "$modules" "$frontend/package-lock.json"; then
        echo "frontend: installed packages at $modules do not match this commit's package-lock.json (details above)"
        echo "  review the lockfile change, then install deliberately: cd $main_root/dashboard/frontend && command npm ci"
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
