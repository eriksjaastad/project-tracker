# Worker Task 1b: Add JSONL Parsing Function

**Worker Model:** Qwen 2.5 Coder
**Objective:** Add the `_read_telemetry_entries()` function to read and parse the JSONL file.

---

## 🎯 [ACCEPTANCE CRITERIA]

- [x] **Function Added:** `_read_telemetry_entries(days: int) -> list[dict]`
- [x] **Reads JSONL:** Opens file, reads line by line, parses JSON
- [x] **Time Filtering:** Only returns entries from last N days
- [x] **Error Handling:** Logs warning if file not found, returns empty list
- [x] **Handles Malformed:** Skips lines that fail JSON parsing

---

## CONSTRAINTS (READ FIRST)

- DO NOT modify `get_telemetry_stats()` yet
- DO NOT add aggregation logic yet
- HANDLE file not found gracefully (log warning, return [])

---

## Reference Code Snippet

```python
def _read_telemetry_entries(days: int = 7) -> list[dict]:
    """
    Read telemetry entries from JSONL file.

    Args:
        days: Only include entries from last N days

    Returns:
        List of telemetry entry dicts
    """
    if not TELEMETRY_PATH.exists():
        logger.warning(f"Telemetry file not found: {TELEMETRY_PATH}")
        return []

    cutoff = datetime.utcnow() - timedelta(days=days)
    entries = []

    try:
        with open(TELEMETRY_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Parse timestamp and filter by date
                    ts_str = entry.get('timestamp', '')
                    if ts_str:
                        # Handle ISO format: 2026-01-05T09:23:14.918438Z
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        if ts.replace(tzinfo=None) >= cutoff:
                            entries.append(entry)
                except json.JSONDecodeError:
                    logger.debug(f"Skipping malformed line: {line[:50]}...")
                    continue
    except Exception as e:
        logger.error(f"Error reading telemetry: {e}")
        return []

    return entries
```

---

## Verification

```bash
cd /Users/eriksjaastad/projects/project-tracker
python -c "
from scripts.discovery.telemetry_reader import _read_telemetry_entries
entries = _read_telemetry_entries(days=30)
print(f'Found {len(entries)} entries')
if entries:
    print(f'First entry model: {entries[0].get(\"model\", \"unknown\")}')
"
# Expected: Found X entries, First entry model: llama3.2:3b
```
