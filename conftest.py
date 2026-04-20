import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so that `scripts` and `dashboard`
# are importable in any environment (including sandboxed uv run on the Mini).
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Phase 2.1a: the pt root callback emits a stderr warning when the DB
# has unapplied migrations. Humans see it; CliRunner merges it into
# ``result.output`` and breaks JSON-parsing tests that invoke real pt
# subcommands against the live ``data/tracker.db`` (which hasn't had
# 002 applied). Suppress by default for tests; tests that specifically
# want to exercise the warning delete this env var per-test.
os.environ.setdefault("PT_SUPPRESS_MIGRATION_WARNING", "1")
