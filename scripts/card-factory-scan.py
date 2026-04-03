#!/usr/bin/env python3
"""
Card Factory Tier 1 Scanner — mechanical checks for objectively verifiable issues.

Runs 7 deterministic checks against a project and outputs structured JSON.
The card-factory agent calls this script and interprets the results.

Usage:
    uv run scripts/card-factory-scan.py <project-path>
    uv run scripts/card-factory-scan.py <project-path> --json
    uv run scripts/card-factory-scan.py <project-path> --check ruff,orphans
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("card-factory-scan")

# Directories/files to always skip
SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".next",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "project-graph-screenshots-movies", "logs", "data",
}
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".db", ".sqlite", ".wasm", ".png", ".jpg", ".jpeg",
    ".gif", ".mov", ".mp4", ".ico", ".svg", ".woff", ".woff2", ".ttf",
    ".lock",
}
# Standard files that are NOT orphans even if nothing imports them
STANDARD_FILES = {
    "__init__.py", "conftest.py", "pyproject.toml", "setup.py", "setup.cfg",
    "requirements.txt", "Makefile", "Dockerfile", ".gitignore", ".env",
    ".env.example", "README.md", "CLAUDE.md", "DIRECTION.md", "AGENTS.md",
    "DECISIONS.md", "REVIEW.md", "LICENSE", "pt",
}


def find_project_files(project_path: Path, extensions: set[str] | None = None) -> list[Path]:
    """Walk project tree, skipping ignored dirs/extensions."""
    files = []
    for root, dirs, filenames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in filenames:
            fp = Path(root) / f
            if fp.suffix in SKIP_EXTENSIONS:
                continue
            if extensions and fp.suffix not in extensions:
                continue
            files.append(fp)
    return files


# =============================================================================
# Check 1: Ruff lint (unused imports/variables)
# =============================================================================

def check_ruff(project_path: Path) -> list[dict]:
    """Run ruff for unused imports (F401) and unused variables (F841)."""
    findings = []
    try:
        result = subprocess.run(
            ["ruff", "check", str(project_path), "--select", "F401,F841",
             "--output-format", "json", "--quiet"],
            capture_output=True, text=True, timeout=30
        )
        if result.stdout.strip():
            for item in json.loads(result.stdout):
                findings.append({
                    "check": "ruff",
                    "file": item.get("filename", ""),
                    "line": item.get("location", {}).get("row", 0),
                    "code": item.get("code", ""),
                    "message": item.get("message", ""),
                })
    except FileNotFoundError:
        logger.info("ruff not installed, skipping lint check")
    except subprocess.TimeoutExpired:
        logger.warning("ruff timed out on %s", project_path)
    except json.JSONDecodeError as e:
        logger.warning("ruff output not valid JSON: %s", e)
    return findings


# =============================================================================
# Check 2: Orphan files (Python files not imported anywhere)
# =============================================================================

def check_orphans(project_path: Path) -> list[dict]:
    """Find Python files that are not imported by any other file in the project."""
    findings = []
    py_files = find_project_files(project_path, {".py"})
    if not py_files:
        return findings

    # Build a set of all module names that are imported somewhere
    imported_modules: set[str] = set()
    import_pattern = re.compile(
        r'(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))'
    )
    for f in py_files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            for m in import_pattern.finditer(text):
                mod = m.group(1) or m.group(2)
                # Add all parts: "from scripts.db.manager" -> scripts, scripts.db, scripts.db.manager
                parts = mod.split(".")
                for i in range(len(parts)):
                    imported_modules.add(".".join(parts[:i+1]))
                # Also add the leaf name alone for relative-style matching
                imported_modules.add(parts[-1])
        except Exception as e:
            logger.debug("Could not read %s: %s", f, e)
            continue

    # Check each Python file: is its module name imported anywhere?
    for f in py_files:
        rel = f.relative_to(project_path)
        if f.name in STANDARD_FILES:
            continue
        # Skip test files (they're checked separately)
        if f.name.startswith("test_") or "/tests/" in str(rel):
            continue
        # Skip files in the project root that are scripts/entry points
        if rel.parent == Path("."):
            continue

        # Derive module name from file path
        stem = f.stem
        module_path = str(rel.with_suffix("")).replace(os.sep, ".")

        # Check if this module is imported anywhere
        if stem not in imported_modules and module_path not in imported_modules:
            # Double-check: is the filename referenced as a string anywhere?
            referenced = False
            for other in py_files:
                if other == f:
                    continue
                try:
                    text = other.read_text(encoding="utf-8", errors="ignore")
                    if stem in text:
                        referenced = True
                        break
                except Exception as e:
                    logger.debug("Could not read %s: %s", other, e)
                    continue
            if not referenced:
                findings.append({
                    "check": "orphan",
                    "file": str(rel),
                    "line": 0,
                    "code": "ORPHAN",
                    "message": f"Python file not imported or referenced by any other file",
                })
    return findings


# =============================================================================
# Check 3: Stale test files
# =============================================================================

def check_stale_tests(project_path: Path) -> list[dict]:
    """Find test files that import modules which don't exist."""
    findings = []
    test_dir = project_path / "tests"
    if not test_dir.is_dir():
        return findings

    # Build set of available modules in the project
    available_modules: set[str] = set()
    for f in find_project_files(project_path, {".py"}):
        rel = f.relative_to(project_path)
        if "/tests/" in str(rel) or str(rel).startswith("tests/"):
            continue
        stem = f.stem
        module_path = str(rel.with_suffix("")).replace(os.sep, ".")
        available_modules.add(stem)
        available_modules.add(module_path)
        # Add partial paths
        parts = module_path.split(".")
        for i in range(len(parts)):
            available_modules.add(".".join(parts[:i+1]))

    # Also add common stdlib/third-party so we don't false-positive on those
    stdlib_prefixes = {
        "os", "sys", "json", "re", "pathlib", "datetime", "unittest",
        "pytest", "click", "flask", "rich", "httpx", "requests",
        "subprocess", "tempfile", "shutil", "collections", "typing",
        "functools", "itertools", "contextlib", "logging", "hashlib",
        "uuid", "time", "math", "random", "io", "copy", "dataclasses",
        "abc", "enum", "textwrap", "argparse", "sqlite3", "socket",
        "urllib", "http", "email", "html", "xml", "csv", "configparser",
        "hypothesis", "mock", "unittest.mock", "freezegun",
        "threading", "asyncio", "importlib", "inspect", "types",
        "multiprocessing", "concurrent", "signal", "struct", "array",
        "decimal", "fractions", "statistics", "secrets", "base64",
        "binascii", "codecs", "difflib", "glob", "fnmatch", "stat",
        "fileinput", "linecache", "tokenize", "pprint", "reprlib",
        "traceback", "warnings", "weakref", "operator", "heapq",
        "bisect", "queue", "shelve", "pickle", "marshal",
        "fastapi", "starlette", "uvicorn", "pydantic", "jinja2",
        "typer", "playwright", "yaml", "toml",
    }
    available_modules.update(stdlib_prefixes)

    import_pattern = re.compile(
        r'(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))'
    )

    for test_file in test_dir.glob("test_*.py"):
        try:
            text = test_file.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.debug("Could not read %s: %s", f, e)
            continue
        for m in import_pattern.finditer(text):
            mod = m.group(1) or m.group(2)
            top_level = mod.split(".")[0]
            # Only flag if the top-level module is not available and not stdlib
            if top_level not in available_modules:
                findings.append({
                    "check": "stale_test",
                    "file": str(test_file.relative_to(project_path)),
                    "line": text[:m.start()].count("\n") + 1,
                    "code": "STALE_TEST",
                    "message": f"Imports '{mod}' which does not exist in this project",
                })
    return findings


# =============================================================================
# Check 4: Governance violations (hardcoded paths in source)
# =============================================================================

def check_governance(project_path: Path) -> list[dict]:
    """Find hardcoded absolute paths in source code files."""
    findings = []
    source_extensions = {".py", ".sh", ".ts", ".js", ".tsx", ".jsx"}
    path_pattern = re.compile(r'(/Users/\w+|/home/\w+)')

    for f in find_project_files(project_path, source_extensions):
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as e:
            logger.debug("Could not read %s: %s", f, e)
            continue
        for i, line in enumerate(lines, 1):
            if path_pattern.search(line):
                # Skip comments that are documenting paths
                stripped = line.strip()
                if stripped.startswith("#") and "example" in stripped.lower():
                    continue
                findings.append({
                    "check": "governance",
                    "file": str(f.relative_to(project_path)),
                    "line": i,
                    "code": "HARDCODED_PATH",
                    "message": f"Hardcoded absolute path: {line.strip()[:100]}",
                })
    return findings


# =============================================================================
# Check 5: Missing pt info entries
# =============================================================================

def check_missing_info(project_path: Path) -> list[dict]:
    """Find env vars in code not documented in pt info."""
    findings = []
    project_name = project_path.name

    # Collect env var references from code
    # Only match actual environment variable access patterns, not shell local vars
    py_env_pattern = re.compile(
        r'(?:os\.getenv\(["\'](\w+)|os\.environ(?:\.get)?\[?["\'](\w+))'
    )
    # For shell: only match vars accessed with $ that are NOT being assigned on the same line
    sh_env_pattern = re.compile(r'\$\{?([A-Z][A-Z0-9_]{2,})\}?')
    sh_assignment_pattern = re.compile(r'^[A-Z][A-Z0-9_]*=')

    env_vars_in_code: dict[str, str] = {}  # var -> file:line

    # Common env vars, shell internals, and local script vars to skip
    skip_vars = {
        "HOME", "PATH", "USER", "SHELL", "PWD", "CI", "TERM", "LANG",
        "EDITOR", "PROJECTS_ROOT", "PT_NO_BANNER", "PORT", "OLDPWD",
        # Shell internals
        "BASH_SOURCE", "BASH_LINENO", "FUNCNAME", "PIPESTATUS",
        # Common local script variables (assigned and used in same file)
        "SCRIPT_DIR", "PROJECT_ROOT", "PROJECT_DIR", "REPO_ROOT",
        "LOG_FILE", "DB_PATH", "DUMP_PATH", "ROW_COUNT",
        "RESULT", "EXIT_CODE", "WARDEN_EXIT", "VALIDATE_EXIT",
        "TRACKER_DIR", "JOURNAL_DIR", "JOURNAL_INDEXER", "UV_RUN",
        "LIBRARIAN", "JOURNAL_SPECIALIST", "GRAPH_BUILDER",
        "PROJECT", "DRY_RUN", "PROMPT", "GOVERNANCE_CHECK",
        "CHAT_URL", "API_KEY", "SENDER", "THROTTLE_FILE", "CURSOR_FILE",
    }

    for f in find_project_files(project_path, {".py", ".sh"}):
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as e:
            logger.debug("Could not read %s: %s", f, e)
            continue

        if f.suffix == ".py":
            for i, line in enumerate(lines, 1):
                for m in py_env_pattern.finditer(line):
                    var = m.group(1) or m.group(2)
                    if var and var not in env_vars_in_code and var not in skip_vars:
                        env_vars_in_code[var] = f"{f.relative_to(project_path)}:{i}"
        elif f.suffix == ".sh":
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # Skip lines that are assigning the variable (local vars)
                if sh_assignment_pattern.match(stripped):
                    continue
                # Skip comments
                if stripped.startswith("#"):
                    continue
                for m in sh_env_pattern.finditer(line):
                    var = m.group(1)
                    if var and var not in env_vars_in_code and var not in skip_vars:
                        env_vars_in_code[var] = f"{f.relative_to(project_path)}:{i}"

    if not env_vars_in_code:
        return findings

    # Get documented entries from pt info
    documented_vars: set[str] = set()
    try:
        result = subprocess.run(
            ["pt", "info", "-p", project_name, "--json"],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            for entry in json.loads(result.stdout):
                documented_vars.add(entry.get("key", "").upper())
    except Exception as e:
        logger.warning("Could not query pt info for %s: %s", project_name, e)

    for var, location in env_vars_in_code.items():
        if var not in documented_vars:
            file_part, line_part = location.rsplit(":", 1)
            findings.append({
                "check": "missing_info",
                "file": file_part,
                "line": int(line_part),
                "code": "MISSING_INFO",
                "message": f"Env var '{var}' used in code but not in pt info",
            })
    return findings


# =============================================================================
# Check 6: Dead dependencies
# =============================================================================

def check_dead_deps(project_path: Path) -> list[dict]:
    """Find packages in requirements/pyproject that are never imported."""
    findings = []

    # Collect all imports in the project
    all_imports: set[str] = set()
    import_pattern = re.compile(r'(?:from\s+([\w]+)|^import\s+([\w]+))', re.MULTILINE)
    for f in find_project_files(project_path, {".py"}):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            for m in import_pattern.finditer(text):
                all_imports.add((m.group(1) or m.group(2)).lower())
        except Exception as e:
            logger.debug("Could not read %s: %s", f, e)
            continue

    # Map of package names to their import names (common mismatches)
    pkg_to_import = {
        "pillow": "pil",
        "python-dateutil": "dateutil",
        "pyyaml": "yaml",
        "beautifulsoup4": "bs4",
        "scikit-learn": "sklearn",
        "python-dotenv": "dotenv",
        "psycopg2-binary": "psycopg2",
        "google-cloud-secret-manager": "google",
        "uvicorn": "uvicorn",
    }

    # Parse requirements.txt
    req_file = project_path / "requirements.txt"
    if req_file.exists():
        try:
            for line in req_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                pkg = re.split(r'[>=<!\[]', line)[0].strip().lower()
                import_name = pkg_to_import.get(pkg, pkg.replace("-", "_"))
                if import_name.lower() not in all_imports:
                    findings.append({
                        "check": "dead_dep",
                        "file": "requirements.txt",
                        "line": 0,
                        "code": "DEAD_DEP",
                        "message": f"Package '{pkg}' is listed but never imported",
                    })
        except Exception as e:
            logger.warning("Could not parse requirements.txt: %s", e)

    # Parse pyproject.toml dependencies
    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text()
            # Simple regex to find dependencies in [project.dependencies]
            in_deps = False
            for line in text.splitlines():
                if line.strip() == "[project.dependencies]" or line.strip().startswith("dependencies = ["):
                    in_deps = True
                    continue
                if in_deps:
                    if line.strip().startswith("[") and not line.strip().startswith('"'):
                        break
                    if line.strip() == "]":
                        in_deps = False
                        continue
                    m = re.match(r'\s*"?([a-zA-Z0-9_-]+)', line)
                    if m:
                        pkg = m.group(1).lower()
                        import_name = pkg_to_import.get(pkg, pkg.replace("-", "_"))
                        if import_name.lower() not in all_imports:
                            findings.append({
                                "check": "dead_dep",
                                "file": "pyproject.toml",
                                "line": 0,
                                "code": "DEAD_DEP",
                                "message": f"Package '{pkg}' is listed but never imported",
                            })
        except Exception as e:
            logger.warning("Could not parse pyproject.toml: %s", e)

    return findings


# =============================================================================
# Check 7: Empty/placeholder files
# =============================================================================

def check_empty_files(project_path: Path) -> list[dict]:
    """Find Python files that are effectively empty (only imports/docstrings/pass)."""
    findings = []
    trivial_pattern = re.compile(
        r'^(\s*#.*|\s*""".*?"""|\s*\'\'\'.*?\'\'\'|\s*import\s+.*|'
        r'\s*from\s+.*import.*|\s*pass\s*|\s*)$',
        re.MULTILINE
    )

    for f in find_project_files(project_path, {".py"}):
        if f.name in STANDARD_FILES:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception as e:
            logger.debug("Could not read %s: %s", f, e)
            continue
        if not text:
            findings.append({
                "check": "empty_file",
                "file": str(f.relative_to(project_path)),
                "line": 0,
                "code": "EMPTY_FILE",
                "message": "File is completely empty",
            })
            continue
        # Check if file has only trivial content
        non_trivial = trivial_pattern.sub("", text).strip()
        lines = text.splitlines()
        if not non_trivial and len(lines) > 1:
            findings.append({
                "check": "empty_file",
                "file": str(f.relative_to(project_path)),
                "line": 0,
                "code": "PLACEHOLDER",
                "message": f"File has {len(lines)} lines but no real logic (only imports/docstrings/pass)",
            })
    return findings


# =============================================================================
# Main
# =============================================================================

ALL_CHECKS = {
    "ruff": check_ruff,
    "orphans": check_orphans,
    "stale_tests": check_stale_tests,
    "governance": check_governance,
    "missing_info": check_missing_info,
    "dead_deps": check_dead_deps,
    "empty_files": check_empty_files,
}


def main():
    parser = argparse.ArgumentParser(description="Card Factory Tier 1 Scanner")
    parser.add_argument("project_path", help="Path to project root")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Output as JSON")
    parser.add_argument("--check", default=None,
                        help="Comma-separated list of checks to run (default: all)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    project_path = Path(args.project_path).resolve()
    if not project_path.is_dir():
        print(f"Error: {project_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Determine which checks to run
    if args.check:
        check_names = [c.strip() for c in args.check.split(",")]
        checks = {k: v for k, v in ALL_CHECKS.items() if k in check_names}
    else:
        checks = ALL_CHECKS

    # Run all checks
    all_findings = []
    check_results = {}
    for name, check_fn in checks.items():
        try:
            findings = check_fn(project_path)
            check_results[name] = {"count": len(findings), "status": "ok"}
            all_findings.extend(findings)
        except Exception as e:
            check_results[name] = {"count": 0, "status": f"error: {e}"}

    # Output
    output = {
        "project": project_path.name,
        "project_path": str(project_path),
        "checks": check_results,
        "total_findings": len(all_findings),
        "findings": all_findings,
    }

    if args.json_output:
        print(json.dumps(output, indent=2))
    else:
        print(f"=== Card Factory Scan: {project_path.name} ===\n")
        print(f"Checks run: {', '.join(checks.keys())}")
        print(f"Total findings: {len(all_findings)}\n")
        if not all_findings:
            print("No issues found.")
        else:
            for f in all_findings:
                loc = f"{f['file']}:{f['line']}" if f['line'] else f['file']
                print(f"  [{f['code']}] {loc} — {f['message']}")
        print()
        for name, result in check_results.items():
            status = f"{result['count']} findings" if result['status'] == 'ok' else result['status']
            print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
