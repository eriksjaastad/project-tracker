"""Operation allowlist and parameter validation.

This module is the security core. Everything else is plumbing.

Two rules it exists to enforce:

1. **An operation must be named ahead of time.** The daemon dispatches only to
   entries in an explicit allowlist. There is no "call any method on the
   backend object" path, so adding a capability is a reviewed deployment, not a
   runtime choice by the caller.

2. **Parameters must match the backend's real signature.** The allowlist names
   the operation and classifies its blast radius; the parameter schema is
   *derived by introspecting the bound method*, so it cannot silently drift out
   of date. If someone changes a backend signature without updating the
   allowlist, `build_operations` raises at daemon startup rather than shipping a
   mismatch.

Deriving params rather than hand-listing them is deliberate. A hand-maintained
copy of 50 signatures is a copy that goes stale, and a stale parameter schema
fails open: it lets through arguments nobody reviewed.
"""

from __future__ import annotations

import inspect
import typing
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .errors import InvalidParams, UnknownOperation


class Kind(str, Enum):
    """Blast radius. Drives authorisation, backup, and audit behaviour."""

    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ParamSpec:
    name: str
    required: bool
    annotation: Any = Any
    default: Any = None


@dataclass(frozen=True)
class OpSpec:
    name: str
    kind: Kind
    method: Callable[..., Any]
    params: dict[str, ParamSpec]
    accepts_extra: frozenset[str] = field(default_factory=frozenset)

    def validate(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Return kwargs safe to splat into the backend method.

        Refuses unknown keys outright. An unrecognised parameter is far more
        likely to be an attempt to reach something than a typo, and either way
        silently dropping it would make the call mean something other than what
        the caller asked for.
        """
        allowed = set(self.params) | set(self.accepts_extra)
        unknown = set(raw) - allowed
        if unknown:
            raise InvalidParams(
                f"operation {self.name!r} does not accept {sorted(unknown)}; "
                f"accepted: {sorted(allowed)}"
            )

        missing = [
            name for name, spec in self.params.items() if spec.required and name not in raw
        ]
        if missing:
            raise InvalidParams(f"operation {self.name!r} requires {sorted(missing)}")

        checked: dict[str, Any] = {}
        for key, value in raw.items():
            spec = self.params.get(key)
            annotation = spec.annotation if spec else self.accepts_extra_annotation(key)
            _check_type(self.name, key, value, annotation)
            checked[key] = value
        return checked

    def accepts_extra_annotation(self, key: str) -> Any:  # pragma: no cover - trivial
        return Any


def build_operations(
    backend: Any, allowlist: dict[str, Kind | tuple[Kind, set[str]]]
) -> dict[str, OpSpec]:
    """Bind an allowlist of operation names to methods on `backend`.

    `allowlist` maps the wire operation name to its Kind, or to a
    (Kind, extra_param_names) pair for methods that take **kwargs.

    Raises ValueError at startup — never at request time — if an entry does not
    correspond to a real public method.
    """
    ops: dict[str, OpSpec] = {}
    for name, entry in allowlist.items():
        if isinstance(entry, tuple):
            kind, extra = entry
        else:
            kind, extra = entry, set()

        if name.startswith("_"):
            raise ValueError(f"{name!r}: private methods are not exposable")
        method = getattr(backend, name, None)
        if method is None or not callable(method):
            raise ValueError(f"{name!r} is not a callable attribute of the backend")

        signature = inspect.signature(method)
        params: dict[str, ParamSpec] = {}
        saw_var_keyword = False
        for pname, param in signature.parameters.items():
            if pname == "self":
                continue
            if param.kind is inspect.Parameter.VAR_KEYWORD:
                saw_var_keyword = True
                continue
            if param.kind is inspect.Parameter.VAR_POSITIONAL:
                raise ValueError(f"{name!r}: *args cannot be expressed over the wire")
            params[pname] = ParamSpec(
                name=pname,
                required=param.default is inspect.Parameter.empty,
                annotation=param.annotation,
                default=None if param.default is inspect.Parameter.empty else param.default,
            )

        if extra and not saw_var_keyword:
            raise ValueError(
                f"{name!r}: allowlist declares extra params {sorted(extra)} but the "
                "method takes no **kwargs"
            )
        if saw_var_keyword and not extra:
            raise ValueError(
                f"{name!r}: method takes **kwargs, so the allowlist must enumerate the "
                "accepted keys — an open kwargs surface is not reviewable"
            )

        ops[name] = OpSpec(
            name=name, kind=kind, method=method, params=params, accepts_extra=frozenset(extra)
        )
    return ops


def resolve(ops: dict[str, OpSpec], name: str) -> OpSpec:
    spec = ops.get(name)
    if spec is None:
        raise UnknownOperation(
            f"{name!r} is not an allowlisted operation. There is no arbitrary-SQL or "
            "arbitrary-method passthrough; if you need this, extend the reviewed tool."
        )
    return spec


_JSON_SCALARS = {int: int, float: (int, float), str: str, bool: bool}


def _check_type(op: str, key: str, value: Any, annotation: Any) -> None:
    """Best-effort structural check against the backend's own annotation.

    Deliberately permissive where the annotation is unhelpful (Any, unannotated,
    or a container of containers) and strict where it is clear. The backend
    still validates its own domain rules; this is about refusing values of a
    shape the method was never written to handle.
    """
    if annotation in (Any, inspect.Parameter.empty, None):
        return

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is typing.Union or (origin is not None and str(origin) == "types.UnionType"):
        if value is None and type(None) in args:
            return
        for candidate in args:
            if candidate is type(None):
                continue
            try:
                _check_type(op, key, value, candidate)
                return
            except InvalidParams:
                continue
        raise InvalidParams(f"{op}.{key}: {type(value).__name__} does not match {annotation}")

    if origin in (list, set, frozenset, tuple):
        if not isinstance(value, list):
            raise InvalidParams(f"{op}.{key}: expected a JSON array, got {type(value).__name__}")
        return
    if origin is dict:
        if not isinstance(value, dict):
            raise InvalidParams(f"{op}.{key}: expected a JSON object, got {type(value).__name__}")
        return

    if annotation is Path or annotation is typing.Optional[Path]:
        # A path parameter is never accepted from a client. Path resolution is
        # the daemon's job; letting a caller name a file is exactly the
        # arbitrary-path bypass the boundary exists to prevent.
        raise InvalidParams(
            f"{op}.{key}: path parameters are not accepted over the socket"
        )

    expected = _JSON_SCALARS.get(annotation)
    if expected is None:
        return
    if annotation is int and isinstance(value, bool):
        raise InvalidParams(f"{op}.{key}: expected int, got bool")
    if not isinstance(value, expected):
        raise InvalidParams(
            f"{op}.{key}: expected {annotation.__name__}, got {type(value).__name__}"
        )
