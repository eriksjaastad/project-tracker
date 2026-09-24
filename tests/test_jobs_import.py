"""Job import from JSONL: idempotency, raw retention, multi-role contract."""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from scripts.db.jobs import JOB_CATEGORIES, JOB_SOURCES


def test_import_upsert_is_idempotent_by_url(db, tmp_path: Path) -> None:
    """Repeated imports of the same URL update fields but preserve first_seen."""
    jsonl = tmp_path / "jobs.jsonl"
    jsonl.write_text(
        '{"company": "Acme", "title": "Engineer", "url": "https://example.test/1", "source": "ats_sweep"}\n'
        '{"company": "Widget", "title": "Designer", "url": "https://example.test/2", "source": "hn"}\n'
    )
    
    # First import
    for line in jsonl.read_text().strip().split("\n"):
        import json
        record = json.loads(line)
        db.upsert_job(**record)
    
    first_jobs = db.get_open_jobs()
    assert len(first_jobs) == 2
    first_seen_by_url = {job["url"]: job["first_seen"] for job in first_jobs}
    
    # Update one job's title and re-import
    jsonl.write_text(
        '{"company": "Acme Corp", "title": "Senior Engineer", "url": "https://example.test/1", "source": "ats_sweep", "category": "Backend"}\n'
        '{"company": "Widget", "title": "Designer", "url": "https://example.test/2", "source": "hn"}\n'
    )
    
    for line in jsonl.read_text().strip().split("\n"):
        import json
        record = json.loads(line)
        db.upsert_job(**record)
    
    second_jobs = db.get_open_jobs()
    assert len(second_jobs) == 2
    
    # URL 1 should have updated fields but preserved first_seen
    updated = next(j for j in second_jobs if j["url"] == "https://example.test/1")
    assert updated["company"] == "Acme Corp"
    assert updated["title"] == "Senior Engineer"
    assert updated["category"] == "Backend"
    assert updated["first_seen"] == first_seen_by_url["https://example.test/1"]
    
    # URL 2 unchanged
    unchanged = next(j for j in second_jobs if j["url"] == "https://example.test/2")
    assert unchanged["company"] == "Widget"
    assert unchanged["first_seen"] == first_seen_by_url["https://example.test/2"]


def test_import_preserves_raw_text_and_dismissal_state(db, tmp_path: Path) -> None:
    """Re-importing a dismissed job preserves deleted_at and raw text."""
    jsonl = tmp_path / "jobs.jsonl"
    initial_raw = "Original ATS posting HTML with full details"
    jsonl.write_text(
        f'{{"company": "Example", "title": "Role", "url": "https://example.test/job", '
        f'"source": "ats_sweep", "raw": "{initial_raw}"}}\n'
    )
    
    import json
    job = db.upsert_job(**json.loads(jsonl.read_text().strip()))
    assert job["raw"] == initial_raw
    assert job["deleted_at"] is None
    
    # Dismiss the job
    dismissed = db.soft_delete_job(job["id"])
    assert dismissed["deleted_at"] is not None
    
    # Re-import with updated fields but no raw
    jsonl.write_text(
        '{"company": "Example Inc", "title": "Updated Role", "url": "https://example.test/job", '
        '"source": "ats_sweep"}\n'
    )
    reimported = db.upsert_job(**json.loads(jsonl.read_text().strip()))
    
    # Should preserve dismissal and raw text
    assert reimported["id"] == job["id"]
    assert reimported["deleted_at"] is not None
    assert reimported["raw"] == initial_raw
    assert reimported["company"] == "Example Inc"


def test_import_validates_required_fields(tmp_path: Path) -> None:
    """Missing required fields raise ValueError."""
    from scripts.db.manager import DatabaseManager
    
    db = DatabaseManager()
    
    # Missing company
    with pytest.raises(ValueError, match="company, title and url are required"):
        db.upsert_job(company="", title="Engineer", url="https://example.test/1", source="manual")
    
    # Missing title
    with pytest.raises(ValueError, match="company, title and url are required"):
        db.upsert_job(company="Acme", title="", url="https://example.test/2", source="manual")
    
    # Missing URL
    with pytest.raises(ValueError, match="company, title and url are required"):
        db.upsert_job(company="Acme", title="Engineer", url="", source="manual")
    
    # Invalid source
    with pytest.raises(ValueError, match="invalid job source"):
        db.upsert_job(company="Acme", title="Engineer", url="https://example.test/3", source="linkedin")
    
    # Invalid category
    with pytest.raises(ValueError, match="invalid job category"):
        db.upsert_job(
            company="Acme", title="Engineer", url="https://example.test/4",
            source="manual", category="Crypto"
        )


def test_hn_multi_role_contract_documented_in_import_contract() -> None:
    """HN multi-role comments must produce one JSONL line per role.
    
    This test documents the contract: each role gets a stable URL fragment
    (e.g., #role-1, #role-2) and unparseable roles must still be exported
    with company='Unknown', title='See raw text', and the full raw comment.
    
    The job-search repo export side is out of scope for this PR, but the
    contract is documented in docs/JOB_IMPORT_CONTRACT.md.
    """
    contract_path = Path(__file__).parent.parent / "docs" / "JOB_IMPORT_CONTRACT.md"
    assert contract_path.exists(), "JOB_IMPORT_CONTRACT.md must exist"
    
    contract = contract_path.read_text()
    assert "HN Multi-Role Handling" in contract
    assert "one JSONL line per role" in contract.lower() or "single role per line" in contract.lower()
    assert "Unknown" in contract
    assert "See raw text" in contract
    assert "Contract violation" in contract or "not allowed" in contract


def test_hn_multi_role_example_imports_successfully(db, tmp_path: Path) -> None:
    """Example multi-role HN comment imports as separate jobs."""
    jsonl = tmp_path / "hn_multi.jsonl"
    jsonl.write_text(
        '{"company": "Widget Inc", "title": "Full Stack Developer", '
        '"url": "https://news.ycombinator.com/item?id=12345678#role-1", '
        '"source": "hn", "category": "Full Stack", '
        '"raw": "Widget Inc | Full Stack | Remote | Apply at jobs@widget.com"}\n'
        
        '{"company": "Widget Inc", "title": "Backend Engineer", '
        '"url": "https://news.ycombinator.com/item?id=12345678#role-2", '
        '"source": "hn", "category": "Backend", '
        '"raw": "Widget Inc | Backend | SF | Apply at jobs@widget.com"}\n'
        
        '{"company": "Unknown", "title": "See raw text", '
        '"url": "https://news.ycombinator.com/item?id=12345678#role-3", '
        '"source": "hn", "category": "Other", '
        '"raw": "Stealth startup | multiple roles | contact: secret@example.com"}\n'
    )
    
    import json
    imported = []
    for line in jsonl.read_text().strip().split("\n"):
        record = json.loads(line)
        job = db.upsert_job(**record)
        imported.append(job)
    
    assert len(imported) == 3
    
    # All three roles from the same HN comment are distinct jobs
    assert imported[0]["url"].startswith("https://news.ycombinator.com/item?id=12345678#role-1")
    assert imported[1]["url"].startswith("https://news.ycombinator.com/item?id=12345678#role-2")
    assert imported[2]["url"].startswith("https://news.ycombinator.com/item?id=12345678#role-3")
    
    # Unparseable role is preserved with fallback fields
    unknown = imported[2]
    assert unknown["company"] == "Unknown"
    assert unknown["title"] == "See raw text"
    assert "Stealth startup" in unknown["raw"]
    
    # All have raw text
    assert all(job["raw"] for job in imported)


def test_valid_sources_and_categories_constants() -> None:
    """JOB_SOURCES and JOB_CATEGORIES match schema constraints."""
    assert JOB_SOURCES == frozenset({"ats_sweep", "hn", "manual"})
    assert JOB_CATEGORIES == frozenset({
        "Frontend/React", "Full Stack", "Forward Deployed / Solutions",
        "SEO", "Backend", "Other",
    })


def test_import_coalesce_behavior_for_optional_fields(db) -> None:
    """Upsert COALESCE logic: new null values don't erase existing data."""
    # First import with all fields populated
    first = db.upsert_job(
        company="Acme", title="Engineer", url="https://example.test/coalesce",
        source="ats_sweep", location="Remote", posted_date="2026-09-20",
        category="Backend", raw="Initial posting text"
    )
    assert first["location"] == "Remote"
    assert first["posted_date"] == "2026-09-20"
    assert first["raw"] == "Initial posting text"
    
    # Re-import with nulls for optional fields
    second = db.upsert_job(
        company="Acme Corp", title="Senior Engineer",
        url="https://example.test/coalesce", source="ats_sweep",
        location=None, posted_date=None, raw=None,
    )
    
    # COALESCE preserves existing values when new value is null
    assert second["id"] == first["id"]
    assert second["company"] == "Acme Corp"
    assert second["title"] == "Senior Engineer"
    assert second["location"] == "Remote"
    assert second["posted_date"] == "2026-09-20"
    assert second["raw"] == "Initial posting text"


def test_cli_import_success_output(tmp_path: Path) -> None:
    """End-to-end CLI test: successful import shows correct output."""
    jsonl = tmp_path / "success.jsonl"
    jsonl.write_text(
        '{"company": "Test Co", "title": "Engineer", "url": "https://example.test/cli1", "source": "manual"}\n'
    )
    
    result = subprocess.run(
        [sys.executable, "-m", "scripts.pt", "jobs", "import", str(jsonl)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent
    )
    
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "✓ Imported 1 job(s)" in result.stdout
    assert str(jsonl) in result.stdout


def test_cli_import_json_output(tmp_path: Path) -> None:
    """End-to-end CLI test: --json flag produces valid JSON envelope."""
    jsonl = tmp_path / "json_mode.jsonl"
    jsonl.write_text(
        '{"company": "Widget", "title": "Designer", "url": "https://example.test/cli2", "source": "hn"}\n'
    )
    
    result = subprocess.run(
        [sys.executable, "-m", "scripts.pt", "jobs", "import", str(jsonl), "--json"],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent
    )
    
    assert result.returncode == 0, f"stderr: {result.stderr}"
    response = json.loads(result.stdout)
    assert response["ok"] is True
    assert response["command"] == "jobs.import"
    assert response["result"]["imported"] == 1
    assert response["result"]["errors"] == 0


def test_cli_import_malformed_jsonl_error(tmp_path: Path) -> None:
    """End-to-end CLI test: malformed JSONL produces error messages."""
    jsonl = tmp_path / "malformed.jsonl"
    jsonl.write_text(
        '{"company": "Good", "title": "Engineer", "url": "https://example.test/cli3", "source": "manual"}\n'
        '{broken json here}\n'
        '{"company": "Also Good", "title": "Designer", "url": "https://example.test/cli4", "source": "hn"}\n'
    )
    
    result = subprocess.run(
        [sys.executable, "-m", "scripts.pt", "jobs", "import", str(jsonl)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent
    )
    
    assert result.returncode == 1
    assert "✓ Imported 2 job(s)" in result.stdout
    assert "✗ 1 error(s):" in result.stderr
    assert "line 2:" in result.stderr
    assert "invalid JSON" in result.stderr


def test_cli_import_missing_required_fields_error(tmp_path: Path) -> None:
    """End-to-end CLI test: missing required fields consolidated into one error."""
    jsonl = tmp_path / "missing_fields.jsonl"
    jsonl.write_text(
        '{"title": "Engineer", "url": "https://example.test/cli5"}\n'
        '{"company": "Widget"}\n'
    )
    
    result = subprocess.run(
        [sys.executable, "-m", "scripts.pt", "jobs", "import", str(jsonl)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent
    )
    
    assert result.returncode == 1
    assert "✗ 2 error(s):" in result.stderr
    assert "line 1:" in result.stderr
    assert "missing required fields:" in result.stderr
    assert "company" in result.stderr and "source" in result.stderr
    assert "line 2:" in result.stderr


def test_cli_import_many_errors_truncated(tmp_path: Path) -> None:
    """End-to-end CLI test: more than 10 errors triggers truncation message."""
    jsonl = tmp_path / "many_errors.jsonl"
    lines = ['{broken}' for _ in range(15)]
    jsonl.write_text('\n'.join(lines) + '\n')
    
    result = subprocess.run(
        [sys.executable, "-m", "scripts.pt", "jobs", "import", str(jsonl)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent
    )
    
    assert result.returncode == 1
    assert "✗ 15 error(s):" in result.stderr
    assert "... and 5 more error(s)" in result.stderr


def test_cli_import_nonexistent_file_error(tmp_path: Path) -> None:
    """End-to-end CLI test: nonexistent file produces IO error."""
    nonexistent = tmp_path / "does_not_exist.jsonl"
    
    result = subprocess.run(
        [sys.executable, "-m", "scripts.pt", "jobs", "import", str(nonexistent)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent
    )
    
    assert result.returncode == 2
    assert "does not exist" in result.stderr.lower() or "no such file" in result.stderr.lower()


def test_cli_import_dry_run_mode(tmp_path: Path) -> None:
    """End-to-end CLI test: --dry-run validates without writing to database."""
    jsonl = tmp_path / "dry_run.jsonl"
    jsonl.write_text(
        '{"company": "Dry Run Co", "title": "Tester", "url": "https://example.test/dry", "source": "manual"}\n'
    )
    
    result = subprocess.run(
        [sys.executable, "-m", "scripts.pt", "jobs", "import", str(jsonl), "--dry-run"],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent
    )
    
    assert result.returncode == 0
    assert "DRY RUN: Would import 1 job(s)" in result.stdout
