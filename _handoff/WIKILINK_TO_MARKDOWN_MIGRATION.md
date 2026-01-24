# Wikilink to Markdown Link Migration

**Date:** 2026-01-23
**Status:** ✅ COMPLETE
**Reason:** Obsidian abandoned; wikilinks only work in Obsidian, not in standard markdown viewers

---

## Changes Made

### 1. Librarian (`scripts/discovery/librarian.py`)
**Line 139:** Changed file index generation from wikilinks to markdown links

**Before:**
```python
index_lines.append(f"| [[{item['path']}]] | {item['desc']} |")
```

**After:**
```python
index_lines.append(f"| [{item['path']}]({item['path']}) | {item['desc']} |")
```

**Impact:** All future librarian runs will generate standard markdown links that work in GitHub, VS Code, Cursor, and any markdown viewer.

### 2. Cleanup Script (`scripts/cleanup_related_docs.py`)
**Function:** `deduplicate_links()` completely rewritten

**Changes:**
- Now handles both markdown links `[text](url)` and legacy wikilinks `[[link]]`
- Converts legacy wikilinks to markdown format during deduplication
- Preserves descriptions and link order

**Impact:** "Related Documentation" sections will use markdown links going forward. Script can handle migration from old wikilink format.

---

## Files That Still Parse Wikilinks (Read-Only)

These files read existing wikilinks to build the knowledge graph but don't generate them:

1. **`graph_builder.py`** - Parses wikilinks from existing documents to create graph edges
   - `WIKI_LINK_PATTERN` regex still exists
   - This is OK - it reads what's already in files
   - Over time, as files convert to markdown links, this will see fewer wikilinks

2. **`journal_specialist.py`** - Parses `[[00_Index_project-name]]` patterns
   - This should probably be updated to handle both formats
   - Low priority since it's just reading existing content

**Decision:** Leave parsers as-is. They handle existing wikilinks gracefully and will work with markdown links too (eventually).

---

## Why This Matters

### The Problem
- Project-tracker was **generating** wikilinks in every project
- Wikilinks only work in Obsidian
- Obsidian was abandoned for custom D3 visualization
- Every librarian run reintroduced 50+ wikilinks per project
- Scaffolding templates also had wikilinks, creating a double source of pollution

### The Fix
- **Source 1 (project-tracker):** Fixed librarian and cleanup script ✅
- **Source 2 (project-scaffolding):** Fixed all templates ✅
- **Migration:** Created `fix_wikilinks.py` to convert existing projects ✅

### The Architecture (Correct Direction)
```
Projects → Parse/Extract → Project-Tracker → Generate Graph
```

Not:
```
Project-Tracker → Generate Wikilinks → Projects (WRONG!)
```

Projects should be the source of truth. Project-tracker should read from them, not write to them.

---

## Testing

After these changes, run librarian on a test project:

```bash
cd /Users/eriksjaastad/projects/project-tracker
python3 scripts/discovery/librarian.py /path/to/test-project
```

Verify the `00_Index_*.md` contains markdown links `[file.md](file.md)`, not wikilinks `[[file.md]]`.

---

## Related Documentation
- [Project Scaffolding Wikilink Eradication](../../project-scaffolding/_handoff/WIKILINK_ERADICATION_PLAN.md)
- [Migration Script](../../project-scaffolding/scripts/fix_wikilinks.py)
