#!/usr/bin/env python3
"""
The Librarian - Global Ecosystem Networking & Indexing.
Automatically maintains 00_Index_*.md files with 'educated' descriptions.
Uses the 00_Index.md.template for rich frontmatter when creating new files.

───────────────────────────────────────────────────────────────────────────────
ARCHITECTURE: Knowledge lives in index files, rules live in Librarian
───────────────────────────────────────────────────────────────────────────────

The index files are the source of truth. They contain flags/markers that describe
what kind of content they hold. Librarian reads these flags and knows how to
behave based on the rules she carries.

This means:
- No .librarian-ignore files scattered across projects
- No hardcoded lists of "special" directories
- Index files do their job (describe contents)
- Librarian does her job (enforce rules based on flags)

As we discover new project types (writing, journals, plugins, etc.), we:
1. Add new flags to the FLAG VOCABULARY below
2. Add rules for those flags to Librarian's logic
3. Mark items in index files with the appropriate flags

The ecosystem grows smarter without carrying knowledge in config files everywhere.

───────────────────────────────────────────────────────────────────────────────
FLAG VOCABULARY (evolving)
───────────────────────────────────────────────────────────────────────────────

Current flags (in description field):
  ✓  = Human reviewed, intentional, skip in future audits
  ⏳ = Waiting for review, needs human attention

Future flags (add as needed):
  📝 = Writing/prose project (different audit rules)
  📓 = Journal directory (append-only, special protections)
  🔌 = Plugin/extension (different structure expectations)
  🧪 = Experimental/sandbox (relaxed rules)
  📦 = Archive (read-only, no audit needed)

When adding a new flag:
1. Add it to this vocabulary
2. Update parse_existing_index() if needed
3. Update inventory functions with flag-specific logic
4. Document the behavior

───────────────────────────────────────────────────────────────────────────────
WORKFLOW
───────────────────────────────────────────────────────────────────────────────

1. Run `librarian.py <path> --audit` to flag items needing review
2. Human reviews index, changes ⏳ to ✓ and adds descriptions
3. Future audits skip ✓ items, only flag new issues
4. If an item with ✓ disappears, librarian notices the broken link

Philosophy: Librarian organizes and flags issues. She doesn't write the books.
"""

import os
import re
import argparse
import yaml
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from collections import Counter

# Template location
PROJECTS_ROOT = Path(os.getenv("PROJECTS_ROOT", Path.home() / "projects"))
TEMPLATE_PATH = PROJECTS_ROOT / "project-scaffolding" / "templates" / "00_Index.md.template"

# Load config from shared YAML file (lives in project-scaffolding)
CONFIG_PATH = PROJECTS_ROOT / "project-scaffolding" / "config" / "scan_config.yaml"


def _load_config() -> dict:
    """Load graph configuration from YAML file."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}


_config = _load_config()

# Technology detection
TECH_EXTENSIONS = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".md": "documentation",
}

# Load skip lists from shared config
SKIP_DIRS = set(_config.get('skip_dirs', []))
SKIP_FILES = set(_config.get('skip_files', []))
IGNORE_PROJECTS = set(_config.get('ignore_projects', []))

# Projects with their own indexing scripts - librarian should not touch
# (This is separate from protected_projects which is for scaffolding tools)
SELF_INDEXED_PROJECTS = {"ai-journal"}

SKIP_EXTENSIONS = {
    ".pyc", ".db", ".sqlite", ".zip", ".tar.gz", ".dmg", ".pdf", ".jpg", ".png", ".gif",
    ".DS_Store", ".plist", ".exe", ".bin", ".tmp", ".bak", ".backup"
}

# Markers for auto-generated content
START_MARKER = "<!-- LIBRARIAN-INDEX-START -->"
END_MARKER = "<!-- LIBRARIAN-INDEX-END -->"

# Review markers
WAITING_REVIEW = "⏳ Waiting for review"
REVIEWED_MARK = "✓"


def parse_existing_index(index_file: Path) -> Dict[str, str]:
    """
    Parse an existing index file to extract human-edited descriptions.

    Returns a dict mapping item names to their descriptions.
    Items with ✓ or custom descriptions should be preserved.
    """
    descriptions = {}

    if not index_file.exists():
        return descriptions

    content = index_file.read_text()

    # Find content between markers
    if START_MARKER not in content or END_MARKER not in content:
        return descriptions

    index_section = content.split(START_MARKER)[1].split(END_MARKER)[0]

    # Parse table rows - look for markdown table format
    # | [name](link) | count | description | or | [name](link) | description |
    for line in index_section.split('\n'):
        line = line.strip()
        if not line.startswith('|') or line.startswith('| :'):
            continue

        # Extract link name and description
        # Format: | [name/](name/) | count | desc | or | [name](name) | desc |
        match = re.search(r'\|\s*\[([^\]]+)\]\([^)]+\)\s*\|[^|]*\|\s*([^|]+)\s*\|', line)
        if not match:
            # Try two-column format (files)
            match = re.search(r'\|\s*\[([^\]]+)\]\([^)]+\)\s*\|\s*([^|]+)\s*\|$', line)

        if match:
            name = match.group(1).rstrip('/')
            desc = match.group(2).strip()
            descriptions[name] = desc

    return descriptions


def detect_primary_tech(directory: Path) -> str:
    """Detect primary technology based on file extensions."""
    extensions = Counter()

    for file in directory.rglob("*"):
        if file.is_file() and not any(part.startswith(".") for part in file.parts):
            if any(skip in file.parts for skip in SKIP_DIRS):
                continue
            ext = file.suffix.lower()
            if ext in TECH_EXTENSIONS:
                extensions[ext] += 1

    if not extensions:
        return "unknown"

    most_common_ext = extensions.most_common(1)[0][0]
    return TECH_EXTENSIONS[most_common_ext]


def detect_domain(directory: Path, tech: str) -> str:
    """Infer domain from directory name and tech stack."""
    name_lower = directory.name.lower()

    # Check for common domain patterns in name
    domain_patterns = {
        "journal": "personal",
        "tracker": "infrastructure",
        "workflow": "automation",
        "image": "image-processing",
        "ai": "ai-orchestration",
        "agent": "ai-orchestration",
        "tool": "infrastructure",
        "mcp": "infrastructure",
        "tax": "finance",
        "invoice": "finance",
        "trading": "finance",
        "knowledge": "research",
        "scaffold": "infrastructure",
    }

    for pattern, domain in domain_patterns.items():
        if pattern in name_lower:
            return domain

    # Fallback based on tech
    if tech == "documentation":
        return "documentation"

    return "general"


def create_from_template(directory: Path, index_content: str) -> str:
    """Create new index file content using the template."""
    dir_name = directory.name
    tech = detect_primary_tech(directory)
    domain = detect_domain(directory, tech)
    created_date = datetime.now().strftime("%Y-%m-%d")

    # Build rich frontmatter
    frontmatter = f"""---
tags:
  - map/project
  - p/{dir_name.lower().replace(' ', '-').lstrip('_')}
  - type/index
  - tech/{tech}
  - domain/{domain}
  - status/active
created: {created_date}
---"""

    # Build the body
    body = f"""
# {dir_name}

{index_content}
"""

    return frontmatter + body


def extract_description(file_path: Path) -> str:
    """Extract an 'educated' description of what a file does."""
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        if not content.strip():
            return "Empty file."

        # Python: Look for module docstring
        if file_path.suffix == ".py":
            # Match triple quote docstring at start
            match = re.search(r'^\s*"""(.*?)"""', content, re.DOTALL)
            if not match:
                match = re.search(r"^\s*'''(.*?)'''", content, re.DOTALL)
            if match:
                desc = match.group(1).strip().split('\n')[0]
                return desc if len(desc) > 5 else "Python utility script."
            
        # Markdown: Look for H1 or first paragraph
        elif file_path.suffix == ".md":
            # Skip YAML frontmatter
            body = content
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    body = parts[2].strip()

            lines = body.split('\n')
            for line in lines:
                line = line.strip()
                if not line: continue
                # Skip HTML tags
                if line.startswith('<') or line.startswith('```'):
                    continue
                # Skip badge lines (shields.io, etc.)
                if '[![' in line or 'img.shields.io' in line:
                    continue
                # Skip the title if it's just the filename
                if line.startswith('#') and file_path.stem.lower() in line.lower():
                    continue
                # Skip generic titles like "# GET SHIT DONE"
                if line.startswith('#'):
                    continue
                # Found first real line of text
                desc = re.sub(r'#+\s*', '', line).strip()
                # Skip if it's just markdown formatting
                if desc.startswith('**') and desc.endswith('**'):
                    desc = desc.strip('*').strip()
                return desc[:100] + "..." if len(desc) > 100 else desc

        # Shell: Look for first comment line
        elif file_path.suffix in [".sh", ".bash", ".zsh"]:
            for line in content.split('\n'):
                if line.startswith('#') and '!' not in line:
                    desc = line.lstrip('#').strip()
                    if desc: return desc
            return "Shell script."

    except Exception:
        pass
    
    return "No description available."

def is_directory_empty(directory: Path) -> bool:
    """Check if a directory is effectively empty (no real files, only empty subdirs)."""
    for item in directory.rglob("*"):
        if item.is_file() and not item.name.startswith("."):
            return False
    return True



def get_directory_inventory(
    directory: Path,
    existing_descriptions: Dict[str, str] = None,
    audit_mode: bool = False
) -> List[Dict]:
    """Build inventory of immediate subdirectories.

    Args:
        directory: Directory to inventory
        existing_descriptions: Dict of name->description from existing index
        audit_mode: If True, flag items without README as needing review
    """
    inventory = []
    existing_descriptions = existing_descriptions or {}

    for item in directory.iterdir():
        if not item.is_dir():
            continue

        # Skip hidden and junk directories
        if item.name.startswith(".") or item.name in SKIP_DIRS:
            continue

        # Count files in directory (non-recursive, just immediate children)
        file_count = sum(1 for f in item.iterdir() if f.is_file() and not f.name.startswith("."))

        # Check for existing description (preserve if has ✓)
        existing_desc = existing_descriptions.get(item.name, "")
        if REVIEWED_MARK in existing_desc:
            # Human reviewed - preserve exactly
            desc = existing_desc
        elif existing_desc and existing_desc != "No description available." and WAITING_REVIEW not in existing_desc:
            # Has a real description (not default, not waiting) - preserve it
            desc = existing_desc
        else:
            # Try to get description from README or index file
            desc = None
            for readme_name in ["README.md", "readme.md", f"00_Index_{item.name}.md"]:
                readme = item / readme_name
                if readme.exists():
                    desc = extract_description(readme)
                    break

            if not desc or desc == "No description available.":
                # No README found
                if audit_mode:
                    desc = WAITING_REVIEW
                else:
                    desc = "No description available."

        # Find the best link target (index file > README > directory)
        link_target = f"{item.name}/"  # Default to directory
        for index_name in [f"00_Index_{item.name}.md", "README.md", "readme.md"]:
            index_file = item / index_name
            if index_file.exists():
                link_target = f"{item.name}/{index_name}"
                break

        inventory.append({
            "name": item.name,
            "file_count": file_count,
            "desc": desc,
            "link_target": link_target
        })

    return sorted(inventory, key=lambda x: x["name"])


def get_file_inventory(
    directory: Path,
    recursive: bool = False,
    skip_file: Optional[Path] = None,
    existing_descriptions: Dict[str, str] = None,
    audit_mode: bool = False
) -> List[Dict]:
    """Build a detailed inventory of files in a directory.

    Args:
        directory: Directory to inventory
        recursive: Include subdirectories
        skip_file: File to skip (usually the index file itself)
        existing_descriptions: Dict of name->description from existing index
        audit_mode: If True, flag suspicious files as needing review
    """
    inventory = []
    pattern = "**/*" if recursive else "*"
    existing_descriptions = existing_descriptions or {}

    # Patterns that suggest one-off or temporary files
    one_off_patterns = [
        r"^test_.*(?<!_test)\.py$",
        r"^tmp_", r"^temp_", r"_backup\.", r"_old\.", r"_copy\.",
        r"\.bak$", r"^scratch", r"^draft_", r"^wip_",
    ]

    for item in directory.glob(pattern):
        if not item.is_file():
            continue

        # Skip hidden and junk
        if item.name.startswith(".") or item.suffix.lower() in SKIP_EXTENSIONS:
            continue

        # Skip the index file we are currently building
        if skip_file and item.resolve() == skip_file.resolve():
            continue

        # Check parent skip list (hidden dirs or skip list)
        rel_path = item.relative_to(directory)
        if any(part.startswith(".") for part in rel_path.parts) or \
           any(part in SKIP_DIRS for part in rel_path.parts):
            continue

        # Check for existing description (preserve if has ✓)
        key = str(rel_path)
        existing_desc = existing_descriptions.get(key, "")
        if REVIEWED_MARK in existing_desc:
            # Human reviewed - preserve exactly
            desc = existing_desc
        elif existing_desc and existing_desc != "No description available." and WAITING_REVIEW not in existing_desc:
            # Has a real description - preserve it
            desc = existing_desc
        else:
            # Extract description from file
            desc = extract_description(item)

            # In audit mode, check if file looks suspicious
            if audit_mode and desc == "No description available.":
                is_suspicious = any(
                    re.search(p, item.name, re.IGNORECASE)
                    for p in one_off_patterns
                )
                if is_suspicious:
                    desc = WAITING_REVIEW

        inventory.append({
            "path": rel_path,
            "name": item.name,
            "desc": desc
        })

    return sorted(inventory, key=lambda x: x["path"])

def update_directory_index(directory: Path, recursive: bool = False, audit_mode: bool = False, dry_run: bool = False):
    """Sync the index file for a directory.

    Args:
        directory: Directory to index
        recursive: Include files from subdirectories
        audit_mode: If True, flag items needing review with ⏳
        dry_run: If True, report what would change without writing
    """
    # Skip projects with their own indexing scripts
    if directory.name in SELF_INDEXED_PROJECTS:
        return

    # Special case for root projects directory
    if directory.name == "projects" or str(directory) == os.getenv("PROJECTS_ROOT"):
        index_file = directory / "00_Index_ROOT.md"
    else:
        # Use case-insensitive search for existing index file to avoid duplicates
        index_file = None
        potential_name = f"00_Index_{directory.name}.md".lower()
        for item in directory.iterdir():
            if item.name.lower() == potential_name:
                index_file = item
                break

        if not index_file:
            index_file = directory / f"00_Index_{directory.name}.md"

    # Parse existing descriptions to preserve human edits
    existing_descriptions = parse_existing_index(index_file)

    dir_inventory = get_directory_inventory(
        directory,
        existing_descriptions=existing_descriptions,
        audit_mode=audit_mode
    )
    file_inventory = get_file_inventory(
        directory,
        recursive,
        skip_file=index_file,
        existing_descriptions=existing_descriptions,
        audit_mode=audit_mode
    )

    if not dir_inventory and not file_inventory:
        return

    # Build the index content
    index_lines = [START_MARKER]

    # Directories section
    if dir_inventory:
        index_lines.append("\n### Subdirectories\n")
        index_lines.append("| Directory | Files | Description |")
        index_lines.append("| :--- | :---: | :--- |")
        for item in dir_inventory:
            index_lines.append(f"| [{item['name']}/]({item['link_target']}) | {item['file_count']} | {item['desc']} |")

    # Files section
    if file_inventory:
        index_lines.append("\n### Files\n")
        index_lines.append("| File | Description |")
        index_lines.append("| :--- | :--- |")
        for item in file_inventory:
            index_lines.append(f"| [{item['path']}]({item['path']}) | {item['desc']} |")

    index_lines.append(f"\n{END_MARKER}")
    
    index_content = "\n".join(index_lines)

    if index_file.exists():
        content = index_file.read_text()
        if START_MARKER in content and END_MARKER in content:
            # Use string replacement instead of re.sub to avoid backreference errors
            before = content.split(START_MARKER)[0]
            after = content.split(END_MARKER)[1]
            new_body = before + index_content + after
        else:
            new_body = content.rstrip() + "\n\n" + index_content
    else:
        # Create new index using rich template
        new_body = create_from_template(directory, index_content)
    
    if not index_file.exists() or index_file.read_text() != new_body:
        if dry_run:
            action = "Would create" if not index_file.exists() else "Would update"
            print(f"📋 {action}: {index_file.relative_to(directory.parent)} ({len(dir_inventory)} dirs, {len(file_inventory)} files)")
        else:
            index_file.write_text(new_body)
            print(f"📖 Librarian: Indexed {len(dir_inventory)} dirs, {len(file_inventory)} files in {directory.name}/")

def main():
    parser = argparse.ArgumentParser(description="The Librarian: Ecosystem Networking")
    parser.add_argument("path", nargs="?", default=".", help="Path to index")
    parser.add_argument("--recursive", "-r", action="store_true", help="Include subdirectories")
    parser.add_argument("--all-projects", action="store_true", help="Run Librarian across all project roots")
    parser.add_argument("--audit", "-a", action="store_true",
                        help="Audit mode: report empty dirs, missing READMEs, suspicious files to TODO.md")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show what would be changed without writing files")

    args = parser.parse_args()

    target = Path(args.path).resolve()

    if args.dry_run:
        print("🔍 Dry run mode: showing what would change...\n")
    if args.audit:
        print("🔍 Audit mode: flagging items needing review in index...\n")

    if args.all_projects:
        # Scan every project root
        root = Path(__file__).resolve().parents[3]
        for item in root.iterdir():
            # Index everything except hidden directories, junk, and ignored projects
            if item.is_dir() and not item.name.startswith(".") and item.name not in SKIP_DIRS and item.name not in IGNORE_PROJECTS:
                update_directory_index(item, recursive=True, audit_mode=args.audit, dry_run=args.dry_run)

        # Also index the root level files (non-recursive)
        update_directory_index(root, recursive=False, audit_mode=args.audit, dry_run=args.dry_run)
    else:
        update_directory_index(target, recursive=args.recursive, audit_mode=args.audit, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
