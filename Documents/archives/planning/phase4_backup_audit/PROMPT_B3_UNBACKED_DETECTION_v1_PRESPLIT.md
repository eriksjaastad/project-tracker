# Prompt B3: Un-Backed Detection Logic

**Task:** Implement logic to detect critical paths not covered by backups
**Estimated Time:** 5-10 minutes
**Worker Model:** qwen3:4b (preferred) or deepseek-r1:14b
**Depends On:** B2 (config parser must work)

---

## CONSTRAINTS (READ FIRST)

- DO NOT add backup automation - detection only
- DO NOT modify existing functions - implement stubs
- DO NOT add complex scanning - keep it simple for MVP
- DO NOT hardcode project paths - make it configurable
- OUTPUT using StrReplace to update the stub functions

---

## Task Description

Implement in `scripts/discovery/backup_reader.py`:

1. **`get_unbacked_paths()`** - Return list of critical paths that should be backed up
2. **`get_backup_status()`** - Return full status dict for dashboard

---

## [ACCEPTANCE CRITERIA] (MANDATORY CHECKLIST)

- [ ] **Critical Paths Defined:** Has list of critical directories to check
- [ ] **Checks Existence:** Only reports paths that actually exist
- [ ] **Status Summary:** Returns healthy/warning/critical status
- [ ] **Remote Count:** Includes number of configured remotes
- [ ] **Actionable Message:** Status message explains what's missing

---

## Implementation Pattern

```python
# Add this constant near the top (after imports)
CRITICAL_PATHS = [
    Path.home() / "projects",           # All project code
    Path.home() / ".config",            # App configurations
    Path.home() / "Documents",          # Personal documents
    Path.home() / ".ssh",               # SSH keys (critical!)
]


def get_unbacked_paths() -> list[str]:
    """
    Get list of critical paths not covered by backups.

    For MVP, we check if rclone is configured at all.
    Future: Check actual backup job coverage.

    Returns:
        List of path strings that need backup attention
    """
    remotes = _parse_rclone_config()

    # If no remotes configured, everything is at risk
    if not remotes:
        return [str(p) for p in CRITICAL_PATHS if p.exists()]

    # For MVP: If remotes exist, assume coverage is manual
    # TODO: Parse rclone job logs to verify actual coverage
    return []


def get_backup_status() -> dict[str, Any]:
    """
    Get backup status for the dashboard.

    Returns:
        Dict with remote info, backup coverage, and warnings
    """
    remotes = _parse_rclone_config()
    unbacked = get_unbacked_paths()

    # Determine status
    if not remotes:
        status = "critical"
        message = "No rclone remotes configured! Data not backed up."
    elif unbacked:
        status = "warning"
        message = f"{len(unbacked)} critical paths may not be backed up"
    else:
        status = "healthy"
        message = f"{len(remotes)} backup remote(s) configured"

    # Color for dashboard
    status_colors = {
        "healthy": "green",
        "warning": "yellow",
        "critical": "red"
    }

    return {
        "status": status,
        "status_color": status_colors.get(status, "gray"),
        "message": message,
        "remotes": list(remotes.keys()),
        "remote_count": len(remotes),
        "critical_unbacked": unbacked,
        "has_automation": False,  # TODO: Check for cron jobs
    }
```

---

## Verification Command

After implementing, run:

```bash
cd $PROJECTS_ROOT/project-tracker
python -c "
from scripts.discovery.backup_reader import get_backup_status, get_unbacked_paths

status = get_backup_status()
print('Backup Status:')
print(f'  Status: {status[\"status\"]} ({status[\"status_color\"]})')
print(f'  Message: {status[\"message\"]}')
print(f'  Remotes: {status[\"remotes\"]}')
print(f'  Unbacked paths: {len(status[\"critical_unbacked\"])}')

# Verify structure
assert 'status' in status, 'ERROR: Missing status field'
assert 'remotes' in status, 'ERROR: Missing remotes field'
assert isinstance(status['remotes'], list), 'ERROR: remotes should be list'
print('OK - Detection logic working')
"
```

**Expected:** Shows status with configured remotes

---

## Result

- [ ] PASS: Detection logic returns valid data
- [ ] FAIL: Describe error

**Hand back to Floor Manager when complete.**


## Related Documentation

- [Local Model Learnings](Documents/reference/LOCAL_MODEL_LEARNINGS.md) - local AI

