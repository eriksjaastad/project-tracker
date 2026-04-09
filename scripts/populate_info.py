#!/usr/bin/env python3
"""Populate pt info with tech stacks, deploy targets, and infrastructure details.

Scans each project directory for build files (package.json, pyproject.toml, etc.)
and auto-detects tech stack, deploy target, and doppler config. Uses DatabaseManager
directly for speed (no subprocess overhead).

Usage:
    uv run scripts/populate_info.py --dry-run   # Preview what would be set
    uv run scripts/populate_info.py              # Populate for real
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import PROJECTS_BASE_DIR
from db.manager import DatabaseManager

# ── Global keys ──────────────────────────────────────────────────────────────

GLOBAL_KEYS = {
    "semantic_search": (
        "grep = grepai (semantic), rg = ripgrep (literal). "
        "Config: ~/projects/.grepai/config.yaml. "
        "Model: ollama nomic-embed-text at localhost:11434."
    ),
    "projects_root": str(PROJECTS_BASE_DIR),
    "db_backend": "local SQLite at data/tracker.db (controlled by ~/projects/.turso-config.json)",
    "default_doppler_config": "dev",
    "mac_mini_ssh": "eriksjaastad@Eriks-Mac-mini.local",
}

# ── Manual overrides for projects where auto-detection is wrong/incomplete ───

TECH_OVERRIDES = {
    "_tools": "Go, Python, Bash (shared infra tooling — gh-agent, ollama-mcp, model-bench)",
    "agent-skills-library": "Markdown knowledge base, Python scripts",
    "automation-consulting": "Markdown knowledge base",
    "land-tracker": "Markdown knowledge base",
    "market-research": "Markdown knowledge base, Python scripts",
    "writing": "Markdown, creative writing",
    "ai-journal": "Markdown journal entries, Python scripts",
    "national-cattle-brands": "Python, web scraping",
    "image-workflow": "Python, Pillow, AI image generation pipelines",
    "hypocrisynow": "TypeScript, Next.js, Tailwind CSS, Vercel",
    "muffinpanrecipes": "Python, FastAPI, Jinja2, Tailwind CSS, Vercel",
    "synth-insight-labs": "Static HTML/CSS, Vercel",
    "3d-pose-factory": "Python, Blender scripting",
    "van-build": "TypeScript, React, Vite (van-dashboard/)",
    "cuperion": "JavaScript (placeholder project)",
    "auxesis": "Markdown/docs (planning stage)",
    "tv-mcp-research": "JavaScript, MCP research",
}

# ── Extra infrastructure keys for projects with databases/services ───────────

EXTRA_KEYS = {
    "project-tracker": {
        "infrastructure": "SQLite (data/tracker.db), FastAPI dashboard on :8000, launchd cron jobs",
    },
    "ai-memory": {
        "infrastructure": "libsql/SQLite (brain.db), MCP server (mcp_server.py), graph analytics (graspologic)",
    },
    "ai-usage-billing-tracker": {
        "infrastructure": "Docker, PostgreSQL via SQLAlchemy, Alembic migrations",
    },
    "trading-copilot": {
        "infrastructure": "Railway cron dispatcher (*/5 min), PostgreSQL, yfinance",
    },
    "muffinpanrecipes": {
        "infrastructure": "Vercel Blob Storage for images, Vercel Cron jobs",
    },
    "holoscape": {
        "infrastructure": "macOS native app, MCP swift-sdk, SwiftTerm terminal emulation",
    },
}

# ── Ignored projects (not in ~/projects or not code) ────────────────────────

IGNORE_PROJECTS = {
    ".git", ".DS_Store", "__pycache__", "node_modules", ".venv", "venv",
    "_worktrees", "_inbox", "_handoff", "_trash", "_configs",
    "__Knowledge", "github-repos", "openclaw", "nanoclaw",
    "fci-plugins", "kaperion",
}


def detect_tech_stack(project_path: Path) -> str:
    """Auto-detect tech stack from build files."""
    parts = []

    # Package.swift → Swift
    pkg_swift = project_path / "Package.swift"
    if pkg_swift.exists():
        content = pkg_swift.read_text(errors="ignore")
        parts.append("Swift 6, macOS")
        if "SwiftTerm" in content:
            parts.append("SwiftTerm")
        if "swift-sdk" in content or "MCP" in content:
            parts.append("MCP")
        return ", ".join(parts)

    # go.mod → Go
    go_mod = project_path / "go.mod"
    if go_mod.exists():
        content = go_mod.read_text(errors="ignore")
        parts.append("Go")
        if "cobra" in content:
            parts.append("Cobra CLI")
        return ", ".join(parts)

    # package.json → JS/TS
    pkg_json = project_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "typescript" in deps:
                parts.append("TypeScript")
            else:
                parts.append("JavaScript")
            if "next" in deps:
                parts.append("Next.js")
            if "react" in deps and "next" not in deps:
                parts.append("React")
            if "remotion" in deps:
                parts.append("Remotion")
            if "vite" in deps:
                parts.append("Vite")
            if "tailwindcss" in deps:
                parts.append("Tailwind CSS")
            if "framer-motion" in deps:
                parts.append("Framer Motion")
            if "@anthropic-ai/sdk" in deps:
                parts.append("Anthropic SDK")
        except (json.JSONDecodeError, OSError):
            parts.append("JavaScript/TypeScript")
        if parts:
            return ", ".join(parts)

    # pyproject.toml → Python
    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(errors="ignore")
        parts.append("Python")
        if "fastapi" in content.lower():
            parts.append("FastAPI")
        if "flask" in content.lower():
            parts.append("Flask")
        if "click" in content.lower():
            parts.append("Click CLI")
        if "rich" in content.lower():
            parts.append("Rich")
        if "typer" in content.lower():
            parts.append("Typer CLI")
        if "jinja2" in content.lower():
            parts.append("Jinja2")
        if "libsql" in content.lower() or "turso" in content.lower():
            parts.append("libsql/Turso")
        if "anthropic" in content.lower():
            parts.append("Anthropic SDK")
        if "playwright" in content.lower():
            parts.append("Playwright")
        if "sqlalchemy" in content.lower():
            parts.append("SQLAlchemy")
        return ", ".join(parts)

    # requirements.txt → Python
    reqs = project_path / "requirements.txt"
    if reqs.exists():
        content = reqs.read_text(errors="ignore").lower()
        parts.append("Python")
        if "fastapi" in content:
            parts.append("FastAPI")
        if "flask" in content:
            parts.append("Flask")
        if "typer" in content:
            parts.append("Typer CLI")
        if "openai" in content:
            parts.append("OpenAI API")
        if "anthropic" in content:
            parts.append("Anthropic SDK")
        if "pandas" in content:
            parts.append("pandas")
        if "yfinance" in content:
            parts.append("yfinance")
        if "yt-dlp" in content or "yt_dlp" in content:
            parts.append("yt-dlp")
        if "faster-whisper" in content or "faster_whisper" in content:
            parts.append("Whisper")
        return ", ".join(parts)

    # Fallback: check for Python/shell scripts
    py_files = list(project_path.glob("*.py")) + list(project_path.glob("scripts/*.py"))
    if py_files:
        return "Python scripts"

    return "Markdown/docs"


def detect_deploy_target(project_path: Path) -> str:
    """Auto-detect deploy target from config files."""
    if (project_path / "vercel.json").exists() or (project_path / ".vercel").exists():
        return "Vercel"
    if (project_path / "railway.toml").exists() or (project_path / "railway.json").exists():
        return "Railway"
    if (project_path / "fly.toml").exists():
        return "Fly.io"
    if (project_path / "Dockerfile").exists() or (project_path / "docker-compose.yml").exists():
        return "Docker (self-hosted)"
    return "Local only"


def detect_doppler(project_path: Path) -> str | None:
    """Extract doppler project/config from doppler.yaml."""
    doppler_file = project_path / "doppler.yaml"
    if not doppler_file.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(doppler_file.read_text())
        setup = data.get("setup", [])
        if isinstance(setup, list) and setup:
            entry = setup[0]
        elif isinstance(setup, dict):
            entry = setup
        else:
            return None
        project = entry.get("project", "")
        config = entry.get("config", "dev")
        if project:
            return f"{project}/{config}"
    except Exception:
        # Fallback: regex parse
        import re
        content = doppler_file.read_text(errors="ignore")
        proj_match = re.search(r"project:\s*(.+)", content)
        conf_match = re.search(r"config:\s*(.+)", content)
        if proj_match:
            project = proj_match.group(1).strip()
            config = conf_match.group(1).strip() if conf_match else "dev"
            return f"{project}/{config}"
    return None


def main():
    parser = argparse.ArgumentParser(description="Populate pt info store")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    db = None if args.dry_run else DatabaseManager()
    count = 0

    # ── Global keys ──
    print("=== Global Keys ===")
    for key, value in GLOBAL_KEYS.items():
        print(f"  {key} = {value}")
        if not args.dry_run:
            db.set_info(key, value)
        count += 1

    # ── Per-project keys ──
    print("\n=== Per-Project Keys ===")
    for item in sorted(PROJECTS_BASE_DIR.iterdir()):
        if not item.is_dir() or item.name in IGNORE_PROJECTS or item.name.startswith("."):
            continue

        project_name = item.name
        print(f"\n  [{project_name}]")

        # Tech stack
        tech = TECH_OVERRIDES.get(project_name) or detect_tech_stack(item)
        print(f"    tech_stack = {tech}")
        if not args.dry_run:
            db.set_info("tech_stack", tech, project_id=project_name)
        count += 1

        # Deploy target
        deploy = detect_deploy_target(item)
        print(f"    deploy_target = {deploy}")
        if not args.dry_run:
            db.set_info("deploy_target", deploy, project_id=project_name)
        count += 1

        # Doppler
        doppler = detect_doppler(item)
        if doppler:
            print(f"    doppler = {doppler}")
            if not args.dry_run:
                db.set_info("doppler", doppler, project_id=project_name)
            count += 1

        # Extra infrastructure keys
        if project_name in EXTRA_KEYS:
            for key, value in EXTRA_KEYS[project_name].items():
                print(f"    {key} = {value}")
                if not args.dry_run:
                    db.set_info(key, value, project_id=project_name)
                count += 1

    mode = "DRY RUN" if args.dry_run else "POPULATED"
    print(f"\n{mode}: {count} entries across pt info")


if __name__ == "__main__":
    main()
