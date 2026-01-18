#!/usr/bin/env python3
"""
Cleanup Script: Remove duplicate links in "Related Documentation" sections.

The auto-linker was appending the same link blocks multiple times.
This script deduplicates them while preserving unique links.

Usage:
    python cleanup_related_docs.py --dry-run          # Preview changes
    python cleanup_related_docs.py                    # Apply changes
    python cleanup_related_docs.py --path /some/dir   # Target specific directory
"""

import re
import argparse
from pathlib import Path
from collections import OrderedDict

PROJECTS_ROOT = Path(__file__).resolve().parents[2]

SKIP_DIRS = {
    "node_modules", "venv", ".venv", "__pycache__", ".git",
    "_trash", "archives", ".pytest_cache", ".ruff_cache"
}


def extract_related_docs_section(content: str) -> tuple[str, str, str]:
    """
    Split content into: before_section, related_docs_section, after_section.
    Returns (before, section, after) or (content, "", "") if no section found.
    """
    pattern = r'(## Related Documentation\s*\n)'
    match = re.search(pattern, content)

    if not match:
        return content, "", ""

    start = match.start()
    header = match.group(1)

    # Find where the section ends (next ## header or end of file)
    rest = content[match.end():]
    next_header = re.search(r'\n## ', rest)

    if next_header:
        section_content = rest[:next_header.start()]
        after = rest[next_header.start():]
    else:
        section_content = rest
        after = ""

    before = content[:start]
    section = header + section_content

    return before, section, after


def deduplicate_links(section: str) -> str:
    """
    Deduplicate wiki-links in a Related Documentation section.
    Preserves order of first occurrence.
    """
    if not section:
        return ""

    # Extract the header
    lines = section.split('\n')
    header = lines[0] if lines else "## Related Documentation"

    # Find all wiki-links with their descriptions
    link_pattern = r'-\s*\[\[([^\]]+)\]\](?:\s*-\s*(.+))?'
    seen_links = OrderedDict()

    for line in lines[1:]:
        match = re.match(link_pattern, line.strip())
        if match:
            link_target = match.group(1)
            description = match.group(2) or ""
            # Keep first occurrence only
            if link_target not in seen_links:
                seen_links[link_target] = description

    if not seen_links:
        return ""

    # Rebuild section with unique links
    new_lines = [header, ""]
    for link, desc in seen_links.items():
        if desc:
            new_lines.append(f"- [[{link}]] - {desc}")
        else:
            new_lines.append(f"- [[{link}]]")
    new_lines.append("")

    return '\n'.join(new_lines)


def cleanup_file(file_path: Path, dry_run: bool = True) -> dict:
    """
    Clean up duplicate Related Documentation links in a file.
    Returns stats about what was changed.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        return {"error": str(e)}

    before, section, after = extract_related_docs_section(content)

    if not section:
        return {"skipped": "no Related Documentation section"}

    # Count original links
    original_links = re.findall(r'\[\[([^\]]+)\]\]', section)
    original_count = len(original_links)

    # Deduplicate
    new_section = deduplicate_links(section)
    new_links = re.findall(r'\[\[([^\]]+)\]\]', new_section)
    new_count = len(new_links)

    if original_count == new_count:
        return {"skipped": "no duplicates found"}

    # Rebuild content
    new_content = before.rstrip() + "\n\n" + new_section.strip() + "\n"
    if after:
        new_content += "\n" + after.lstrip()

    duplicates_removed = original_count - new_count

    if not dry_run:
        file_path.write_text(new_content, encoding='utf-8')

    return {
        "cleaned": True,
        "original_links": original_count,
        "unique_links": new_count,
        "duplicates_removed": duplicates_removed
    }


def scan_and_cleanup(root: Path, dry_run: bool = True) -> dict:
    """Scan all markdown files and cleanup duplicates."""
    stats = {
        "files_scanned": 0,
        "files_cleaned": 0,
        "files_skipped": 0,
        "total_duplicates_removed": 0,
        "errors": []
    }

    for md_file in root.rglob("*.md"):
        # Skip ignored directories
        if any(part in SKIP_DIRS for part in md_file.parts):
            continue
        if any(part.startswith(".") for part in md_file.parts):
            continue

        stats["files_scanned"] += 1
        result = cleanup_file(md_file, dry_run)

        if "error" in result:
            stats["errors"].append(f"{md_file}: {result['error']}")
        elif "skipped" in result:
            stats["files_skipped"] += 1
        elif result.get("cleaned"):
            stats["files_cleaned"] += 1
            stats["total_duplicates_removed"] += result["duplicates_removed"]

            rel_path = md_file.relative_to(root)
            action = "Would clean" if dry_run else "Cleaned"
            print(f"  {action}: {rel_path} ({result['duplicates_removed']} duplicates)")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Cleanup duplicate Related Documentation links")
    parser.add_argument("--path", default=str(PROJECTS_ROOT), help="Root path to scan")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    mode = "DRY RUN" if args.dry_run else "CLEANUP"

    print(f"\n🧹 Related Documentation Cleanup [{mode}]")
    print(f"   Root: {root}\n")

    stats = scan_and_cleanup(root, dry_run=args.dry_run)

    print(f"\n📊 Summary:")
    print(f"   Files scanned: {stats['files_scanned']}")
    print(f"   Files with duplicates: {stats['files_cleaned']}")
    print(f"   Total duplicates removed: {stats['total_duplicates_removed']}")

    if stats["errors"]:
        print(f"\n⚠️ Errors ({len(stats['errors'])}):")
        for err in stats["errors"][:5]:
            print(f"   {err}")

    if args.dry_run and stats["files_cleaned"] > 0:
        print(f"\n💡 Run without --dry-run to apply changes")


if __name__ == "__main__":
    main()
