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
        "PT_DB_PATH": "Path to tracker.db (default: data/tracker.db)",
        "PT_EXTERNAL_BACKUP_DIR": "External backup directory for sandboxed environments",
        "PT_AUDIT_BIN": "Path to audit binary",
        "PT_TEST_MODE": "Set to 1 for test mode (disables safety backups)",
        "PT_ALLOW_FRESH_DB": "Set to 1 to allow starting with empty database",
        "PT_AGENT_MODEL": "Agent model for calendar poller hooks",
        "SAFE_MODE": "Set to 0 to enable permanent deletions (Erik only)",
        "ALLOW_BULK_DELETE": "Enable bulk delete operations in DatabaseManager",
        "COST_TRACKER_API_KEY": "SIL cost tracker API key (from Doppler synth-insight-labs)",
        "TELEMETRY_PATH": "Path to telemetry log file for discovery module",
        "CRON_JOB_LOG": "Cron job log file path for discovery module",
        # --- added by #6257 -------------------------------------------------
        # `pt info` documented 6 of roughly 30 PT_* vars actually read in
        # source. Three of the missing ones were in USAGE.md but not here, and
        # two were in neither. Note this is one of FOUR hand-maintained
        # registries (this file, USAGE.md, the `cli` group docstring, and
        # `_effective_config_payload`) that drift independently — deliberately
        # left as four for now; unifying them is its own change.
        "PT_ALLOW_REMOTE_ADMIN": "Set to 1 to allow dashboard admin endpoints off loopback (default: loopback only)",
        "PT_DASHBOARD_HOST": "Dashboard bind host (default: 127.0.0.1)",
        "PT_DASHBOARD_PORT": "Dashboard bind port (default: 8000)",
        "PT_DASHBOARD_URL": "Full dashboard URL used by the watchdog probe",
        "PT_BACKUP_DB_PATH": "Database path used by scripts/backup-db.sh",
        "PT_FULL_BACKUP_DIR": "Destination directory for full DB backups",
        "PT_BACKUP_LOG_PATH": "Backup log path read by discovery/backup_reader.py",
        "PT_BACKUP_RCLONE_DEST": "rclone remote for offsite backup copies",
        "PT_BACKUP_LAUNCH_AGENT_PATH": "Path to the backup LaunchAgent plist",
        "PT_BACKUP_CLOUD_STATE_FILE": "State file tracking cloud backup status",
        "PT_CALLER_CWD": "Set by the pt launcher to the directory you ran pt from — read this, never Path.cwd(), which is always project-tracker",
        "PT_PROJECTS_DIR": "Override for the projects root (default: ~/projects)",
        "PT_RESOURCES_FILE": "Path to the resources reference file",
        "PT_REINDEX_SCRIPT": "Path to the reindex script",
        "PT_MEMORY_DB_PATH": "Override for the Open Brain memory database",
        "PT_MIGRATION_DIR": "Override for migration state files (default: ~/.project-tracker/migrations)",
        "PT_NO_BANNER": "Set to 1 to suppress the pt startup banner",
        "PT_SUPPRESS_MIGRATION_WARNING": "Set to 1 to silence the unapplied-migration warning (tests set this)",
        "PT_SKIP_DOPPLER": "Set to 1 to skip the launcher's doppler wrap — read-only cron/SSH paths",
        "PT_DOPPLER_PROJECT": "Override the Doppler project the launcher passes (default: project-tracker)",
        "PT_DOPPLER_CONFIG": "Override the Doppler config the launcher passes (default: dev)",
        "PT_ALERTS_URL": "Alerts endpoint the digest reads (default: localhost:8000/api/alerts)",
        "PT_TASKS_URL": "Tasks endpoint the digest reads",
        "PT_MINI_HOST": "SSH host for the Mac Mini scan (default: eriks-mac-mini)",
        "PT_MINI_ENABLED": "Set to 0 to skip the Mac Mini section of the digest",
        "PT_LOG_MAX_BYTES": "Rotation cap for Python-written logs (default: 10MB)",
        "PT_LOG_BACKUP_COUNT": "Generations kept by the Python log handler (default: 3)",
        "PT_LOG_BACKUPS": "Generations kept by scripts/log_rotation.py for launchd-owned logs (default: 2)",
        "PT_DASHBOARD_LOG_MAX_BYTES": "Rotation cap for the launchd-owned dashboard logs",
        "PT_DASHBOARD_LOG_BACKUPS": "Generations kept for the launchd-owned dashboard logs",
        "PT_DESTRUCTIVE_LOG_PATH": "Override for the in-process deletion audit log (tests redirect this)",
        "PT_ALLOW_MAIN_EDIT": "One-shot bypass for the no-edits-on-main hook",
        "PT_ALLOW_DIRTY_EXIT": "One-shot bypass for the session-end cleanliness gate",
    },
    "ai-memory": {
        "infrastructure": "libsql/SQLite (brain.db), MCP server (mcp_server.py), graph analytics (graspologic)",
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
