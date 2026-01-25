#!/usr/bin/env python3
"""
Generate README.md index files for Documents/ directories.

Finds all Documents/ directories across the ecosystem and creates/updates
a README.md that links directly to every document within.
"""

import argparse
import os
from datetime import datetime
from pathlib import Path


def find_documents_dirs(root: Path) -> list[Path]:
    """Find all Documents/ directories in the ecosystem."""
    docs_dirs = []

    skip_dirs = {
        'node_modules', 'venv', '.venv', '__pycache__',
        '.git', '.pytest_cache', 'dist', 'build', '.next',
        '_trash', 'trash', 'archives', '_inbox',
        'logs', 'temp', 'tmp', 'cursor_history', 'data'
    }

    for dirpath, dirnames, _ in os.walk(root):
        # Skip hidden and junk directories
        dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in skip_dirs]

        p = Path(dirpath)
        if p.name == 'Documents':
            docs_dirs.append(p)

    return docs_dirs


def collect_documents(docs_dir: Path) -> dict[str, list[Path]]:
    """
    Collect all documents in a Documents/ directory, organized by subdirectory.

    Returns dict like:
    {
        '': [file1.md, file2.md],  # root level
        'patterns': [code-review.md, learning-loop.md],
        'reference': [LOCAL_MODEL.md],
    }
    """
    documents = {}

    for item in sorted(docs_dir.rglob('*')):
        if item.is_file() and item.suffix.lower() in {'.md', '.yaml', '.yml', '.json'}:
            # Get relative path from Documents/
            rel_path = item.relative_to(docs_dir)

            # Determine the category (subdirectory or root)
            if len(rel_path.parts) == 1:
                category = ''
            else:
                category = str(rel_path.parent)

            if category not in documents:
                documents[category] = []
            documents[category].append(item)

    return documents


def generate_readme(docs_dir: Path, documents: dict[str, list[Path]], dry_run: bool = False) -> str:
    """Generate README.md content for a Documents/ directory."""
    project_name = docs_dir.parent.name

    lines = [
        f"# {project_name} Documents",
        "",
        f"*Auto-generated index. Last updated: {datetime.now().strftime('%Y-%m-%d')}*",
        "",
    ]

    # Sort categories: root first, then alphabetically
    categories = sorted(documents.keys(), key=lambda x: (x != '', x))

    for category in categories:
        files = documents[category]

        if category == '':
            lines.append("## Overview")
        else:
            # Convert path to title (patterns -> Patterns, reference -> Reference)
            title = category.replace('/', ' / ').title()
            lines.append(f"## {title}")

        lines.append("")

        for file_path in sorted(files, key=lambda x: x.name.lower()):
            rel_path = file_path.relative_to(docs_dir)
            # Create a readable name from filename
            name = file_path.stem.replace('_', ' ').replace('-', ' ')
            lines.append(f"- [{name}]({rel_path})")

        lines.append("")

    return '\n'.join(lines)


def update_documents_index(docs_dir: Path, dry_run: bool = False) -> tuple[bool, str]:
    """
    Update or create README.md for a Documents/ directory.

    Returns (was_updated, message)
    """
    documents = collect_documents(docs_dir)

    if not documents:
        return False, f"No documents found in {docs_dir}"

    readme_path = docs_dir / 'README.md'
    new_content = generate_readme(docs_dir, documents, dry_run)

    # Check if update needed
    if readme_path.exists():
        existing = readme_path.read_text()
        if existing == new_content:
            return False, f"Already up to date: {docs_dir}"

    if dry_run:
        return True, f"Would update: {readme_path}"

    readme_path.write_text(new_content)
    return True, f"Updated: {readme_path}"


def main():
    parser = argparse.ArgumentParser(
        description="Generate README.md index files for Documents/ directories"
    )
    parser.add_argument(
        '--root',
        type=str,
        default=str(Path(__file__).resolve().parents[2]),
        help='Root directory to scan (default: projects root)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--project',
        type=str,
        help='Only process a specific project'
    )
    args = parser.parse_args()

    root = Path(args.root)
    print(f"Scanning for Documents/ directories in: {root}")

    docs_dirs = find_documents_dirs(root)

    if args.project:
        docs_dirs = [d for d in docs_dirs if args.project in str(d)]

    print(f"Found {len(docs_dirs)} Documents/ directories")
    print()

    updated = 0
    skipped = 0

    for docs_dir in sorted(docs_dirs):
        was_updated, message = update_documents_index(docs_dir, args.dry_run)
        print(message)
        if was_updated:
            updated += 1
        else:
            skipped += 1

    print()
    action = "Would update" if args.dry_run else "Updated"
    print(f"{action}: {updated} | Skipped: {skipped}")


if __name__ == '__main__':
    main()
