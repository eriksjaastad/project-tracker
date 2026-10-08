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
# Imports are pinned to cs.BASELINE_DATE; the real survey was written at this instant.
IMPORT_TS = "2026-10-08T10:41:29-0400"


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
# storage (append-only runs)
# ---------------------------------------------------------------------------


def _count(conn, kind=None) -> int:
    if kind is None:
        return conn.execute("SELECT COUNT(*) FROM codebase_size_snapshots").fetchone()[0]
    return conn.execute(
        "SELECT COUNT(*) FROM codebase_size_snapshots WHERE kind = ?", (kind,)
    ).fetchone()[0]


def test_scan_runs_append_and_the_newest_complete_run_is_read(mgr, conn) -> None:
    first = mgr.save_codebase_scan([cs.RepoSize("a", code=1), cs.RepoSize("b", code=2)], "2026-10-08")
    second = mgr.save_codebase_scan([cs.RepoSize("a", code=9)], "2026-10-08")
    assert first != second
    # Nothing was replaced or deleted: both runs are stored.
    assert _count(conn, "scan") == 3
    # b left the projects root between the runs; the newest run is read whole,
    # so b does not leak in from the first run.
    date, scan = mgr.codebase_latest_scan()
    assert date == "2026-10-08"
    assert {p: r.code for p, r in scan.items()} == {"a": 9}


def test_save_refuses_errored_empty_or_duplicate_sets_before_any_write(mgr, conn) -> None:
    mgr.save_codebase_scan([cs.RepoSize("a", code=5)], "2026-10-08")
    with pytest.raises(ValueError, match="errored"):
        mgr.save_codebase_scan([cs.RepoSize("a", error="boom")], "2026-10-08")
    with pytest.raises(ValueError, match="empty"):
        mgr.save_codebase_scan([], "2026-10-08")
    with pytest.raises(ValueError, match="duplicate"):
        mgr.save_codebase_scan([cs.RepoSize("b"), cs.RepoSize("b")], "2026-10-08")
    assert _count(conn) == 1
    assert mgr.codebase_latest_scan()[1]["a"].code == 5


def test_table_refuses_update_and_delete(mgr, conn) -> None:
    mgr.save_codebase_scan([cs.RepoSize("a", code=5)], "2026-10-08")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE codebase_size_snapshots SET code_lines = 0")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM codebase_size_snapshots")
    conn.rollback()
    assert _count(conn) == 1


# ---------------------------------------------------------------------------
# baseline import (pinned to 2026-10-08, immutable)
# ---------------------------------------------------------------------------


def _baseline_file(path: Path, rows: list[tuple]) -> Path:
    lines = ["   code   tests  docs       last  c90  project"]
    for code, tests, docs, project in rows:
        lines.append(f"{code:>7} {tests:>7} {docs:>5} 2026-01-01    1  {project}")
    lines.append(
        f"TOTAL code {sum(r[0] for r in rows)} tests {sum(r[1] for r in rows)} "
        f"docs {sum(r[2] for r in rows)} repos {len(rows)}"
    )
    path.write_text("\n".join(lines) + "\n")
    return path


def test_import_baseline_stores_rows_with_doc_lines(tmp_path: Path, mgr, conn) -> None:
    make_repo(tmp_path, "proj", FILES)
    make_repo(tmp_path, "other", {"x.py": "1\n2\n"})
    file = _baseline_file(tmp_path / "base.txt", [(9, 6, 2, "proj"), (2, 0, 0, "other")])
    assert len(mgr.import_codebase_baseline(file, IMPORT_TS, tmp_path)) == 2
    stored = conn.execute(
        "SELECT project, code_lines, test_lines, doc_files, doc_lines, kind, snapshot_date "
        "FROM codebase_size_snapshots ORDER BY project"
    ).fetchall()
    assert stored == [
        ("other", 2, 0, 0, 0, "baseline", "2026-10-08"),
        ("proj", 9, 6, 2, 5, "baseline", "2026-10-08"),
    ]
    date, base = mgr.codebase_baseline()
    assert date == cs.BASELINE_DATE and base["proj"].doc_lines == 5


def test_baseline_is_immutable_once_stored(tmp_path: Path, mgr, conn) -> None:
    make_repo(tmp_path, "proj", FILES)
    make_repo(tmp_path, "other", {"x.py": "1\n2\n"})
    both = _baseline_file(tmp_path / "both.txt", [(9, 6, 2, "proj"), (2, 0, 0, "other")])
    mgr.import_codebase_baseline(both, IMPORT_TS, tmp_path)
    one = _baseline_file(tmp_path / "one.txt", [(9, 6, 2, "proj")])
    with pytest.raises(ValueError, match="immutable"):
        mgr.import_codebase_baseline(one, IMPORT_TS, tmp_path)
    assert _count(conn, "baseline") == 2
    # The database itself allows one baseline row per project.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO codebase_size_snapshots (run_id, kind, snapshot_date, project, "
            "code_lines, test_lines, doc_files, doc_lines, scanned_at) "
            "VALUES ('r2', 'baseline', '2026-10-08', 'proj', 1, 0, 0, 0, 't')"
        )
    conn.rollback()
    # A scan never touches it.
    mgr.save_codebase_scan([cs.RepoSize("proj", code=1)], "2026-10-08")
    assert mgr.codebase_baseline()[1]["proj"].code == 9


@pytest.mark.parametrize("at", [BASELINE_TS, "2026-10-09T10:00:00-0400", "2026-10-07T23:00:00-0400"])
def test_baseline_on_any_other_date_is_refused(tmp_path: Path, mgr, conn, at: str) -> None:
    make_repo(tmp_path, "proj", FILES)
    file = _baseline_file(tmp_path / "base.txt", [(9, 6, 2, "proj")])
    with pytest.raises(ValueError, match="pinned"):
        mgr.import_codebase_baseline(file, at, tmp_path)
    assert _count(conn) == 0


def test_import_baseline_mismatch_or_unknown_stores_nothing(tmp_path: Path, mgr, conn) -> None:
    make_repo(tmp_path, "proj", FILES)
    make_repo(tmp_path, "other", {"x.py": "1\n2\n"})
    file = _baseline_file(
        tmp_path / "base.txt",
        [(9, 6, 2, "proj"), (3, 0, 0, "other"), (1, 0, 0, "ghost")],
    )
    with pytest.raises(cs.BaselineMismatch) as err:
        mgr.import_codebase_baseline(file, IMPORT_TS, tmp_path)
    assert "other" in str(err.value) and "ghost" in str(err.value)
    assert "proj:" not in str(err.value)
    assert _count(conn) == 0


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
        "id", "run_id", "kind", "snapshot_date", "project", "code_lines", "test_lines",
        "doc_files", "doc_lines", "last_commit", "commits_90d", "scanned_at",
    ]
    with pytest.raises(sqlite3.IntegrityError):
        fresh.execute(
            "INSERT INTO codebase_size_snapshots (run_id, kind, snapshot_date, project, code_lines,"
            " test_lines, doc_files, doc_lines, scanned_at) VALUES ('r','bogus','d','p',0,0,0,0,'t')"
        )

    after = sqlite3.connect(tmp_path / "after.db")
    _m(15).up(after)
    _m(17).up(after)
    tables = {r[0] for r in after.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"outreach_contacts", "codebase_size_snapshots"} <= tables


def _codebase_objects(db: sqlite3.Connection) -> dict[str, str]:
    return {
        name: " ".join(sql.split())
        for name, sql in db.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE tbl_name = 'codebase_size_snapshots' AND sql IS NOT NULL"
        )
    }


def test_schema_py_and_migration_017_create_the_same_objects(tmp_path: Path, conn) -> None:
    migrated = sqlite3.connect(tmp_path / "migrated.db")
    _m(17).up(migrated)
    expected = _codebase_objects(migrated)
    assert set(expected) == {
        "codebase_size_snapshots", "idx_codebase_size_one_baseline",
        "idx_codebase_size_kind_id", "codebase_size_snapshots_no_update",
        "codebase_size_snapshots_no_delete", "codebase_size_one_baseline_run",
    }
    # `conn` is the per-test DB that schema.py built.
    assert _codebase_objects(conn) == expected


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

    result = _pt(monkeypatch, root, ["size", "import-baseline", str(file), "--at", IMPORT_TS])
    assert result.exit_code == 0, result.output

    commit(repo, {"app.py": "a\n"}, "2026-02-01T00:00:00+0000")  # code 9 -> 7
    result = _pt(monkeypatch, root, ["size", "--json", "--snapshot"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["baseline_date"] == "2026-10-08"
    assert payload["rows"][0]["code"] == 7
    assert payload["rows"][0]["score"] == pytest.approx(2 / 14 * 100)
    assert payload["total"]["score"] == pytest.approx(2 / 14 * 100)
    assert conn.execute(
        "SELECT code_lines FROM codebase_size_snapshots WHERE kind='scan'"
    ).fetchall() == [(7,)]
    # A second same-day snapshot appends a run; the first stays stored.
    assert _pt(monkeypatch, root, ["size", "--snapshot"]).exit_code == 0
    assert _count(conn, "scan") == 2

    text = _pt(monkeypatch, root, ["size"])
    assert text.exit_code == 0
    assert "TOTAL code 7" in text.output and "+14.3" in text.output


def test_pt_size_import_baseline_mismatch_exits_nonzero(tmp_path: Path, monkeypatch, conn) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    make_repo(root, "proj", FILES)
    file = _baseline_file(tmp_path / "base.txt", [(10, 6, 2, "proj")])
    result = _pt(monkeypatch, root, ["size", "import-baseline", str(file), "--at", IMPORT_TS])
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


def test_listed_but_absent_md_counts_as_a_doc_file_like_the_survey(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "proj", FILES)
    blob = _git(repo, "hash-object", "-w", "--stdin", data=b"l1\nl2\n")
    _git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},ghost.md")
    size = cs.scan_repo(repo)
    assert size.error is None
    assert size.doc_files == EXPECTED[2] + 1
    assert size.doc_lines == EXPECTED[3]  # nothing on disk to count
    assert (size.code, size.tests, size.doc_files) == survey(repo)


def test_scan_repo_at_counts_empty_blobs_as_zero_lines(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "proj", {**FILES, "empty.py": "", "empty.md": ""})
    then = cs.scan_repo_at(repo, BASELINE_TS)
    assert then.error is None
    assert (then.code, then.tests, then.doc_files, then.doc_lines) == (
        EXPECTED[0], EXPECTED[1], EXPECTED[2] + 1, EXPECTED[3])
    now = cs.scan_repo(repo)
    assert (now.code, now.tests, now.doc_files, now.doc_lines) == (
        then.code, then.tests, then.doc_files, then.doc_lines)


def test_pt_size_snapshot_stores_nothing_when_a_repo_fails(tmp_path: Path, monkeypatch, conn) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    make_repo(root, "good", {"a.py": "x\n"})
    (root / "bad" / ".git").mkdir(parents=True)
    result = _pt(monkeypatch, root, ["size", "--json", "--snapshot"])
    assert result.exit_code == 1
    assert "Snapshot NOT stored" in result.output
    assert json.loads(result.output[: result.output.rindex("}") + 1])["snapshot_stored"] is False
    assert conn.execute("SELECT COUNT(*) FROM codebase_size_snapshots").fetchone()[0] == 0


@pytest.mark.parametrize("damage, expected", [
    (lambda t: t.replace("      2       0     0 2026-01-01    1  other\n",
                         "      2       0     0 2026-01-01  other\n"), "not a repo row"),
    (lambda t: t.replace("TOTAL code 11 tests 6 docs 2 repos 2\n", ""), "no TOTAL line"),
    (lambda t: t.replace("repos 2", "repos 3"), "rows add up to"),
    (lambda t: t.replace("      2       0     0 2026-01-01    1  other\n", ""), "rows add up to"),
    (lambda t: t + "      9       6     2 2026-01-01    1  proj\n", "row after the TOTAL"),
    (lambda t: t.replace("   code   tests", "   lines   tests"), "survey header"),
])
def test_damaged_baseline_file_is_refused_and_stores_nothing(
        tmp_path: Path, mgr, conn, damage, expected) -> None:
    make_repo(tmp_path, "proj", FILES)
    make_repo(tmp_path, "other", {"x.py": "1\n2\n"})
    file = _baseline_file(tmp_path / "base.txt", [(9, 6, 2, "proj"), (2, 0, 0, "other")])
    file.write_text(damage(file.read_text()))
    with pytest.raises(cs.BaselineMismatch, match=expected):
        mgr.import_codebase_baseline(file, IMPORT_TS, tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM codebase_size_snapshots").fetchone()[0] == 0


def test_duplicate_repo_row_is_refused(tmp_path: Path) -> None:
    file = _baseline_file(tmp_path / "base.txt", [(9, 6, 2, "proj"), (9, 6, 2, "proj")])
    with pytest.raises(cs.BaselineMismatch, match="appears twice"):
        cs.parse_baseline_file(file)


def test_pt_size_with_no_repos_is_an_error_and_stores_nothing(tmp_path: Path, monkeypatch, conn) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    result = _pt(monkeypatch, root, ["size", "--snapshot"])
    assert result.exit_code != 0
    assert "no git repos found" in result.output
    assert conn.execute("SELECT COUNT(*) FROM codebase_size_snapshots").fetchone()[0] == 0


def test_at_selects_the_same_commit_in_any_offset(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "proj", {"a.py": "1\n"}, date="2026-01-15T10:00:00+0000")
    commit(repo, {"a.py": "1\n2\n3\n"}, "2026-01-15T12:00:00+0000")
    # 11:00Z written three ways: before the second commit.
    for at in ("2026-01-15T11:00:00+00:00", "2026-01-15T07:00:00-04:00", "2026-01-15T20:00:00+09:00"):
        assert cs.scan_repo_at(repo, at).code == 1, at
    # 12:30Z: after the second commit.
    assert cs.scan_repo_at(repo, "2026-01-15T08:30:00-04:00").code == 3
    assert cs.baseline_date("2026-01-15T22:30:00-04:00") == "2026-01-15"


@pytest.mark.parametrize("at", ["2026-01-15", "2026-01-15T11:00:00", "yesterday"])
def test_at_without_an_offset_is_refused(tmp_path: Path, at: str) -> None:
    with pytest.raises(ValueError, match="--at"):
        cs.parse_at(at)
    make_repo(tmp_path, "proj", FILES)
    file = _baseline_file(tmp_path / "base.txt", [(9, 6, 2, "proj")])
    with pytest.raises(ValueError, match="--at"):
        cs.verify_baseline(file, at, tmp_path)


def test_pt_size_with_a_missing_projects_root_is_a_clear_error(tmp_path: Path, monkeypatch, conn) -> None:
    result = _pt(monkeypatch, tmp_path / "does-not-exist", ["size", "--snapshot"])
    assert result.exit_code == 1
    assert "does not exist" in result.output
    assert "Traceback" not in result.output
    assert _count(conn) == 0
    with pytest.raises(cs.ProjectsRootMissing):
        cs.scan_portfolio(tmp_path / "does-not-exist")


def test_scan_repo_at_ignores_branch_commits_merged_after_the_instant(tmp_path: Path) -> None:
    # The ai-memory shape on 2026-10-08: a branch commit dated before the
    # baseline instant, merged into the mainline after it.
    repo = make_repo(tmp_path, "proj", {"a.py": "1\n"}, date="2026-01-15T10:00:00+0000")
    main = _git(repo, "symbolic-ref", "--short", "HEAD")
    _git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, {"b.py": "1\n2\n3\n4\n"}, "2026-01-15T10:30:00+0000")
    _git(repo, "checkout", "-q", main)
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge", "feature", date="2026-01-15T12:00:00+0000")
    assert cs.scan_repo(repo).code == 5
    # At 11:00 the mainline had only a.py; the branch commit was not on it yet.
    assert cs.scan_repo_at(repo, "2026-01-15T11:00:00+00:00").code == 1
    assert cs.scan_repo_at(repo, "2026-01-15T12:30:00+00:00").code == 5


def _raw_baseline_insert(conn, run_id: str, project: str, date: str = "2026-10-08") -> None:
    conn.execute(
        "INSERT INTO codebase_size_snapshots (run_id, kind, snapshot_date, project, "
        "code_lines, test_lines, doc_files, doc_lines, scanned_at) "
        "VALUES (?, 'baseline', ?, ?, 1, 0, 0, 0, 't')",
        (run_id, date, project),
    )


def test_database_refuses_a_second_baseline_run_even_for_other_projects(mgr, conn) -> None:
    _raw_baseline_insert(conn, "run-1", "a")
    _raw_baseline_insert(conn, "run-1", "b")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        _raw_baseline_insert(conn, "run-2", "c")
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        _raw_baseline_insert(conn, "run-1", "z", date="2026-10-09")  # pinned date
    conn.rollback()
    assert sorted(mgr.codebase_baseline()[1]) == ["a", "b"]


def test_import_race_loser_gets_a_clean_refusal(tmp_path: Path, mgr, conn, monkeypatch) -> None:
    make_repo(tmp_path, "proj", FILES)
    make_repo(tmp_path, "other", {"x.py": "1\n2\n"})
    one = _baseline_file(tmp_path / "one.txt", [(9, 6, 2, "proj")])
    two = _baseline_file(tmp_path / "two.txt", [(2, 0, 0, "other")])
    mgr.import_codebase_baseline(one, IMPORT_TS, tmp_path)
    # A second import that raced past the app-level check (it saw no baseline
    # yet) is refused by the database, whole, with a clean error.
    monkeypatch.setattr(type(mgr), "codebase_baseline", lambda self: (None, {}))
    with pytest.raises(ValueError, match="immutable"):
        mgr.import_codebase_baseline(two, IMPORT_TS, tmp_path)
    monkeypatch.undo()
    assert sorted(mgr.codebase_baseline()[1]) == ["proj"]
    assert _count(conn, "baseline") == 1


def test_repo_with_no_commits_is_measured_not_an_error(tmp_path: Path) -> None:
    repo = tmp_path / "fresh"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.py").write_text("1\n2\n")
    _git(repo, "add", "a.py")
    size = cs.scan_repo(repo)
    assert size.error is None
    assert (size.code, size.last_commit, size.commits_90d) == (2, None, 0)


def test_import_from_a_feature_branch_head_is_refused_not_stored(tmp_path: Path, mgr, conn) -> None:
    repo = make_repo(tmp_path, "proj", FILES, date="2026-10-01T00:00:00+0000")
    _git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, {"extra.py": "1\n2\n"}, "2026-10-05T00:00:00+0000")
    # The file records the mainline (9 code lines); HEAD is the feature branch.
    file = _baseline_file(tmp_path / "base.txt", [(9, 6, 2, "proj")])
    with pytest.raises(cs.BaselineMismatch, match="proj"):
        mgr.import_codebase_baseline(file, IMPORT_TS, tmp_path)
    assert _count(conn) == 0
