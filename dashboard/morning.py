"""Morning warm-up checklist page data.

The step list lives in another repository's README and is read from there at
request time, never hand-copied into code. Parsing produces inline-markdown
"segments" so the frontend never needs dangerouslySetInnerHTML.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path


class MorningPlanError(RuntimeError):
    """Raised when the morning plan source is missing or cannot be parsed."""


JOB_SEARCH_REPO = "eriksjaastad/job-search"
GITHUB_BLOB_BASE = f"https://github.com/{JOB_SEARCH_REPO}/blob/main"

_SECTION_HEADING = "## Standing morning plan"
_NEXT_MORNING_HEADING = "### Next morning"
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")


def projects_root() -> Path:
    """Return the portfolio projects root, honouring the same override as app.py."""
    return Path(os.environ.get("PROJECTS_ROOT", str(Path.home() / "projects")))


def readme_path() -> Path:
    return projects_root() / "job-search" / "README.md"


def _link_href(target: str) -> str:
    """Resolve a link target: absolute URLs pass through, repo-relative ones get a GitHub blob URL."""
    target = target.strip()
    if target.startswith("./"):
        target = target[2:]
    if target.startswith("#"):
        return f"{GITHUB_BLOB_BASE}/README.md{target}"
    if re.match(r"^(https?://|mailto:)", target, flags=re.IGNORECASE):
        return target
    return f"{GITHUB_BLOB_BASE}/{target}"


def _inline_segments(text: str) -> list[dict]:
    """Split one paragraph into inline segments: text, strong, code, link."""
    segments: list[dict] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "`":
            end = text.find("`", i + 1)
            if end == -1:
                segments.append({"type": "text", "text": text[i:]})
                break
            segments.append({"type": "code", "text": text[i + 1 : end]})
            i = end + 1
        elif text.startswith("**", i):
            end = text.find("**", i + 2)
            if end == -1:
                segments.append({"type": "text", "text": text[i:]})
                break
            segments.append({"type": "strong", "text": text[i + 2 : end]})
            i = end + 2
        elif char == "[":
            match = _LINK_RE.match(text, i)
            if match:
                label, target = match.group(1), match.group(2)
                # Flatten any inline markup inside the label into plain link text.
                flat_label = "".join(
                    part["text"] for part in _inline_segments(label)
                )
                segments.append({
                    "type": "link",
                    "text": flat_label,
                    "href": _link_href(target),
                })
                i = match.end()
            else:
                segments.append({"type": "text", "text": char})
                i += 1
        else:
            end = i
            while end < len(text):
                if text[end] in "`[" or text.startswith("**", end):
                    break
                end += 1
            segments.append({"type": "text", "text": text[i:end]})
            i = end

    merged: list[dict] = []
    for segment in segments:
        if (
            segment["type"] == "text"
            and merged
            and merged[-1]["type"] == "text"
        ):
            merged[-1]["text"] += segment["text"]
        else:
            merged.append(segment)
    return merged


def _paragraphs(lines: list[str]) -> list[list[dict]]:
    """Group lines into paragraphs, joining wrapped lines with a space, then inline-parse each."""
    paragraphs: list[list[dict]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(_inline_segments(" ".join(current)))
                current = []
        else:
            current.append(stripped)
    if current:
        paragraphs.append(_inline_segments(" ".join(current)))
    return paragraphs


def _is_table_row(line: str) -> bool:
    return line.strip().startswith("|")


def _table_cells(line: str) -> list[str]:
    """Split a markdown table row into trimmed cells (no leading/trailing pipes)."""
    parts = line.strip().split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [part.strip() for part in parts]


def _find_section_bounds(lines: list[str]) -> tuple[int, int]:
    """Return (start, end) line indices for the Standing morning plan section."""
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == _SECTION_HEADING:
            start = idx
            break
    if start is None:
        raise MorningPlanError(
            f"Could not find '{_SECTION_HEADING}' section in the morning plan source"
        )

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].strip().startswith("## "):
            end = idx
            break
    return start, end


def _extract_table(section_lines: list[str]) -> tuple[int, int]:
    """Return (table_start, table_end) indices within the section slice."""
    table_start = None
    for idx, line in enumerate(section_lines):
        if _is_table_row(line):
            table_start = idx
            break
    if table_start is None:
        raise MorningPlanError(
            "The morning plan section has no steps table"
        )

    table_end = table_start
    while table_end < len(section_lines) and _is_table_row(section_lines[table_end]):
        table_end += 1
    return table_start, table_end


def _parse_steps(table_lines: list[str]) -> list[dict]:
    if len(table_lines) < 2:
        raise MorningPlanError("The morning plan table is malformed")

    header = _table_cells(table_lines[0])
    separator = table_lines[1].strip()
    if len(header) < 4 or not separator.replace("|", "").replace("-", "").replace(":", "").strip() == "":
        raise MorningPlanError("The morning plan table is malformed")

    data_lines = table_lines[2:]
    if not data_lines:
        raise MorningPlanError("The morning plan table has zero steps")

    steps: list[dict] = []
    for line in data_lines:
        cells = _table_cells(line)
        if len(cells) < 4:
            raise MorningPlanError("The morning plan table has a malformed row")
        description = " | ".join(cells[3:])
        steps.append({
            "number": cells[0],
            "channel": cells[1],
            "time": cells[2],
            "description": _inline_segments(description),
        })
    if not steps:
        raise MorningPlanError("The morning plan table has zero steps")
    return steps


def _extract_next_morning(section_lines: list[str]) -> list[list[dict]]:
    heading_index = None
    for idx, line in enumerate(section_lines):
        if line.strip() == _NEXT_MORNING_HEADING:
            heading_index = idx
            break
    if heading_index is None:
        return []

    body: list[str] = []
    for line in section_lines[heading_index + 1 :]:
        stripped = line.strip()
        if stripped.startswith("#"):
            break
        body.append(stripped)
    return _paragraphs(body)


def parse_morning_plan(readme_text: str) -> dict:
    """Parse the Standing morning plan section out of the job-search README.

    Raises MorningPlanError when the section, its steps table, or any step row
    is missing. An empty steps list is never a successful result.
    """
    lines = readme_text.splitlines()
    start, end = _find_section_bounds(lines)
    section_lines = lines[start + 1 : end]

    table_start, table_end = _extract_table(section_lines)
    intro_lines = section_lines[:table_start]
    intro = _paragraphs(intro_lines)
    steps = _parse_steps(section_lines[table_start:table_end])
    next_morning = _extract_next_morning(section_lines[table_end:])

    return {
        "intro": intro,
        "steps": steps,
        "next_morning": next_morning,
    }


def load_hn_snapshots(snapshot_dir: Path, day: date) -> list[dict]:
    """Load the two HN job snapshots for a given day.

    A missing file is ``present: False`` — never "nothing new".
    """
    snapshots: list[dict] = []
    for kind in ("freelance", "hiring"):
        filename = f"hn-jobs-{day.isoformat()}-{kind}.txt"
        path = snapshot_dir / filename
        present = path.is_file()
        text: str | None = None
        if present:
            try:
                text = path.read_text()
            except OSError:
                text = None
        snapshots.append({
            "kind": kind,
            "filename": filename,
            "present": present,
            "text": text,
        })
    return snapshots


def morning_snapshot(today: date | None = None) -> dict:
    """Build the full /api/morning payload from the source README and HN snapshots."""
    # Machine-local date, because hn_jobs.py names its snapshots with date.today().
    display_day = today or date.today()
    source = readme_path()
    if not source.is_file():
        raise MorningPlanError(
            f"Morning plan source not found: {source}"
        )
    try:
        readme_text = source.read_text()
    except OSError as exc:
        raise MorningPlanError(
            f"Morning plan source could not be read: {source}"
        ) from exc

    plan = parse_morning_plan(readme_text)
    snapshot_dir = projects_root() / "job-search" / "market-monitor" / "snapshots"
    return {
        "date": display_day.isoformat(),
        "source": str(source),
        "intro": plan["intro"],
        "steps": plan["steps"],
        "next_morning": plan["next_morning"],
        "snapshots": load_hn_snapshots(snapshot_dir, display_day),
    }
