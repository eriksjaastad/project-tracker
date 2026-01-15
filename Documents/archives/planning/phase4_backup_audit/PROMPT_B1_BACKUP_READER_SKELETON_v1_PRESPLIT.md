# Prompt B1: Backup Reader Skeleton

**Task:** Create the basic structure for backup_reader.py
**Estimated Time:** 5-10 minutes
**Worker Model:** qwen3:4b (preferred) or deepseek-r1:14b

---

## CONSTRAINTS (READ FIRST)

- DO NOT implement detection logic yet - skeleton only
- DO NOT hardcode paths - use `Path.home()` or environment variables
- DO NOT add features beyond the acceptance criteria
- COPY the import and structure pattern from telemetry_reader.py exactly
- OUTPUT a single complete file

---

## Task Description

Create `scripts/discovery/backup_reader.py` with:
1. Module docstring explaining purpose
2. Imports (pathlib, logging, os, typing)
3. Logger setup
4. Path constants for rclone config (configurable via env var)
5. Stub functions with docstrings (no implementation yet)

---

## [ACCEPTANCE CRITERIA] (MANDATORY CHECKLIST)

- [ ] **File Created:** `scripts/discovery/backup_reader.py` exists
- [ ] **Imports:** Uses pathlib.Path, logging, os, typing
- [ ] **Logger:** Has `logger = logging.getLogger(__name__)`
- [ ] **Config Path:** `RCLONE_CONFIG_PATH` uses Path.home() + env var fallback
- [ ] **Stub Functions:**
  - `get_backup_status() -> dict` (stub returns empty dict)
  - `get_unbacked_paths() -> list[str]` (stub returns empty list)
  - `_parse_rclone_config() -> dict` (stub returns empty dict)
- [ ] **No Hardcoded Paths:** All paths use Path.home() or env vars
- [ ] **Runs Without Error:** `python -c "from scripts.discovery.backup_reader import get_backup_status; print('OK')"`

---

## Context Bridge: Pattern to Follow

Copy this structure from `telemetry_reader.py`:

```python
"""
Backup Reader for rclone integration.
Reads rclone config and detects backup coverage for the dashboard.
"""
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# rclone config location (configurable via environment variable)
_default_config = Path.home() / ".config" / "rclone" / "rclone.conf"
RCLONE_CONFIG_PATH = Path(os.getenv("RCLONE_CONFIG_PATH", str(_default_config)))


def _parse_rclone_config() -> dict[str, dict]:
    """
    Parse rclone.conf and return remote configurations.

    Returns:
        Dict mapping remote name to config dict
    """
    # TODO: Implement in B2
    return {}


def get_backup_status() -> dict[str, Any]:
    """
    Get backup status for the dashboard.

    Returns:
        Dict with remote info, backup coverage, and warnings
    """
    # TODO: Implement in B2/B3
    return {
        "remotes": [],
        "critical_unbacked": [],
        "status": "unknown",
        "message": "Not yet implemented"
    }


def get_unbacked_paths() -> list[str]:
    """
    Get list of critical paths not covered by backups.

    Returns:
        List of path strings that should be backed up
    """
    # TODO: Implement in B3
    return []


if __name__ == "__main__":
    # Quick test
    status = get_backup_status()
    print(f"Status: {status}")
```

---

## Verification Command

After creating the file, run:

```bash
cd $PROJECTS_ROOT/project-tracker
python -c "
from scripts.discovery.backup_reader import get_backup_status, get_unbacked_paths
status = get_backup_status()
unbacked = get_unbacked_paths()
print(f'get_backup_status() returned: {type(status).__name__}')
print(f'get_unbacked_paths() returned: {type(unbacked).__name__}')
print('OK - Skeleton created successfully')
"
```

**Expected:** Both functions return their stub values without error.

---

## Result

- [ ] PASS: File created and verification command succeeds
- [ ] FAIL: Describe error

**Hand back to Floor Manager when complete.**


## Related Documentation

- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[LOCAL_MODEL_LEARNINGS]] - local AI

