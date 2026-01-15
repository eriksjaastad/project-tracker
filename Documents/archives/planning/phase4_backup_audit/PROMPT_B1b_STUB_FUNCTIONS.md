# Prompt B1b: Backup Reader - Stub Functions

**Task:** Add stub functions to backup_reader.py
**Estimated Time:** 3-5 minutes
**Worker Model:** qwen3:4b or deepseek-r1:14b
**Depends On:** B1a (file must exist with imports)

---

## CONSTRAINTS (READ FIRST)

- DO NOT rewrite the file - APPEND code after existing content
- DO NOT implement logic - stubs only (return empty values)
- KEEP the addition under 30 lines

---

## Task Description

Add to `scripts/discovery/backup_reader.py`:
1. `_parse_rclone_config()` stub - returns empty dict
2. `get_backup_status()` stub - returns dict with placeholder values
3. `get_unbacked_paths()` stub - returns empty list

---

## [ACCEPTANCE CRITERIA]

- [x] `_parse_rclone_config()` exists, returns `{}`
- [x] `get_backup_status()` exists, returns dict with status/message keys
- [x] `get_unbacked_paths()` exists, returns `[]`
- [x] All functions have docstrings
- [x] Runs without error

---

## Code to Append

```python


def _parse_rclone_config() -> dict[str, dict]:
    """Parse rclone.conf and return remote configurations."""
    # TODO: Implement in B2
    return {}


def get_backup_status() -> dict[str, Any]:
    """Get backup status for the dashboard."""
    # TODO: Implement in B3
    return {"status": "unknown", "message": "Not implemented", "remotes": []}


def get_unbacked_paths() -> list[str]:
    """Get list of critical paths not covered by backups."""
    # TODO: Implement in B3
    return []
```

---

## Verification

```bash
python -c "
from scripts.discovery.backup_reader import get_backup_status, get_unbacked_paths, _parse_rclone_config
print(f'_parse_rclone_config(): {_parse_rclone_config()}')
print(f'get_backup_status(): {get_backup_status()}')
print(f'get_unbacked_paths(): {get_unbacked_paths()}')
print('OK - All stubs work')
"
```

---

## Result

- [x] PASS: FM Cleaned - model included thinking text.
- [ ] FAIL: Describe error

**After PASS, proceed to B2.**


## Related Documentation

- [[LOCAL_MODEL_LEARNINGS]] - local AI

