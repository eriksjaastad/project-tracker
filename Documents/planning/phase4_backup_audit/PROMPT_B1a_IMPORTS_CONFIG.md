# Prompt B1a: Backup Reader - Imports & Config

**Task:** Create backup_reader.py with imports and config only
**Estimated Time:** 3-5 minutes
**Worker Model:** qwen3:4b or deepseek-r1:14b

> **Note:** Split from B1 to keep Context Bridge under 30 lines (learning from Agent Dispatcher A1 timeout).

---

## CONSTRAINTS (READ FIRST)

- OUTPUT ONLY: imports + logger + config path constant
- DO NOT add functions yet (that's B1b)
- KEEP IT SHORT - under 20 lines total

---

## Task Description

Create `scripts/discovery/backup_reader.py` with ONLY:
1. Module docstring (1 line)
2. Imports (logging, os, pathlib, typing)
3. Logger setup
4. RCLONE_CONFIG_PATH constant with env var fallback

---

## [ACCEPTANCE CRITERIA]

- [ ] File created at `scripts/discovery/backup_reader.py`
- [ ] Has `from pathlib import Path`
- [ ] Has `logger = logging.getLogger(__name__)`
- [ ] Has `RCLONE_CONFIG_PATH` using `Path.home()` + env var fallback
- [ ] File is under 20 lines
- [ ] Runs without error

---

## Exact Code to Output

```python
"""Backup Reader for rclone integration."""
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# rclone config location (configurable via environment variable)
_default_config = Path.home() / ".config" / "rclone" / "rclone.conf"
RCLONE_CONFIG_PATH = Path(os.getenv("RCLONE_CONFIG_PATH", str(_default_config)))
```

---

## Verification

```bash
python -c "
from scripts.discovery.backup_reader import RCLONE_CONFIG_PATH, logger
print(f'Config path: {RCLONE_CONFIG_PATH}')
print(f'Logger: {logger.name}')
print('OK')
"
```

---

## Result

- [x] PASS: FM Direct - model output corruption issue.
- [ ] FAIL: Describe error

**After PASS, proceed to B1b.**
