"""Tests for scripts/agent_chat_status.py.

The point of this script is to answer "what is deployed?" when everything else
has failed -- expired gcloud auth, a service that is down, a proxy returning
HTML. So the cases that matter most here are the ugly ones: it must never
traceback, because a status command that crashes is useless exactly when it is
needed.
"""

import importlib.util
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "agent_chat_status.py"


def _load():
    spec = importlib.util.spec_from_file_location("agent_chat_status", _SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot load {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


describe = _load().describe


def test_reports_version_status_and_timestamp():
    out = describe('{"status": "ok", "ts": "2026-09-07T05:00:00", "version": "abc1234"}')
    assert "abc1234" in out
    assert "ok" in out
    assert "2026-09-07T05:00:00" in out


def test_tolerates_surrounding_whitespace():
    assert "v1" in describe('   {"status": "ok", "ts": "t", "version": "v1"}   \n')


def test_missing_version_reads_unknown_not_absent():
    # A deploy that forgot to set AGENT_CHAT_VERSION must be visibly "unknown",
    # not a blank that reads like a successful answer.
    assert "unknown" in describe('{"status": "ok", "ts": "t"}')


def test_empty_response_is_reported_not_raised():
    assert "UNREACHABLE" in describe("")
    assert "UNREACHABLE" in describe("   \n  ")


def test_html_error_page_is_reported_not_raised():
    out = describe("<html><body>502 Bad Gateway</body></html>")
    assert "non-JSON" in out
    assert "502" in out


def test_truncated_body_is_reported_not_raised():
    # --max-time can cut a response mid-object, producing a '{'-prefixed string
    # that is not valid JSON. A prefix check alone would let this reach the
    # parser and traceback.
    out = describe('{"status": "ok", "vers')
    assert "non-JSON" in out


@pytest.mark.parametrize("body", ["[]", "null", '"a string"', "42"])
def test_valid_json_that_is_not_an_object_is_reported_not_raised(body):
    assert "unexpected JSON" in describe(body)


def test_empty_object_is_not_mislabelled_as_unreachable():
    # {} is falsy but parsed fine. Reporting it as unreachable would send
    # someone hunting a network problem that does not exist.
    out = describe("{}")
    assert "UNREACHABLE" not in out
    assert "unknown" in out


def test_output_is_truncated_so_a_huge_body_cannot_flood_the_terminal():
    assert len(describe("x" * 100_000)) < 400


def test_truncated_multibyte_bytes_do_not_crash_the_script():
    """The stdin decode, not just describe(), must survive truncation.

    describe() takes an already-decoded str, so the ASCII truncation test above
    never exercises the byte path. A response cut mid-transfer by --max-time can
    end inside a multi-byte UTF-8 character, and a strict decode would raise
    before describe() is ever called -- tracebacking in precisely the case this
    script exists to report on.
    """
    import subprocess

    truncated = b'{"status": "ok", "ver\xe2\x82'  # euro sign, cut one byte short
    result = subprocess.run(
        [str(_SCRIPT)], input=truncated, capture_output=True, timeout=60
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert b"Traceback" not in result.stderr
    assert b"non-JSON" in result.stdout
