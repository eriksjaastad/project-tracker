"""Skills registry — enumerate installed Claude Code skills.

Walks a skills root directory (default ``~/.claude/skills/``) for every
``SKILL.md`` file at any depth, parses the YAML frontmatter, and returns
the canonical skill name — the string the ``Skill`` tool carries as
``tool_input.skill`` when a user invokes a slash command.

The canonical name is the frontmatter ``name:`` field, *not* the
directory name. Directory prefixes (``apple-``, ``blender-`` etc.) are
organisational; they are stripped in the name the agent actually sees.

Stdlib-only to stay importable from any hook/script.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.DOTALL)
_NAME_LINE_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)

DEFAULT_SKILLS_ROOT = Path.home() / ".claude" / "skills"


def _extract_name(skill_md_path: Path) -> str | None:
    """Return the frontmatter ``name:`` value from a SKILL.md, or None."""
    try:
        text = skill_md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    block = _FRONTMATTER_RE.match(text)
    if block is None:
        return None
    name_match = _NAME_LINE_RE.search(block.group(1))
    if name_match is None:
        return None
    raw = name_match.group(1).strip().strip('"').strip("'")
    return raw or None


def installed_skills(root: Path | None = None) -> dict[str, Path]:
    """Return ``{canonical_name: SKILL.md path}`` for every installed skill.

    If two SKILL.md files declare the same canonical name the first one
    encountered wins and later duplicates are silently dropped (the Skill
    tool would have the same ambiguity to resolve at invocation time;
    de-duping here keeps the registry single-valued for reporting).

    ``root`` defaults to ``~/.claude/skills/`` resolved *at call time* so
    tests can monkeypatch ``$HOME`` and pick up a fixture directory.
    """
    if root is None:
        root = Path.home() / ".claude" / "skills"
    out: dict[str, Path] = {}
    if not root.is_dir():
        return out
    for md in root.rglob("SKILL.md"):
        name = _extract_name(md)
        if name and name not in out:
            out[name] = md
    return out
