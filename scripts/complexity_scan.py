#!/usr/bin/env python3
"""Monthly complexity scan across all projects.

Tracks cognitive complexity, duplication density, and refactoring ratio
to detect whether codebases are improving or degrading over time.

Usage:
    uv run scripts/complexity_scan.py                    # All projects, markdown
    uv run scripts/complexity_scan.py --project <name>   # Single project
    uv run scripts/complexity_scan.py --json             # JSON output
    uv run scripts/complexity_scan.py --trend            # Append to trend file

Requires radon for cognitive complexity (optional):
    uv pip install radon

See CODE_QUALITY_STRATEGY.md and card #5528.
"""

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add parent directory to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.config import PROJECTS_BASE_DIR, PROJECT_ROOT

TREND_FILE = PROJECT_ROOT / "data" / "complexity_trends.jsonl"

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".claude", "_worktrees",
}

CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx"}


def find_code_files(project_path: Path) -> list[Path]:
    """Find all code files in a project, skipping vendored/generated dirs."""
    files = []
    for root, dirs, filenames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in filenames:
            p = Path(root) / f
            if p.suffix in CODE_EXTENSIONS:
                files.append(p)
    return files


def measure_complexity(project_path: Path) -> dict[str, Any] | None:
    """Run radon cognitive complexity on Python files. Returns None if radon unavailable."""
    try:
        result = subprocess.run(
            ["radon", "cc", str(project_path), "-a", "-j",
             "--exclude", ",".join(SKIP_DIRS)],
            capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "average": None, "worst": []}

    if result.returncode != 0:
        return {"error": result.stderr.strip(), "average": None, "worst": []}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": "invalid json from radon", "average": None, "worst": []}

    all_blocks = []
    for filepath, blocks in data.items():
        for b in blocks:
            all_blocks.append({
                "file": str(Path(filepath).relative_to(project_path)),
                "name": b.get("name", "?"),
                "complexity": b.get("complexity", 0),
                "rank": b.get("rank", "?"),
            })

    if not all_blocks:
        return {"average": 0.0, "worst": [], "total_blocks": 0}

    avg = sum(b["complexity"] for b in all_blocks) / len(all_blocks)
    worst = sorted(all_blocks, key=lambda b: b["complexity"], reverse=True)[:5]

    return {
        "average": round(avg, 2),
        "worst": worst,
        "total_blocks": len(all_blocks),
    }


def measure_duplication(files: list[Path]) -> dict[str, Any]:
    """Hash non-blank, non-comment lines and report duplication density."""
    line_hashes: Counter[str] = Counter()
    total_lines = 0

    for f in files:
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            total_lines += 1
            line_hashes[hashlib.md5(stripped.encode()).hexdigest()] += 1

    if total_lines == 0:
        return {"density": 0.0, "total_lines": 0, "duplicated_lines": 0}

    duplicated = sum(count for count in line_hashes.values() if count >= 3)
    density = round(duplicated / total_lines * 100, 1)

    return {
        "density": density,
        "total_lines": total_lines,
        "duplicated_lines": duplicated,
    }


def measure_refactoring_ratio(project_path: Path) -> dict[str, Any]:
    """Count refactoring commits vs total in last 30 days."""
    if not (project_path / ".git").is_dir():
        return {"ratio": 0.0, "refactor_commits": 0, "total_commits": 0}

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--since=30 days ago"],
            capture_output=True, text=True, timeout=30,
            cwd=project_path,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"ratio": 0.0, "refactor_commits": 0, "total_commits": 0}

    lines = [l for l in result.stdout.strip().splitlines() if l]
    total = len(lines)
    if total == 0:
        return {"ratio": 0.0, "refactor_commits": 0, "total_commits": 0}

    refactor_keywords = {"refactor", "cleanup", "simplify", "reorganize", "clean up"}
    refactor_count = sum(
        1 for l in lines
        if any(kw in l.lower() for kw in refactor_keywords)
    )

    return {
        "ratio": round(refactor_count / total * 100, 1),
        "refactor_commits": refactor_count,
        "total_commits": total,
    }


def scan_project(project_path: Path) -> dict[str, Any]:
    """Run all metrics on a single project."""
    files = find_code_files(project_path)

    return {
        "project": project_path.name,
        "path": str(project_path),
        "file_count": len(files),
        "complexity": measure_complexity(project_path),
        "duplication": measure_duplication(files),
        "refactoring": measure_refactoring_ratio(project_path),
    }


def get_active_projects(project_filter: str | None = None) -> list[Path]:
    """Get project directories, optionally filtered by name."""
    projects = []
    for item in sorted(PROJECTS_BASE_DIR.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith(("_", ".")):
            continue
        if not (item / ".git").is_dir():
            continue
        if project_filter and item.name != project_filter:
            continue
        projects.append(item)
    return projects


def format_markdown(results: list[dict]) -> str:
    """Format scan results as markdown report."""
    lines = [
        f"# Complexity Scan — {datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]

    radon_available = any(r["complexity"] is not None for r in results)
    if not radon_available:
        lines.append("> **Note:** radon not installed — cognitive complexity skipped. Install with `uv pip install radon`")
        lines.append("")

    lines.append("| Project | Files | Avg Complexity | Duplication | Refactor Ratio |")
    lines.append("|---------|-------|---------------|-------------|----------------|")

    for r in sorted(results, key=lambda x: x["project"]):
        complexity_str = "n/a"
        if r["complexity"] and r["complexity"].get("average") is not None:
            complexity_str = f"{r['complexity']['average']:.1f}"

        dup = r["duplication"]
        dup_str = f"{dup['density']}%"

        ref = r["refactoring"]
        ref_str = f"{ref['ratio']}% ({ref['refactor_commits']}/{ref['total_commits']})"

        lines.append(f"| {r['project']} | {r['file_count']} | {complexity_str} | {dup_str} | {ref_str} |")

    # Detail section for worst complexity offenders
    if radon_available:
        lines.extend(["", "## Worst Complexity (top 5 per project)", ""])
        for r in sorted(results, key=lambda x: x["project"]):
            if not r["complexity"] or not r["complexity"].get("worst"):
                continue
            lines.append(f"### {r['project']}")
            for w in r["complexity"]["worst"]:
                lines.append(f"- `{w['file']}:{w['name']}` — complexity {w['complexity']} (rank {w['rank']})")
            lines.append("")

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Monthly complexity scan")
    parser.add_argument("--project", "-p", help="Scan a single project")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--trend", action="store_true", help="Append to trend file")
    args = parser.parse_args()

    projects = get_active_projects(args.project)
    if not projects:
        print(f"No projects found{f' matching {args.project}' if args.project else ''}", file=sys.stderr)
        sys.exit(1)

    results = [scan_project(p) for p in projects]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_markdown(results))

    if args.trend:
        TREND_FILE.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "projects_scanned": len(results),
            "per_project": {
                r["project"]: {
                    "files": r["file_count"],
                    "avg_complexity": r["complexity"]["average"] if r["complexity"] else None,
                    "duplication_pct": r["duplication"]["density"],
                    "refactor_pct": r["refactoring"]["ratio"],
                }
                for r in results
            },
        }
        with open(TREND_FILE, "a") as f:
            f.write(json.dumps(summary) + "\n")
        print(f"\nTrend data appended to {TREND_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
