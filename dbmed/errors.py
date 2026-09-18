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

    def __init__(
        self, message: str, *, detail: str | None = None, exc_type: str | None = None
    ) -> None:
        super().__init__(message, detail=detail)
        self.exc_type = exc_type

    def to_wire(self) -> dict:
        payload = super().to_wire()
        if self.exc_type:
            payload["exc_type"] = self.exc_type
        return payload


# A domain error raised by the backend used to reach the caller as itself,
# because the caller and the backend were the same process. They are not any
# more, and an exception cannot cross a socket.
#
# That matters beyond tidiness: `dashboard/app.py` catches ValueError around
# update_task, delete_task and the idea operations to turn invalid input into
# an HTTP 400. Without this, those became 500s — the API would report a server
# fault for a user mistake.
#
# So a short allowlist of builtin exception types is carried on the wire by
# name, and re-raised here as something that is both `OperationFailed` and the
# original type. `except ValueError` and `except OperationFailed` both still
# work. Arbitrary types are deliberately not transported: that way lies
# reconstructing attacker-chosen classes from a wire payload.
_TRANSPARENT_EXC_TYPES: dict[str, type[Exception]] = {
    "ValueError": ValueError,
    "KeyError": KeyError,
    "TypeError": TypeError,
    "FileNotFoundError": FileNotFoundError,
    "PermissionError": PermissionError,
    "NotImplementedError": NotImplementedError,
}

_TRANSPARENT_CACHE: dict[str, type] = {}


def _transparent_class(name: str) -> type | None:
    """Build (once) a class that is both OperationFailed and the named builtin."""
    builtin = _TRANSPARENT_EXC_TYPES.get(name)
    if builtin is None:
        return None
    if name not in _TRANSPARENT_CACHE:
        _TRANSPARENT_CACHE[name] = type(
            f"Remote{name}",
            (OperationFailed, builtin),
            {"__doc__": f"A {name} raised by the dbmed backend, re-raised locally."},
        )
    return _TRANSPARENT_CACHE[name]


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
    message = payload.get("message", "unknown error")
    detail = payload.get("detail")

    if code == "OPERATION_FAILED":
        exc_type = payload.get("exc_type")
        transparent = _transparent_class(exc_type) if exc_type else None
        if transparent is not None:
            err = transparent(message, detail=detail, exc_type=exc_type)
            err.code = code
            return err
        err = OperationFailed(message, detail=detail, exc_type=exc_type)
        err.code = code
        return err

    cls = BY_CODE.get(code, DbmedError)
    err = cls(message, detail=detail)
    err.code = code
    return err
