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

HN "Who's Hiring" comments are free text, and one comment often advertises several roles. Their headers cannot be parsed completely, so the contract guarantees one row per comment and treats per-role rows as extras:

1. **Guaranteed `#post` row**: Every exported HN comment produces exactly one JSONL line with URL `{comment_url}#post` and the **full comment text** in `raw`. Its `title` is always `"Full HN post (read for every role)"`. `company` is best-effort; when the header cannot be parsed, use `company: "Hacker News (company not parsed)"`. Because this row always carries the whole comment, no advertised role is lost even when parsing fails.
2. **Best-effort `#role-N` rows**: When the exporter can confidently split out individual roles, it may also emit one line per role with URL `{comment_url}#role-{N}` (N starting at 1, stable for the same comment text). These are optional and may be incomplete; consumers must not assume every role has one.

**Contract violation**: Omitting the `#post` row for an exported comment, or emitting it without the full comment text, is not allowed. Missing or partial `#role-N` rows are not a violation.

The importer needs no special handling: `url` is the unique key, so `#post` and each `#role-N` are separate jobs.

## Idempotency

- Repeated imports are idempotent by `url` (the unique key)
- On conflict: updates company, title, location, source, posted_date, category
- On conflict: preserves existing first_seen, deleted_at, and raw (if new raw is null)
- A dismissed job (deleted_at set) stays dismissed after re-import

## Example

```jsonl
{"company": "Acme Corp", "title": "Senior React Engineer", "url": "https://jobs.acme.com/123", "source": "ats_sweep", "location": "Remote", "category": "Frontend/React", "raw": "<html>...original ATS posting...</html>"}
{"company": "Widget Inc", "title": "Full HN post (read for every role)", "url": "https://news.ycombinator.com/item?id=12345678#post", "source": "hn", "category": "Other", "raw": "Widget Inc | Full Stack, Backend | Remote | $120k-$180k\n\nWe're looking for..."}
{"company": "Widget Inc", "title": "Full Stack Developer", "url": "https://news.ycombinator.com/item?id=12345678#role-1", "source": "hn", "category": "Full Stack", "raw": "Widget Inc | Full Stack, Backend | Remote | $120k-$180k\n\nWe're looking for..."}
{"company": "Hacker News (company not parsed)", "title": "Full HN post (read for every role)", "url": "https://news.ycombinator.com/item?id=87654321#post", "source": "hn", "category": "Other", "raw": "Stealth startup hiring several engineers, contact jobs@example.com"}
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
4. For HN comments:
   - Always export one `#post` line per comment with the full comment text in `raw`, titled "Full HN post (read for every role)" (company "Hacker News (company not parsed)" when the header can't be parsed)
   - Optionally add `#role-N` lines (stable fragments #role-1, #role-2, ...) for roles that parse cleanly
5. Always include `raw` field when available

These changes are OUT OF SCOPE for this PR (#7536), which implements only the project-tracker import side. A follow-up card/PR in job-search will implement the export.
