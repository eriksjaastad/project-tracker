"""Origin resolution — which agent/context filed this card.

Used to populate the `created_by` field on tasks. Derives a short label
from the caller's cwd, so the CLI, MCP server, and any future surface all
tag provenance consistently.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_created_by() -> str:
    """Infer a card's origin label from the caller's cwd.

    - ``~/projects`` exactly → ``"architect"``
    - inside ``~/projects/<name>/...`` → ``"<name>"``
    - elsewhere → ``"unknown"``

    Honors ``PT_CALLER_CWD`` so wrappers can forward the user's cwd.
    """
    cwd_raw = os.environ.get("PT_CALLER_CWD", os.getcwd())
    try:
        cwd = Path(cwd_raw).resolve()
        projects_root = (Path.home() / "projects").resolve()
    except Exception:
        return "unknown"
    if cwd == projects_root:
        return "architect"
    try:
        rel = cwd.relative_to(projects_root)
    except ValueError:
        return "unknown"
    return rel.parts[0] if rel.parts else "architect"
