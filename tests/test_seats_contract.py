from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "benchmarks" / "seats" / "calendar_agent_prompt.jsonl"
POLLER = ROOT / "scripts" / "hooks" / "calendar_poller.py"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_calendar_fixture_contract_and_provenance() -> None:
    fixtures = _rows(FIXTURES)
    assert len(fixtures) == 10
    assert len({row["fixture_id"] for row in fixtures}) == len(fixtures)

    remainders = set()
    for row in fixtures:
        fixture_id = row["fixture_id"]
        remainders.add(hashlib.sha256(fixture_id.encode()).digest()[0] % 5)

        source = ROOT / row["source_ref"]
        assert source.is_file()
        assert row["source_excerpt"] in source.read_text()

        event = row["input"]
        assert event["title"]
        assert event["event_type"] in {
            "reminder",
            "deadline",
            "milestone",
            "meeting",
            "recurring",
        }
        assert event["prompt"]

        expected = row["expected_output"]
        assert expected["required_facts"]
        assert expected["forbidden_claims"]
        assert expected["max_chars"] == 2000

    assert 0 in remainders
    assert remainders - {0}


def test_runtime_prompt_and_default_pin_are_tracked() -> None:
    source = POLLER.read_text()
    assert 'os.getenv("PT_AGENT_MODEL", "qwen2.5-coder:7b")' in source
    assert '["ollama", "run", model, full_prompt]' in source
    assert 'result.stdout.strip()[:2000]' in source
    assert "Please respond with what you would do or any relevant analysis." in source
