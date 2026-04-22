"""Smoke tests for the pt CLI help surface."""

from __future__ import annotations

from collections.abc import Iterator
import sys
from pathlib import Path

from click.core import Command, Group
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pt import cli


def _iter_command_paths(cmd: Command, prefix: list[str] | None = None) -> Iterator[list[str]]:
    """Yield every invokable command path in the click tree."""
    prefix = prefix or []
    yield prefix
    if isinstance(cmd, Group):
        for name, subcmd in cmd.commands.items():
            yield from _iter_command_paths(subcmd, [*prefix, name])


def test_root_help_lists_expected_sync_surfaces() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "sync" in result.output
    assert "sync-project" in result.output


def test_every_command_path_supports_help() -> None:
    runner = CliRunner()
    for path in _iter_command_paths(cli):
        result = runner.invoke(cli, [*path, "--help"])
        joined = " ".join(path) or "<root>"
        assert result.exit_code == 0, f"{joined} --help failed:\n{result.output}"
