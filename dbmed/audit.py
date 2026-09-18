"""Append-only audit log for the privileged side.

Records *that* an operation happened and by whom, never the data it carried.
Parameter names are logged; parameter values are not. Card #7229 requires
"audit events without secrets", and Phase 2's tax-organizer makes that concrete
— a ledger row in a log file is a copy of filing data outside the boundary,
which is the thing we are trying to stop.

The log lives in the root-owned data root, so an agent cannot read it to mine
what it could not query, and cannot truncate it to hide an attempt.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        event: str,
        uid: int,
        project: str,
        op: str,
        kind: str,
        ok: bool,
        duration_ms: float,
        param_names: list[str] | None = None,
        error_code: str | None = None,
        detail: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "event": event,
            "uid": uid,
            "project": project,
            "op": op,
            "kind": kind,
            "ok": ok,
            "duration_ms": round(duration_ms, 2),
            "params": sorted(param_names or []),
        }
        if error_code:
            entry["error_code"] = error_code
        if detail:
            entry["detail"] = detail

        line = json.dumps(entry, separators=(",", ":"), default=str) + "\n"
        with _LOCK:
            # Open per write so log rotation by root cannot leave us writing to
            # an unlinked inode without noticing.
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)
