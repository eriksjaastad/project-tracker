"""Codebase size scanner and optimization score (#8083).

Measures how much code and documentation each git repo under the projects root
carries and scores a repo against its baseline. Dated snapshots are stored by
``db.codebase_size.CodebaseSizeMixin`` in ``codebase_size_snapshots``; this
module has no database code.

Optimization score, verbatim::

    score = (baseline_lean - current_lean) / baseline_lean * 100

where ``lean`` = non-test code lines + markdown doc lines, and the baseline
is the repo's 2026-10-08 measurement (``BASELINE_DATE``). Positive = leaner.
Tests are shown but excluded so cutting tests cannot raise the score. Doc LINES
(not files) are counted so moving a doc into docstrings scores neutral, while
deleting redundant docs or code scores positive. The score is ``None`` when the
repo has no baseline row or ``baseline_lean`` is 0.

Classification (CODE / SKIP / TEST regexes and the line-count rule) is the
same as the 2026-10-08 portfolio survey so totals match it exactly. The
baseline is imported once from that survey and is immutable; scans are
appended as runs and never replace it.

Failure handling: every git call has a timeout and a checked return code. A
repo whose git call fails is reported with ``error`` set and is never counted
as zero lines. A file git lists but that is gone from disk is an expected
absence and is skipped; nothing else is swallowed. A missing projects root
raises ProjectsRootMissing rather than reading as an empty portfolio.
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
# The score's fixed reference point: the Architect's 2026-10-08 survey.
BASELINE_DATE = "2026-10-08"


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


def _has_commits(path: Path) -> bool:
    """False for an unborn HEAD (``git init`` with no commit yet)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--verify", "-q", "HEAD"],
            capture_output=True, timeout=GIT_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git rev-parse timed out after {GIT_TIMEOUT}s") from exc
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False  # no HEAD commit yet: an expected state, measured as no activity
    detail = proc.stderr.decode("utf-8", "replace").strip()[:200]
    raise GitError(f"git rev-parse exited {proc.returncode}: {detail}")


def _activity(path: Path) -> tuple[Optional[str], int]:
    if not _has_commits(path):
        return None, 0
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


def parse_at(timestamp: str) -> datetime:
    """Parse an ISO timestamp that names one instant, or raise ValueError.

    A date-only or naive value is refused: git and Python could read it in
    different time zones and pick different commits.
    """
    try:
        when = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise ValueError(f"--at must be an ISO timestamp, got {timestamp!r}") from exc
    if when.tzinfo is None:
        raise ValueError(
            f"--at must include a UTC offset, e.g. 2026-10-08T10:41:29-0400; got {timestamp!r}"
        )
    return when


def scan_repo_at(path: Path, timestamp: str) -> RepoSize:
    """Rebuild the numbers for one repo from git history at ``timestamp``.

    Uses the last commit at or before the timestamp on HEAD's first-parent
    (mainline) history, so branch commits merged later, later commits and
    the working tree are ignored.
    """
    path = Path(path)
    name = path.name
    try:
        when = parse_at(timestamp)
        since = int(when.timestamp()) - RECENT_DAYS * 86400
        # Give git the same instant Python parsed, as a Unix epoch. Follow
        # first parents only: a branch merged after ``when`` can carry commits
        # dated before it that were never on the mainline at that moment.
        sha = _git(
            path, "rev-list", "-1", "--first-parent",
            f"--before={int(when.timestamp())}", "HEAD",
        ).decode().strip()
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


class ProjectsRootMissing(FileNotFoundError):
    """The projects root does not exist or is not a directory."""


def _project_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        raise ProjectsRootMissing(f"projects root {root} does not exist")
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


_SURVEY_HEADER = ["code", "tests", "docs", "last", "c90", "project"]
_SURVEY_ROW = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)\s+(\S+)\s*$"
)
_SURVEY_TOTAL = re.compile(r"^TOTAL code (\d+) tests (\d+) docs (\d+) repos (\d+)\s*$")


def parse_baseline_file(file: Path) -> dict[str, tuple[int, int, int]]:
    """Rows ``code tests docs last c90 project`` -> {project: (code, tests, docs)}.

    Strict: every non-blank line must be the survey header, a repo row or the
    single TOTAL line, no repo may repeat, and the TOTAL must equal the rows'
    sums and count. A damaged file raises BaselineMismatch instead of
    importing as a partial baseline.
    """
    lines = [line for line in Path(file).read_text().splitlines() if line.strip()]
    if not lines or lines[0].split() != _SURVEY_HEADER:
        raise BaselineMismatch(f"{file}: first line is not the survey header")
    parsed: dict[str, tuple[int, int, int]] = {}
    total: Optional[tuple[int, int, int, int]] = None
    problems: list[str] = []
    for number, line in enumerate(lines[1:], start=2):
        match = _SURVEY_TOTAL.match(line)
        if match:
            if total is not None:
                problems.append(f"line {number}: a second TOTAL line")
            total = tuple(int(g) for g in match.groups())  # type: ignore[assignment]
            continue
        match = _SURVEY_ROW.match(line)
        if not match:
            problems.append(f"line {number}: not a repo row: {line.strip()!r}")
            continue
        if total is not None:
            problems.append(f"line {number}: repo row after the TOTAL line")
        project = match.group(6)
        if project in parsed:
            problems.append(f"line {number}: {project} appears twice")
        parsed[project] = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    if not parsed:
        problems.append("no repo rows")
    if total is None:
        problems.append("no TOTAL line")
    else:
        sums = (
            sum(v[0] for v in parsed.values()),
            sum(v[1] for v in parsed.values()),
            sum(v[2] for v in parsed.values()),
            len(parsed),
        )
        if sums != total:
            problems.append(
                f"TOTAL line says code/tests/docs/repos {total}, rows add up to {sums}"
            )
    if problems:
        raise BaselineMismatch(
            f"{file} is not a complete survey output:\n  " + "\n  ".join(problems)
        )
    return parsed


def baseline_date(at: str) -> str:
    """The date part of an ISO timestamp, in the timestamp's own offset."""
    return parse_at(at).date().isoformat()


def verify_baseline(file: Path, at: str, root: Optional[Path] = None) -> list[RepoSize]:
    """Rebuild each repo listed in ``file`` from git at ``at`` and verify.

    Returns the rebuilt rows (with doc_lines) when code/tests/doc_files equal
    the file for every repo. Raises BaselineMismatch naming every repo that is
    unknown, unmeasurable or different.
    """
    parse_at(at)
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
