#!/usr/bin/env python3
"""
Validate project structure and requirements.

Usage:
    ./scripts/validate_project.py [project_name]      # Check specific project
    ./scripts/validate_project.py --all               # Check all projects
    ./scripts/validate_project.py --missing           # List projects without indexes

This script enforces:
- Mandatory files (CLAUDE.md, README.md, etc.)
- Mandatory directories
- DNA integrity (no absolute paths, no secrets)
- Safety checks (no dangerous patterns, no unfilled placeholders)
"""

import sys
import os
from pathlib import Path
from typing import List
import re
from scaffold.utils import safe_slug
from scaffold.alerts import send_discord_alert
from scaffold.constants import PROTECTED_PROJECTS

# Configuration
PROJECTS_ROOT_ENV = os.getenv("PROJECTS_ROOT")
if not PROJECTS_ROOT_ENV:
    # Fallback to standard layout: parent of scaffolding root
    PROJECTS_ROOT = Path(__file__).parent.parent.parent.resolve()
else:
    PROJECTS_ROOT = Path(PROJECTS_ROOT_ENV).resolve()

SKIP_DIRS = PROTECTED_PROJECTS

# Mandatory files and directories
MANDATORY_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    ".cursorignore",
    "README.md",
    ".gitignore"
]
MANDATORY_DIRS = [
    "Documents"
]


class ValidationError(Exception):
    """Raised when project fails validation."""
    pass


def find_projects(root: Path) -> List[Path]:
    """Find all project directories (top-level folders)."""
    projects = []
    for item in root.iterdir():
        if item.is_dir() and not item.name.startswith((".", "_")):
            # Skip explicit directories
            if item.name in SKIP_DIRS:
                continue
            projects.append(item)
    return sorted(projects)




def validate_dna_integrity(project_path: Path) -> List[str]:
    """Scan project for absolute paths and secrets. Returns list of errors."""
    errors = []
    
    # Patterns to catch absolute paths (using character class to avoid self-detection)
    path_pattern = re.compile(r"/[U]sers/[a-zA-Z0-9._-]+")
    # Patterns to catch common secrets (sk-, AIza, etc.)
    secret_pattern = re.compile(r"(sk-[a-zA-Z0-9]{32,}|AIza[a-zA-Z0-9_-]{35})")
    
    # Files to exclude from scan
    exclude_dirs = {
        ".git", "venv", ".venv", "__pycache__", "node_modules", "data",
        "library", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        "htmlcov", ".tox", ".nox", ".cache", "logs", "recovered", "cursor_history",
        "entries", "insights"
    }
    
    for root, dirs, files in os.walk(project_path):
        # Filter directories in-place
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".")]
        
        for file in files:
            # Skip binary files, known safe files, generated files, and env files
            if file.endswith((".png", ".jpg", ".jpeg", ".pyc", ".db", ".zip", ".tar.gz", ".bak", ".xml", ".log", ".pdf", ".json", ".csv")) or \
               file in {".env", ".env.example", "full_repo_context.txt", "billing.error.log", "repomix-output.xml", "pandoc"}:
                continue
                
            file_path = Path(root) / file
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                
                # Check for absolute paths
                if path_pattern.search(content):
                    # Skip common intentional paths if any (e.g. journal protocol uses absolute paths)
                    journal_path_str = str(PROJECTS_ROOT / "ai-journal" / "entries")
                    if journal_path_str in content:
                        continue
                    # Skip AGENTS.md absolute paths (they are ecosystem-wide)
                    if file == "AGENTS.md":
                        continue
                    errors.append(f"DNA Defect: Absolute path found in {file_path.relative_to(project_path)}")
                
                # Check for secrets
                if secret_pattern.search(content):
                    errors.append(f"Security Defect: Potential secret found in {file_path.relative_to(project_path)}")
                    
            except Exception as e:
                # We log but don't fail the whole scan for one unreadable file
                errors.append(f"Scan Defect: Could not read file {file_path.relative_to(project_path)}: {e}")
                
    return errors


def validate_project(project_path: Path, verbose: bool = True) -> bool:
    """
    Validate a single project against the Master Compliance Checklist.
    
    Returns:
        True if valid, False otherwise
    """
    project_name = project_path.name
    errors = []
    
    # 1. Check for mandatory files
    for filename in MANDATORY_FILES:
        if not (project_path / filename).exists():
            # Special case: check for README.md in Documents/ if not in root
            if filename == "README.md" and (project_path / "Documents" / "README.md").exists():
                continue
            errors.append(f"Missing mandatory file: {filename}")
            
    # 3. Check for mandatory directories
    for dirname in MANDATORY_DIRS:
        if not (project_path / dirname).is_dir():
            errors.append(f"Missing mandatory directory: {dirname}")
            
    # 4. DNA Integrity Scan (Automated Gate 0)
    dna_errors = validate_dna_integrity(project_path)
    errors.extend(dna_errors)
    
    # 5. Dangerous Command Scan (Automated Gate 1)
    # Check for banned functions like rm, shutil.rmtree, os.remove
    dangerous_patterns = [
        (r"\brm\s+", "rm command found - use 'trash <file>' instead"),
        (r"shutil\.rmtree\s*\(", "shutil.rmtree() found - use send2trash"),
        (r"os\.remove\s*\(", "os.remove() found - use send2trash"),
        (r"os\.unlink\s*\(", "os.unlink() found - use send2trash"),
    ]
    
    # Files to skip for safety scan
    safety_skip_files = {"validate_project.py", "warden_audit.py"}
    
    # 6. Placeholder Scan (Automated Gate 2)
    # Check for unfilled template placeholders: {{VAR}}
    placeholder_patterns = [
        (re.compile(r"\{\{[A-Z0-9_]+\}\}"), "Unfilled double-brace placeholder"),
    ]
    
    # Intentional placeholders that are allowed to remain (e.g. in documentation or examples)
    ALLOWED_PLACEHOLDERS = {
        "{{RECIPE_ID}}",
        "{{BACKGROUND}}",
        "{{PRIMARY}}",
        "{{SECONDARY}}",
        "{{ACCENT}}",
        "{{PLACEHOLDER}}"
    }
    
    # Files/directories to skip for placeholder scan
    placeholder_skip_files = {
        "SILENT_FAILURES_AUDIT.md",
        "TODO_FORMAT_STANDARD.md",
        "REVIEWS_AND_GOVERNANCE_PROTOCOL.md",
        "validate_project.py",
        "cli.py"
    }
    placeholder_skip_dirs = {"templates", "_handoff", "prompts"}
    
    for root, dirs, files in os.walk(project_path):
        # Filter directories in-place
        dirs[:] = [d for d in dirs if d not in {"venv", ".venv", "__pycache__", "node_modules", ".git"}]
        
        rel_root = Path(root).relative_to(project_path)
        is_in_skip_dir = any(part in placeholder_skip_dirs for part in rel_root.parts)
        
        for file in files:
            # Check placeholders in Markdown, Python, and Shell scripts
            if not file.endswith((".md", ".py", ".sh", ".js", ".ts")):
                continue
            
            is_placeholder_skip_file = file in placeholder_skip_files
                
            file_path = Path(root) / file
            rel_file_path = file_path.relative_to(project_path)
            
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                
                # Check for dangerous patterns (skip if in skip list)
                if file not in safety_skip_files:
                    for pattern, reason in dangerous_patterns:
                        if re.search(pattern, content):
                            errors.append(f"Safety Defect: {reason} in {rel_file_path}")
                
                # Check for unfilled placeholders (skip if in skip list)
                if not is_in_skip_dir and not is_placeholder_skip_file:
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        for pattern, reason in placeholder_patterns:
                            match = pattern.search(line)
                            if match:
                                placeholder = match.group(0)
                                if placeholder in ALLOWED_PLACEHOLDERS:
                                    continue
                                
                                # Special case: ignore some common single-brace patterns that aren't placeholders
                                # e.g. f-strings in python or shell variables if they look like placeholders
                                if file.endswith(".py") and ("f\"" in line or "f'" in line):
                                    continue
                                
                                errors.append(f"Placeholder Defect: {reason} found in {rel_file_path}:{i+1} - {match.group(0)}")
            except (OSError, UnicodeDecodeError):
                # Silently skip unreadable files during placeholder scan
                pass

    if errors:
        if verbose:
            print(f"⚠️  {project_name}")
            for error in errors:
                print(f"   - {error}")

        # Send Discord alert — wrapped with timeout to prevent hanging during pt scan
        try:
            msg = f"Validation errors in {project_name}:\n" + "\n".join(f"  - {e}" for e in errors)
            send_discord_alert(msg)
        except Exception:
            pass  # Never let a notification failure block or hang the scan

        return False
    
    # All good!
    if verbose:
        print(f"✅ {project_name} (Fully Compliant)")
    return True


def main() -> None:
    """Main validation logic."""
    if len(sys.argv) < 2 or sys.argv[1] in ["--help", "-h"]:
        print("Usage:")
        print("  ./scripts/validate_project.py [project_name]  # Check specific project")
        print("  ./scripts/validate_project.py --all           # Check all projects")
        print("  ./scripts/validate_project.py --missing       # List missing indexes")
        sys.exit(0 if len(sys.argv) > 1 else 1)
    
    arg = sys.argv[1]
    
    if arg == "--all":
        # Validate all projects
        print("Validating all projects...\n")
        projects = find_projects(PROJECTS_ROOT)
        
        valid_count = 0
        invalid_count = 0
        
        for project in projects:
            is_valid = validate_project(project, verbose=True)
            if is_valid:
                valid_count += 1
            else:
                invalid_count += 1
            print()  # Blank line between projects
        
        # Summary
        total = valid_count + invalid_count
        print(f"{'='*60}")
        print(f"Summary: {valid_count}/{total} projects valid ({invalid_count} need attention)")
        
        if invalid_count > 0:
            print(f"\n⚠️  {invalid_count} projects need index files or fixes")
            print("Run with --missing to see which projects need indexes")
            sys.exit(1)
        else:
            print("\n✅ All projects have valid index files!")
            sys.exit(0)
    
    elif arg == "--missing":
        # List projects without CLAUDE.md
        print("Projects missing CLAUDE.md:\n")
        projects = find_projects(PROJECTS_ROOT)

        missing = []
        for project in projects:
            if not (project / "CLAUDE.md").exists():
                missing.append(project.name)

        if missing:
            for name in missing:
                print(f"  - {name}")
            print(f"\n{len(missing)} projects need CLAUDE.md")
        else:
            print("All projects have CLAUDE.md!")
        
        sys.exit(len(missing))  # Exit code = number of missing
    
    else:
        # Validate specific project
        # First try the raw name
        project_path = (PROJECTS_ROOT / arg).resolve()
        if not project_path.exists() or not project_path.is_dir():
            # Fallback to slugged name
            project_name = safe_slug(arg)
            project_path = (PROJECTS_ROOT / project_name).resolve()
        
        # Security: Ensure path stays within PROJECTS_ROOT
        if not project_path.is_relative_to(PROJECTS_ROOT):
            print(f"❌ Security Alert: Path traversal detected for {arg}")
            sys.exit(1)
            
        if not project_path.exists():
            print(f"❌ Project not found: {arg}")
            print(f"   Expected: {project_path}")
            sys.exit(1)
        
        if not project_path.is_dir():
            print(f"❌ Not a directory: {arg}")
            sys.exit(1)
        
        print(f"Validating: {project_path.name}\n")
        is_valid = validate_project(project_path, verbose=True)
        
        if not is_valid:
            print(f"\n❌ Validation failed for {project_path.name}")
            sys.exit(1)
        else:
            print(f"\n✅ {project_path.name} is valid!")
            sys.exit(0)


if __name__ == "__main__":
    main()

