#!/usr/bin/env python3
"""
The Librarian - Global Ecosystem Networking & Indexing.
Automatically maintains 00_Index_*.md files with 'educated' descriptions.
"""

import os
import re
import argparse
from pathlib import Path
from typing import List, Dict, Optional

# Standard ignore list
SKIP_DIRS = {
    "node_modules", "venv", ".venv", "__pycache__", ".git", 
    "data", "logs", "archives", "temp", "tmp", "cursor_history",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".next",
    "_trash", "_inbox", "trash"
}

SKIP_EXTENSIONS = {
    ".pyc", ".db", ".sqlite", ".zip", ".tar.gz", ".dmg", ".pdf", ".jpg", ".png", ".gif",
    ".DS_Store", ".plist", ".exe", ".bin"
}

# Markers for auto-generated content
START_MARKER = "<!-- LIBRARIAN-INDEX-START -->"
END_MARKER = "<!-- LIBRARIAN-INDEX-END -->"

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
                # Skip the title if it's just the filename
                if line.startswith('#') and file_path.stem.lower() in line.lower():
                    continue
                # Found first real line of text
                desc = re.sub(r'#+\s*', '', line).strip()
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

def get_file_inventory(directory: Path, recursive: bool = False, skip_file: Optional[Path] = None) -> List[Dict]:
    """Build a detailed inventory of files in a directory."""
    inventory = []
    pattern = "**/*" if recursive else "*"
    
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
            
        inventory.append({
            "path": rel_path,
            "name": item.name,
            "desc": extract_description(item)
        })
        
    return sorted(inventory, key=lambda x: x["path"])

def update_directory_index(directory: Path, recursive: bool = False):
    """Sync the index file for a directory."""
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
    
    inventory = get_file_inventory(directory, recursive, skip_file=index_file)
    
    if not inventory:
        return

    # Build the index content
    index_lines = [START_MARKER, "\n### File Index\n"]
    index_lines.append("| File | Description |")
    index_lines.append("| :--- | :--- |")
    for item in inventory:
        # Use wiki-links for the file path
        index_lines.append(f"| [[{item['path']}]] | {item['desc']} |")
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
        # Create new index with standard project-tracker frontmatter
        new_body = f"""---
tags:
  - type/index
  - p/{directory.name.lower()}
status: #status/active
---

# {directory.name} Index

{index_content}
"""
    
    if not index_file.exists() or index_file.read_text() != new_body:
        index_file.write_text(new_body)
        print(f"📖 Librarian: Indexed {len(inventory)} files in {directory.name}/")

def main():
    parser = argparse.ArgumentParser(description="The Librarian: Ecosystem Networking")
    parser.add_argument("path", nargs="?", default=".", help="Path to index")
    parser.add_argument("--recursive", "-r", action="store_true", help="Include subdirectories")
    parser.add_argument("--all-projects", action="store_true", help="Run Librarian across all project roots")
    
    args = parser.parse_args()
    
    if args.all_projects:
        # Scan every project root
        root = Path(__file__).resolve().parents[3]
        for item in root.iterdir():
            # Index everything except hidden directories and junk
            if item.is_dir() and not item.name.startswith(".") and item.name not in SKIP_DIRS:
                update_directory_index(item, recursive=True)
        
        # Also index the root level files (non-recursive)
        update_directory_index(root, recursive=False)
    else:
        target = Path(args.path).resolve()
        update_directory_index(target, recursive=args.recursive)

if __name__ == "__main__":
    main()
