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
    monkeypatch.setattr(cli, "collect", lambda *a, **kw: snapshot())
    monkeypatch.setenv("PT_CALLER_CWD", "/synthetic/owner-repo")
    seen = []
    monkeypatch.setattr(cli, "ConditionalGhaTransport", lambda cwd: seen.append(cwd) or type("Transport", (), {})())
    args = ["7", "--repo", "owner/repo", "--owner", "agent-1"]
    runner = CliRunner()
    result = runner.invoke(cli.pr_group, ["settle", *args])
    assert result.exit_code == 0, result.output
    events = [json.loads(line) for line in result.output.splitlines()]
    assert events[-1]["type"] == "closed" and events[-1]["head"] == "a" * 40
    assert str(seen[0]) == "/synthetic/owner-repo"
    assert storage.load()["events"] == events
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


@pytest.mark.parametrize("change", ["acknowledgment", "head"])
def test_failed_request_keeps_fresh_observation_without_another_reservation(storage, monkeypatch, change):
    monkeypatch.setattr(cli.time, "time", lambda: 100)
    state = cli.engine.fresh(storage.repo, 7, storage.owner, 0, 180)
    current = snapshot()
    current["pr_end"]["state"] = "open"
    cli.engine.consume(state, current, 10)
    url = "https://github.com/owner/repo/pull/7"
    cli.engine.reconcile(state, [], [url], "No prior executions", 10, snapshot_id=state["snapshot_id"])
    cli.engine.request(state, "a" * 40, "initial", 11)
    storage.save(state)
    observed = deepcopy(current)
    if change == "acknowledgment":
        observed["pr_reactions"] = [dict(id=77, content="eyes", created_at="1970-01-01T00:01:30Z")]
        observed["actor_verification"] = [dict(source="pr_reactions", id=77, connector_verified=True)]
    else:
        observed["head_sha"] = "b" * 40
    monkeypatch.setattr(cli, "collect", lambda *a, **kw: observed)
    result = CliRunner().invoke(cli.pr_group, ["request", "7", "--repo", "owner/repo", "--owner", "agent-1",
        "--head", "a" * 40, "--kind", "thorough"])
    assert result.exit_code != 0 and "assess_external_evidence" in result.output
    saved = storage.load()
    assert saved["snapshot"] == observed and saved["polls"] == 2
    assert saved["events"][-1]["type"] == "evidence"
    assert len(saved["requests"]) == len(saved["cycles"]) == 1
    if change == "acknowledgment":
        assert saved["cycles"][0]["status"] == "acknowledged"
        rejected = deepcopy(saved["cycles"])
        rejected[0]["status"] = "rejected"
        with pytest.raises(ValueError, match="Acknowledged executions"):
            cli.engine.reconcile(saved, rejected, [url], "Wrongly rejected", 101,
                                 snapshot_id=saved["snapshot_id"])
    else:
        assert saved["head"] == "b" * 40
