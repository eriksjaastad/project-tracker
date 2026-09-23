import json
from copy import deepcopy

import click
from click.testing import CliRunner
import pytest

from scripts import pr_settle as cli


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("PT_PR_SETTLE_DIR", str(tmp_path))
    return cli.Store("owner/repo", 7, "agent-1")


def snapshot():
    return dict(repo="owner/repo", number=7, status="complete", head_sha="a" * 40,
                pr_end={"state": "closed", "draft": False}, errors={}, reviews=[],
                inline_comments=[], issue_comments=[], pr_reactions=[], actor_verification=[])


def test_foreground_delivery_is_durable_and_can_be_acknowledged(storage, monkeypatch):
    def collect(*args, **kwargs):
        assert kwargs["request_comment_ids"] == [82]
        return snapshot()
    monkeypatch.setattr(cli, "collect", collect)
    monkeypatch.setenv("PT_CALLER_CWD", "/synthetic/owner-repo")
    seen = []
    monkeypatch.setattr(cli, "ConditionalGhaTransport", lambda cwd: seen.append(cwd) or type("Transport", (), {})())
    args = ["7", "--repo", "owner/repo", "--owner", "agent-1"]
    runner = CliRunner()
    result = runner.invoke(cli.pr_group, ["settle", *args, "--request-comment-id", "82"])
    assert result.exit_code == 0, result.output
    events = [json.loads(line) for line in result.output.splitlines()]
    assert events[-1]["type"] == "closed" and events[-1]["head"] == "a" * 40
    assert str(seen[0]) == "/synthetic/owner-repo"
    assert storage.load()["events"] == events
    assert storage.load()["request_comment_ids"] == [82]
    assert runner.invoke(cli.pr_group, ["acknowledge", *args, "--event", str(events[-1]["seq"])]).exit_code == 0
    assert runner.invoke(cli.pr_group, ["settle", *args]).output == ""


def test_ten_repositories_are_isolated_but_same_pr_has_one_lease(storage):
    stores = [cli.Store(f"owner/repo-{i}", 7, f"agent-{i}") for i in range(10)]
    for i, store in enumerate(stores):
        store.save(cli.engine.fresh(store.repo, 7, store.owner, 100, 180))
    assert len({store.path for store in stores}) == 10
    assert [store.load()["owner"] for store in stores] == [f"agent-{i}" for i in range(10)]
    with storage.lock(runner=True):
        with pytest.raises(click.ClickException, match="active monitor"):
            with cli.Store("OWNER/REPO", 7, "different-agent").lock(runner=True):
                pytest.fail("same PR acquired a second lease")
        # State/control commands remain usable while the foreground process owns its lease.
        with storage.lock():
            storage.save(cli.engine.fresh(storage.repo, 7, storage.owner, 100, 180))
    assert storage.load()["status"] == "active"
    with pytest.raises(click.ClickException, match="belongs to session"):
        cli.Store("owner/repo", 7, "different-agent").load()


@pytest.mark.parametrize("payload", ["not-json", "{}", '{"schema_version":99}'])
def test_corrupt_state_is_preserved(storage, payload):
    storage.path.write_text(payload)
    with pytest.raises(click.ClickException, match="Corrupt"):
        storage.load()
    assert storage.path.read_text() == payload


@pytest.mark.parametrize("corruption", ["deadline", "review_hold", "cursor", "sequence", "polls"])
def test_valid_json_with_corrupt_budget_or_delivery_is_rejected_without_rewrite(storage, corruption):
    state = cli.engine.fresh(storage.repo, 7, storage.owner, 100, 180)
    cli.engine.emit(state, "example", "wait", 100)
    if corruption in {"deadline", "review_hold"}:
        del state[corruption]
    elif corruption == "cursor":
        state["acked"] = 999
    elif corruption == "sequence":
        state["events"][0]["seq"] = 9
    else:
        state["polls"] = -1
    payload = json.dumps(state)
    storage.path.write_text(payload)
    result = CliRunner().invoke(cli.pr_group, ["settle", "7", "--repo", "owner/repo", "--owner", "agent-1"])
    assert result.exit_code != 0 and "Corrupt" in result.output
    assert storage.path.read_text() == payload


def test_stop_during_collection_wins_and_history_survives(storage, monkeypatch):
    def collect(*args, **kwargs):
        with storage.lock():
            state = storage.load()
            state["status"] = "stopped"
            state["finding_heads"] = ["b" * 40]
            storage.save(state)
        return snapshot()
    monkeypatch.setattr(cli, "collect", collect)
    result = CliRunner().invoke(cli.pr_group, ["settle", "7", "--repo", "owner/repo", "--owner", "agent-1"])
    assert result.exit_code == 0, result.output
    assert storage.load()["status"] == "stopped"
    assert storage.load()["finding_heads"] == ["b" * 40]
    assert storage.load()["events"] == []


def test_failed_collection_is_visible_and_does_not_poll_again(storage, monkeypatch):
    calls = []
    def collect(*args, **kwargs):
        calls.append(1)
        result = deepcopy(snapshot())
        result.update(status="unknown", pr_end=None, errors={"reviews": {"http_status": 403}})
        return result
    monkeypatch.setattr(cli, "collect", collect)
    result = CliRunner().invoke(cli.pr_group, ["settle", "7", "--repo", "owner/repo", "--owner", "agent-1"])
    assert result.exit_code != 0 and "GitHub evidence unavailable" in result.output
    assert calls == [1]
    assert storage.load()["snapshot"]["errors"]["reviews"]["http_status"] == 403


def test_head_change_during_collection_waits_for_consistent_snapshot(storage, monkeypatch):
    changing = snapshot()
    changing.update(status="inconsistent", pr_end={"state": "open", "draft": False},
                    errors={"pr_identity": {"kind": "changed"}})
    results = iter([changing, snapshot()])
    calls = []
    def collect(*args, **kwargs):
        calls.append(1)
        return next(results)
    clock = iter(range(0, 1000, 60))
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(cli, "collect", collect)
    result = CliRunner().invoke(cli.pr_group, ["settle", "7", "--repo", "owner/repo", "--owner", "agent-1"])
    assert result.exit_code == 0, result.output
    assert calls == [1, 1]
    assert storage.load()["events"][-1]["type"] == "closed"


def test_pause_and_resume_keep_third_execution_request_limit(storage, monkeypatch, tmp_path):
    monkeypatch.setattr(cli.time, "time", lambda: 100)
    state = cli.engine.fresh(storage.repo, 7, storage.owner, 0, 180)
    current = snapshot()
    current["pr_end"]["state"] = "open"
    cli.engine.consume(state, current, 10)
    storage.save(state)
    ledger = tmp_path / "ledger.json"
    url = "https://github.com/owner/repo/pull/7"
    ledger.write_text(json.dumps([dict(id=str(i), head="a" * 40,
        status="completed" if i < 3 else "acknowledged", at=i,
        acknowledged_at=i + 1, evidence=[url], summary="Distinct ready event") for i in (1, 2, 3)]))
    target = ["7", "--repo", "owner/repo", "--owner", "agent-1"]
    runner = CliRunner()
    result = runner.invoke(cli.pr_group, ["history", *target, "--ledger", str(ledger),
        "--snapshot", state["snapshot_id"], "--evidence", url, "--summary", "Complete distinct execution history"])
    assert result.exit_code == 0, result.output
    assert storage.load()["review_hold"] is True
    assert runner.invoke(cli.pr_group, ["settle", *target, "--hold"]).exit_code == 0
    monkeypatch.setattr(cli, "collect", lambda *a, **kw: snapshot())
    result = runner.invoke(cli.pr_group, ["settle", *target, "--resume"])
    assert result.exit_code == 0, result.output
    assert len(storage.load()["cycles"]) == 3
    assert storage.load()["review_hold"] is True
    assert not any(event["action"] == "recheck_and_merge" for event in storage.load()["events"])


def test_completed_clean_third_review_hands_back_merge_without_human_hold(storage, monkeypatch, tmp_path):
    monkeypatch.setattr(cli.time, "time", lambda: 100)
    state = cli.engine.fresh(storage.repo, 7, storage.owner, 0, 180)
    current = snapshot()
    current["pr_end"]["state"] = "open"
    cli.engine.consume(state, current, 10)
    storage.save(state)
    ledger = tmp_path / "completed.json"
    url = "https://github.com/owner/repo/pull/7"
    ledger.write_text(json.dumps([dict(id=str(i), head="a" * 40, status="completed", at=i,
        evidence=[url], summary="Distinct completed review") for i in (1, 2, 3)]))
    target = ["7", "--repo", "owner/repo", "--owner", "agent-1"]
    runner = CliRunner()
    result = runner.invoke(cli.pr_group, ["history", *target, "--ledger", str(ledger),
        "--snapshot", state["snapshot_id"], "--evidence", url, "--summary", "Three completed executions"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli.pr_group, ["assess", *target, "--head", "a" * 40,
        "--snapshot", state["snapshot_id"], "--review", "clean", "--ci", "satisfied",
        "--evidence", url, "--summary", "Third execution clean, unchanged head and all CI passed"])
    assert result.exit_code == 0, result.output
    saved = storage.load()
    assert saved["status"] == "settled"
    assert saved["events"][-1]["action"] == "recheck_and_merge"
    assert len(saved["cycles"]) == 3
    assert not any(event["action"] == "notify_erik_and_stop" for event in saved["events"])


@pytest.mark.parametrize("change", ["acknowledgment", "comment_acknowledgment", "head"])
def test_failed_request_keeps_fresh_observation_without_another_reservation(storage, monkeypatch, change):
    monkeypatch.setattr(cli.time, "time", lambda: 100)
    state = cli.engine.fresh(storage.repo, 7, storage.owner, 0, 180)
    current = snapshot()
    current["pr_end"]["state"] = "open"
    current["comment_reactions"] = {"82": []}
    state["request_comment_ids"] = [82]
    cli.engine.consume(state, current, 10)
    url = "https://github.com/owner/repo/pull/7"
    cli.engine.reconcile(state, [], [url], "No prior executions", 10, snapshot_id=state["snapshot_id"])
    cli.engine.request(state, "a" * 40, "initial", 11)
    storage.save(state)
    observed = deepcopy(current)
    if change != "head":
        reaction = dict(id=77, content="eyes", created_at="1970-01-01T00:01:30Z")
        source = "comment_reactions:82" if change == "comment_acknowledgment" else "pr_reactions"
        if change == "comment_acknowledgment":
            observed["comment_reactions"]["82"] = [reaction]
        else:
            observed["pr_reactions"] = [reaction]
        observed["actor_verification"] = [dict(source=source, id=77, connector_verified=True)]
    else:
        observed["head_sha"] = "b" * 40
    def collect(*args, **kwargs):
        assert kwargs["request_comment_ids"] == [82]
        return observed
    monkeypatch.setattr(cli, "collect", collect)
    result = CliRunner().invoke(cli.pr_group, ["request", "7", "--repo", "owner/repo", "--owner", "agent-1",
        "--head", "a" * 40, "--kind", "thorough"])
    assert result.exit_code != 0 and "assess_external_evidence" in result.output
    saved = storage.load()
    assert saved["snapshot"] == observed and saved["polls"] == 2
    assert saved["events"][-1]["type"] == "evidence"
    assert len(saved["requests"]) == len(saved["cycles"]) == 1
    if change != "head":
        assert saved["cycles"][0]["status"] == "acknowledged"
        rejected = deepcopy(saved["cycles"])
        rejected[0]["status"] = "rejected"
        with pytest.raises(ValueError, match="Acknowledged executions"):
            cli.engine.reconcile(saved, rejected, [url], "Wrongly rejected", 101,
                                 snapshot_id=saved["snapshot_id"])
    else:
        assert saved["head"] == "b" * 40


def test_comment_acknowledgment_poll_after_five_minutes_preserves_active_execution(storage, monkeypatch):
    monkeypatch.setattr(cli.time, "time", lambda: 303)
    state = cli.engine.fresh(storage.repo, 7, storage.owner, 0, 180)
    current = snapshot()
    current.update(pr_end={"state": "open", "draft": False}, comment_reactions={"82": []})
    cli.engine.consume(state, current, 1)
    cli.engine.reconcile(state, [], ["https://github.com/owner/repo/pull/7"], "No prior execution", 1,
                         snapshot_id=state["snapshot_id"])
    cli.engine.request(state, "a" * 40, "initial", 2)
    state.update(status="held", request_comment_ids=[82])
    storage.save(state)
    observed = deepcopy(current)
    observed["comment_reactions"]["82"] = [dict(id=77, content="eyes", created_at="1970-01-01T00:01:00Z")]
    observed["actor_verification"] = [dict(source="comment_reactions:82", id=77, connector_verified=True)]
    def collect(*args, **kwargs):
        assert kwargs["request_comment_ids"] == [82]
        return observed
    def pause(_seconds):
        state = storage.load()
        assert state["status"] == "active" and state["cycles"][0]["status"] == "acknowledged"
        state["status"] = "held"
        storage.save(state)
    monkeypatch.setattr(cli, "collect", collect)
    monkeypatch.setattr(cli.time, "sleep", pause)
    result = CliRunner().invoke(cli.pr_group, ["settle", "7", "--repo", "owner/repo", "--owner", "agent-1", "--resume"])
    assert result.exit_code == 0, result.output
    assert storage.load()["cycles"][0]["acknowledged_at"] == 60
    assert "notify_erik_and_stop" not in result.output


def test_resume_adds_comment_ids_without_resetting_history_or_deadline(storage, monkeypatch):
    monkeypatch.setattr(cli.time, "time", lambda: 100)
    state = cli.engine.fresh(storage.repo, 7, storage.owner, 0, 180)
    current = snapshot()
    current["pr_end"]["state"] = "open"
    cli.engine.consume(state, current, 1)
    assert state["snapshot_id"] is not None
    state.update(status="held", polls=7, request_comment_ids=[82])
    storage.save(state)
    def collect(*args, **kwargs):
        assert kwargs["request_comment_ids"] == [82, 99]
        assert storage.load()["snapshot_id"] is None  # Old evidence cannot clear newly added sources.
        return snapshot()
    monkeypatch.setattr(cli, "collect", collect)
    args = ["7", "--repo", "owner/repo", "--owner", "agent-1"]
    result = CliRunner().invoke(cli.pr_group, ["settle", *args, "--resume", "--request-comment-id", "99", "--request-comment-id", "82"])
    assert result.exit_code == 0, result.output
    saved = storage.load()
    assert saved["polls"] == 8 and saved["deadline"] == state["deadline"]
    assert CliRunner().invoke(cli.pr_group, ["settle", *args]).exit_code == 0
    assert storage.load()["request_comment_ids"] == [82, 99]
    assert storage.load()["polls"] == 8


@pytest.mark.parametrize("bad", [None, "82", [0], [-1], [True], ["82"]])
def test_invalid_persisted_comment_ids_fail_without_rewrite(storage, bad):
    state = cli.engine.fresh(storage.repo, 7, storage.owner, 0, 180)
    state["request_comment_ids"] = bad
    storage.save(state)
    before = storage.path.read_text()
    with pytest.raises(click.ClickException, match="Corrupt"):
        storage.load()
    assert storage.path.read_text() == before


@pytest.mark.parametrize("options", [["--request-comment-id", "0"], ["--request-comment-id", "-1"],
    ["--hold", "--request-comment-id", "82"], ["--stop", "--request-comment-id", "82"]])
def test_invalid_comment_options_never_start_or_ignore_configuration(storage, options):
    result = CliRunner().invoke(cli.pr_group, ["settle", "7", "--repo", "owner/repo", "--owner", "agent-1", *options])
    assert result.exit_code != 0 and not storage.path.exists()


def test_request_rejects_configuration_changed_during_collection(storage, monkeypatch):
    state = cli.engine.fresh(storage.repo, 7, storage.owner, 0, 180)
    state["request_comment_ids"] = [82]
    storage.save(state)
    def collect(*args, **kwargs):
        assert kwargs["request_comment_ids"] == [82]
        newer = storage.load()
        newer["request_comment_ids"] = [82, 99]
        storage.save(newer)
        return snapshot()
    monkeypatch.setattr(cli, "collect", collect)
    result = CliRunner().invoke(cli.pr_group, ["request", "7", "--repo", "owner/repo", "--owner", "agent-1",
        "--head", "a" * 40, "--kind", "initial"])
    assert result.exit_code != 0 and "configuration changed" in result.output
    saved = storage.load()
    assert saved["request_comment_ids"] == [82, 99] and saved["snapshot"] is None and saved["requests"] == []


@pytest.mark.parametrize("content,created", [("eyes", 50), ("+1", 50), ("eyes", 150)])
def test_late_comment_source_is_raw_evidence_until_owner_reconciles(storage, monkeypatch, tmp_path, content, created):
    monkeypatch.setattr(cli.time, "time", lambda: 200)
    state = cli.engine.fresh(storage.repo, 7, storage.owner, 0, 180)
    current = snapshot()
    current.update(pr_end={"state": "open", "draft": False}, comment_reactions={})
    url = "https://github.com/owner/repo/pull/7"
    cli.engine.consume(state, current, 90)
    cli.engine.reconcile(state, [], [url], "No prior executions", 90, snapshot_id=state["snapshot_id"])
    cli.engine.request(state, "a" * 40, "initial", 100)
    state["status"] = "held"
    storage.save(state)
    observed = deepcopy(current)
    observed["comment_reactions"]["82"] = [dict(id=77, content=content,
        created_at="1970-01-01T00:00:50Z" if created == 50 else "1970-01-01T00:02:30Z")]
    observed["actor_verification"] = [dict(source="comment_reactions:82", id=77, connector_verified=True)]
    def collect(*args, **kwargs):
        assert kwargs["request_comment_ids"] == [82]
        return observed
    def pause(_seconds):
        saved = storage.load()
        saved["status"] = "held"
        storage.save(saved)
    monkeypatch.setattr(cli, "collect", collect)
    monkeypatch.setattr(cli.time, "sleep", pause)
    args = ["7", "--repo", "owner/repo", "--owner", "agent-1"]
    runner = CliRunner()
    result = runner.invoke(cli.pr_group, ["settle", *args, "--resume", "--request-comment-id", "82"])
    assert result.exit_code == 0, result.output
    saved = storage.load()
    assert saved["snapshot"] == observed and saved["cycles"][0]["status"] == "requested"
    assert "acknowledged_at" not in saved["requests"][0] and not saved["requests"][0].get("completed")
    assert saved["requests"][0]["snapshot"]["comment_reactions"] == {}
    assert "completion_candidate" not in result.output
    if created == 150:
        ledger = deepcopy(saved["cycles"])
        ledger[0].update(status="acknowledged", acknowledged_at=150)
        path = tmp_path / "creation-proof-ledger.json"
        path.write_text(json.dumps(ledger))
        result = runner.invoke(cli.pr_group, ["history", *args, "--ledger", str(path),
            "--snapshot", saved["snapshot_id"], "--evidence", url + "#issuecomment-82",
            "--summary", "Owner observed comment creation after reservation, empty baseline, then eyes"])
        assert result.exit_code == 0, result.output
        assert storage.load()["cycles"][0]["acknowledged_at"] == 150
