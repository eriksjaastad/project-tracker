"""Codebase size scanner and optimization score (#8083).

Measures how much code and documentation each git repo under the projects root
carries and scores a repo against its baseline. Dated snapshots are stored by
``db.codebase_size.CodebaseSizeMixin`` in ``codebase_size_snapshots``; this
module has no database code.

Optimization score, verbatim::

    score = (baseline_lean - current_lean) / baseline_lean * 100

where ``lean`` = non-test code lines + markdown doc lines. Positive = leaner.
Tests are shown but excluded so cutting tests cannot raise the score. Doc LINES
(not files) are counted so moving a doc into docstrings scores neutral, while
deleting redundant docs or code scores positive. The score is ``None`` when the
repo has no baseline row or ``baseline_lean`` is 0.

Classification (CODE / SKIP / TEST regexes and the line-count rule) is the
same as the 2026-10-08 portfolio survey so totals match it exactly. The
baseline is a ``kind='baseline'`` row; a ``kind='scan'`` row on the same date
never overwrites it because ``kind`` is part of the unique key.

Failure handling: every git call has a timeout and a checked return code. A
repo whose git call fails is reported with ``error`` set and is never counted
as zero lines. A file git lists but that is gone from disk is an expected
absence and is skipped; nothing else is swallowed.
"""

from __future__ import annotations

import io
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

CODE = re.compile(r"\.(py|js|ts|tsx|jsx|sh|swift|go|rs|mjs|cjs)$")
SKIP = re.compile(
    r"(^|/)(node_modules|vendor|dist|build|\.venv|venv|migrations|fixtures|data)/"
    r"|\.min\.js$|package-lock|\.lock$"
)
TEST = re.compile(
    r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|_test\.|\.test\.|\.spec\."
)

GIT_TIMEOUT = 60
GIT_BULK_TIMEOUT = 300
RECENT_DAYS = 90


class GitError(RuntimeError):
    """A git call timed out or exited nonzero."""


class BaselineMismatch(ValueError):
    """The baseline file does not match what git history reproduces."""


@dataclass(frozen=True)
class RepoSize:
    project: str
    code: int = 0
    tests: int = 0
    doc_files: int = 0
    doc_lines: int = 0
    last_commit: Optional[str] = None
    commits_90d: Optional[int] = None
    error: Optional[str] = None

    @property
    def lean(self) -> int:
        return self.code + self.doc_lines

    def as_dict(self) -> dict:
        return {
            "project": self.project,
            "code": self.code,
            "tests": self.tests,
            "doc_files": self.doc_files,
            "doc_lines": self.doc_lines,
            "last_commit": self.last_commit,
            "commits_90d": self.commits_90d,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# git + counting helpers
# ---------------------------------------------------------------------------


def _git(path: Path, *args: str, input: Optional[bytes] = None,
         timeout: int = GIT_TIMEOUT) -> bytes:
    cmd = ["git", "-C", str(path), *args]
    try:
        proc = subprocess.run(
            cmd, input=input, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} timed out after {timeout}s") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()[:200]
        raise GitError(f"git {args[0]} exited {proc.returncode}: {detail}")
    return proc.stdout


def count_lines(data: bytes) -> int:
    """Number of lines, counting a final unterminated line (survey rule)."""
    stream = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", errors="ignore")
    return sum(1 for _ in stream)


def _classify(files_with_counts: Iterable[tuple[str, int]]) -> tuple[int, int, int, int]:
    """(code, tests, doc_files, doc_lines) from (path, line_count) pairs."""
    code = tests = doc_files = doc_lines = 0
    for path, n in files_with_counts:
        if path.endswith(".md"):
            doc_files += 1
            doc_lines += n
        elif TEST.search(path):
            tests += n
        else:
            code += n
    return code, tests, doc_files, doc_lines


def _wanted(path: str) -> bool:
    """Counted paths: not skipped, and either markdown or a code extension."""
    if not path or SKIP.search(path):
        return False
    return path.endswith(".md") or bool(CODE.search(path))


def _activity(path: Path) -> tuple[str, int]:
    last = _git(path, "log", "-1", "--format=%cs").decode().strip()
    count = _git(
        path, "rev-list", "--count", f"--since={RECENT_DAYS} days ago", "HEAD"
    ).decode().strip()
    return last, int(count)


# ---------------------------------------------------------------------------
# scanning
# ---------------------------------------------------------------------------


def scan_repo(path: Path) -> RepoSize:
    """Measure the working tree of one git repo."""
    path = Path(path)
    name = path.name
    try:
        listed = _git(path, "ls-files", "-z").decode("utf-8", "replace").split("\0")
        counts: list[tuple[str, int]] = []
        for rel in listed:
            if not _wanted(rel):
                continue
            try:
                data = (path / rel).read_bytes()
            except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
                # Listed by git, absent on disk: expected. The survey counts a
                # tracked .md without opening it, so keep it as a 0-line doc.
                if rel.endswith(".md"):
                    counts.append((rel, 0))
                continue
            counts.append((rel, count_lines(data)))
        last, c90 = _activity(path)
    except (GitError, OSError) as exc:
        return RepoSize(project=name, error=str(exc))
    code, tests, doc_files, doc_lines = _classify(counts)
    return RepoSize(name, code, tests, doc_files, doc_lines, last, c90)


def scan_repo_at(path: Path, timestamp: str) -> RepoSize:
    """Rebuild the numbers for one repo from git history at ``timestamp``.

    Uses the last commit at or before the timestamp on HEAD's history, so
    later commits and the working tree are ignored.
    """
    path = Path(path)
    name = path.name
    try:
        since = int(datetime.fromisoformat(timestamp).timestamp()) - RECENT_DAYS * 86400
        sha = _git(path, "rev-list", "-1", f"--before={timestamp}", "HEAD").decode().strip()
        if not sha:
            return RepoSize(project=name, error=f"no commit at or before {timestamp}")
        tree = _git(path, "ls-tree", "-r", "-z", sha).decode("utf-8", "replace")
        wanted: list[tuple[str, str]] = []  # (path, blob id)
        for entry in tree.split("\0"):
            if not entry:
                continue
            meta, _, rel = entry.partition("\t")
            _mode, kind, blob = meta.split(" ")
            if kind == "blob" and _wanted(rel):
                wanted.append((rel, blob))
        counts = _blob_line_counts(path, wanted)
        last = _git(path, "log", "-1", "--format=%cs", sha).decode().strip()
        c90 = _git(
            path, "rev-list", "--count",
            f"--since={since}", sha,
        ).decode().strip()
    except (GitError, ValueError) as exc:
        return RepoSize(project=name, error=str(exc))
    code, tests, doc_files, doc_lines = _classify(counts)
    return RepoSize(name, code, tests, doc_files, doc_lines, last, int(c90))


def _blob_line_counts(path: Path, wanted: list[tuple[str, str]]) -> list[tuple[str, int]]:
    if not wanted:
        return []
    request = "".join(f"{blob}\n" for _, blob in wanted).encode()
    out = _git(path, "cat-file", "--batch", input=request, timeout=GIT_BULK_TIMEOUT)
    counts: list[tuple[str, int]] = []
    pos = 0
    for rel, blob in wanted:
        end = out.index(b"\n", pos)
        header = out[pos:end].split()
        if len(header) != 3 or header[1] != b"blob":
            raise GitError(f"git cat-file returned {out[pos:end]!r} for {rel}")
        size = int(header[2])
        body = out[end + 1:end + 1 + size]
        pos = end + 1 + size + 1
        counts.append((rel, count_lines(body)))
    return counts


def _project_dirs(root: Path) -> list[Path]:
    return [
        p for p in sorted(root.iterdir())
        if (p / ".git").is_dir() and "-wt-" not in p.name
    ]


def scan_portfolio(root: Optional[Path] = None) -> list[RepoSize]:
    """Scan every git repo under the projects root, sorted by code descending."""
    if root is None:
        from scripts.config import projects_root
        root = projects_root()
    rows = [scan_repo(p) for p in _project_dirs(Path(root))]
    return sorted(rows, key=lambda r: (r.code, r.tests, r.doc_files, r.project), reverse=True)


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


def optimization_score(baseline: Optional[RepoSize], current: RepoSize) -> Optional[float]:
    """(baseline_lean - current_lean) / baseline_lean * 100, or None."""
    if baseline is None or baseline.lean == 0:
        return None
    return (baseline.lean - current.lean) / baseline.lean * 100


# ---------------------------------------------------------------------------
# baseline file
# ---------------------------------------------------------------------------


def parse_baseline_file(file: Path) -> dict[str, tuple[int, int, int]]:
    """Rows ``code tests docs last c90 project`` -> {project: (code, tests, docs)}."""
    parsed: dict[str, tuple[int, int, int]] = {}
    for line in Path(file).read_text().splitlines():
        parts = line.split()
        if len(parts) == 6 and parts[0].isdigit():
            parsed[parts[5]] = (int(parts[0]), int(parts[1]), int(parts[2]))
    if not parsed:
        raise BaselineMismatch(f"no baseline rows found in {file}")
    return parsed


def baseline_date(at: str) -> str:
    """The date part of an ISO timestamp."""
    try:
        return datetime.fromisoformat(at).date().isoformat()
    except ValueError as exc:
        raise ValueError(f"--at must be an ISO timestamp, got {at!r}") from exc


def verify_baseline(file: Path, at: str, root: Optional[Path] = None) -> list[RepoSize]:
    """Rebuild each repo listed in ``file`` from git at ``at`` and verify.

    Returns the rebuilt rows (with doc_lines) when code/tests/doc_files equal
    the file for every repo. Raises BaselineMismatch naming every repo that is
    unknown, unmeasurable or different.
    """
    try:
        datetime.fromisoformat(at)
    except ValueError as exc:
        raise ValueError(f"--at must be an ISO timestamp, got {at!r}") from exc
    if root is None:
        from scripts.config import projects_root
        root = projects_root()
    root = Path(root)
    expected = parse_baseline_file(file)
    problems: list[str] = []
    rebuilt: list[RepoSize] = []
    for project, want in sorted(expected.items()):
        repo = root / project
        if not (repo / ".git").is_dir():
            problems.append(f"{project}: unknown repo (no git repo at {repo})")
            continue
        size = scan_repo_at(repo, at)
        if size.error:
            problems.append(f"{project}: {size.error}")
        elif (size.code, size.tests, size.doc_files) != want:
            problems.append(
                f"{project}: file has code/tests/docs {want}, "
                f"git at {at} gives {(size.code, size.tests, size.doc_files)}"
            )
        else:
            rebuilt.append(size)
    if problems:
        raise BaselineMismatch("baseline does not match git history:\n  " + "\n  ".join(problems))
    return rebuilt
