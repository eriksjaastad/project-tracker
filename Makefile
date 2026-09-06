# project-tracker — local convenience targets (#6065).
#
# Every target that touches secrets routes through `doppler run --` so a
# fresh shell with no env exported just works. `doppler.yaml` at the repo
# root pins `project-tracker/dev`. See CLAUDE.md → "Authorization — Check
# Doppler First" for the full token list and what each one is for.
#
# Two project-tracker-specific wrinkles the reference pattern does not have:
#
#   1. `./pt` wraps ITSELF in `doppler run` (see the launcher, lines 24-58).
#      Targets that shell out to `./pt` therefore carry NO `doppler run --`
#      prefix — double-wrapping is the bug, not the fix.
#   2. Not every secret lives in `project-tracker/dev`. The alert digest and
#      the Grok card factory read from `synth-insight-labs/prd`; the Turso
#      dump reads from `openclaw/dev`. Those targets pass explicit
#      `--project/--config` rather than relying on `doppler.yaml`.
#
# Targets are tab-indented (Makefile-required) and intentionally trivial —
# they exist as muscle-memory shortcuts, not abstractions over the
# underlying commands. If a target stops working, run the body directly.
#
# PYTHON resolves to the repo venv, and finds it from a git worktree too.
#
# A worktree has no venv/ of its own, so a bare `venv/bin/python` simply did
# not exist there and every target failed on sight. The override was
# documented, but three separate agents still tripped over it in one day --
# and worktrees are the sanctioned way to do risky work (editing
# ~/.claude/hooks/ in place blocks every concurrent agent's Bash calls the
# moment the file is briefly unparseable). A tax on the safe workflow gets
# paid in people not using it.
#
# --git-common-dir points at the MAIN checkout's .git even from a worktree (a
# worktree's own .git is a text pointer file, so --git-dir would give the wrong
# answer), and its parent is the main worktree root. Outside a repo both lookups
# miss and PYTHON falls back to python3, which fails loudly on a missing import.
#
# Resolved entirely inside one $(shell), NOT with $(abspath)/$(patsubst): those
# operate on whitespace-separated word lists, so a checkout path containing a
# space is shredded into fragments, the venv lookup misses, and make silently
# falls back to python3 -- breaking the very worktree case this exists to fix,
# with no error. Shell quoting handles spaces; Make's word functions cannot.
# Every use site quotes "$(PYTHON)" for the same reason.
PYTHON ?= $(shell \
	if [ -x venv/bin/python ]; then printf '%s' venv/bin/python; \
	else \
	  common=$$(git rev-parse --git-common-dir 2>/dev/null) && \
	  root=$$(cd "$$common/.." 2>/dev/null && pwd) && \
	  [ -x "$$root/venv/bin/python" ] && printf '%s' "$$root/venv/bin/python" \
	  || printf '%s' python3; \
	fi)
HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: help test test-fast dashboard dashboard-restart dashboard-stop \
        dashboard-health digest digest-dry backup backup-status \
        turso-sync turso-sync-dry doppler-check

help:  ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

test:  ## Full pytest suite (no secrets needed — tests run offline).
	"$(PYTHON)" -m pytest tests/ -q

test-fast:  ## Same suite, stop at the first failure.
	"$(PYTHON)" -m pytest tests/ -q -x --no-header

dashboard:  ## Launch the dashboard in the foreground (doppler-wrapped by the script).
	./scripts/launch-dashboard.sh

dashboard-restart:  ## Kill and relaunch the dashboard in the background on $(HOST):$(PORT).
	-pkill -f "uvicorn dashboard.app"
	sleep 1
	doppler run -- "$(PYTHON)" -m uvicorn dashboard.app:app --host $(HOST) --port $(PORT) &

dashboard-stop:  ## Stop the running dashboard.
	-pkill -f "uvicorn dashboard.app"

dashboard-health:  ## Curl the dashboard health endpoint.
	@curl -sf http://$(HOST):$(PORT)/api/health || \
	  { echo "dashboard not responding on $(HOST):$(PORT)"; exit 1; }

digest-dry:  ## Render the portfolio alert digest to stdout without sending.
	./scripts/alert-digest.sh --dry-run

digest:  ## Send the portfolio alert digest email (synth-insight-labs/prd secrets).
	./scripts/alert-digest.sh

backup:  ## Atomic point-in-time snapshot of tracker.db (no secrets needed).
	./scripts/backup-db.sh

backup-status:  ## Backup + off-machine backup health (./pt self-wraps doppler).
	./pt backup status

turso-sync-dry:  ## Show what a Turso → local tracker.db dump would write.
	doppler run -p openclaw -c dev -- \
	  $(HOME)/.local/bin/uv run scripts/turso_to_local.py --dry-run

turso-sync:  ## Dump Turso → local tracker.db (backs up the existing local DB first).
	doppler run -p openclaw -c dev -- \
	  $(HOME)/.local/bin/uv run scripts/turso_to_local.py

doppler-check:  ## Verify Doppler auth by listing secret NAMES (never values).
	doppler secrets --project project-tracker --config dev --only-names
