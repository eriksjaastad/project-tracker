"""Error taxonomy for dbmed.

Every failure crossing the socket carries a stable machine-readable code so the
client can be truthful about *why* it failed. The distinction that matters most
is DB_UNAVAILABLE (the daemon could not be reached) versus everything else:
DB_UNAVAILABLE must never be interpreted by a caller as "empty result", and
there is no code path anywhere in the client that reacts to it by opening a
database file. See dbmed/PRD.md, "Fail-closed".
"""

from __future__ import annotations


class DbmedError(Exception):
    """Base class. `code` is the wire-stable identifier."""

    code = "INTERNAL"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_wire(self) -> dict:
        payload = {"code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


class DbUnavailable(DbmedError):
    """The mediation daemon could not be reached, or died mid-request.

    This is the fail-closed path. It is raised by the client, never received
    from the daemon.
    """

    code = "DB_UNAVAILABLE"


class ProtocolError(DbmedError):
    """Malformed frame, bad version, or oversized request."""

    code = "PROTOCOL"


class NotRegistered(DbmedError):
    """No registry entry for the requested project.

    A missing registration is a deployment failure, not permission to reach the
    database another way (card #7228, delivery item 3).
    """

    code = "NOT_REGISTERED"


class UnknownOperation(DbmedError):
    """The operation is not on the project's allowlist. There is no passthrough."""

    code = "UNKNOWN_OPERATION"


class InvalidParams(DbmedError):
    """Parameters failed the operation's schema."""

    code = "INVALID_PARAMS"


class NotAuthorized(DbmedError):
    """Peer credentials rejected, or a destructive op attempted without a token."""

    code = "NOT_AUTHORIZED"


class BackupRequired(DbmedError):
    """A destructive operation was requested but its backup could not be verified."""

    code = "BACKUP_REQUIRED"


class OperationFailed(DbmedError):
    """The backend raised while executing an otherwise valid operation."""

    code = "OPERATION_FAILED"


BY_CODE = {
    cls.code: cls
    for cls in (
        DbUnavailable,
        ProtocolError,
        NotRegistered,
        UnknownOperation,
        InvalidParams,
        NotAuthorized,
        BackupRequired,
        OperationFailed,
    )
}


def from_wire(payload: dict) -> DbmedError:
    """Rebuild a typed exception from a wire error object."""
    code = payload.get("code", "INTERNAL")
    cls = BY_CODE.get(code, DbmedError)
    err = cls(payload.get("message", "unknown error"), detail=payload.get("detail"))
    err.code = code
    return err
