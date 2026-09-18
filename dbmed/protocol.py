"""Wire protocol for dbmed.

Newline-delimited JSON over a Unix domain socket. One request, one response,
connection closed. The framing is deliberately dull; the security property is
in what the frame is *allowed to say*, not in how it is encoded.

A request names a project and an operation. It cannot name a SQL statement, a
database path, a file, a shell command, or a module to import. There is no
field for any of those, so there is nothing for an attacker to smuggle them
through. See dbmed/PRD.md, "Non-Goals".
"""

from __future__ import annotations

import json
from typing import Any, BinaryIO

from .errors import ProtocolError

VERSION = 1

# A request is a handful of scalars and a small params object. 1 MiB is already
# far more than any legitimate call needs; raw_import_tasks is the largest and
# is bounded well under this.
MAX_REQUEST_BYTES = 1 << 20

# Responses carry row sets. get_tasks over a large board is the worst case.
MAX_RESPONSE_BYTES = 64 << 20

_REQUEST_FIELDS = {"v", "project", "op", "params", "token"}


def encode_request(
    project: str, op: str, params: dict[str, Any], token: str | None = None
) -> bytes:
    frame: dict[str, Any] = {"v": VERSION, "project": project, "op": op, "params": params}
    if token is not None:
        frame["token"] = token
    blob = json.dumps(frame, separators=(",", ":"), default=_json_default).encode("utf-8")
    if len(blob) > MAX_REQUEST_BYTES:
        raise ProtocolError(
            f"request is {len(blob)} bytes, over the {MAX_REQUEST_BYTES} byte limit"
        )
    return blob + b"\n"


def decode_request(blob: bytes) -> dict[str, Any]:
    """Parse and structurally validate a request frame. Raises ProtocolError."""
    if len(blob) > MAX_REQUEST_BYTES:
        raise ProtocolError(f"request over the {MAX_REQUEST_BYTES} byte limit")
    try:
        frame = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"unparseable request frame: {exc}") from exc

    if not isinstance(frame, dict):
        raise ProtocolError("request frame must be a JSON object")

    unknown = set(frame) - _REQUEST_FIELDS
    if unknown:
        # Refusing unknown fields keeps the frame from growing a side channel.
        raise ProtocolError(f"unknown request fields: {sorted(unknown)}")

    if frame.get("v") != VERSION:
        raise ProtocolError(f"unsupported protocol version {frame.get('v')!r}")

    for field in ("project", "op"):
        if not isinstance(frame.get(field), str) or not frame[field]:
            raise ProtocolError(f"{field!r} must be a non-empty string")

    params = frame.get("params", {})
    if not isinstance(params, dict):
        raise ProtocolError("'params' must be an object")
    if not all(isinstance(k, str) for k in params):
        raise ProtocolError("'params' keys must be strings")
    frame["params"] = params

    token = frame.get("token")
    if token is not None and not isinstance(token, str):
        raise ProtocolError("'token' must be a string when present")

    return frame


def encode_response(ok: bool, data: Any = None, error: dict | None = None) -> bytes:
    frame: dict[str, Any] = {"ok": ok}
    if ok:
        frame["data"] = data
    else:
        frame["error"] = error or {"code": "INTERNAL", "message": "unspecified failure"}
    blob = json.dumps(frame, separators=(",", ":"), default=_json_default).encode("utf-8")
    if len(blob) > MAX_RESPONSE_BYTES:
        # Truthful failure beats a silently truncated row set.
        blob = json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "OPERATION_FAILED",
                    "message": (
                        f"response is {len(blob)} bytes, over the "
                        f"{MAX_RESPONSE_BYTES} byte limit; narrow the query"
                    ),
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
    return blob + b"\n"


def read_frame(stream: BinaryIO, limit: int) -> bytes:
    """Read one newline-terminated frame, refusing anything over `limit`.

    Returns b"" on clean EOF. Raises ProtocolError if the peer sends more than
    `limit` bytes without a newline, so a hostile client cannot exhaust memory.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.readline(limit + 1 - total)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if chunk.endswith(b"\n"):
            return b"".join(chunks)
        if total > limit:
            raise ProtocolError(f"frame exceeded {limit} bytes with no terminator")


def _json_default(obj: Any) -> Any:
    """Serialise the handful of non-JSON types the backend legitimately returns.

    Deliberately narrow: anything not named here raises, rather than being
    coerced to a str that a caller might mistake for real data.
    """
    import datetime
    import decimal
    import pathlib

    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return str(obj)
    if isinstance(obj, pathlib.PurePath):
        return str(obj)
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    if isinstance(obj, (bytes, bytearray)):
        import base64

        return {"__bytes_b64__": base64.b64encode(bytes(obj)).decode("ascii")}
    raise TypeError(f"{type(obj).__name__} is not JSON-serialisable across the dbmed socket")
