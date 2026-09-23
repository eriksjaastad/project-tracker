"""Owner judgments stay pinned, limits survive restarts, and pending polls stay quiet."""
from copy import deepcopy
import json

import pytest

from scripts.pr_settle_state import assess, consume, fresh, observed_ci, reconcile, request

PROOF = ["https://github.com/owner/repo/pull/7"]


def cycle(id="initial-observed", head="a" * 40, status="completed", at=0):
    return dict(id=id, head=head, status=status, at=at, evidence=PROOF,
                summary="Owner grouped execution request and completion evidence")


def history(state, cycles=None, now=0):
    return reconcile(state, state["cycles"] if cycles is None else cycles, PROOF,
                     "Owner reconciled the complete execution history", now,
                     snapshot_id=state["snapshot_id"])


def snapshot(head="a" * 40, finding=False):
    return dict(repo="owner/repo", number=7, head_sha=head, status="complete",
        started_at="first", finished_at="last", sources={"reviews": {"observed_at": "now"}},
        pr_end={"state": "open", "draft": False, "body": "PR body"}, reviews=[],
        inline_comments=[dict(id=1, original_commit_id=head, body="[P2] A finding")] if finding else [],
        actor_verification=[dict(source="inline_comments", id=1, connector_verified=True)],
        pr_reactions=[], comment_reactions={})


def active():
    state = fresh("owner/repo", 7, "session-owner", 0, 240)
    consume(state, snapshot(), 0)
    history(state)
    return state


def judge(state, review="clean", ci="satisfied", now=1):
    if review == "clean" and not state["review_hold"]:
        history(state, state["cycles"] or [cycle(head=state["head"])], now=now)
    return assess(state, state["head"], state["snapshot_id"], review, ci,
                  ["https://github.com/owner/repo/pull/7#pullrequestreview-8"],
                  "Owner checked external review against current policy", now=now)


def test_pending_quiet_then_owner_handoff_on_next_observation():
    state = active()
    later = snapshot()
    later.update(started_at="new", finished_at="new")
    later["sources"]["reviews"]["observed_at"] = "new"
    assert consume(state, later, 60) == []
    later["reviews"] = [dict(id=8, body="Completion candidate", commit_id=state["head"])]
    assert consume(state, later, 120)[0]["action"] == "assess_external_evidence"
    assert state["review"] == "pending"  # Text cannot approve itself.
    events = judge(state, now=121)
    assert events[-1]["action"] == "recheck_and_merge"
    assert state["status"] == "settled" and events[-1]["owner"] == "session-owner"
    assert [event["seq"] for event in state["events"]] == list(range(1, len(state["events"]) + 1))


@pytest.mark.parametrize("ci", ["unknown", "pending", "failed"])
def test_ci_does_not_pass_from_empty_or_unknown(ci):
    state = active()
    assert not any(event["action"] == "recheck_and_merge" for event in judge(state, ci=ci))
    assert state["status"] == "active"


def test_head_change_and_same_head_new_finding_invalidate_assessment():
    state = active()
    old_id, old_head = state["snapshot_id"], state["head"]
    judge(state, ci="pending")
    consume(state, snapshot(finding=True), 60)
    assert state["assessment"] is None and state["review"] == "findings"
    with pytest.raises(ValueError, match="current head and snapshot"):
        assess(state, old_head, old_id, "clean", "satisfied", [], "old", now=61)
    consume(state, snapshot("b" * 40), 120)
    assert state["head"] != old_head and state["review"] == "pending"


@pytest.mark.parametrize("review", ["findings", "ambiguous"])
def test_finding_heads_are_not_execution_counts_and_third_adjudicated_problem_stops(review):
    state = active()
    for index, char in enumerate("abc"):
        state = json.loads(json.dumps(state))
        consume(state, snapshot(char * 40, finding=True), index * 60)
        assert consume(state, snapshot(char * 40, finding=True), index * 60 + 1) == []
    assert state["status"] == "active" and len(state["finding_heads"]) == 3
    events = history(state, [cycle(str(i), char * 40, at=i) for i, char in enumerate("abc")], 180)
    assert state["review_hold"] and state["status"] == "active"
    events = judge(state, review=review, now=180)
    assert sum(event["action"] == "notify_erik_and_stop" for event in events) == 1
    assert judge(state, now=180) == []
    assert consume(state, snapshot("d" * 40), 240) == []


def test_third_request_blocks_fourth_but_completed_clean_can_pass():
    state = active()
    for when in (1, 3):
        request(state, state["head"], "initial", when)
        completed = deepcopy(state["cycles"])
        completed[-1]["status"] = "completed"
        history(state, completed, now=when + 1)
        state = json.loads(json.dumps(state))
    events = request(state, state["head"], "thorough", 5)
    assert events[0]["action"] == "owner_trigger_final_review_and_hold"
    assert state["review_hold"] and state["status"] == "active"
    with pytest.raises(ValueError, match="hold"):
        request(state, state["head"], "thorough", 6)
    with pytest.raises(ValueError, match="completed third"):
        judge(state, now=6)
    with pytest.raises(ValueError, match="dropped"):
        history(state, [], 6)
    completed = deepcopy(state["cycles"])
    completed[-1]["status"] = "completed"
    history(state, completed, 7)
    assert state["status"] == "active" and state["review_hold"]
    assert judge(state, now=8)[-1]["action"] == "recheck_and_merge"
    assert state["status"] == "settled"
    assert state["requests"][0]["snapshot"] == snapshot()
    assert len(state["cycles"]) == 3


@pytest.mark.parametrize("ci", ["pending", "unknown", "failed"])
def test_clean_third_waits_for_ci_and_failed_ci_requires_discussion(ci):
    state = active()
    history(state, [cycle("one"), cycle("two", at=1), cycle("three", at=2)], 2)
    events = judge(state, ci=ci, now=3)
    assert not any(event["action"] == "recheck_and_merge" for event in events)
    assert state["status"] == ("escalated" if ci == "failed" else "active")
    if ci == "failed":
        assert events[-1]["action"] == "notify_erik_and_stop"
    else:
        with pytest.raises(ValueError, match="hold"):
            request(state, state["head"], "thorough", 4)
        old_id = state["snapshot_id"]
        changed = snapshot()
        changed["pr_end"]["body"] = "CI evidence has changed"
        consume(state, changed, 5)
        with pytest.raises(ValueError, match="current head and snapshot"):
            assess(state, state["head"], old_id, "clean", "satisfied", PROOF, "old", now=6)
        history(state, now=7)
        assert judge(state, now=8)[-1]["action"] == "recheck_and_merge"


def test_earlier_current_head_review_cannot_clear_a_third_cycle_on_another_head():
    state = active()
    history(state, [cycle("one"), cycle("two", head="b" * 40, at=1),
                    cycle("three", head="b" * 40, at=2)], 2)
    with pytest.raises(ValueError, match="completed third execution at the current head"):
        judge(state, now=3)


def test_clean_third_cannot_hand_off_a_draft_and_closed_pr_is_terminal():
    state = active()
    history(state, [cycle("one"), cycle("two", at=1), cycle("three", at=2)], 2)
    data = snapshot()
    data["pr_end"]["draft"] = True
    consume(state, data, 3)
    history(state, now=4)
    with pytest.raises(ValueError, match="open, ready PR"):
        judge(state, now=5)
    data["pr_end"]["state"] = "closed"
    assert consume(state, data, 6)[-1]["type"] == "closed"
    assert state["status"] == "settled"


def test_fingerprint_ignores_transport_order_but_keeps_source_edits():
    state = active()
    data = snapshot()
    data["reviews"] = [{"id": 2, "body": "two"}, {"id": 1, "body": "one"}]
    consume(state, data, 1)
    reordered = deepcopy(data)
    reordered["reviews"].reverse()
    assert consume(state, reordered, 2) == []
    reordered["reviews"][0]["body"] = "edited old comment"
    assert consume(state, reordered, 3)[0]["type"] == "evidence"


@pytest.mark.parametrize("limit", ["time", "polls"])
def test_limits_are_sticky_and_deadline_also_applies_to_assessment(limit):
    state = active()
    if limit == "polls":
        state["polls"] = 240
    else:
        state["deadline"] = 1
    assert judge(state, now=2)[0]["action"] == "notify_erik_and_stop"
    assert state["status"] == "escalated" and judge(state, now=3) == []


@pytest.mark.parametrize("change,status", [({"draft": True}, "held"), ({"state": "closed"}, "settled")])
def test_draft_and_closed_are_terminal_for_this_run(change, status):
    state, data = active(), snapshot()
    data["pr_end"].update(change)
    consume(state, data, 1)
    assert state["status"] == status and consume(state, snapshot(), 2) == []


def test_unknown_collection_and_missing_external_evidence_cannot_clear():
    state = active()
    with pytest.raises(ValueError, match="External GitHub"):
        assess(state, state["head"], state["snapshot_id"], "clean", "satisfied", [], "local PASS", now=1)
    data = snapshot()
    data["status"] = "unknown"
    consume(state, data, 2)
    with pytest.raises(ValueError, match="complete"):
        judge(state, now=3)


def test_authenticated_acknowledgment_prevents_silent_retry():
    state = active()
    request(state, state["head"], "initial", 1)
    data = snapshot()
    data["pr_reactions"] = [dict(id=9, content="eyes")]
    data["actor_verification"].append(dict(source="pr_reactions", id=9, connector_verified=True))
    consume(state, data, 60)
    with pytest.raises(ValueError, match="active execution"):
        request(state, state["head"], "silent_retry", 301)


def test_five_minutes_silence_escalates_without_any_retry_permission():
    state = active()
    request(state, state["head"], "initial", 0)
    with pytest.raises(ValueError, match="active execution"):
        request(state, state["head"], "silent_retry", 299)
    events = consume(state, snapshot(), 300)
    assert len(events) == 1 and events[0]["action"] == "notify_erik_and_stop"
    assert "unknown" in events[0]["summary"]["reason"]
    assert consume(state, snapshot(), 301) == []


@pytest.mark.parametrize("completion", [False, True])
def test_acknowledgment_timeout_survives_restart_but_completion_candidate_ends_wait(completion):
    state = active()
    request(state, state["head"], "initial", 0)
    data = snapshot()
    data["pr_reactions"] = [dict(id=9, content="eyes")]
    data["actor_verification"].append(dict(source="pr_reactions", id=9, connector_verified=True))
    consume(state, data, 60)
    if completion:
        data["pr_reactions"].append(dict(id=10, content="+1"))
        data["actor_verification"].append(dict(source="pr_reactions", id=10, connector_verified=True))
        consume(state, data, 120)
    state = json.loads(json.dumps(state))
    events = consume(state, data, 960)
    assert state["review"] == "pending"
    assert state["status"] == ("active" if completion else "escalated")
    assert not events if completion else events[0]["action"] == "notify_erik_and_stop"


@pytest.mark.parametrize("prefix,source", [("", "check_runs"), ("merge_", "check_runs"),
                                          ("", "statuses"), ("merge_", "statuses")])
def test_observed_ci_uses_latest_run_in_each_sha_bucket(prefix, source):
    data = snapshot()
    data.update(merge_sha="b" * 40, check_runs=[], merge_check_runs=[], statuses=[], merge_statuses=[])
    sha = data["merge_sha" if prefix else "head_sha"]
    failure = dict(id=1, head_sha=sha, name="pytest", app={"id": 2}, status="completed",
                   conclusion="failure", context="pytest", state="failure")
    data[prefix + source] = [failure]
    state = active()
    assert consume(state, data, 1)[0]["ci"] == "failed"
    assert consume(state, data, 2) == []
    data[prefix + source].append({**failure, "id": 2, "conclusion": "success", "state": "success"})
    assert observed_ci(data) == "unknown"  # Latest success cannot establish required-workflow clearance.
    data[prefix + source].append({**failure, "id": 3, "status": "queued", "state": "pending"})
    assert observed_ci(data) == "pending"
    data["status"] = "unknown"
    assert observed_ci(data) == "unknown"


def test_absent_ci_or_mismatched_check_head_is_unknown():
    data = snapshot()
    data.update(check_runs=[], statuses=[])
    assert observed_ci(data) == "unknown"
    data["check_runs"] = [dict(id=1, name="pytest", head_sha="wrong", status="completed", conclusion="failure")]
    assert observed_ci(data) == "unknown"


def test_history_is_explicit_and_must_match_the_latest_snapshot():
    state = fresh("owner/repo", 7, "owner", 0, 30)
    consume(state, snapshot(), 0)
    with pytest.raises(ValueError, match="Reconciled history"):
        request(state, state["head"], "initial", 1)
    with pytest.raises(ValueError, match="Reconcile execution history"):
        assess(state, state["head"], state["snapshot_id"], "clean", "satisfied", PROOF, "proof", now=1)
    history(state, [cycle()], 1)
    changed = snapshot()
    changed["reviews"] = [dict(id=9, body="Additional evidence")]
    consume(state, changed, 2)
    with pytest.raises(ValueError, match="Reconcile execution history"):
        assess(state, state["head"], state["snapshot_id"], "clean", "satisfied", PROOF, "proof", now=3)


def test_rejected_requests_do_not_count_but_unknown_execution_stops():
    state = active()
    history(state, [cycle("rejected", status="rejected"), cycle("initial")], 1)
    events = request(state, state["head"], "thorough", 2)
    assert not state["review_hold"] and events[0]["counters"]["cycles"] == 2
    uncertain = deepcopy(state["cycles"])
    uncertain[-1]["status"] = "unknown"
    assert history(state, uncertain, 3)[-1]["action"] == "notify_erik_and_stop"
    assert state["status"] == "escalated"


def test_three_cycles_same_head_hold_without_counting_each_comment():
    state = active()
    data = snapshot(finding=True)
    data["inline_comments"] *= 5
    consume(state, data, 1)
    history(state, [cycle("one")], 1)
    assert len(state["cycles"]) == 1 and not state["review_hold"]
    third = cycle("three", status="acknowledged", at=3)
    third["acknowledged_at"] = 4
    history(state, [cycle("one"), cycle("two", at=2), third], 4)
    assert state["review_hold"] and state["status"] == "active"
    data["pr_end"]["body"] = "new observation during hold"
    assert consume(state, data, 60)[0]["type"] == "evidence"
    assert state["review_hold"] and state["status"] == "active"
    assert consume(state, data, 904)[0]["action"] == "notify_erik_and_stop"


def test_rejected_third_reservation_preserves_hold_without_losing_ledger():
    state = active()
    history(state, [cycle("one"), cycle("two", at=1)], 1)
    request(state, state["head"], "thorough", 2)
    rejected = deepcopy(state["cycles"])
    rejected[-1]["status"] = "rejected"
    events = history(state, rejected, 3)
    assert state["review_hold"] and state["status"] == "escalated"
    assert events[-1]["action"] == "notify_erik_and_stop"


def test_third_reserved_candidate_notifies_without_approving_or_blocking_owner():
    state = active()
    history(state, [cycle("one"), cycle("two", at=1)], 1)
    request(state, state["head"], "thorough", 2)
    data = snapshot()
    data["pr_reactions"] = [dict(id=9, content="+1")]
    data["actor_verification"].append(dict(source="pr_reactions", id=9, connector_verified=True))
    events = consume(state, data, 60)
    reports = [event for event in events if event["type"] == "completion_candidate"]
    assert len(reports) == 1 and reports[0]["action"] == "assess_external_evidence"
    assert state["status"] == "active" and state["review_hold"]
    assert state["review"] == "pending" and state["cycles"][-1]["status"] == "acknowledged"
    assert not any(event["action"] == "recheck_and_merge" for event in state["events"])
    assert consume(state, data, 120) == []
    with pytest.raises(ValueError, match="hold"):
        request(state, state["head"], "thorough", 121)
    completed = deepcopy(state["cycles"])
    completed[-1]["status"] = "completed"
    history(state, completed, 122)
    assert judge(state, now=123)[-1]["action"] == "recheck_and_merge"
    assert len(state["requests"]) == 1


@pytest.mark.parametrize("bad", [None, {**cycle(), "head": None}, {**cycle(), "status": []}])
def test_malformed_execution_records_leave_history_unchanged(bad):
    state = active()
    before = deepcopy(state)
    with pytest.raises(ValueError):
        history(state, [bad], 1)
    assert state == before


def test_stale_history_cannot_stamp_a_new_snapshot_or_authorize_a_request():
    state = active()
    inspected = state["snapshot_id"]
    prepared = [cycle()]
    changed = snapshot()
    changed["reviews"] = [dict(id=99, commit_id=state["head"], state="COMMENTED")]
    consume(state, changed, 1)
    before = deepcopy(state)
    with pytest.raises(ValueError, match="inspected current snapshot"):
        reconcile(state, prepared, PROOF, "Prepared before the new observation", 2,
                  snapshot_id=inspected)
    assert state == before
    with pytest.raises(ValueError, match="Reconciled history"):
        request(state, state["head"], "thorough", 3)
    history(state, prepared, 4)
    assert request(state, state["head"], "thorough", 5)[0]["action"] == "owner_trigger_reserved_request"


@pytest.mark.parametrize("intermediate_unknown", [False, True])
def test_acknowledged_execution_cannot_be_removed_from_count(intermediate_unknown):
    state = active()
    acknowledged = cycle("first", status="acknowledged")
    acknowledged["acknowledged_at"] = 1
    history(state, [acknowledged], 1)
    if intermediate_unknown:
        acknowledged["status"] = "unknown"
        history(state, [acknowledged], 2)
    rejected = {**acknowledged, "status": "rejected"}
    before = deepcopy(state)
    with pytest.raises(ValueError, match="Acknowledged executions"):
        history(state, [rejected], 3)
    assert state == before
    # Removing the timestamp cannot erase the already recorded acknowledgment either.
    rejected.pop("acknowledged_at")
    with pytest.raises(ValueError, match="Acknowledged executions"):
        history(state, [rejected], 3)
    assert state == before


@pytest.mark.parametrize("legacy_attempt_only", [False, True])
def test_observed_acknowledgment_is_counted_and_cannot_be_rejected(legacy_attempt_only):
    state = active()
    request(state, state["head"], "initial", 1)
    data = snapshot()
    data["pr_reactions"] = [dict(id=9, content="eyes")]
    data["actor_verification"].append(dict(source="pr_reactions", id=9, connector_verified=True))
    consume(state, data, 60)
    assert state["cycles"][0]["status"] == "acknowledged"
    assert state["cycles"][0]["acknowledged_at"] == state["requests"][0]["acknowledged_at"] == 60
    if legacy_attempt_only:  # Previously persisted states kept this fact only on the attempt.
        state["cycles"][0].pop("acknowledged_at")
        state["cycles"][0]["status"] = "requested"
    rejected = deepcopy(state["cycles"])
    rejected[0].update(status="rejected")
    rejected[0].pop("acknowledged_at", None)
    with pytest.raises(ValueError, match="Acknowledged executions"):
        history(state, rejected, 61)


def test_new_rejected_record_cannot_contain_acknowledgment_evidence():
    state = active()
    before = deepcopy(state)
    with pytest.raises(ValueError, match="Acknowledged executions"):
        history(state, [{**cycle(status="rejected"), "acknowledged_at": 0}], 1)
    assert state == before


def test_requested_then_confirmed_rejected_does_not_count_as_execution():
    state = active()
    request(state, state["head"], "initial", 1)
    rejected = deepcopy(state["cycles"])
    rejected[0]["status"] = "rejected"
    events = history(state, rejected, 2)
    assert state["status"] == "active" and not state["review_hold"]
    assert events[-1]["counters"]["cycles"] == 0
    events = request(state, state["head"], "initial", 3)
    assert events[0]["counters"]["cycles"] == 1
    assert len(state["cycles"]) == 2 and state["cycles"][0]["status"] == "rejected"


@pytest.mark.parametrize("source,fields,ack", [
    ("issue_comments", {"body": "Connect your GitHub account to use Codex."}, False),
    ("issue_comments", {"body": "Unrelated update"}, False),
    ("pr_reactions", {"content": "heart"}, False),
    ("pr_reactions", {"content": "eyes"}, True),
    ("comment_reactions:82", {"content": "+1"}, True),
    ("reviews", {"commit_id": "a" * 40, "state": "COMMENTED"}, True),
    ("reviews", {"commit_id": "a" * 40, "state": "PENDING"}, True),
    ("reviews", {"commit_id": "b" * 40, "state": "COMMENTED"}, False),
])
@pytest.mark.parametrize("preexisting", [False, True])
def test_only_new_acknowledgment_shapes_make_rejection_impossible(source, fields, ack, preexisting):
    state, data = active(), snapshot()
    rows = data["comment_reactions"].setdefault("82", []) if source.startswith("comment_reactions:") else data.setdefault(source, [])
    row = {"id": 90, **fields}
    data["actor_verification"].append(dict(source=source, id=90, connector_verified=True))
    if preexisting:
        rows.append({**row, "body": "Pre-request object"})
    consume(state, data, 1)
    history(state, now=1)
    request(state, state["head"], "initial", 2)
    rows[:] = [{**row, "body": fields.get("body", "Updated object")}]
    consume(state, data, 60)
    acknowledged = ack and not preexisting
    assert ("acknowledged_at" in state["cycles"][0]) is acknowledged
    rejected = deepcopy(state["cycles"])
    rejected[0].update(status="rejected")
    if acknowledged:
        with pytest.raises(ValueError, match="Acknowledged executions"):
            history(state, rejected, 61)
    else:
        assert history(state, rejected, 61)[-1]["counters"]["cycles"] == 0
        assert state["status"] == "active"
