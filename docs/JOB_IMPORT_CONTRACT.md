# Job Import JSONL Contract

This document defines the JSONL export/import contract between job-search scripts and project-tracker's `pt jobs import` command.

## Overview

Job-search scripts (ATS sweep, HN scraper) can optionally export discovered listings as JSONL (one JSON object per line). The `pt jobs import` command reads this format and upserts jobs into the local project-tracker database.

## JSONL Format

Each line must be a valid JSON object with these fields:

### Required Fields

- `company` (string): Company name, will be trimmed
- `title` (string): Job title, will be trimmed  
- `url` (string): Canonical posting URL (unique key for upsert)
- `source` (string): One of: `ats_sweep`, `hn`, `manual`

### Optional Fields

- `location` (string | null): Job location (e.g., "Remote", "San Francisco, CA")
- `posted_date` (string | null): ISO date string when job was posted (e.g., "2026-09-20")
- `category` (string): Must be one of:
  - `Frontend/React`
  - `Full Stack`
  - `Forward Deployed / Solutions`
  - `SEO`
  - `Backend`
  - `Other` (default if omitted)
- `raw` (string | null): Original posting text/HTML for reference. **Must be preserved**; never omit this field if the source has it.

### HN Multi-Role Handling

HN "Who's Hiring" comments often contain multiple job listings in a single comment. The export contract must handle this explicitly:

1. **Single role per line**: Each distinct role mentioned in a comment becomes one JSONL line with its own URL (constructed as `{base_comment_url}#role-{N}` or similar stable fragment)
2. **Unknown fields**: If a role cannot be parsed into company/title/location, the line should still be exported with:
   - `company`: "Unknown" or best-effort extraction
   - `title`: "See raw text" or best-effort extraction
   - `raw`: Full comment text (required)
   - A note in `raw` or metadata that this needs manual review

**Contract violation**: Silently dropping roles from multi-role comments is not allowed. Every advertised position must produce one JSONL line.

## Idempotency

- Repeated imports are idempotent by `url` (the unique key)
- On conflict: updates company, title, location, source, posted_date, category
- On conflict: preserves existing first_seen, deleted_at, and raw (if new raw is null)
- A dismissed job (deleted_at set) stays dismissed after re-import

## Example

```jsonl
{"company": "Acme Corp", "title": "Senior React Engineer", "url": "https://jobs.acme.com/123", "source": "ats_sweep", "location": "Remote", "category": "Frontend/React", "raw": "<html>...original ATS posting...</html>"}
{"company": "Widget Inc", "title": "Full Stack Developer", "url": "https://news.ycombinator.com/item?id=12345678#role-1", "source": "hn", "category": "Full Stack", "raw": "Widget Inc | Full Stack | Remote | $120k-$180k\n\nWe're looking for..."}
{"company": "Unknown", "title": "See raw text", "url": "https://news.ycombinator.com/item?id=12345678#role-2", "source": "hn", "category": "Other", "raw": "Stealth startup | multiple roles | contact jobs@example.com"}
```

## Usage

```bash
# job-search script exports to JSONL
python tools/ats_sweep.py --export-jsonl > /tmp/ats_jobs.jsonl

# project-tracker imports (upserts)
pt jobs import /tmp/ats_jobs.jsonl

# Repeat safely (idempotent)
pt jobs import /tmp/ats_jobs.jsonl
```

## Companion Changes Required in job-search Repo

The job-search repository will need:

1. Add `--export-jsonl` flag to `tools/ats_sweep.py` and HN scripts
2. Print normal stdout by default (unchanged behavior)
3. When `--export-jsonl` is set, write JSONL to stdout instead (or to a specified file)
4. For HN multi-role comments:
   - Parse each distinct role into separate JSONL lines
   - Generate stable fragment URLs (#role-1, #role-2, etc.)
   - Export unparseable roles with "Unknown"/"See raw text" and full raw text
5. Always include `raw` field when available

These changes are OUT OF SCOPE for this PR (#7536), which implements only the project-tracker import side. A follow-up card/PR in job-search will implement the export.
