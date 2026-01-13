#!/usr/bin/env python3
import os
import re
from pathlib import Path

# Configuration
# We handle both the full project path and the generic user home prefix
REPLACEMENTS = {
    "/Users/eriksjaastad/projects": "$PROJECTS_ROOT",
    "/Users/eriksjaastad": "$HOME"
}
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

def fix_validate_script():
    """Remove Documents/core from mandatory directories and add logs to exclude."""
    validate_script = PROJECT_ROOT / "scripts" / "validate_project.py"
    if not validate_script.exists():
        print(f"⚠️  Could not find {validate_script}")
        return

    content = validate_script.read_text()
    
    # Remove "Documents/core" from the list
    new_content = re.sub(r'    "Documents/core",?\n', '', content)
    # Handle the logs exclusion if not already done (though we did it via StrReplace, let's be sure)
    if '"logs"' not in new_content:
        new_content = new_content.replace('"data"', '"data", "logs"')
    
    if content != new_content:
        validate_script.write_text(new_content)
        print(f"✅ Updated {validate_script.name}")
    else:
        print(f"ℹ️  {validate_script.name} already updated or pattern not found.")

def cleanup_absolute_paths():
    """Replace hardcoded absolute paths with variables in all markdown and config files."""
    count = 0
    extensions = {".md", ".cursorrules", ".cursorignore", ".sh"}
    
    # Files to skip to avoid self-replacement or breaking scripts
    skip_files = {"fix_portability.py", "validate_project.py", "warden_audit.py"}

    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip directories
        if any(d in root for d in [".git", "venv", "__pycache__", "node_modules", "data", "logs"]):
            continue

        for file in files:
            if file in skip_files:
                continue
                
            file_path = Path(root) / file
            if file_path.suffix in extensions or file in [".cursorrules", ".cursorignore"]:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    new_content = content
                    for old, new in REPLACEMENTS.items():
                        if old in new_content:
                            new_content = new_content.replace(old, new)
                    
                    if content != new_content:
                        file_path.write_text(new_content, encoding="utf-8")
                        print(f"✅ Updated {file_path.relative_to(PROJECT_ROOT)}")
                        count += 1
                except Exception as e:
                    print(f"❌ Error processing {file_path}: {e}")

    print(f"\n✨ Path cleanup complete. Updated {count} files.")

if __name__ == "__main__":
    print(f"🚀 Starting Enhanced Portability Cleanup in {PROJECT_ROOT}...\n")
    fix_validate_script()
    cleanup_absolute_paths()
    print("\n🎉 All tasks complete.")
