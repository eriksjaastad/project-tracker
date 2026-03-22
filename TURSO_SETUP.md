# Turso Setup Guide — project-tracker (open-kanban)

> Step-by-step guide for cards #5227, #5231, #5232, #5233.

---

## Prerequisites

Card #5227: Install Turso CLI on both machines first.

```bash
curl -sSL tur.so/install | sh
turso auth login
```

---

## Step 1 — Export tracker.db (card #5231)

Run on your laptop:

```bash
cd ~/projects/project-tracker
bash scripts/export_tracker_db.sh
# → creates tracker_export.sql
```

---

## Step 2 — Create Turso DB and import (card #5231)

```bash
# Create the database
turso db create open-kanban

# Import the dump
turso db shell open-kanban < tracker_export.sql

# Verify row count
turso db shell open-kanban "SELECT COUNT(*) FROM tasks;"
```

---

## Step 3 — Get credentials and add to Doppler (card #5232)

```bash
# Get the URL
turso db show open-kanban --url
# → libsql://open-kanban-<org>.turso.io

# Create a token
turso db tokens create open-kanban
# → (copy the token output)
```

Then add to Doppler (project: `project-tracker`, config: `dev` + `prd`):

```bash
doppler secrets set TURSO_KANBAN_URL="libsql://open-kanban-<org>.turso.io"
doppler secrets set TURSO_KANBAN_TOKEN="<paste token>"
```

Install the libsql Python package in the project venv:

```bash
cd ~/projects/project-tracker
uv add libsql
```

---

## Step 4 — Test on laptop (card #5232)

```bash
cd ~/projects/project-tracker
doppler run -- ./pt tasks list
# Should show tasks from Turso cloud

doppler run -- ./pt tasks show 5232
# Verify specific card readable from cloud
```

---

## Step 5 — Deploy to Mac Mini (card #5233)

SSH into the Mac Mini, then:

```bash
cd ~/projects/project-tracker
git pull
uv sync   # installs libsql
doppler run -- ./pt tasks list
# Should show the same tasks — shared Kanban confirmed!
# CEO sees laptop cards, laptop sees CEO completions ✅
```

---

## Notes

- **Offline mode:** If `TURSO_KANBAN_URL` / `TURSO_KANBAN_TOKEN` are not set, the `pt` CLI automatically falls back to the local `tracker.db` file.
- **File-based safety backups** (data/backups/, ~/.project-tracker/backups/) remain local-file based — this is correct since they guard against local data loss and are not cloud-synced.
- **Fingerprint checking** remains local — the `.db-fingerprint` file guards against local file replacement accidents.
