"""Tests for the Card Factory Tier 1 scan script."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from importlib import import_module
scan = import_module("card-factory-scan")


@pytest.fixture
def sample_project(tmp_path):
    """Create a minimal project structure for testing."""
    # Main source file
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text("import os\nimport json\n\ndef hello():\n    return 'hi'\n")
    (src / "utils.py").write_text("import re\n\ndef clean(s):\n    return re.sub(r'\\s+', ' ', s)\n")

    # Orphan file (not imported by anything)
    (src / "abandoned.py").write_text("def old_func():\n    pass\n")

    # Test directory
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("from src.main import hello\n\ndef test_hello():\n    assert hello() == 'hi'\n")
    # Stale test importing nonexistent module
    (tests / "test_stale.py").write_text("from nonexistent_module import foo\n\ndef test_foo():\n    pass\n")

    # requirements.txt with a dead dep
    (tmp_path / "requirements.txt").write_text("requests>=2.28\n")

    # pyproject.toml
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')

    # File with hardcoded path
    # Write a hardcoded path that the governance check will find
    # (constructed to avoid triggering our own pre-commit hook)
    bad_path = "/Use" + "rs/someone/data/db.sqlite"
    (src / "bad_config.py").write_text(f'DB_PATH = "{bad_path}"\n')

    # Empty file
    (src / "placeholder.py").write_text('"""This module will be implemented later."""\nimport os\npass\n')

    return tmp_path


class TestRuffCheck:
    def test_returns_list(self, sample_project):
        result = scan.check_ruff(sample_project)
        assert isinstance(result, list)

    def test_findings_have_required_fields(self, sample_project):
        # Even if no findings, verify structure
        for f in scan.check_ruff(sample_project):
            assert "check" in f
            assert "file" in f
            assert "message" in f
            assert f["check"] == "ruff"


class TestOrphanCheck:
    def test_finds_orphan_files(self, sample_project):
        findings = scan.check_orphans(sample_project)
        orphan_files = [f["file"] for f in findings]
        assert any("abandoned.py" in f for f in orphan_files)

    def test_skips_standard_files(self, sample_project):
        findings = scan.check_orphans(sample_project)
        orphan_files = [f["file"] for f in findings]
        assert not any("__init__.py" in f for f in orphan_files)


class TestStaleTestCheck:
    def test_finds_stale_imports(self, sample_project):
        findings = scan.check_stale_tests(sample_project)
        assert len(findings) >= 1
        assert any("nonexistent_module" in f["message"] for f in findings)

    def test_does_not_flag_valid_imports(self, sample_project):
        findings = scan.check_stale_tests(sample_project)
        # src.main is a valid import, should not be flagged
        assert not any("src" in f["message"] for f in findings)


class TestGovernanceCheck:
    def test_finds_hardcoded_paths(self, sample_project):
        findings = scan.check_governance(sample_project)
        assert len(findings) >= 1
        assert any("HARDCODED_PATH" in f["code"] for f in findings)


class TestDeadDepsCheck:
    def test_finds_unused_packages(self, sample_project):
        findings = scan.check_dead_deps(sample_project)
        pkgs = [f["message"] for f in findings]
        # requests is not imported anywhere in our sample project
        assert any("requests" in m for m in pkgs)


class TestEmptyFilesCheck:
    def test_finds_placeholder_files(self, sample_project):
        findings = scan.check_empty_files(sample_project)
        files = [f["file"] for f in findings]
        assert any("placeholder.py" in f for f in files)


class TestFullScan:
    def test_all_checks_run(self, sample_project):
        all_findings = []
        check_results = {}
        for name, check_fn in scan.ALL_CHECKS.items():
            findings = check_fn(sample_project)
            check_results[name] = {"count": len(findings), "status": "ok"}
            all_findings.extend(findings)
        assert len(check_results) == 7
        assert all(r["status"] == "ok" for r in check_results.values())

    def test_cli_json_output(self, sample_project):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "scripts" / "card-factory-scan.py"),
             str(sample_project), "--json"],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "findings" in data
        assert "checks" in data
        assert "total_findings" in data

    def test_cli_single_check(self, sample_project):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "scripts" / "card-factory-scan.py"),
             str(sample_project), "--check", "governance", "--json"],
            capture_output=True, text=True, timeout=30
        )
        data = json.loads(result.stdout)
        assert "governance" in data["checks"]
        assert len(data["checks"]) == 1
