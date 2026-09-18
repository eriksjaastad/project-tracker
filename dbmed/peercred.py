"""Peer credentials on a Unix domain socket, macOS and Linux.

The socket file's group and mode are the first gate, but they are a property of
a path, and paths can be wrong. Asking the kernel who is on the other end is
the check that cannot be misconfigured into permissiveness.

If the peer uid cannot be determined, this raises. The connection is then
refused. An unidentifiable caller is not served — that is what failing closed
means here.
"""

from __future__ import annotations

import socket
import struct
import sys

# macOS: getsockopt(SOL_LOCAL, LOCAL_PEERCRED) yields struct xucred, whose first
# two fields are u_int cr_version and uid_t cr_uid.
_SOL_LOCAL = 0
_LOCAL_PEERCRED = 1
_XUCRED_VERSION = 0

# Linux: SO_PEERCRED yields struct ucred { pid_t, uid_t, gid_t }.
_UCRED_FMT = "=iII"


class PeerCredentialError(RuntimeError):
    """The caller's identity could not be established. Always refuse."""


def peer_uid(conn: socket.socket) -> int:
    if sys.platform == "darwin":
        return _peer_uid_darwin(conn)
    if sys.platform.startswith("linux"):
        return _peer_uid_linux(conn)
    raise PeerCredentialError(
        f"peer credentials are not implemented for {sys.platform!r}; refusing rather "
        "than serving an unidentified caller"
    )


def _peer_uid_darwin(conn: socket.socket) -> int:
    try:
        blob = conn.getsockopt(_SOL_LOCAL, _LOCAL_PEERCRED, 8)
    except OSError as exc:
        raise PeerCredentialError(f"LOCAL_PEERCRED failed: {exc}") from exc
    if len(blob) < 8:
        raise PeerCredentialError("LOCAL_PEERCRED returned a short struct")
    version, uid = struct.unpack("=II", blob[:8])
    if version != _XUCRED_VERSION:
        raise PeerCredentialError(f"unexpected xucred version {version}")
    return uid


def _peer_uid_linux(conn: socket.socket) -> int:
    try:
        blob = conn.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize(_UCRED_FMT)
        )
    except OSError as exc:
        raise PeerCredentialError(f"SO_PEERCRED failed: {exc}") from exc
    _pid, uid, _gid = struct.unpack(_UCRED_FMT, blob)
    return uid
