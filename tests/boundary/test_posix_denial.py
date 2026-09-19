"""The boundary itself: can a process running as the agent open the file?

Everything in `test_operation_surface.py` is about what the socket accepts.
This file is about the thing underneath, which is the only reason any of that
matters: a `0700` directory owned by `_dbmed` that the agent's uid cannot
traverse. That is a kernel check. It does not care which tool is asking, how
the path is spelled, or whether the caller read the rules.

**These tests skip without the root install, and a skip is not a pass.**
Card #7217: "Unsupported or unverified access paths remain blocked and prevent
declaring universal coverage." `test_evidence_matrix.py` prints the skips as
UNVERIFIED so an uninstalled machine reports as uncovered rather than green.

Every probe targets a synthetic fixture the daemon provisioned inside the
protected root — never the live database. Card #7217 again: "Never probe by
opening or modifying a live database directly." The fixture sits in the same
directory, with the same owner and mode, so what is proven about it is true of
its neighbour.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from dbmed.registry import DEFAULT_CONFIG_DIR, DEFAULT_INSTALL_DIR

from .conftest import INSTALLED_DATA, INSTALLED_SOCKET, requires_real_install

pytestmark = requires_real_install

# The one path with no constant to borrow: launchd's system domain.
LAUNCH_DAEMON_PLIST = "/Library/LaunchDaemons/com.dbmed.plist"

PROTECTED_DIR = INSTALLED_DATA / "project-tracker"
FIXTURE_NAME = f"boundary_{uuid.uuid4().hex}"


@pytest.fixture(scope="module")
def fixture_db():
    """A disposable synthetic database inside the protected directory."""
    from dbmed.client import DbmedClient

    client = DbmedClient("project-tracker", path=INSTALLED_SOCKET)
    created = client.call("dbmed.fixture.create", {"name": FIXTURE_NAME})
    path = Path(created["path"])
    try:
        yield path
    finally:
        client.call("dbmed.fixture.destroy", {"name": FIXTURE_NAME})


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    """Run a probe as this user. Never raises on failure — failure is the point."""
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=60, check=False
    )


def _assert_denied(result: subprocess.CompletedProcess, what: str) -> None:
    combined = (result.stdout + result.stderr).lower()
    denied = result.returncode != 0 and any(
        token in combined
        for token in ("permission denied", "not permitted", "unable to open", "errno 13")
    )
    assert denied, (
        f"{what} was NOT denied.\n"
        f"exit={result.returncode}\nstdout={result.stdout[:300]}\n"
        f"stderr={result.stderr[:300]}"
    )


# -- the directory itself ---------------------------------------------------


def test_the_protected_directory_is_not_traversable():
    info = PROTECTED_DIR.stat()
    assert info.st_mode & 0o077 == 0, (
        f"{PROTECTED_DIR} is mode {info.st_mode & 0o777:04o}; group or other can "
        "reach it, so the boundary is open"
    )
    assert info.st_uid != os.getuid(), (
        "the protected directory is owned by the user running the agent, who can "
        "therefore chmod it back. Ownership by a separate account is the boundary."
    )


def test_listing_the_protected_directory_is_denied():
    with pytest.raises(PermissionError):
        list(PROTECTED_DIR.iterdir())


# -- SQL clients ------------------------------------------------------------


def _sqlite_binaries() -> list[str]:
    """Every spelling of the sqlite3 client available on this host.

    Both the bare name and its fully-resolved location, because "the CLI is
    blocked" is a claim about a command name and this suite is meant to prove
    something stronger. Resolved rather than hardcoded so the probe covers
    wherever sqlite3 actually lives here, not two guesses.
    """
    found = shutil.which("sqlite3")
    if found is None:
        return []
    return list(dict.fromkeys(["sqlite3", found, str(Path(found).resolve())]))


@pytest.mark.parametrize("binary", _sqlite_binaries() or ["sqlite3"])
def test_sqlite_clients_are_denied(fixture_db, binary):
    if shutil.which(binary) is None and not Path(binary).exists():
        pytest.skip(f"{binary} is not installed on this host")
    _assert_denied(_run([binary, str(fixture_db), "SELECT 1"]), f"{binary} read")


# -- language drivers -------------------------------------------------------


def test_python_sqlite3_driver_is_denied(fixture_db):
    code = (
        "import sqlite3,sys\n"
        f"sqlite3.connect('file:{fixture_db}?mode=ro', uri=True)"
        ".execute('SELECT 1').fetchone()\n"
    )
    _assert_denied(_run([sys.executable, "-c", code]), "python sqlite3 read-only open")


def test_python_sqlite3_write_is_denied(fixture_db):
    code = (
        "import sqlite3\n"
        f"sqlite3.connect('{fixture_db}').execute('CREATE TABLE x (i int)')\n"
    )
    _assert_denied(_run([sys.executable, "-c", code]), "python sqlite3 write")


def test_node_is_denied_if_present(fixture_db):
    if shutil.which("node") is None:
        pytest.skip("node is not installed on this host")
    code = f"require('fs').readFileSync({str(fixture_db)!r})"
    _assert_denied(_run(["node", "-e", code]), "node fs.readFileSync")


# -- file tools -------------------------------------------------------------


@pytest.mark.parametrize("tool", ["cat", "head", "strings", "xxd", "wc"])
def test_file_readers_are_denied(fixture_db, tool):
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} is not installed on this host")
    _assert_denied(_run([tool, str(fixture_db)]), f"{tool}")


def test_copying_the_database_is_denied(fixture_db, tmp_path):
    _assert_denied(_run(["cp", str(fixture_db), str(tmp_path / "stolen.db")]), "cp")
    assert not (tmp_path / "stolen.db").exists()


def test_moving_the_database_is_denied(fixture_db, tmp_path):
    _assert_denied(_run(["mv", str(fixture_db), str(tmp_path / "moved.db")]), "mv")


def test_dd_is_denied(fixture_db, tmp_path):
    _assert_denied(
        _run(["dd", f"if={fixture_db}", f"of={tmp_path / 'dd.db'}"]), "dd"
    )


def test_overwriting_the_database_is_denied(fixture_db):
    code = f"open({str(fixture_db)!r}, 'wb').write(b'destroyed')"
    _assert_denied(_run([sys.executable, "-c", code]), "truncating write")


def test_deleting_the_database_is_denied(fixture_db):
    code = f"import os; os.remove({str(fixture_db)!r})"
    _assert_denied(_run([sys.executable, "-c", code]), "os.remove")


# -- journals and copies ----------------------------------------------------


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
def test_journals_are_denied_too(fixture_db, suffix):
    """A WAL holds committed transactions that are not in the main file yet."""
    _assert_denied(_run(["cat", f"{fixture_db}{suffix}"]), f"cat of the {suffix} journal")


def test_the_backup_directory_is_denied():
    """Backups are copies of real rows, so they get the same protection."""
    _assert_denied(_run(["ls", str(PROTECTED_DIR / "backups")]), "ls of backups")


# -- alternate routes to the same bytes -------------------------------------


def test_a_symlink_does_not_help(fixture_db, tmp_path):
    """Following a link still lands on a directory the kernel will not open."""
    link = tmp_path / "shortcut.db"
    link.symlink_to(fixture_db)
    _assert_denied(_run(["cat", str(link)]), "cat through a symlink")


def test_a_relative_path_does_not_help(fixture_db):
    relative = os.path.relpath(fixture_db, Path.home())
    result = subprocess.run(
        ["cat", relative], cwd=Path.home(), capture_output=True, text=True,
        timeout=60, check=False,
    )
    _assert_denied(result, "cat through a relative path")


def test_a_subprocess_does_not_help(fixture_db):
    _assert_denied(_run(["sh", "-c", f"cat {fixture_db}"]), "sh -c")


def test_xargs_does_not_help(fixture_db):
    result = subprocess.run(
        ["xargs", "cat"], input=str(fixture_db), capture_output=True, text=True,
        timeout=60, check=False,
    )
    _assert_denied(result, "xargs cat")


def test_ssh_to_localhost_does_not_help(fixture_db):
    """A remote session is still this uid; the boundary is not about locality."""
    if shutil.which("ssh") is None:
        pytest.skip("ssh is not installed on this host")
    result = _run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
         "localhost", f"cat {fixture_db}"]
    )
    if result.returncode != 0 and "permission denied (publickey" in result.stderr.lower():
        pytest.skip("ssh to localhost is not configured on this host")
    _assert_denied(result, "ssh localhost cat")


def test_the_env_override_does_not_help(fixture_db):
    """PT_DB_PATH was the documented path-substitution vector."""
    env = {**os.environ, "PT_DB_PATH": str(fixture_db)}
    code = (
        "import sqlite3, os\n"
        "sqlite3.connect(os.environ['PT_DB_PATH']).execute('SELECT 1')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True,
        timeout=60, check=False,
    )
    _assert_denied(result, "PT_DB_PATH pointed at the protected path")


# -- attempts to remove the guard -------------------------------------------


def test_chmod_of_the_protected_directory_is_denied():
    _assert_denied(_run(["chmod", "755", str(PROTECTED_DIR)]), "chmod of the data dir")


def test_chown_of_the_protected_directory_is_denied():
    _assert_denied(
        _run(["chown", str(os.getuid()), str(PROTECTED_DIR)]), "chown of the data dir"
    )


def test_the_installed_backend_cannot_be_edited():
    """If an agent could edit the daemon's code, the daemon is not a boundary."""
    target = DEFAULT_INSTALL_DIR / "dbmed" / "daemon.py"
    if not target.exists():
        pytest.skip("the installed backend is not present")
    code = f"open({str(target)!r}, 'a').write('# owned\\n')"
    _assert_denied(_run([sys.executable, "-c", code]), "appending to installed code")


def test_the_launch_daemon_plist_cannot_be_edited():
    plist = Path(LAUNCH_DAEMON_PLIST)
    if not plist.exists():
        pytest.skip("the LaunchDaemon plist is not installed")
    code = f"open({str(plist)!r}, 'a').write('<!-- owned -->')"
    _assert_denied(_run([sys.executable, "-c", code]), "appending to the plist")


def test_the_vendored_extension_cannot_be_replaced():
    """A SQLite extension is native code inside the privileged process."""
    dylib = DEFAULT_INSTALL_DIR / "lib" / "crsqlite.dylib"
    if not dylib.exists():
        pytest.skip("cr-sqlite has not been vendored on this host")
    code = f"open({str(dylib)!r}, 'wb').write(b'\\x00')"
    _assert_denied(_run([sys.executable, "-c", code]), "overwriting the vendored dylib")


def test_the_registry_cannot_be_edited():
    """Whoever writes the registry chooses which database a project talks to."""
    entry = DEFAULT_CONFIG_DIR / "registry.d" / "project-tracker.toml"
    if not entry.exists():
        pytest.skip("the registry entry is not installed")
    code = f"open({str(entry)!r}, 'a').write('test_support = true\\n')"
    _assert_denied(_run([sys.executable, "-c", code]), "enabling test_support in the registry")


def test_unloading_the_daemon_is_denied():
    """Stopping the service must not be something an agent can do.

    Denial here is what makes fail-closed meaningful: if an agent could stop
    the daemon it could not read the data either, but it could deny the
    service to everything else.
    """
    result = _run(["launchctl", "bootout", "system/com.dbmed"])
    assert result.returncode != 0, (
        "launchctl bootout of the system daemon succeeded as an unprivileged "
        "user. The daemon can be stopped by an agent."
    )


# -- and the sanctioned path still works ------------------------------------


def test_the_sanctioned_interface_still_works(fixture_db):  # noqa: ARG001
    """A denial suite proves nothing unless the allowed route works."""
    from dbmed.client import DbmedClient

    assert DbmedClient("project-tracker").call("dbmed.ping")["ok"] is True
