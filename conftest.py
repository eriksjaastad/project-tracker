import os
import sys
import tempfile
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

# Keep the destructive-operation audit log out of the developer's real one.
# `_audit_destructive` records every in-process deletion so a future incident
# can be attributed; tests that exercise those code paths were writing
# synthetic pytest-tmp entries straight into it (51 of 51 entries were test
# chaff), burying real evidence in the file that exists to preserve it.
# Session-scoped so a single run's records stay together if anyone inspects them.
_TEST_DESTRUCTIVE_LOG = (
    Path(tempfile.gettempdir()) / f"pt-destructive-tests-{os.getpid()}.log"
)
os.environ.setdefault("PT_DESTRUCTIVE_LOG_PATH", str(_TEST_DESTRUCTIVE_LOG))
