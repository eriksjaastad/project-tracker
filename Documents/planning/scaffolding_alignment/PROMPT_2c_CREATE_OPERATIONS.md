# Prompt 2c: Create OPERATIONS.md

**Estimated Time:** 10 minutes
**Model:** Any
**File to Create:** `Documents/OPERATIONS.md`

---

## Objective

Create an OPERATIONS.md document at the Documents/ root that describes how to run, deploy, and maintain project-tracker.

---

## CONSTRAINTS (READ FIRST)

- DO NOT invent commands — only document what actually works
- DO NOT use hardcoded absolute paths
- DO NOT put in a subdirectory — it goes at Documents/ root
- EXTRACT commands from existing AGENTS.md and CLAUDE.md
- FOLLOW the template structure below

---

## Context to Extract From

Read these files for operational commands:
- `AGENTS.md` — Run/test commands
- `CLAUDE.md` — Key commands, validation
- `pt.py` — Available CLI commands

---

## Template

```markdown
# Project Tracker Operations

> **Last Updated:** January 2026
> **Environment:** macOS, Python 3.11+

---

## Quick Start

```bash
# Navigate to project
cd ~/projects/project-tracker

# Activate virtual environment
source venv/bin/activate

# Launch dashboard
./pt launch
```

---

## Available Commands

| Command | Description |
|---------|-------------|
| `./pt launch` | Start the dashboard (opens browser) |
| `./pt launch --no-scan` | Start without scanning projects |
| `./pt scan` | Full project scan |
| `./pt list` | List all tracked projects |

---

## Development Setup

```bash
# Clone/navigate to project
cd ~/projects/project-tracker

# Create virtual environment (if not exists)
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Testing

```bash
# Activate venv first
source venv/bin/activate

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_scanner.py
```

---

## Database

- **Location:** `projects.db` (SQLite)
- **Schema:** `scripts/db/schema.py`
- **Reset:** Delete `projects.db` and run `./pt scan`

---

## Troubleshooting

### Dashboard won't start
1. Check venv is activated: `which python`
2. Check port 8000 is free: `lsof -i :8000`
3. Check dependencies: `pip install -r requirements.txt`

### Scan not finding projects
1. Verify `~/projects/` exists
2. Check projects have `00_Index_*.md` files
3. Run with verbose: `./pt scan --verbose`

---

## Maintenance

### Adding new discovery scanners
1. Create module in `scripts/discovery/`
2. Import in `scripts/discovery/__init__.py`
3. Add API route in `dashboard/app.py` if needed

### Updating dependencies
```bash
pip freeze > requirements.txt
```

---

*Part of project-scaffolding documentation standard.*
```

---

## Acceptance Criteria

- [ ] **Exists:** File is at `Documents/OPERATIONS.md`
- [ ] **Accurate:** Commands match what actually works
- [ ] **Complete:** Has Quick Start, Commands, Setup, Testing sections
- [ ] **No hardcoded paths:** Uses ~/projects/ or relative references

---

**Hand back to Floor Manager when complete.**
