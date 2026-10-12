"""The `pt` launcher runs without Doppler.

Nothing in `pt` needs a Doppler secret; `pt memory` and `pt launch` wrap
themselves. The launcher used to wrap everything in `doppler run` unless
~/projects/.turso-config.json said otherwise, so a machine without that file
paid for (and depended on) Doppler on every call.
"""
import os
import stat
import subprocess
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parent.parent / "pt"


def _sandbox(tmp_path: Path) -> dict[str, str]:
    """An environment with no ~/projects/.turso-config.json and a doppler that fails."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    # The launcher execs $HOME/.local/bin/uv; hand it to the real uv with the real HOME.
    real_uv = Path(os.path.expanduser("~/.local/bin/uv"))
    shim = home / ".local" / "bin" / "uv"
    shim.write_text(f'#!/bin/sh\nHOME="{Path.home()}" exec "{real_uv}" "$@"\n')
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    called = tmp_path / "doppler-called"
    doppler = fake_bin / "doppler"
    doppler.write_text(f'#!/bin/sh\ntouch "{called}"\nexit 99\n')
    doppler.chmod(doppler.stat().st_mode | stat.S_IXUSR)

    env = dict(os.environ)
    env.pop("PT_SKIP_DOPPLER", None)
    env.update(
        HOME=str(home),
        PATH=f"{fake_bin}{os.pathsep}{env['PATH']}",
        UV_CACHE_DIR=str(tmp_path / "uv-cache"),
        PT_DB_PATH=str(tmp_path / "tracker.db"),
        PT_SUPPRESS_MIGRATION_WARNING="1",
    )
    return env


def test_bare_pt_never_invokes_doppler(tmp_path):
    env = _sandbox(tmp_path)
    # --version, not --help: the old launcher skipped Doppler for --help only.
    result = subprocess.run([str(LAUNCHER), "--version"], env=env, cwd=tmp_path,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "doppler-called").exists()


def test_inherited_skip_doppler_is_a_harmless_noop(tmp_path):
    env = _sandbox(tmp_path)
    env["PT_SKIP_DOPPLER"] = "1"
    result = subprocess.run([str(LAUNCHER), "--version"], env=env, cwd=tmp_path,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "doppler-called").exists()
