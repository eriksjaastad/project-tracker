# Prompt B3a: Critical Paths & Unbacked Detection

**Task:** Add CRITICAL_PATHS constant and implement get_unbacked_paths()
**Estimated Time:** 3-5 minutes
**Worker Model:** qwen3:4b or deepseek-r1:14b
**Depends On:** B2 (config parser must work)

> **Note:** Split from B3 to implement one function at a time (learning from Agent Dispatcher).

---

## CONSTRAINTS (READ FIRST)

- DO NOT implement get_backup_status() yet (that's B3b)
- USE StrReplace to update the stub function
- KEEP changes under 25 lines

---

## Task Description

1. Add CRITICAL_PATHS constant after RCLONE_CONFIG_PATH
2. Replace the `get_unbacked_paths()` stub with real implementation

---

## [ACCEPTANCE CRITERIA]

- [x] CRITICAL_PATHS list exists with 4 paths
- [x] get_unbacked_paths() calls _parse_rclone_config()
- [x] Returns paths only if they exist on disk
- [x] Returns empty list if remotes are configured
- [x] Runs without error

---

## Code Changes

**Add after RCLONE_CONFIG_PATH line:**
```python

# Critical paths that should be backed up
CRITICAL_PATHS = [
    Path.home() / "projects",
    Path.home() / ".config",
    Path.home() / "Documents",
    Path.home() / ".ssh",
]
```

**Replace get_unbacked_paths() stub with:**
```python
def get_unbacked_paths() -> list[str]:
    """Get list of critical paths not covered by backups."""
    remotes = _parse_rclone_config()
    if not remotes:
        return [str(p) for p in CRITICAL_PATHS if p.exists()]
    return []
```

---

## Verification

```bash
python -c "
from scripts.discovery.backup_reader import get_unbacked_paths, CRITICAL_PATHS
print(f'CRITICAL_PATHS: {len(CRITICAL_PATHS)} paths defined')
unbacked = get_unbacked_paths()
print(f'Unbacked paths: {len(unbacked)}')
print('OK')
"
```

---

## Result

- [x] PASS: FM Direct - model output included escaping characters and redundant code.
- [ ] FAIL: Describe error

**After PASS, proceed to B3b.**


## Related Documentation

- [[LOCAL_MODEL_LEARNINGS]] - local AI

