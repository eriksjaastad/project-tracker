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


@pytest.fixture
def daemon(dbmed_daemon, tmp_path):
    """The per-test dbmed daemon from the root conftest, described for this suite.

    There used to be a second, session-scoped daemon here. That made these
    tests share one database, and state from the destructive-gate tests leaked
    into the surface tests — `get_all_projects()` stopped being empty and a
    baseline assertion failed for a reason that had nothing to do with the
    boundary. One isolated daemon per test, defined in one place.
    """
    root = tmp_path / "_dbmed"
    data = root / "var"
    return {
        "socket": dbmed_daemon,
        "root": root,
        "config": root / "etc",
        "install": root / "libexec",
        "data": data,
        "project_data": data / "project-tracker",
    }


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
