# Worker Task 1a: Create Telemetry Reader Skeleton

**Worker Model:** Qwen 2.5 Coder
**Objective:** Create the basic structure of `scripts/discovery/telemetry_reader.py` with imports and path configuration.

---

## 🎯 [ACCEPTANCE CRITERIA]

- [x] **File Created:** `scripts/discovery/telemetry_reader.py` exists
- [x] **Imports:** Includes json, pathlib, logging, datetime
- [x] **Path Config:** `TELEMETRY_PATH` constant pointing to AI Router telemetry
- [x] **Logging:** Configured using existing logger pattern
- [x] **Stub Function:** `get_telemetry_stats()` returns empty dict

---

## CONSTRAINTS (READ FIRST)

- DO NOT implement any parsing logic yet
- DO NOT read the actual file yet
- FOLLOW the pattern from `scripts/discovery/todo_parser.py`
- USE pathlib.Path, not os.path

---

## Reference Code Snippet

```python
"""
Telemetry Reader for AI Router integration.
Reads telemetry.jsonl and provides stats for the dashboard.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# AI Router telemetry location
TELEMETRY_PATH = Path("$PROJECTS_ROOT/_tools/ai_router/logs/telemetry.jsonl")


def get_telemetry_stats(days: int = 7) -> dict[str, Any]:
    """
    Get aggregated telemetry stats for the dashboard.

    Args:
        days: Number of days to look back (default 7)

    Returns:
        Dict with model usage, durations, costs, etc.
    """
    # TODO: Implement in next task
    return {}


if __name__ == "__main__":
    # Quick test
    stats = get_telemetry_stats()
    print(f"Stats: {stats}")
```

---

## Verification

```bash
cd $PROJECTS_ROOT/project-tracker
python -c "from scripts.discovery.telemetry_reader import get_telemetry_stats; print(get_telemetry_stats())"
# Expected: {}
```


## Related Documentation

- [Local Model Learnings](Documents/reference/LOCAL_MODEL_LEARNINGS.md) - local AI

