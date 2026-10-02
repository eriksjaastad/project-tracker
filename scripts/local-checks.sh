#!/usr/bin/env bash
# Local checks for project-tracker (#7828): the pytest and frontend jobs of
# .github/workflows/tests.yml.
#
# Only the shared runner (claude-user-config hooks/git-local-checks.py) runs
# this: on every push, and by hand with `~/.claude/hooks/git-local-checks.py
# --head`. It checks the commit out in a fresh worktree, sets the
# LOCAL_CHECKS_* variables (with no base, every check runs) and bounds the run.
#
# pytest syncs its own environment inside this throwaway worktree. The frontend
# job runs in a throwaway export of dashboard/ against a clone of the installed
# node_modules (from the checkout the push came from, else the main checkout;
# a symlinked node_modules is resolved first) and never installs packages:
# Erik's shell blocks unaudited npm ci/install as a supply-chain risk. What npm
# ci would reject fails here too (npm's own check decides), as do installed
# packages that differ from the lockfile, with how to install deliberately.
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

# The installed node_modules to clone, as a real directory: the checkout the
# push came from when it has one, else the main checkout. Prints the expected
# path, for the caller to report, when neither has one.
modules_dir() {
    local root rel="dashboard/frontend/node_modules"
    for root in "${LOCAL_CHECKS_ROOT:-}" "$(git worktree list --porcelain | sed -n '1s/^worktree //p')"; do
        if [ -n "$root" ] && [ -f "$root/$rel/.package-lock.json" ]; then
            (cd "$root/$rel" && pwd -P)
            return 0
        fi
    done
    echo "${LOCAL_CHECKS_ROOT:-$(pwd -P)}/$rel"
}

# Copy installed node_modules into the checkout under test. An APFS clone
# (cp -c) is near-instant and shares disk blocks; a symlink would let build
# caches land in the live checkout.
clone_tree() {
    cp -cR "$1" "$2" 2>/dev/null || cp -R "$1" "$2"
}

# Exit 0 when npm ci would accept package.json and package-lock.json in $2 and
# the installed node_modules ($1) holds exactly what npm ci would install from
# them; else say why. Both halves are npm's own logic, not a re-implementation:
# - Acceptance is npm ci with --dry-run, which runs its lockfile validation and
#   returns before node_modules is removed or anything is written. --offline
#   never fetches and --ignore-scripts never runs package code: this is the
#   check, not the install Erik's shell guards against.
# - What npm ci would install is the ideal tree npm's own installer (Arborist,
#   shipped inside npm) builds from those two files, less what its reify step
#   skips on this machine: each optional package that fails npm's engine or
#   platform check (npm-install-checks), with its optional set. Each remaining
#   package must be installed with the same version, source and integrity, and
#   nothing else may be installed. node_modules/.package-lock.json is npm's
#   record of the installed tree.
installed_matches_lock() {
    local npm_root
    if ! (cd "$2" && npm ci --dry-run --offline --ignore-scripts --no-audit --no-fund >/dev/null); then
        echo "npm ci cannot install this commit's package.json and package-lock.json as locked (npm's reason above)"
        return 1
    fi
    if ! npm_root="$(npm root -g)"; then
        echo "cannot find npm's installation (npm root -g failed)"
        return 1
    fi
    node -e '
        const fs = require("fs"), path = require("path");
        const [npmRoot, installedFile, dir] = process.argv.slice(1);
        const identity = e => JSON.stringify([e.version, e.resolved, e.integrity, Boolean(e.link)].map(v => v ?? null));
        (async () => {
            const npmDir = path.join(npmRoot, "npm");
            const npmModule = name => require(path.join(npmDir, "node_modules", name));
            const Arborist = npmModule("@npmcli/arborist");
            const optionalSet = npmModule("@npmcli/arborist/lib/optional-set.js");
            const { checkEngine, checkPlatform } = npmModule("npm-install-checks");
            const npmVersion = require(path.join(npmDir, "package.json")).version;
            const installed = JSON.parse(fs.readFileSync(installedFile, "utf8")).packages || {};
            const ideal = await new Arborist({ path: dir, offline: true, packageLock: true, save: false, audit: false }).buildIdealTree();
            // As reify does: an optional package this machine fails the engine or
            // platform check for is skipped, with everything only it needs.
            const skipped = new Set();
            for (const node of ideal.inventory.values()) {
                if (!node.optional || node.isProjectRoot) continue;
                try {
                    checkEngine(node.package, npmVersion, process.version, false);
                    checkPlatform(node.package, false);
                } catch {
                    for (const gone of optionalSet(node)) skipped.add(gone.location);
                }
            }
            const bad = [], planned = new Set();
            for (const node of ideal.inventory.values()) {
                if (node.isProjectRoot) continue;
                planned.add(node.location);
                const want = identity({ version: node.version, resolved: node.resolved, integrity: node.integrity, link: node.isLink });
                const have = installed[node.location];
                if (!have && skipped.has(node.location)) continue;
                if (!have) bad.push(`${node.location}: npm ci would install it; it is not installed`);
                else if (identity(have) !== want) bad.push(`${node.location}: installed ${identity(have)}, npm ci would install ${want}`);
            }
            for (const key of Object.keys(installed)) if (!planned.has(key)) bad.push(`${key}: installed; npm ci would not install it`);
            if (bad.length) { console.log(bad.slice(0, 10).join("\n")); process.exit(1); }
        })().catch(err => {
            console.log(`cannot compare installed packages with what npm ci would install: ${err.message}`);
            process.exit(2);
        });
    ' "$npm_root" "$1/.package-lock.json" "$2"
}

if check "sync test dependencies" "$UV" sync -q --extra test --python 3.13; then
    step "pytest" "$UV" run --no-sync --python 3.13 python -m pytest tests/ -q -p no:cacheprovider
fi

if changed dashboard/ scripts/local-checks.sh; then
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    git archive "$sha" dashboard | tar -x -C "$tmp"
    frontend="$tmp/dashboard/frontend"
    modules="$(modules_dir)"
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
