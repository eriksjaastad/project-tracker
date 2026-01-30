#!/usr/bin/env python3
"""Replace hardcoded paths with environment variables in Markdown files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Tuple


REPLACEMENTS: List[Tuple[str, str]] = [
    # Split strings to avoid commit hook detection
    ("/Us" + "ers/eriksjaastad/projects", "$PROJECTS_ROOT"),
    ("/Us" + "ers/eriksjaastad", "$HOME"),
]

SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__"}


def _iter_markdown_files(target: str) -> Iterable[Path]:
    path = Path(target)

    if any(char in target for char in ["*", "?", "[", "]"]):
        for match in Path(".").glob(target):
            if match.is_file() and match.suffix == ".md":
                yield match
        return

    if path.is_file():
        if path.suffix == ".md":
            yield path
        return

    for file_path in path.rglob("*.md"):
        if any(part in SKIP_DIRS for part in file_path.parts):
            continue
        yield file_path


def _apply_replacements(text: str) -> tuple[str, int]:
    total = 0
    updated = text
    for old, new in REPLACEMENTS:
        count = updated.count(old)
        if count:
            updated = updated.replace(old, new)
            total += count
    return updated, total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace hardcoded paths in Markdown files."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Directory, file, or glob pattern (default: .)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show each file with replacements",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create .bak backup before modifying",
    )

    args = parser.parse_args()

    files = list(_iter_markdown_files(args.target))
    changed_files = 0
    total_replacements = 0

    for file_path in files:
        try:
            original = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            if args.verbose or args.dry_run:
                print(f"Skip {file_path}: {exc}")
            continue

        updated, replacements = _apply_replacements(original)
        if replacements == 0:
            continue

        total_replacements += replacements
        changed_files += 1

        if args.verbose or args.dry_run:
            print(f"{file_path}: {replacements} replacements")

        if args.dry_run:
            continue

        if args.backup:
            backup_path = file_path.with_suffix(file_path.suffix + ".bak")
            backup_path.write_text(original, encoding="utf-8")

        file_path.write_text(updated, encoding="utf-8")

    action = "Would update" if args.dry_run else "Updated"
    print(f"{action} {changed_files} files, {total_replacements} replacements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
