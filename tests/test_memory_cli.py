"""Read-only JSON memory CLI tests for SSH/cron automation."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pt import cli


def _seed_brain_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE thoughts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                embedding TEXT,
                metadata TEXT,
                scope TEXT DEFAULT 'shared',
                agent_family TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source_machine TEXT,
                uuid TEXT,
                embedding_model TEXT
            )
            """
        )
        rows = [
            (
                "LoopLens needs weekly PT memory analysis",
                '{"type":"decision","project":"project-tracker","source_agent":"Codex"}',
                "shared",
                "codex",
                "2026-05-01 10:00:00",
                "mini.local",
                "u1",
            ),
            (
                "Hermes should not touch PT databases directly",
                '{"type":"observation","project":"ai-memory","source_agent":"Claude Code"}',
                "shared",
                "claude",
                "2026-04-24 10:00:00",
                "macbook.local",
                "u2",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO thoughts
                (content, metadata, scope, agent_family, created_at, source_machine, uuid)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _invoke(tmp_path: Path, args: list[str]):
    db_path = tmp_path / "brain.db"
    _seed_brain_db(db_path)
    runner = CliRunner()
    return runner.invoke(
        cli,
        args,
        env={
            "PT_MEMORY_DB_PATH": str(db_path),
            "PT_SUPPRESS_MIGRATION_WARNING": "1",
            "PT_NO_BANNER": "1",
        },
        catch_exceptions=False,
    )


def test_memory_search_json_has_stable_schema_and_filters(tmp_path: Path) -> None:
    result = _invoke(
        tmp_path,
        [
            "memory",
            "search",
            "--query",
            "LoopLens",
            "--since",
            "7d",
            "--project",
            "project-tracker",
            "--limit",
            "10",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "pt.memory.v1"
    assert payload["ok"] is True
    assert payload["read_only"] is True
    assert payload["command"] == "memory.search"
    assert payload["pagination"]["returned"] == 1
    assert payload["results"][0]["project"] == "project-tracker"
    assert payload["results"][0]["source_agent"] == "Codex"
    assert "LoopLens" in payload["results"][0]["content"]


def test_memory_recent_json_uses_pagination(tmp_path: Path) -> None:
    result = _invoke(
        tmp_path,
        ["memory", "recent", "--limit", "1", "--offset", "1", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "memory.recent"
    assert payload["pagination"] == {
        "limit": 1,
        "offset": 1,
        "returned": 1,
        "total": 2,
    }
    assert payload["results"][0]["project"] == "ai-memory"


def test_memory_stats_json_is_machine_readable(tmp_path: Path) -> None:
    result = _invoke(tmp_path, ["memory", "stats", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "pt.memory.v1"
    assert payload["stats"]["total"] == 2
    assert payload["stats"]["oldest_created_at"] == "2026-04-24 10:00:00"
    assert payload["stats"]["newest_created_at"] == "2026-05-01 10:00:00"


def test_memory_search_json_validation_error_is_structured(tmp_path: Path) -> None:
    result = _invoke(
        tmp_path,
        ["memory", "search", "--query", "LoopLens", "--limit", "0", "--json"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["class"] == "validation"


def test_config_show_effective_json(tmp_path: Path) -> None:
    db_path = tmp_path / "brain.db"
    _seed_brain_db(db_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "show", "--effective", "--json"],
        env={
            "PT_MEMORY_DB_PATH": str(db_path),
            "PT_SUPPRESS_MIGRATION_WARNING": "1",
            "PT_NO_BANNER": "1",
        },
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "pt.config.v1"
    assert payload["memory_db_path"] == str(db_path)


def test_memory_export_emits_ndjson(tmp_path: Path) -> None:
    result = _invoke(tmp_path, ["memory", "export", "--format", "ndjson"])

    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    contents = {row["content"] for row in parsed}
    assert contents == {
        "LoopLens needs weekly PT memory analysis",
        "Hermes should not touch PT databases directly",
    }
    for row in parsed:
        assert "id" in row and "created_at" in row and "metadata" in row


def test_memory_export_respects_project_filter(tmp_path: Path) -> None:
    result = _invoke(tmp_path, ["memory", "export", "--project", "ai-memory"])

    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["project"] == "ai-memory"
    assert "Hermes" in row["content"]


def test_memory_export_error_goes_to_stderr_not_stdout(tmp_path: Path) -> None:
    """An NDJSON stream must not be polluted by error JSON on stdout."""
    missing_db = tmp_path / "does-not-exist.db"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["memory", "export"],
        env={
            "PT_MEMORY_DB_PATH": str(missing_db),
            "PT_SUPPRESS_MIGRATION_WARNING": "1",
            "PT_NO_BANNER": "1",
        },
        catch_exceptions=False,
    )

    assert result.exit_code == 3
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["ok"] is False
    assert payload["command"] == "memory.export"
    assert payload["error"]["class"] == "backend_unavailable"
