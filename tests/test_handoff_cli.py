"""Tests for `pt handoff` command group (Phase D: structured unfinished-work records).

Schema version: pt.handoff.v1

Uses CliRunner (Click 8.3+, no mix_stderr kwarg).
Each test sets PT_DB_PATH to a tmp_path-based DB and runs the migration
(via _ensure_handoffs_table, which is called inside every command) so the
schema is always up to date before assertions.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pt import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracker_db(path: Path) -> None:
    """Create a minimal tracker DB with a tasks row for card_id=6151."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                project_id TEXT NOT NULL,
                priority TEXT,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute(
            "INSERT INTO tasks (id, text, status, project_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (6151, "Phase D handoff test card", "In Progress", "project-tracker",
             "2026-05-05T00:00:00Z", "2026-05-05T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


_COMMON_ENV = {
    "PT_SUPPRESS_MIGRATION_WARNING": "1",
    "PT_NO_BANNER": "1",
    "PT_SKIP_DOPPLER": "1",
}

_REQUIRED_CREATE_ARGS = [
    "--intent", "Add pt handoff command for unfinished-work records",
    "--status", "Migration written, command scaffolded, tests pending",
    "--next", "pytest tests/test_handoff_cli.py -v",
    "--guidance", "Keep all staged files; discard nothing",
]


def _invoke(tmp_path: Path, args: list[str]):
    db_path = tmp_path / "tracker.db"
    _make_tracker_db(db_path)
    runner = CliRunner()
    return runner.invoke(
        cli,
        args,
        env={**_COMMON_ENV, "PT_DB_PATH": str(db_path)},
        catch_exceptions=False,
    )


def _invoke_on_db(db_path: Path, args: list[str]):
    """Invoke against an already-prepared DB (for multi-step tests)."""
    runner = CliRunner()
    return runner.invoke(
        cli,
        args,
        env={**_COMMON_ENV, "PT_DB_PATH": str(db_path)},
        catch_exceptions=False,
    )


# ---------------------------------------------------------------------------
# create — happy path
# ---------------------------------------------------------------------------

def test_handoff_create_unfinished_json(tmp_path: Path) -> None:
    """create with --type unfinished emits pt.handoff.v1 JSON."""
    result = _invoke(
        tmp_path,
        ["handoff", "create", "6151", "--json", "--type", "unfinished"] + _REQUIRED_CREATE_ARGS,
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "pt.handoff.v1"
    assert payload["ok"] is True
    assert payload["command"] == "handoff.create"
    rec = payload["result"]
    assert rec["card_id"] == 6151
    assert rec["record_type"] == "unfinished"
    assert rec["project"] == "project-tracker"
    assert rec["resolved_at"] is None
    assert isinstance(rec["file_list"], list)


def test_handoff_create_persists_record(tmp_path: Path) -> None:
    """create inserts a row visible via handoff list."""
    db_path = tmp_path / "tracker.db"
    _make_tracker_db(db_path)
    _invoke_on_db(db_path, ["handoff", "create", "6151"] + _REQUIRED_CREATE_ARGS)
    result = _invoke_on_db(db_path, ["handoff", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["result"]) == 1
    assert payload["result"][0]["card_id"] == 6151


def test_handoff_create_with_auto_files(tmp_path: Path) -> None:
    """--auto-files runs git status; result is a list (may be empty in test env)."""
    result = _invoke(
        tmp_path,
        ["handoff", "create", "6151", "--json", "--auto-files"] + _REQUIRED_CREATE_ARGS,
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload["result"]["file_list"], list)


def test_handoff_create_with_explicit_files(tmp_path: Path) -> None:
    """--files accepts a JSON array and round-trips it."""
    files_json = json.dumps([
        {"path": "scripts/pt.py", "classification": "dirty"},
        {"path": "tests/test_handoff_cli.py", "classification": "untracked"},
    ])
    result = _invoke(
        tmp_path,
        ["handoff", "create", "6151", "--json", "--files", files_json] + _REQUIRED_CREATE_ARGS,
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    fl = payload["result"]["file_list"]
    assert len(fl) == 2
    assert fl[0]["path"] == "scripts/pt.py"
    assert fl[1]["classification"] == "untracked"


# ---------------------------------------------------------------------------
# create — pr_exempt happy path
# ---------------------------------------------------------------------------

def test_handoff_create_pr_exempt_json(tmp_path: Path) -> None:
    """create with --type pr_exempt emits correct JSON envelope."""
    result = _invoke(
        tmp_path,
        [
            "handoff", "create", "6151",
            "--json",
            "--type", "pr_exempt",
            "--reason", "Changes reverted by rebase; nothing to ship",
            "--disposition", "reverted",
            "--approver", "eriksjaastad",
        ] + _REQUIRED_CREATE_ARGS,
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    rec = payload["result"]
    assert rec["record_type"] == "pr_exempt"
    assert rec["pr_exempt_reason"] == "Changes reverted by rebase; nothing to ship"
    assert rec["pr_exempt_disposition"] == "reverted"
    assert rec["pr_exempt_approver"] == "eriksjaastad"


# ---------------------------------------------------------------------------
# create — validation errors
# ---------------------------------------------------------------------------

def test_handoff_create_pr_exempt_missing_reason(tmp_path: Path) -> None:
    """pr_exempt without --reason exits with EXIT_VALIDATION=2."""
    result = _invoke(
        tmp_path,
        [
            "handoff", "create", "6151",
            "--json",
            "--type", "pr_exempt",
            "--disposition", "discarded",
        ] + _REQUIRED_CREATE_ARGS,
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["class"] == "validation"
    assert "reason" in payload["error"]["message"].lower()


def test_handoff_create_pr_exempt_missing_disposition(tmp_path: Path) -> None:
    """pr_exempt without --disposition exits with EXIT_VALIDATION=2."""
    result = _invoke(
        tmp_path,
        [
            "handoff", "create", "6151",
            "--json",
            "--type", "pr_exempt",
            "--reason", "Nothing to ship",
        ] + _REQUIRED_CREATE_ARGS,
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["class"] == "validation"


def test_handoff_create_invalid_card_id(tmp_path: Path) -> None:
    """Non-existent card_id exits with EXIT_VALIDATION=2 and structured error."""
    result = _invoke(
        tmp_path,
        ["handoff", "create", "9999999", "--json"] + _REQUIRED_CREATE_ARGS,
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["class"] == "validation"
    assert "9999999" in payload["error"]["message"]


def test_handoff_create_files_and_auto_files_exclusive(tmp_path: Path) -> None:
    """--files and --auto-files together exit with EXIT_VALIDATION=2."""
    result = _invoke(
        tmp_path,
        [
            "handoff", "create", "6151", "--json",
            "--files", "[]",
            "--auto-files",
        ] + _REQUIRED_CREATE_ARGS,
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["class"] == "validation"


# ---------------------------------------------------------------------------
# list — filters
# ---------------------------------------------------------------------------

def _seed_two_handoffs(db_path: Path) -> None:
    """Insert two handoffs: one for card 6151 (project-tracker), one won't match filters."""
    runner = CliRunner()
    env = {**_COMMON_ENV, "PT_DB_PATH": str(db_path)}
    # First handoff for card 6151
    runner.invoke(
        cli,
        ["handoff", "create", "6151"] + _REQUIRED_CREATE_ARGS,
        env=env,
        catch_exceptions=False,
    )
    # Second handoff for card 6151 (different intent, will also match card filter)
    runner.invoke(
        cli,
        [
            "handoff", "create", "6151",
            "--intent", "Second handoff intent",
            "--status", "nothing done",
            "--next", "echo done",
            "--guidance", "discard all",
        ],
        env=env,
        catch_exceptions=False,
    )


def test_handoff_list_json_schema(tmp_path: Path) -> None:
    """list --json returns pt.handoff.v1 envelope with a list result."""
    db_path = tmp_path / "tracker.db"
    _make_tracker_db(db_path)
    _seed_two_handoffs(db_path)
    result = _invoke_on_db(db_path, ["handoff", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "pt.handoff.v1"
    assert payload["ok"] is True
    assert payload["command"] == "handoff.list"
    assert isinstance(payload["result"], list)
    assert len(payload["result"]) == 2


def test_handoff_list_filter_by_card(tmp_path: Path) -> None:
    """--card filters to only matching records."""
    db_path = tmp_path / "tracker.db"
    _make_tracker_db(db_path)
    _seed_two_handoffs(db_path)
    result = _invoke_on_db(db_path, ["handoff", "list", "--card", "6151", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    for rec in payload["result"]:
        assert rec["card_id"] == 6151


def test_handoff_list_filter_by_project(tmp_path: Path) -> None:
    """--project filters to only matching records."""
    db_path = tmp_path / "tracker.db"
    _make_tracker_db(db_path)
    _seed_two_handoffs(db_path)
    result = _invoke_on_db(db_path, ["handoff", "list", "--project", "project-tracker", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["result"]) >= 1
    for rec in payload["result"]:
        assert rec["project"] == "project-tracker"


def test_handoff_list_unresolved_only(tmp_path: Path) -> None:
    """--unresolved-only excludes resolved records."""
    db_path = tmp_path / "tracker.db"
    _make_tracker_db(db_path)
    _seed_two_handoffs(db_path)

    # Resolve the first handoff (id=1)
    _invoke_on_db(db_path, ["handoff", "resolve", "1", "--note", "done"])

    result = _invoke_on_db(db_path, ["handoff", "list", "--unresolved-only", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    for rec in payload["result"]:
        assert rec["resolved_at"] is None


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

def test_handoff_show_json(tmp_path: Path) -> None:
    """show HANDOFF_ID --json returns single record with pt.handoff.v1 envelope."""
    db_path = tmp_path / "tracker.db"
    _make_tracker_db(db_path)
    # Create one handoff
    create_result = _invoke_on_db(
        db_path,
        ["handoff", "create", "6151", "--json"] + _REQUIRED_CREATE_ARGS,
    )
    handoff_id = json.loads(create_result.output)["result"]["id"]

    result = _invoke_on_db(db_path, ["handoff", "show", str(handoff_id), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "pt.handoff.v1"
    assert payload["ok"] is True
    assert payload["command"] == "handoff.show"
    assert payload["result"]["id"] == handoff_id
    assert payload["result"]["card_id"] == 6151


def test_handoff_show_missing_id(tmp_path: Path) -> None:
    """show on non-existent handoff ID exits with EXIT_VALIDATION=2."""
    result = _invoke(tmp_path, ["handoff", "show", "99999", "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["class"] == "validation"


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------

def test_handoff_resolve_sets_resolved_at(tmp_path: Path) -> None:
    """resolve sets resolved_at and resolved_note on the record."""
    db_path = tmp_path / "tracker.db"
    _make_tracker_db(db_path)
    create_result = _invoke_on_db(
        db_path,
        ["handoff", "create", "6151", "--json"] + _REQUIRED_CREATE_ARGS,
    )
    handoff_id = json.loads(create_result.output)["result"]["id"]

    result = _invoke_on_db(
        db_path,
        ["handoff", "resolve", str(handoff_id), "--note", "Resumed and completed", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "pt.handoff.v1"
    assert payload["ok"] is True
    assert payload["command"] == "handoff.resolve"
    rec = payload["result"]
    assert rec["resolved_at"] is not None
    assert rec["resolved_note"] == "Resumed and completed"


def test_handoff_resolve_missing_id(tmp_path: Path) -> None:
    """resolve on non-existent handoff ID exits with EXIT_VALIDATION=2."""
    result = _invoke(tmp_path, ["handoff", "resolve", "99999", "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["class"] == "validation"


# ---------------------------------------------------------------------------
# JSON envelope — error path
# ---------------------------------------------------------------------------

def test_handoff_error_path_emits_ok_false(tmp_path: Path) -> None:
    """All JSON error paths emit ok=false with an error.class field."""
    result = _invoke(tmp_path, ["handoff", "create", "9999999", "--json"] + _REQUIRED_CREATE_ARGS)
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "class" in payload["error"]
    assert "message" in payload["error"]
