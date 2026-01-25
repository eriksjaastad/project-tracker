# Prompt B3b: Backup Status Function

**Task:** Implement get_backup_status() with full status logic
**Estimated Time:** 3-5 minutes
**Worker Model:** qwen3:4b or deepseek-r1:14b
**Depends On:** B3a (get_unbacked_paths must work)

---

## CONSTRAINTS (READ FIRST)

- USE StrReplace to replace the stub function
- KEEP changes under 30 lines

---

## Task Description

Replace the `get_backup_status()` stub with full implementation that:
1. Gets remotes from _parse_rclone_config()
2. Gets unbacked paths
3. Returns status (healthy/warning/critical) based on state

---

## [ACCEPTANCE CRITERIA]

- [x] Returns status: "critical" if no remotes
- [x] Returns status: "warning" if unbacked paths exist
- [x] Returns status: "healthy" if remotes configured
- [x] Includes status_color (green/yellow/red)
- [x] Includes remotes list and count

---

## Replace get_backup_status() with:

```python
def get_backup_status() -> dict[str, Any]:
    """Get backup status for the dashboard."""
    remotes = _parse_rclone_config()
    unbacked = get_unbacked_paths()

    if not remotes:
        status, color = "critical", "red"
        message = "No rclone remotes configured!"
    elif unbacked:
        status, color = "warning", "yellow"
        message = f"{len(unbacked)} paths may not be backed up"
    else:
        status, color = "healthy", "green"
        message = f"{len(remotes)} backup remote(s) configured"

    return {
        "status": status,
        "status_color": color,
        "message": message,
        "remotes": list(remotes.keys()),
        "remote_count": len(remotes),
        "critical_unbacked": unbacked,
    }
```

---

## Verification

```bash
python -c "
from scripts.discovery.backup_reader import get_backup_status
status = get_backup_status()
print(f'Status: {status[\"status\"]} ({status[\"status_color\"]})')
print(f'Message: {status[\"message\"]}')
print(f'Remotes: {status[\"remotes\"]}')
assert 'status' in status
assert 'remotes' in status
print('OK')
"
```

---

## Result

- [x] PASS: FM Direct.
- [ ] FAIL: Describe error

**After PASS, proceed to B4.**


## Related Documentation

- [Local Model Learnings](Documents/reference/LOCAL_MODEL_LEARNINGS.md) - local AI

