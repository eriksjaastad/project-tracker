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

# Launch dashboard (this also performs an initial scan)
./pt launch
```

---

## Available Commands

| Command | Description |
|---------|-------------|
| `./pt launch` | Start the dashboard (opens browser) |
| `./pt launch --no-scan` | Start dashboard without performing a new project scan |
| `./pt scan` | Perform a full scan of all projects in the workspace |
| `./pt list` | List all tracked projects with their status |
| `./pt init` | Initialize the SQLite database and create schemas |

---

## Development Setup

```bash
# Clone/navigate to project
cd ~/projects/project-tracker

# Create virtual environment
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
pytest tests/test_parsers.py
```

---

## Database

- **Location:** `project_tracker.db` (SQLite)
- **Schema:** Defined in `scripts/db/schema.py`
- **Management:** Logic handled in `scripts/db/manager.py`
- **Reset:** To reset the database, you can use the `pt init` command (which will re-initialize tables) or delete the `.db` file and run a new scan.

---

## Troubleshooting

### Dashboard won't start
1. Verify the virtual environment is active: `which python` should point to the `venv` directory. See [PROJECT_STRUCTURE_STANDARDS](../../project-scaffolding/Documents/PROJECT_STRUCTURE_STANDARDS.md).
2. Ensure required ports (default 8000) are not in use: `lsof -i :8000`.
3. Check if all dependencies are installed: `pip install -r requirements.txt`.

### Scan not finding projects
1. Verify the project root is correct in `config.py` (defaults to `~/projects`).
2. Ensure projects follow the naming convention and have a `README.md` or `00_Index_*.md` file. See [PROJECT_STRUCTURE_STANDARDS](../../project-scaffolding/Documents/PROJECT_STRUCTURE_STANDARDS.md).
3. Check the logs for any discovery errors: `tail -f logs/project_tracker.log`.

---

## Maintenance

### Adding new discovery scanners
1. Add the new scanning logic as a module in `scripts/discovery/`.
2. Update the `DatabaseManager` if new tables or fields are required.
3. Integrate the scanner into the `discover_projects` flow in `scripts/discovery/project_scanner.py`.
4. Update the dashboard in `dashboard/app.py` and relevant templates to display new data.

### Updating dependencies
When adding new libraries, update the `requirements.txt` file:
```bash
pip freeze > requirements.txt
```

---

*See also: [ARCHITECTURE](../../hypocrisynow/ARCHITECTURE.md), [SCAFFOLDING_TRANSFER_GUIDE](SCAFFOLDING_TRANSFER_GUIDE.md), and [Doppler Secrets Management](Documents/reference/DOPPLER_SECRETS_MANAGEMENT.md).*

## Related Documentation

- [PROJECT_KICKOFF_GUIDE](../../project-scaffolding/Documents/PROJECT_KICKOFF_GUIDE.md) - project setup
- [README](README) - Project Tracker
