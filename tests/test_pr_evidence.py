"""Evidence stays attributable and incomplete collection never looks like no findings."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import time
from urllib.parse import quote

import pytest

from scripts.pr_evidence import CONNECTOR, EvidenceError, GhaTransport, collect

REPO = "owner/tracker"
HEAD, BASE, MERGE = "a" * 40, "b" * 40, "c" * 40
PR = f"repos/{REPO}/pulls/7"
BOT = {"login": CONNECTOR, "type": "Bot", "id": 99, "node_id": "BOT_99"}


class FakeAPI:
    def __init__(self):
        self.pr = {"id": 77, "number": 7, "state": "open", "draft": False,
                   "html_url": "https://github.com/owner/tracker/pull/7",
                   "head": {"sha": HEAD, "ref": "feature", "repo": {"full_name": REPO}},
                   "base": {"sha": BASE, "ref": "release/main", "repo": {"full_name": REPO}},
                   "merge_commit_sha": MERGE}
        self.end = None
        self.calls = []
        self.responses = {
            f"{PR}/reviews?per_page=100": [[{"id": 3, "commit_id": HEAD, "user": BOT,
                                            "body": "raw reviewer text", "state": "COMMENTED"}]],
            f"{PR}/comments?per_page=100": [[]],
            f"repos/{REPO}/issues/7/comments?per_page=100": [[{"id": 82, "body": "request",
                                                                       "user": BOT}]],
            f"repos/{REPO}/issues/7/reactions?per_page=100": [[{"id": 6, "content": "+1",
                "created_at": "2026-09-22T12:00:00Z", "user": {**BOT, "type": "User"}}]],
            f"repos/{REPO}/issues/7/timeline?per_page=100": [[{"id": 5, "event": "head_ref_force_pushed"}]],
            f"repos/{REPO}/actions/workflows?per_page=100": [{"total_count": 1, "workflows": [
                {"id": 10, "path": ".github/workflows/ci.yml", "state": "active"}]}],
            f"repos/{REPO}/branches/release%2Fmain/protection": {"required_status_checks": {"contexts": ["pytest"]}},
            f"repos/{REPO}/rules/branches/release%2Fmain?per_page=100": [[{"type": "required_status_checks"}]],
            f"users/{quote(CONNECTOR, safe='')}": BOT,
            f"repos/{REPO}/issues/comments/82/reactions?per_page=100": [[{"id": 8, "user": BOT, "content": "eyes"}]],
        }
        for sha in (HEAD, MERGE):
            self.responses[f"repos/{REPO}/commits/{sha}/check-runs?filter=all&per_page=100"] = [
                {"total_count": 1, "check_runs": [{"id": 23, "head_sha": sha,
                    "name": "pytest", "status": "completed", "conclusion": "success"}]}]
            self.responses[f"repos/{REPO}/commits/{sha}/statuses?per_page=100"] = [[]]

    def get(self, endpoint, *, paginate=False):
        self.calls.append((endpoint, paginate))
        if endpoint == PR:
            result = self.end if self.end and sum(call[0] == PR for call in self.calls) > 1 else self.pr
        else:
            result = self.responses[endpoint]
        if isinstance(result, Exception):
            raise result
        return deepcopy(result)


def capture(api, **kwargs):
    return collect(REPO, 7, Path("/synthetic/checkout"), transport=api, **kwargs)


def test_complete_snapshot_retains_raw_evidence_and_separates_merge_checks():
    api = FakeAPI()
    result = capture(api)
    assert result["status"] == "complete" and result["errors"] == {}
    assert result["head_sha"] == HEAD and result["merge_sha"] == MERGE
    assert result["pr_start"] == result["pr_end"] == api.pr
    assert result["reviews"][0]["body"] == "raw reviewer text"
    assert result["check_runs"][0]["head_sha"] == HEAD
    assert result["merge_check_runs"][0]["head_sha"] == MERGE
    assert result["timeline"] == [{"id": 5, "event": "head_ref_force_pushed"}]
    assert result["branch_protection"]["required_status_checks"]["contexts"] == ["pytest"]
    assert result["gate_assessment"] == "not_performed"
    assert result["started_at"] <= result["finished_at"]
    assert json.loads(json.dumps(result))["repo"] == REPO
    assert not any("/issues/comments/" in endpoint for endpoint, _ in api.calls)


def test_every_page_and_older_head_review_remain_visible():
    api = FakeAPI()
    newer_stale = {"id": 4, "commit_id": "d" * 40, "submitted_at": "2099-01-01T00:00:00Z",
                   "user": BOT, "state": "APPROVED"}
    api.responses[f"{PR}/reviews?per_page=100"].append([newer_stale])
    checks = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    api.responses[checks] = [{"total_count": 2, "check_runs": [{"id": 1}]},
                             {"total_count": 2, "check_runs": [{"id": 2}]}]
    result = capture(api)
    assert [r["id"] for r in result["reviews"]] == [3, 4]
    assert result["reviews"][1] == newer_stale
    assert result["head_sha"] == HEAD
    assert result["check_runs"] == [{"id": 1}, {"id": 2}]
    assert all(paginate for endpoint, paginate in api.calls if "per_page=" in endpoint)


@pytest.mark.parametrize("response", [[], [{}], [[None]], [{"message": "forbidden"}]])
def test_malformed_pages_are_unknown_instead_of_no_findings(response):
    api = FakeAPI()
    api.responses[f"{PR}/reviews?per_page=100"] = response
    result = capture(api)
    assert result["status"] == "unknown"
    assert result["reviews"] is None
    assert result["errors"]["reviews"]["kind"] == "shape"
    assert result["check_runs"][0]["conclusion"] == "success"


@pytest.mark.parametrize("pages", [
    [{"total_count": 2, "workflows": [{"id": 1}]}],
    [{"total_count": 1, "workflows": []}, {"total_count": 0, "workflows": []}],
    [{"workflows": []}],
])
def test_envelope_truncation_or_changing_totals_are_unknown(pages):
    api = FakeAPI()
    api.responses[f"repos/{REPO}/actions/workflows?per_page=100"] = pages
    result = capture(api)
    assert result["status"] == "unknown" and result["workflows"] is None
    assert "workflows" in result["errors"]


def test_permission_failure_does_not_discard_reviews_or_claim_absent_requirements():
    api = FakeAPI()
    endpoint = f"repos/{REPO}/branches/release%2Fmain/protection"
    api.responses[endpoint] = EvidenceError("http", "Request denied", http_status=403)
    result = capture(api)
    assert result["status"] == "unknown"
    assert result["branch_protection"] is None and result["reviews"][0]["id"] == 3
    assert result["errors"]["branch_protection"] == {
        "kind": "http", "message": "Request denied", "http_status": 403, "endpoint": endpoint}


@pytest.mark.parametrize("change", ["head", "base", "base_ref", "merge", "draft", "closed"])
def test_pr_changes_make_the_collection_inconsistent(change):
    api = FakeAPI()
    api.end = deepcopy(api.pr)
    if change in {"head", "base"}:
        api.end[change]["sha"] = "e" * 40
    elif change == "base_ref":
        api.end["base"]["ref"] = "other"
    elif change == "merge":
        api.end["merge_commit_sha"] = "f" * 40
    elif change == "draft":
        api.end["draft"] = True
    else:
        api.end["state"] = "closed"
    result = capture(api)
    assert result["status"] == "inconsistent"
    assert result["errors"]["pr_identity"]["kind"] == "changed"
    assert result["pr_start"] != result["pr_end"]


def test_missing_initial_head_preserves_independent_evidence():
    api = FakeAPI()
    del api.pr["head"]["sha"]
    result = capture(api)
    assert result["status"] == "unknown" and result["head_sha"] is None
    assert result["reviews"][0]["id"] == 3
    assert result["check_runs"] is None and "check_runs" in result["errors"]
    assert not any("/commits/" in endpoint for endpoint, _ in api.calls)


@pytest.mark.parametrize("mismatch", [None, "id", "node_id", "login"])
def test_reaction_identity_is_resolved_not_trusted_from_display_login(mismatch):
    api = FakeAPI()
    reaction = api.responses[f"repos/{REPO}/issues/7/reactions?per_page=100"][0][0]
    if mismatch:
        reaction["user"][mismatch] = 123 if mismatch == "id" else "imposter"
    result = capture(api, request_comment_ids=(82, 82))
    verdict = next(row for row in result["actor_verification"] if row["source"] == "pr_reactions")
    assert verdict["connector_verified"] is (mismatch is None)
    assert result["comment_reactions"]["82"][0]["id"] == 8
    assert sum("/issues/comments/82/reactions" in endpoint for endpoint, _ in api.calls) == 1
    assert result["pr_reactions"][0] == reaction


def test_unavailable_bot_lookup_cannot_authenticate_reactions():
    api = FakeAPI()
    api.responses[f"users/{quote(CONNECTOR, safe='')}"] = EvidenceError("http", "Denied", http_status=403)
    result = capture(api)
    assert result["status"] == "unknown"
    assert not any(row["connector_verified"] for row in result["actor_verification"])


@pytest.mark.parametrize("actor", ["malformed", [BOT]])
def test_malformed_actor_is_unknown_without_discarding_other_evidence(actor):
    api = FakeAPI()
    api.responses[f"{PR}/reviews?per_page=100"][0][0]["user"] = actor
    result = capture(api)
    assert result["status"] == "unknown"
    assert result["errors"]["actor:reviews:3"]["kind"] == "shape"
    assert result["reviews"][0]["user"] == actor
    assert next(row for row in result["actor_verification"]
                if row["source"] == "reviews")["connector_verified"] is False
    assert result["check_runs"][0]["conclusion"] == "success"


@pytest.mark.parametrize("message,expected", [("Branch not protected", "complete"),
                                              ("Not Found", "unknown")])
def test_unprotected_branch_is_explicit_absence_but_generic_404_is_unknown(message, expected):
    api = FakeAPI()
    endpoint = f"repos/{REPO}/branches/release%2Fmain/protection"
    def run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "gha", output=json.dumps({"message": message}),
                                            stderr=f"gh: {message} (HTTP 404)")
    try:
        GhaTransport(Path("."), run=run).get(endpoint)
    except EvidenceError as error:
        api.responses[endpoint] = error
    result = capture(api)
    assert result["status"] == expected
    if message == "Branch not protected":
        assert result["branch_protection"] == {
            "present": False, "reason": message, "http_status": 404}
        assert "branch_protection" not in result["errors"]
    else:
        assert result["branch_protection"] is None
        assert result["errors"]["branch_protection"]["http_status"] == 404


def test_transport_uses_get_pagination_cwd_timeout_and_checked_exit(tmp_path):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "[[{\"id\":1}],[]]", "")
    result = GhaTransport(tmp_path, run=run).get("repos/owner/repo/issues", paginate=True)
    assert result == [[{"id": 1}], []]
    command, kwargs = calls[0]
    assert command[:4] == ["gha", "api", "--method", "GET"]
    assert command[-2:] == ["--paginate", "--slurp"]
    assert kwargs == {"cwd": tmp_path, "capture_output": True, "text": True,
                      "check": True, "timeout": 30}


@pytest.mark.parametrize("failure,kind,status", [
    (subprocess.TimeoutExpired("gha", 30), "timeout", None),
    (FileNotFoundError("gha"), "unavailable", None),
    (subprocess.CalledProcessError(1, "gha", stderr="HTTP 403 synthetic-secret"), "http", 403),
    (subprocess.CalledProcessError(2, "gha", stderr="synthetic-secret"), "command", None),
])
def test_transport_failure_is_explicit_and_does_not_echo_credentials(failure, kind, status):
    def run(*args, **kwargs):
        raise failure
    with pytest.raises(EvidenceError) as error:
        GhaTransport(Path("."), run=run).get("repos/owner/repo")
    assert error.value.kind == kind and error.value.http_status == status
    assert "synthetic-secret" not in str(error.value)


def test_invalid_json_is_an_error_and_expired_deadline_does_not_call_gha():
    def invalid(*args, **kwargs):
        return subprocess.CompletedProcess([], 0, "not json", "")
    with pytest.raises(EvidenceError, match="invalid JSON"):
        GhaTransport(Path("."), run=invalid).get("repos/owner/repo")
    def forbidden(*args, **kwargs):
        pytest.fail("expired deadline must not execute gha")
    with pytest.raises(EvidenceError, match="deadline"):
        GhaTransport(Path("."), run=forbidden, deadline=time.monotonic() - 1).get("repos/owner/repo")
