# Prompt B2: rclone Config Parser

**Task:** Implement `_parse_rclone_config()` to read rclone remotes
**Estimated Time:** 5-10 minutes
**Worker Model:** qwen3:4b (preferred) or deepseek-r1:14b
**Depends On:** B1 (backup_reader.py skeleton must exist)

---

## CONSTRAINTS (READ FIRST)

- DO NOT modify function signatures - implement the existing stub
- DO NOT add new functions - only implement `_parse_rclone_config()`
- DO NOT hardcode paths - the constant is already defined
- DO NOT silent fail - log warnings if config doesn't exist
- OUTPUT only the `_parse_rclone_config()` function body (use StrReplace)

---

## Task Description

Implement `_parse_rclone_config()` in `scripts/discovery/backup_reader.py`:
1. Check if RCLONE_CONFIG_PATH exists
2. Parse the INI-style config file
3. Return dict mapping remote name to config entries

---

## [ACCEPTANCE CRITERIA] (MANDATORY CHECKLIST)

- [x] **Reads Config:** Successfully reads `~/.config/rclone/rclone.conf`
- [x] **Parses Remotes:** Returns dict with remote names as keys
- [x] **Handles Missing:** Returns empty dict and logs warning if file missing
- [x] **No Crash:** Handles malformed config gracefully
- [x] **Returns Real Data:** Returns actual remotes (gbackup, r2_pose_factory, etc.)

---

## Context Bridge: Config File Format

The rclone.conf file looks like:

```ini
[gbackup]
type = drive
scope = drive
token = {...}
root_folder_id = 1SQchTET8-MTjWVv1BT-JoxKtN5VeJSCm

[r2_pose_factory]
type = s3
access_key_id = ...
endpoint = https://...
```

---

## Implementation Pattern

Use Python's configparser:

```python
def _parse_rclone_config() -> dict[str, dict]:
    """
    Parse rclone.conf and return remote configurations.

    Returns:
        Dict mapping remote name to config dict
    """
    if not RCLONE_CONFIG_PATH.exists():
        logger.warning(f"rclone config not found: {RCLONE_CONFIG_PATH}")
        return {}

    import configparser
    config = configparser.ConfigParser()

    try:
        config.read(RCLONE_CONFIG_PATH)
        remotes = {}
        for section in config.sections():
            remotes[section] = dict(config[section])
        return remotes
    except Exception as e:
        logger.error(f"Error parsing rclone config: {e}")
        return {}
```

---

## Verification Command

After implementing, run:

```bash
cd $PROJECTS_ROOT/project-tracker
python -c "
from scripts.discovery.backup_reader import _parse_rclone_config
remotes = _parse_rclone_config()
print(f'Found {len(remotes)} remotes:')
for name, config in remotes.items():
    remote_type = config.get('type', 'unknown')
    print(f'  - {name}: type={remote_type}')

assert len(remotes) > 0, 'ERROR: No remotes found'
print('OK - Config parser working')
"
```

**Expected:** Lists remotes like `gbackup: type=drive`

---

## Result

- [x] PASS: FM Cleaned - model included thinking text.
- [ ] FAIL: Describe error

**Hand back to Floor Manager when complete.**
