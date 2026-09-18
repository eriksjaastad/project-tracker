"""Fixtures for the dbmed boundary evidence suite.

Two very different kinds of test live here, and conflating them would make the
evidence worthless.

**Surface tests** run against an in-process daemon on a temporary tree. They
prove the protocol, the allowlist, the destructive gate and the fail-closed
path behave as specified. They run everywhere, including CI, and they need no
root.

**POSIX denial tests** prove the thing that actually matters: that an agent
process cannot open the file. That property comes from a service account and
0700 ownership, which only the real root install creates. They cannot be
faked on a temporary directory the test itself owns — a test that chmods a
directory it owns and then "proves" it cannot read it has proved nothing,
because it could chmod it back.

So when the real install is absent those tests **skip**, and
`test_evidence_matrix.py` reports the skip as UNVERIFIED. Card #7217 is
explicit that an uncovered path is unfinished work, not a pass, so the suite
is built to make an uninstalled machine look uncovered rather than green.

Nothing here ever touches the live database. The surface tests get a synthetic
schema in a temp directory; the denial tests get a daemon-provisioned fixture
inside the protected root.
"""

from __future__ import annotations

import os
import socket
import tempfile
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for candidate in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

# Where the real installation lives, if it exists.
INSTALLED_SOCKET = Path("/usr/local/var/run/dbmed.sock")
INSTALLED_DATA = Path("/usr/local/var/dbmed")
INSTALLED_CONFIG = Path("/usr/local/etc/dbmed")


def real_install_present() -> bool:
    """True when the root install exists and the daemon is answering."""
    if not INSTALLED_SOCKET.exists():
        return False
    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(2.0)
        conn.connect(str(INSTALLED_SOCKET))
        conn.close()
        return True
    except OSError:
        return False


requires_real_install = pytest.mark.skipif(
    not real_install_present(),
    reason=(
        "the dbmed root install is not present on this host, so kernel-level "
        "denial cannot be observed. This is UNVERIFIED, not passing — run "
        "sudo scripts/dbmed-install/install.sh and re-run."
    ),
)


@pytest.fixture(scope="session")
def boundary_tree(tmp_path_factory) -> dict:
    """A temporary install/config/data layout for the in-process daemon."""
    root = tmp_path_factory.mktemp("dbmed-boundary")
    install = root / "libexec"
    config = root / "etc"
    data = root / "var"
    project_data = data / "project-tracker"

    (config / "registry.d").mkdir(parents=True)
    install.mkdir()
    for sub in ("backups", "fixtures", "attic"):
        (project_data / sub).mkdir(parents=True)
    (data / "external" / "project-tracker").mkdir(parents=True)

    (config / "registry.d" / "project-tracker.toml").write_text(
        "\n".join(
            [
                'project = "project-tracker"',
                f'db_path = "{project_data}/tracker.db"',
                f'data_root = "{data}"',
                f'backup_dir = "{project_data}/backups"',
                f'external_backup_dir = "{data}/external/project-tracker"',
                f'fixture_root = "{project_data}/fixtures"',
                'ops_module = "db.dbmed_ops"',
                f"allowed_users = [{os.getuid()}]",
                "",
            ]
        )
    )
    # The socket lives in /tmp rather than under tmp_path. sun_path is capped
    # at 104 bytes on macOS and pytest's temp roots
    # (/private/var/folders/xx/.../pytest-of-user/pytest-N/...) blow straight
    # through it — the failure is a bare "AF_UNIX path too long" at bind time.
    socket_dir = Path(tempfile.mkdtemp(prefix="dbmed-t", dir="/tmp"))

    return {
        "root": root,
        "install": install,
        "config": config,
        "data": data,
        "project_data": project_data,
        "socket": socket_dir / "d.sock",
    }


@pytest.fixture(scope="session")
def daemon(boundary_tree) -> dict:
    """An in-process dbmed daemon on a temporary tree.

    `verify_integrity=False` because pytest cannot create root-owned files.
    The daemon refuses that flag when running as root, so this relaxation is
    unavailable to the real service — see `Service.__init__`.
    """
    # The tracker schema refuses to initialise on an unexpectedly empty
    # database; here an empty database is exactly what we want.
    os.environ.setdefault("PT_ALLOW_FRESH_DB", "1")

    from dbmed import daemon as dbmed_daemon

    ready = threading.Event()
    thread = threading.Thread(
        target=dbmed_daemon.serve,
        kwargs={
            "socket_path": boundary_tree["socket"],
            "config_dir": boundary_tree["config"],
            "install_dir": boundary_tree["install"],
            "data_root": boundary_tree["data"],
            "verify_integrity": False,
            "ready": ready,
        },
        daemon=True,
    )
    thread.start()
    assert ready.wait(30), "the in-process dbmed daemon never became ready"

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if boundary_tree["socket"].exists():
            break
        time.sleep(0.05)
    assert boundary_tree["socket"].exists(), "the daemon never created its socket"

    return {**boundary_tree, "thread": thread}


@pytest.fixture
def client(daemon):
    from dbmed.client import DbmedClient

    return DbmedClient("project-tracker", path=daemon["socket"])


@pytest.fixture
def manager(daemon):
    """The `DatabaseManager`-shaped proxy the real callers use."""
    from dbmed.client import DbmedClient, RemoteDatabaseManager

    return RemoteDatabaseManager(
        client=DbmedClient("project-tracker", path=daemon["socket"])
    )
