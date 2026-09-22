"""Every evidence page is revalidated; unchanged first pages cannot hide edits."""
import json
import subprocess
import time

import pytest

from scripts.pr_conditional import ConditionalGhaTransport
from scripts.pr_evidence import EvidenceError

FIRST = "repos/owner/repo/issues/7/comments?per_page=100"
SECOND = FIRST + "&page=2"
LINK = f'<https://api.github.com/{SECOND}>; rel="next"'


def response(status=200, body=None, headers=(), newline="\r\n", protocol="HTTP/2.0"):
    text = json.dumps(body) if status != 304 else ""
    lines = [f"{protocol} {status}", *(f"{key}: {value}" for key, value in headers), "", text]
    return newline.join(lines)


class Runner:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        expected, raw = self.responses.pop(0)
        assert command[command.index("Accept: application/vnd.github+json") + 1] == expected
        assert command[:7] == ["gha", "api", "--hostname", "github.com", "--method", "GET", "--include"]
        assert kwargs["check"] is True and 0 < kwargs["timeout"] <= 30
        status = int(raw.splitlines()[0].split()[1])
        if status >= 300:
            raise subprocess.CalledProcessError(1, command, output=raw, stderr="synthetic-secret")
        return subprocess.CompletedProcess(command, 0, raw, "")


def test_later_page_changes_even_when_first_is_304_without_links(tmp_path):
    runner = Runner(
        (FIRST, response(body=[{"id": 1}], headers=[("ETag", '"a"'), ("Link", LINK)])),
        (SECOND, response(body=[{"id": 2, "body": "old"}], headers=[("ETag", '"b"')])),
        (FIRST, response(304)),
        (SECOND, response(body=[{"id": 2, "body": "edited finding"}], headers=[("ETag", '"c"')])),
    )
    transport = ConditionalGhaTransport(tmp_path, run=runner)
    assert transport.get(FIRST, paginate=True) == [[{"id": 1}], [{"id": 2, "body": "old"}]]
    assert transport.get(FIRST, paginate=True) == [[{"id": 1}], [{"id": 2, "body": "edited finding"}]]
    assert 'If-None-Match: "a"' in runner.calls[2][0]
    assert 'If-None-Match: "b"' in runner.calls[3][0]
    assert not runner.responses


@pytest.mark.parametrize("envelope", [None, "check_runs", "workflows"])
def test_full_terminal_page_probe_finds_new_evidence_after_304_without_link(tmp_path, envelope):
    def wrap(rows, total):
        return {envelope: rows, "total_count": total} if envelope else rows
    full = wrap([{"id": n} for n in range(100)], 100)
    empty = wrap([], 100)
    appended = wrap([{"id": 100, "body": "new finding"}], 101)
    runner = Runner(
        (FIRST, response(body=full, headers=[("etag", '"full"')])),
        (SECOND, response(body=empty, headers=[("etag", '"empty"')])),
        (FIRST, response(304)),
        (SECOND, response(body=appended, headers=[("etag", '"new"')])),
    )
    transport = ConditionalGhaTransport(tmp_path, run=runner)
    assert transport.get(FIRST, paginate=True) == [full, empty]
    assert transport.get(FIRST, paginate=True) == [full, appended]
    assert 'If-None-Match: "empty"' in runner.calls[-1][0]
    assert not runner.responses


def test_full_later_terminal_page_probes_next_number_and_preserves_filters(tmp_path):
    second = "repos/owner/repo/commits/abc/check-runs?filter=all&per_page=2&page=2"
    third = "repos/owner/repo/commits/abc/check-runs?filter=all&per_page=2&page=3"
    full = {"total_count": 4, "check_runs": [{"id": 3}, {"id": 4}]}
    empty = {"total_count": 4, "check_runs": []}
    runner = Runner((second, response(body=full)), (third, response(body=empty)))
    assert ConditionalGhaTransport(tmp_path, run=runner).get(second, paginate=True) == [full, empty]
    assert not runner.responses


def test_old_comment_edit_and_reaction_id_replacement_are_not_count_shortcuts(tmp_path):
    endpoint = "repos/owner/repo/issues/7/reactions"
    runner = Runner(
        (endpoint, response(body=[{"id": 3, "content": "+1"}], headers=[("etag", 'W/"old"')])),
        (endpoint, response(body=[{"id": 4, "content": "+1"}], headers=[("etag", 'W/"new"')])),
    )
    transport = ConditionalGhaTransport(tmp_path, run=runner)
    assert transport.get(endpoint, paginate=True)[0][0]["id"] == 3
    assert transport.get(endpoint, paginate=True)[0][0]["id"] == 4
    assert 'If-None-Match: W/"old"' in runner.calls[1][0]


def test_200_removes_old_page_chain_and_missing_validator_forces_get(tmp_path):
    runner = Runner(
        (FIRST, response(body=[], headers=[("etag", '"a"'), ("link", LINK)])),
        (SECOND, response(body=[], headers=[("etag", '"b"')])),
        (FIRST, response(body=[{"id": 9}])),
        (FIRST, response(body=[{"id": 10}])),
    )
    transport = ConditionalGhaTransport(tmp_path, run=runner)
    assert transport.get(FIRST, paginate=True) == [[], []]
    assert transport.get(FIRST, paginate=True) == [[{"id": 9}]]
    assert transport.get(FIRST, paginate=True) == [[{"id": 10}]]
    assert not any("If-None-Match" in arg for arg in runner.calls[-1][0])
    assert not runner.responses


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_errors_never_return_cached_success_or_retry(tmp_path, status):
    runner = Runner((FIRST, response(body=[{"id": 1}], headers=[("etag", '"old"')])),
                    (FIRST, response(status, {"message": "synthetic-secret"})))
    transport = ConditionalGhaTransport(tmp_path, run=runner)
    transport.get(FIRST)
    with pytest.raises(EvidenceError) as error:
        transport.get(FIRST)
    assert error.value.http_status == status
    assert "synthetic-secret" not in str(error.value)
    assert len(runner.calls) == 2


def test_304_requires_cache_and_return_values_cannot_mutate_cache(tmp_path):
    runner = Runner((FIRST, response(304)))
    with pytest.raises(EvidenceError, match="lacks cached evidence"):
        ConditionalGhaTransport(tmp_path, run=runner).get(FIRST)
    runner = Runner((FIRST, response(body=[{"id": 1}], headers=[("etag", '"old"')])),
                    (FIRST, response(304)))
    transport = ConditionalGhaTransport(tmp_path, run=runner)
    transport.get(FIRST)[0]["id"] = "caller mutation"
    assert transport.get(FIRST) == [{"id": 1}]


def test_malformed_304_body_is_not_accepted_as_a_cache_hit(tmp_path):
    runner = Runner((FIRST, response(body=[{"id": 1}], headers=[("etag", '"v1"')])),
                    (FIRST, response(304) + "unexpected body"))
    transport = ConditionalGhaTransport(tmp_path, run=runner)
    transport.get(FIRST)
    with pytest.raises(EvidenceError, match="contains a body"):
        transport.get(FIRST)


@pytest.mark.parametrize("target", [
    "https://evil.invalid/repos/owner/repo/issues/7/comments?page=2",
    "http://api.github.com/repos/owner/repo/issues/7/comments?page=2",
    "https://github.com/owner/repo/issues/7/comments?page=2",
    "https://[invalid/repos/owner/repo/issues/7/comments?page=2",
    "https://api.github.com/login", "https://api.github.com/repos/../login",
    "https://api.github.com/repos/other/repo/issues/7/comments?page=2",
])
def test_untrusted_next_link_is_never_requested(tmp_path, target):
    runner = Runner((FIRST, response(body=[], headers=[("link", f'<{target}>; rel="next"')])))
    with pytest.raises(EvidenceError, match="Pagination|pagination|REST API"):
        ConditionalGhaTransport(tmp_path, run=runner).get(FIRST, paginate=True)
    assert len(runner.calls) == 1


@pytest.mark.parametrize("protocol,newline", [("HTTP/1.1", "\r\n"), ("HTTP/2", "\n")])
def test_http_formats_and_multiple_link_relations(tmp_path, protocol, newline):
    header = f'<https://api.github.com/{SECOND}>; rel="last", {LINK}'
    runner = Runner((FIRST, response(body=[], headers=[("Link", header)], protocol=protocol, newline=newline)),
                    (SECOND, response(body=[{"id": 2}], protocol=protocol, newline=newline)))
    assert ConditionalGhaTransport(tmp_path, run=runner).get(FIRST, paginate=True) == [[], [{"id": 2}]]


def test_repeated_page_is_an_error(tmp_path):
    runner = Runner((FIRST, response(body=[], headers=[("Link", f'<https://api.github.com/{FIRST}>; rel="next"')])))
    with pytest.raises(EvidenceError, match="repeated a page"):
        ConditionalGhaTransport(tmp_path, run=runner).get(FIRST, paginate=True)
    assert len(runner.calls) == 1


def test_unprotected_branch_preserves_collector_absence_protocol(tmp_path):
    endpoint = "repos/owner/repo/branches/main/protection"
    runner = Runner((endpoint, response(404, {"message": "Branch not protected"})))
    with pytest.raises(EvidenceError) as error:
        ConditionalGhaTransport(tmp_path, run=runner).get(endpoint)
    assert error.value.kind == "not_protected" and error.value.http_status == 404


def test_deadline_can_be_reset_and_timeout_never_serves_stale(tmp_path):
    runner = Runner((FIRST, response(body=[], headers=[("etag", '"v1"')])))
    transport = ConditionalGhaTransport(tmp_path, run=runner, deadline=time.monotonic() - 1)
    with pytest.raises(EvidenceError, match="deadline"):
        transport.get(FIRST)
    assert runner.calls == []
    transport.deadline = time.monotonic() + 5
    assert transport.get(FIRST) == []
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("gha", 5)
    transport.run = timeout
    with pytest.raises(EvidenceError, match="timed out"):
        transport.get(FIRST)
