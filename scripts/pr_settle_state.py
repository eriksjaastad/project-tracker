"""Pure, persistent settle state. Owner assessments record external evidence, not approval."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import re
import time
from urllib.parse import urlparse

REVIEWS = {"clean", "findings", "pending", "ambiguous"}
CI = {"satisfied", "not_configured", "pending", "failed", "unknown"}


def fresh(repo, number, owner, now, max_minutes):
    if (not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or type(number) is not int
            or number <= 0 or not isinstance(owner, str) or not owner.strip()
            or not math.isfinite(now) or not math.isfinite(max_minutes) or max_minutes <= 0):
        raise ValueError("Valid repository, PR, owner, time and positive runtime required")
    return dict(schema_version=1, repo=repo, number=number, owner=owner, started_at=now,
                updated_at=now, deadline=now + max_minutes * 60, head=None,
                snapshot_id=None, snapshot=None, status="active", finding_heads=[],
                requests=[], cycles=[], history_snapshot_id=None, review_hold=False, hold_cycle_id=None,
                events=[], polls=0, review="pending", ci="unknown", assessment=None)


def _event(state, kind, action):
    event = {key: state[key] for key in
             ("repo", "number", "owner", "head", "snapshot_id", "review", "ci")}
    event.update(seq=len(state["events"]) + 1, type=kind, at=state["updated_at"],
                 url=f"https://github.com/{state['repo']}/pull/{state['number']}",
                 counters={"polls": state["polls"], "finding_heads": len(state["finding_heads"]),
                           "cycles": sum(c["status"] != "rejected" for c in state["cycles"]),
                           "requests": len(state["requests"])}, action=action)
    state["events"].append(event)
    return event


def emit(state, type, action, now, **details):
    """Append a control/delivery event using the same durable sequence contract."""
    state["updated_at"] = now
    event = _event(state, type, action)
    event.update(details)
    return event


def _bounded(state, now):
    state["updated_at"] = now
    if state["status"] != "active":
        return False
    if now >= state["deadline"] or state["polls"] >= 240:
        _escalate(state, "Runtime or poll limit reached")
        return False
    return True


def _escalate(state, reason):
    state["status"] = "escalated"
    snapshot = state["snapshot"] or {}
    refs = [{"id": row.get("id"), "url": row.get("html_url"), "body": (row.get("body") or "")[:500]}
            for source in ("reviews", "inline_comments") for row in snapshot.get(source) or []
            if row.get("original_commit_id", row.get("commit_id")) == state["head"]][:10]
    emit(state, "escalation", "notify_erik_and_stop", state["updated_at"],
         summary={"reason": reason, "elapsed_seconds": state["updated_at"] - state["started_at"],
                  "evidence": refs, "cycles": [{"id": c["id"], "head": c["head"], "status": c["status"],
                      "evidence": c["evidence"][:3], "summary": c["summary"][:500]} for c in state["cycles"][:10]],
                  "owner_summary": (state["assessment"] or {}).get("summary", "")[:1000]})


def _digest(snapshot):
    value = deepcopy(snapshot)
    for key in ("started_at", "finished_at"):
        value.pop(key, None)
    for source in value.get("sources", {}).values():
        source.pop("observed_at", None)

    def canonical(item):
        if isinstance(item, dict):
            return {key: canonical(val) for key, val in sorted(item.items())}
        if isinstance(item, list):
            return sorted((canonical(val) for val in item), key=lambda val: json.dumps(val, sort_keys=True))
        return item
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True).encode()).hexdigest()


def observed_ci(snapshot):
    """Report visible failure/pending; workflow clearance always needs owner judgment."""
    if snapshot.get("status") != "complete" or snapshot.get("errors"):
        return "unknown"
    latest = {}
    for prefix, sha in (("", snapshot.get("head_sha")), ("merge_", snapshot.get("merge_sha"))):
        if not sha:
            continue
        for source in ("check_runs", "statuses"):
            rows = snapshot.get(prefix + source)
            if not isinstance(rows, list):
                return "unknown"
            for row in rows:
                if type(row.get("id")) is not int:
                    return "unknown"
                if source == "check_runs":
                    app = row.get("app") or {}
                    if (row.get("head_sha") != sha or not row.get("name") or not isinstance(app, dict)
                            or row.get("status") not in {"completed", "queued", "in_progress", "waiting", "requested", "pending"}):
                        return "unknown"
                    key = (sha, row["name"], app.get("id"))
                    value = row.get("conclusion") if row.get("status") == "completed" else "pending"
                else:
                    if not row.get("context"):
                        return "unknown"
                    key, value = (sha, row["context"]), row.get("state")
                if row["id"] > latest.get(key, (-1, None))[0]:
                    latest[key] = (row["id"], value)
    values = {value for _, value in latest.values()}
    if values & {"failure", "error", "timed_out", "cancelled", "action_required", "startup_failure", "stale"}:
        return "failed"
    return "pending" if "pending" in values else "unknown"


def _findings(snapshot, head):
    verified = {(row["source"], row["id"]) for row in snapshot.get("actor_verification", [])
                if row.get("connector_verified")}
    for row in snapshot.get("reviews") or []:
        if (("reviews", row.get("id")) in verified and row.get("commit_id") == head
                and row.get("state") == "CHANGES_REQUESTED"):
            return True
    for row in snapshot.get("inline_comments") or []:
        if (("inline_comments", row.get("id")) in verified
                and row.get("original_commit_id") == head
                and re.search(r"\bP[0-3]\b", row.get("body") or "")):
            return True
    return False


def _finding_head(state):
    if state["head"] not in state["finding_heads"]:
        state["finding_heads"].append(state["head"])


def _external(evidence, summary):
    if (not isinstance(evidence, list) or not evidence or not isinstance(summary, str)
            or not summary.strip() or any(not isinstance(url, str)
                or urlparse(url).scheme != "https" or urlparse(url).hostname not in
                {"github.com", "api.github.com"} for url in evidence)):
        raise ValueError("External GitHub evidence URLs and a summary are required")


def _cycle_hold(state):
    counted = [cycle for cycle in state["cycles"] if cycle["status"] != "rejected"]
    if len(counted) >= 3 and not state["review_hold"]:
        state["review_hold"] = True
        state["hold_cycle_id"] = counted[2]["id"]
        _event(state, "review_hold", "stop_changes_monitor_only")
    if state["status"] != "active":
        return
    if any(cycle["status"] == "unknown" for cycle in counted):
        _escalate(state, "Execution history is uncertain; ask Erik before another request")
    elif state["review_hold"] and (len(counted) > 3 or any(c["id"] == state["hold_cycle_id"]
            and c["status"] in {"completed", "rejected"} for c in state["cycles"])):
        _escalate(state, "Third GitHub review cycle requires Erik's direction, even when clean")


def reconcile(state, cycles, evidence, summary, now):
    """Owner groups executions using external proof; raw objects are never counted.

    Full ledger records have id, head, status, evidence, summary and numeric at.
    Acknowledged records also need acknowledged_at. Existing records cannot be
    dropped or reassigned; this operation never clears a hold or restarts a run.
    """
    _external(evidence, summary)
    if not isinstance(cycles, list) or not state["snapshot_id"]:
        raise ValueError("A full cycle ledger and collected snapshot are required")
    previous = {cycle["id"]: cycle for cycle in state["cycles"]}
    seen = set()
    for cycle in cycles:
        if not isinstance(cycle, dict):
            raise ValueError("Each execution record must be an object")
        _external(cycle.get("evidence"), cycle.get("summary"))
        if (not isinstance(cycle.get("id"), str) or not cycle["id"] or cycle["id"] in seen
                or not isinstance(cycle.get("head"), str) or not re.fullmatch(r"[0-9a-f]{40}", cycle["head"])
                or not isinstance(cycle.get("status"), str)
                or cycle.get("status") not in {"requested", "acknowledged", "completed", "rejected", "unknown"}
                or type(cycle.get("at")) not in (int, float) or not math.isfinite(cycle["at"])
                or cycle["at"] > now):
            raise ValueError("Invalid or duplicate execution record")
        if cycle["status"] == "acknowledged" and (not isinstance(cycle.get("acknowledged_at"), (int, float))
                or not cycle["at"] <= cycle["acknowledged_at"] <= now):
            raise ValueError("Acknowledgment needs its observed timestamp")
        old = previous.get(cycle["id"])
        if old and (old["head"] != cycle["head"] or old["at"] != cycle["at"]
                    or old["status"] in {"completed", "rejected"} and old["status"] != cycle["status"]
                    or old.get("acknowledged_at") is not None and old["acknowledged_at"] != cycle.get("acknowledged_at")
                    or old["status"] == "acknowledged" and cycle["status"] == "requested"):
            raise ValueError("Execution identity or terminal outcome cannot be rewritten")
        seen.add(cycle["id"])
    if not previous.keys() <= seen:
        raise ValueError("Existing execution history cannot be dropped")
    offset = len(state["events"])
    state.update(cycles=deepcopy(sorted(cycles, key=lambda c: c["at"])),
                 history_snapshot_id=state["snapshot_id"], updated_at=now,
                 history_evidence=list(evidence), history_summary=summary)
    _event(state, "history", "review_recorded_history")
    _cycle_hold(state)
    _request_wait(state, now)
    return state["events"][offset:]


def _activity(snapshot, baseline, head):
    """Fresh authenticated activity is acknowledgment evidence, never approval."""
    for actor in snapshot.get("actor_verification", []):
        source = actor["source"]
        if not actor.get("connector_verified"):
            continue
        def rows(data):
            return (data.get("comment_reactions", {}).get(source.split(":", 1)[1])
                    if source.startswith("comment_reactions:") else data.get(source)) or []
        before = {row.get("id"): row for row in rows(baseline)}
        for row in rows(snapshot):
            if row.get("id") != actor["id"] or before.get(row.get("id")) == row:
                continue
            if source == "reviews" and row.get("commit_id") != head:
                continue
            if source == "inline_comments" and row.get("original_commit_id") != head:
                continue
            yield source, row


def _request_wait(state, now):
    prior = [item for item in state["requests"] if item["head"] == state["head"]]
    if state["status"] != "active":
        return
    for cycle in state["cycles"]:
        if prior and cycle["id"] == prior[-1]["cycle_id"]:
            continue
        if cycle["status"] == "acknowledged" and now - cycle["acknowledged_at"] >= 900:
            _escalate(state, "Acknowledged review incomplete after fifteen minutes")
            return
        if cycle["status"] == "requested" and not any(r["cycle_id"] == cycle["id"] for r in prior) and now - cycle["at"] >= 300:
            _escalate(state, "Execution status unknown after five minutes; ask Erik")
            return
    if not prior:
        return
    attempt = prior[-1]
    cycle = next(c for c in state["cycles"] if c["id"] == attempt["cycle_id"])
    if cycle["status"] in {"completed", "rejected"}:
        return
    if cycle["status"] == "acknowledged":
        attempt.setdefault("acknowledged_at", cycle["acknowledged_at"])
    if state["assessment"] and state["review"] in {"clean", "findings"}:
        attempt["completed"] = True
    for source, row in _activity(state["snapshot"], attempt["snapshot"], state["head"]):
        try:
            observed = datetime.fromisoformat(row.get("created_at", "").replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            observed = now
        attempt.setdefault("acknowledged_at", max(attempt["at"], min(now, observed)))
        if (("reactions" in source and row.get("content") == "+1")
                or source == "reviews" and row.get("state") in {"APPROVED", "COMMENTED", "CHANGES_REQUESTED"}):
            attempt["completed"] = True  # Candidate only: never grants clearance.
    if attempt.get("completed"):
        if state["review_hold"] and attempt["cycle_id"] == state["hold_cycle_id"]:
            _escalate(state, "Third-cycle completion candidate observed; Erik and the owner must inspect it, not a clean verdict")
        return
    if "acknowledged_at" in attempt:
        if now - attempt["acknowledged_at"] >= 900:
            _escalate(state, "Acknowledged review incomplete after fifteen minutes")
    elif now - attempt["at"] >= 300:
        _escalate(state, "Execution status unknown after five minutes; ask Erik before any retry")


def consume(state, snapshot, now):
    """Observe a complete or failed collection; unchanged evidence produces no event."""
    offset = len(state["events"])
    if not _bounded(state, now):
        return state["events"][offset:]
    if (snapshot.get("repo"), snapshot.get("number")) != (state["repo"], state["number"]):
        raise ValueError("Snapshot belongs to another PR")
    state["polls"] += 1
    digest = _digest(snapshot)
    changed = digest != state["snapshot_id"]
    state.update(snapshot=deepcopy(snapshot), snapshot_id=digest, head=snapshot.get("head_sha"))
    if changed:
        state.update(review="pending", ci=observed_ci(snapshot), assessment=None)
        if state["head"] and _findings(snapshot, state["head"]):
            state["review"] = "findings"
            _finding_head(state)
        if state["status"] != "escalated":
            _event(state, "evidence", "assess_external_evidence")
    pr = snapshot.get("pr_end") or {}
    if state["status"] == "active" and state["review_hold"] and pr.get("state") == "closed":
        _escalate(state, "PR closed during the third-cycle hold; report outcome to Erik")
    elif state["status"] == "active" and pr.get("state") == "closed":
        state["status"] = "settled"
        _event(state, "closed", "none")
    elif state["status"] == "active" and pr.get("draft") and not state["review_hold"]:
        state["status"] = "held"
        _event(state, "draft", "owner_resume")
    _request_wait(state, now)
    _bounded(state, now)
    return state["events"][offset:]


def assess(state, head, snapshot_id, review, ci, evidence, summary, *, now=None):
    """Record the owner's policy judgment, pinned to the exact collected evidence.

    Evidence links and summary document the owner's review; this function does
    not infer clearance from arbitrary GitHub prose. Tests may inject the clock.
    """
    offset = len(state["events"])
    if not _bounded(state, time.time() if now is None else now):
        return state["events"][offset:]
    if (not head or head != state["head"]
            or not snapshot_id or snapshot_id != state["snapshot_id"]):
        raise ValueError("Assessment requires active state and current head and snapshot")
    if review not in REVIEWS or ci not in CI:
        raise ValueError("Unknown review or CI assessment")
    _external(evidence, summary)
    if state["review_hold"]:
        raise ValueError("Third-cycle hold requires Erik; no clean merge handoff")
    if review == "clean" and state["history_snapshot_id"] != snapshot_id:
        raise ValueError("Reconcile execution history against this snapshot first")
    if review == "clean" and (not any(c["head"] == head and c["status"] == "completed" for c in state["cycles"])
                             or any(c["status"] in {"requested", "acknowledged", "unknown"} for c in state["cycles"])):
        raise ValueError("Clean requires a completed current-head execution and no active or unknown attempts")
    if review == "clean" and state["snapshot"]["status"] != "complete":
        raise ValueError("Clean requires complete evidence collection")
    state.update(review=review, ci=ci, assessment=dict(head=head, snapshot_id=snapshot_id,
                 review=review, ci=ci, evidence=list(evidence), summary=summary))
    _event(state, "assessment", "wait")
    if review == "findings":
        _finding_head(state)
    elif review == "clean" and ci in {"satisfied", "not_configured"}:
        state["status"] = "settled"
        _event(state, "ready", "recheck_and_merge")
    _request_wait(state, state["updated_at"])
    return state["events"][offset:]


def request(state, head, kind, now):
    """Record a baseline before an owner-triggered request; never call GitHub."""
    offset = len(state["events"])
    if not _bounded(state, now):
        return state["events"][offset:]
    _request_wait(state, now)
    if state["status"] != "active":
        return state["events"][offset:]
    if (not head or head != state["head"] or not state["snapshot"]
            or state["snapshot"]["status"] != "complete"):
        raise ValueError("Request baseline requires complete current-head evidence")
    if (state["review_hold"] or state["history_snapshot_id"] != state["snapshot_id"]
            or any(c["status"] in {"requested", "acknowledged", "unknown"} for c in state["cycles"])):
        raise ValueError("Reconciled history below the hold and no active execution are required")
    if kind not in {"initial", "thorough"}:
        raise ValueError("Only explicit initial/thorough requests are supported; no automatic retry")
    cycle_id = f"reserved-{len(state['requests']) + 1}"
    if any(c["id"] == cycle_id for c in state["cycles"]):
        raise ValueError("Reserved execution ID already exists")
    snapshot = state["snapshot"]
    state["requests"].append(dict(head=head, kind=kind, at=now, cycle_id=cycle_id, snapshot_id=state["snapshot_id"],
        snapshot=deepcopy(snapshot),
        pr_body=(snapshot.get("pr_end") or {}).get("body"),
        pr_reaction_ids=[row.get("id") for row in snapshot.get("pr_reactions") or []],
        comment_reaction_ids={key: [row.get("id") for row in rows or []]
                              for key, rows in snapshot.get("comment_reactions", {}).items()}))
    state["cycles"].append(dict(id=cycle_id, head=head, status="requested", at=now,
        evidence=[f"https://github.com/{state['repo']}/pull/{state['number']}"],
        summary="Reserved before owner trigger; request outcome not yet known"))
    state.update(review="pending", assessment=None)
    event = _event(state, "request_baseline", "owner_trigger_reserved_request")
    event["cycle_id"] = cycle_id
    _cycle_hold(state)
    if state["review_hold"]:
        event["action"] = "owner_trigger_final_review_and_hold"
    return state["events"][offset:]
