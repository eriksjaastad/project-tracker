"""dbmed — mediated database access.

Agents and services talk to `dbmed.client`. Only `dbmed.daemon`, running as a
dedicated service account from a root-owned install, ever opens a database.

See dbmed/PRD.md for intent and dbmed/PROJECT_DOD.md for what "done" requires.
"""

from .errors import (  # noqa: F401
    BackupRequired,
    DbmedError,
    DbUnavailable,
    InvalidParams,
    NotAuthorized,
    NotRegistered,
    OperationFailed,
    ProtocolError,
    UnknownOperation,
)

__all__ = [
    "BackupRequired",
    "DbUnavailable",
    "DbmedError",
    "InvalidParams",
    "NotAuthorized",
    "NotRegistered",
    "OperationFailed",
    "ProtocolError",
    "UnknownOperation",
]
