"""Codebase size scanner, snapshots, score and `pt size` (#8083)."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.crr_manifest import LOCAL_ONLY_TABLES  # noqa: E402
from db.migration_runner import discover_migrations  # noqa: E402
from pt import cli  # noqa: E402
from scripts import codebase_size as cs  # noqa: E402

MIGRATIONS_DIR = Path(__file__).parent.parent / "scripts" / "db" / "migrations"
BASELINE_TS = "2026-01-15T12:00:00+0000"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str, date: str | None = None, data: bytes | None = None) -> str:
    env = dict(os.environ)
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, env=env, input=data,
    )
    return proc.stdout.decode().strip()


def make_repo(root: Path, name: str, files: dict[str, str],
              date: str = "2026-01-01T00:00:00+0000") -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    commit(repo, files, date)
    return repo


def commit(repo: Path, files: dict[str, str], date: str) -> None:
    for rel, content in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "c", date=date)


FILES = {
    "app.py": "a\nb\nc\n",                        # code 3
    "tool.sh": "x\ny",                            # code 2 (unterminated last line)
    "src/mod.ts": "1\n2\n3\n4\n",                 # code 4
    "tests/test_app.py": "t1\nt2\n",              # test 2
    "src/widget.test.ts": "w\n",                  # test 1
    "pkg/helper_test.go": "g\ng\ng\n",            # test 3
    "node_modules/lib/index.js": "n\n" * 50,      # skipped
    "scripts/db/migrations/001_x.py": "m\n" * 9,  # skipped
    "web/app.min.js": "z\n" * 7,                  # skipped
    "package-lock.json": "{}\n",                  # not code anyway
    "data/fixture.py": "d\n" * 11,                # skipped (data/)
    "README.md": "r1\nr2\nr3\n",                  # doc 3 lines
    "docs/guide.md": "g1\ng2",                    # doc 2 lines
    "notes.txt": "ignored\n",                     # not code
}

EXPECTED = (9, 6, 2, 5)  # code, tests, doc_files, doc_lines


def survey(repo: Path) -> tuple[int, int, int]:
    """Independent re-implementation of the 2026-10-08 survey loop."""
    code_re = re.compile(r"\.(py|js|ts|tsx|jsx|sh|swift|go|rs|mjs|cjs)$")
    skip_re = re.compile(
        r"(^|/)(node_modules|vendor|dist|build|\.venv|venv|migrations|fixtures|data)/"
        r"|\.min\.js$|package-lock|\.lock$"
    )
    test_re = re.compile(
        r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|_test\.|\.test\.|\.spec\."
    )
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split("\n")
    code = test = docs = 0
    for f in out:
        if not f or skip_re.search(f):
            continue
        if f.endswith(".md"):
            docs += 1
            continue
        if not code_re.search(f):
            continue
        n = sum(1 for _ in open(repo / f, errors="ignore"))
        if test_re.search(f):
            test += n
        else:
            code += n
    return code, test, docs


@pytest.fixture
def mgr():
    from db.manager import DatabaseManager

    return DatabaseManager()


@pytest.fixture
def conn():
    db = sqlite3.connect(os.environ["PT_DB_PATH"])
    yield db
    db.close()


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------


def test_classification_and_line_counts(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "proj", FILES)
    size = cs.scan_repo(repo)
    assert size.error is None
    assert (size.code, size.tests, size.doc_files, size.doc_lines) == EXPECTED
    assert (size.code, size.tests, size.doc_files) == survey(repo)
    assert size.last_commit == "2026-01-01"


def test_listed_but_absent_file_is_skipped_but_git_failure_is_an_error(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "proj", FILES)
    # A path git lists that is not on disk: index entry for a blob with no file.
    blob = _git(repo, "hash-object", "-w", "--stdin", data=b"1\n2\n3\n4\n5\n")
    _git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},ghost.py")
    assert "ghost.py" in _git(repo, "ls-files")
    size = cs.scan_repo(repo)
    assert size.error is None
    assert size.code == EXPECTED[0]  # ghost.py contributes nothing

    broken = tmp_path / "broken"
    (broken / ".git").mkdir(parents=True)
    result = cs.scan_repo(broken)
    assert result.error and "git" in result.error
    assert result.code == 0


def test_portfolio_skips_worktree_dirs_and_non_repos(tmp_path: Path) -> None:
    make_repo(tmp_path, "big", {"a.py": "x\n" * 10})
    make_repo(tmp_path, "small", {"a.py": "x\n"})
    make_repo(tmp_path, "big-wt-feature", {"a.py": "x\n" * 99})
    (tmp_path / "plain").mkdir()
    rows = cs.scan_portfolio(tmp_path)
    assert [(r.project, r.code) for r in rows] == [("big", 10), ("small", 1)]


# ---------------------------------------------------------------------------
# history scan
# ---------------------------------------------------------------------------


def test_scan_repo_at_reproduces_commit_and_ignores_later_commits(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "proj", FILES, date="2026-01-01T00:00:00+0000")
    commit(repo, {"big.py": "x\n" * 1000, "more.md": "d\n" * 40}, "2026-03-01T00:00:00+0000")
    assert cs.scan_repo(repo).code == EXPECTED[0] + 1000

    then = cs.scan_repo_at(repo, BASELINE_TS)
    assert then.error is None
    assert (then.code, then.tests, then.doc_files, then.doc_lines) == EXPECTED
    assert then.last_commit == "2026-01-01"
    assert then.commits_90d == 1


def test_scan_repo_at_before_first_commit_is_an_error(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "proj", FILES, date="2026-01-01T00:00:00+0000")
    result = cs.scan_repo_at(repo, "2025-01-01T00:00:00+0000")
    assert result.error and "no commit" in result.error


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


def _size(code=100, tests=50, doc_files=2, doc_lines=40) -> cs.RepoSize:
    return cs.RepoSize("p", code, tests, doc_files, doc_lines)


def test_score_shrink_is_positive() -> None:
    score = cs.optimization_score(_size(), _size(code=70))
    assert score == pytest.approx(30 / 140 * 100)
    assert score > 0


def test_score_growth_is_negative() -> None:
    assert cs.optimization_score(_size(), _size(code=200)) < 0


def test_score_moving_docs_into_code_is_neutral() -> None:
    assert cs.optimization_score(_size(), _size(code=130, doc_lines=10)) == 0.0


def test_score_deleting_redundant_docs_is_positive() -> None:
    assert cs.optimization_score(_size(), _size(doc_lines=10)) > 0


def test_score_ignores_test_lines() -> None:
    assert cs.optimization_score(_size(), _size(tests=0)) == 0.0
    assert cs.optimization_score(_size(), _size(tests=5000)) == 0.0


def test_score_none_without_usable_baseline() -> None:
    assert cs.optimization_score(None, _size()) is None
    assert cs.optimization_score(_size(code=0, doc_lines=0), _size()) is None


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------


def _rows(conn, kind, date="2026-10-08"):
    return conn.execute(
        "SELECT project, code_lines FROM codebase_size_snapshots "
        "WHERE kind=? AND snapshot_date=? ORDER BY project", (kind, date)
    ).fetchall()


def test_same_day_same_kind_replaces(mgr, conn) -> None:
    mgr.save_codebase_snapshot([cs.RepoSize("a", code=1), cs.RepoSize("b", code=2)], "scan", "2026-10-08")
    mgr.save_codebase_snapshot([cs.RepoSize("a", code=9)], "scan", "2026-10-08")
    assert _rows(conn, "scan") == [("a", 9), ("b", 2)]


def test_scan_does_not_overwrite_baseline_on_same_date(mgr, conn) -> None:
    mgr.save_codebase_snapshot([cs.RepoSize("a", code=100)], "baseline", "2026-10-08")
    mgr.save_codebase_snapshot([cs.RepoSize("a", code=80)], "scan", "2026-10-08")
    assert _rows(conn, "baseline") == [("a", 100)]
    assert _rows(conn, "scan") == [("a", 80)]
    date, base = mgr.codebase_baseline()
    assert date == "2026-10-08" and base["a"].code == 100
    date, scan = mgr.codebase_latest_scan()
    assert scan["a"].code == 80


def test_save_refuses_errored_rows_and_bad_kind(mgr, conn) -> None:
    with pytest.raises(ValueError):
        mgr.save_codebase_snapshot([cs.RepoSize("a", error="boom")], "scan", "2026-10-08")
    with pytest.raises(ValueError):
        mgr.save_codebase_snapshot([cs.RepoSize("a")], "weekly", "2026-10-08")
    assert _rows(conn, "scan") == []


# ---------------------------------------------------------------------------
# import_baseline
# ---------------------------------------------------------------------------


def _baseline_file(path: Path, rows: list[tuple]) -> Path:
    lines = ["   code   tests  docs       last  c90  project"]
    for code, tests, docs, project in rows:
        lines.append(f"{code:>7} {tests:>7} {docs:>5} 2026-01-01    1  {project}")
    lines.append("TOTAL code 0 tests 0 docs 0 repos 0")
    path.write_text("\n".join(lines) + "\n")
    return path


def test_import_baseline_stores_rows_with_doc_lines(tmp_path: Path, mgr, conn) -> None:
    make_repo(tmp_path, "proj", FILES)
    make_repo(tmp_path, "other", {"x.py": "1\n2\n"})
    file = _baseline_file(tmp_path / "base.txt", [(9, 6, 2, "proj"), (2, 0, 0, "other")])
    assert len(mgr.import_codebase_baseline(file, BASELINE_TS, tmp_path)) == 2
    stored = conn.execute(
        "SELECT project, code_lines, test_lines, doc_files, doc_lines, kind, snapshot_date "
        "FROM codebase_size_snapshots ORDER BY project"
    ).fetchall()
    assert stored == [
        ("other", 2, 0, 0, 0, "baseline", "2026-01-15"),
        ("proj", 9, 6, 2, 5, "baseline", "2026-01-15"),
    ]
    mgr.import_codebase_baseline(file, BASELINE_TS, tmp_path)  # re-import replaces
    assert conn.execute("SELECT COUNT(*) FROM codebase_size_snapshots").fetchone()[0] == 2


def test_import_baseline_mismatch_or_unknown_stores_nothing(tmp_path: Path, mgr, conn) -> None:
    make_repo(tmp_path, "proj", FILES)
    make_repo(tmp_path, "other", {"x.py": "1\n2\n"})
    file = _baseline_file(
        tmp_path / "base.txt",
        [(9, 6, 2, "proj"), (3, 0, 0, "other"), (1, 0, 0, "ghost")],
    )
    with pytest.raises(cs.BaselineMismatch) as err:
        mgr.import_codebase_baseline(file, BASELINE_TS, tmp_path)
    assert "other" in str(err.value) and "ghost" in str(err.value)
    assert "proj:" not in str(err.value)
    assert conn.execute("SELECT COUNT(*) FROM codebase_size_snapshots").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# migration 017
# ---------------------------------------------------------------------------


def _m(version: int):
    return next(m for m in discover_migrations(MIGRATIONS_DIR) if m.version == version)


def test_migration_017_on_fresh_db_and_after_015(tmp_path: Path) -> None:
    fresh = sqlite3.connect(tmp_path / "fresh.db")
    _m(17).up(fresh)
    _m(17).up(fresh)  # idempotent
    cols = [r[1] for r in fresh.execute("PRAGMA table_info(codebase_size_snapshots)")]
    assert cols == [
        "id", "snapshot_date", "kind", "project", "code_lines", "test_lines",
        "doc_files", "doc_lines", "last_commit", "commits_90d", "scanned_at",
    ]
    with pytest.raises(sqlite3.IntegrityError):
        fresh.execute(
            "INSERT INTO codebase_size_snapshots (snapshot_date, kind, project, code_lines,"
            " test_lines, doc_files, doc_lines, scanned_at) VALUES ('d','bogus','p',0,0,0,0,'t')"
        )

    after = sqlite3.connect(tmp_path / "after.db")
    _m(15).up(after)
    _m(17).up(after)
    tables = {r[0] for r in after.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"outreach_contacts", "codebase_size_snapshots"} <= tables


def test_table_is_local_only_and_migration_declares_no_crr() -> None:
    assert "codebase_size_snapshots" in LOCAL_ONLY_TABLES
    assert _m(17).crr_tables == frozenset()


# ---------------------------------------------------------------------------
# pt size CLI
# ---------------------------------------------------------------------------

_ENV = {"PT_SKIP_DOPPLER": "1", "PT_NO_BANNER": "1", "PT_SUPPRESS_MIGRATION_WARNING": "1"}


def _pt(monkeypatch, root: Path, args: list[str]):
    monkeypatch.setenv("PROJECTS_ROOT", str(root))
    return CliRunner().invoke(cli, args, env=dict(_ENV))


def test_pt_size_json_snapshot_and_score(tmp_path: Path, monkeypatch, conn) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    repo = make_repo(root, "proj", FILES)
    file = _baseline_file(tmp_path / "base.txt", [(9, 6, 2, "proj")])

    result = _pt(monkeypatch, root, ["size", "--json"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)["rows"][0]
    assert (row["project"], row["code"], row["tests"], row["doc_files"], row["doc_lines"]) == (
        "proj", 9, 6, 2, 5)
    assert row["score"] is None  # no baseline yet

    result = _pt(monkeypatch, root, ["size", "import-baseline", str(file), "--at", BASELINE_TS])
    assert result.exit_code == 0, result.output

    commit(repo, {"app.py": "a\n"}, "2026-02-01T00:00:00+0000")  # code 9 -> 7
    result = _pt(monkeypatch, root, ["size", "--json", "--snapshot"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["baseline_date"] == "2026-01-15"
    assert payload["rows"][0]["code"] == 7
    assert payload["rows"][0]["score"] == pytest.approx(2 / 14 * 100)
    assert payload["total"]["score"] == pytest.approx(2 / 14 * 100)
    assert conn.execute(
        "SELECT code_lines FROM codebase_size_snapshots WHERE kind='scan'"
    ).fetchall() == [(7,)]

    text = _pt(monkeypatch, root, ["size"])
    assert text.exit_code == 0
    assert "TOTAL code 7" in text.output and "+14.3" in text.output


def test_pt_size_import_baseline_mismatch_exits_nonzero(tmp_path: Path, monkeypatch, conn) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    make_repo(root, "proj", FILES)
    file = _baseline_file(tmp_path / "base.txt", [(10, 6, 2, "proj")])
    result = _pt(monkeypatch, root, ["size", "import-baseline", str(file), "--at", BASELINE_TS])
    assert result.exit_code != 0
    assert "proj" in result.output
    assert conn.execute("SELECT COUNT(*) FROM codebase_size_snapshots").fetchone()[0] == 0


def test_pt_size_reports_failing_repo_and_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    make_repo(root, "good", {"a.py": "x\n"})
    (root / "bad" / ".git").mkdir(parents=True)
    result = _pt(monkeypatch, root, ["size", "--json"])
    assert result.exit_code == 1
    assert "bad" in result.output


def test_pt_size_missing_table_fails_before_scanning(tmp_path: Path, monkeypatch, conn) -> None:
    conn.execute("DROP TABLE codebase_size_snapshots")
    conn.commit()

    def boom(*_a, **_k):
        raise AssertionError("scan must not run when the table is missing")

    monkeypatch.setattr(cs, "scan_portfolio", boom)
    result = _pt(monkeypatch, tmp_path, ["size", "--json"])
    assert result.exit_code != 0
    assert "pt db migrate" in result.output


def test_score_text_never_shows_negative_zero():
    from pt import _size_score_text

    assert _size_score_text(None) == "-"
    assert _size_score_text(-0.006) == "+0.0"
    assert _size_score_text(-0.06) == "-0.1"
    assert _size_score_text(12.34) == "+12.3"
