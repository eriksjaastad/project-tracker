"""Foreground PR monitoring. Events reach an attached owner, not an idle session."""
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

import click

from scripts import pr_settle_state as engine
from scripts.pr_evidence import collect
from scripts.pr_conditional import ConditionalGhaTransport


class Store:
    def __init__(self, repo, number, owner):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or any(
            part in {".", ".."} for part in repo.split("/")
        ):
            raise click.ClickException("Repository must be owner/name")
        if not owner.strip():
            raise click.ClickException("An owning agent/session ID is required")
        self.repo, self.number, self.owner = repo.lower(), number, owner
        root = Path(os.environ.get("PT_PR_SETTLE_DIR", "~/.project-tracker/pr-settle")).expanduser()
        self.directory = root / self.repo / str(number)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "state.json"

    @contextmanager
    def lock(self, runner=False):
        with (self.directory / ("runner.lock" if runner else "state.lock")).open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | (fcntl.LOCK_NB if runner else 0))
            except BlockingIOError as exc:
                raise click.ClickException("This PR already has an active monitor or state writer") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def load(self):
        if not self.path.exists():
            raise click.ClickException("No settle record; start pt pr settle first")
        try:
            state = json.loads(self.path.read_text())
            if not isinstance(state, dict) or not engine.fresh(self.repo, self.number, self.owner, 0, 1).keys() <= state.keys():
                raise ValueError("missing required state")
            if type(state["review_hold"]) is not bool:
                raise ValueError("invalid review hold")
            if state["schema_version"] != 1 or state["repo"] != self.repo or state["number"] != self.number:
                raise ValueError("state identity or version mismatch")
            if state["owner"] != self.owner:
                raise click.ClickException(f"This PR belongs to session {state['owner']}")
            for key in ("events", "requests", "finding_heads", "cycles"):
                if not isinstance(state[key], list):
                    raise ValueError("invalid history")
            comment_ids = state.get("request_comment_ids", [])
            if not isinstance(comment_ids, list) or any(type(value) is not int or value <= 0 for value in comment_ids):
                raise ValueError("invalid request comment IDs")
            for key in ("started_at", "updated_at", "deadline"):
                if type(state[key]) not in (int, float) or not math.isfinite(state[key]):
                    raise ValueError("invalid clock")
            if state["deadline"] < state["started_at"] or type(state["polls"]) is not int or not 0 <= state["polls"] <= 240:
                raise ValueError("invalid budget")
            if any(not isinstance(event, dict) or event.get("seq") != index
                   for index, event in enumerate(state["events"], 1)):
                raise ValueError("invalid event sequence")
            acked = state.get("acked", 0)
            if type(acked) is not int or not 0 <= acked <= len(state["events"]):
                raise ValueError("invalid delivery cursor")
            if state["review"] not in engine.REVIEWS or state["ci"] not in engine.CI:
                raise ValueError("invalid assessment")
            if "snapshot" not in state or "snapshot_id" not in state or "head" not in state:
                raise ValueError("missing evidence state")
            if state["status"] not in {"active", "held", "stopped", "settled", "escalated"}:
                raise ValueError("invalid status")
            return state
        except (ValueError, KeyError, TypeError) as exc:
            raise click.ClickException("Corrupt or unsupported settle record; preserve it for inspection") from exc

    def save(self, state):
        with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as handle:
            json.dump(state, handle, sort_keys=True, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, self.path)


def target(function):
    function = click.option("--owner", required=True, help="Unique owning agent/session ID.")(function)
    function = click.option("--repo", required=True, help="GitHub owner/repository.")(function)
    return click.argument("number", type=click.IntRange(min=1))(function)


def output(events):
    for event in events:
        click.echo(json.dumps(event, sort_keys=True))


def guarded(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@click.group(name="pr")
def pr_group():
    """Monitor a PR while its owning agent stays attached. Never merges."""


@pr_group.command("settle")
@target
@click.option("--interval", type=click.IntRange(30, 60), default=60, show_default=True)
@click.option("--max-minutes", type=click.IntRange(1, 240), default=180, show_default=True)
@click.option("--stop", is_flag=True, help="Persist a stop; an active monitor exits promptly.")
@click.option("--hold", is_flag=True, help="Pause this PR without resetting its history.")
@click.option("--resume", is_flag=True, help="Resume an explicit/draft hold within the original deadline.")
@click.option("--request-comment-id", multiple=True, type=click.IntRange(min=1),
              help="Observe reactions on this review-request comment; repeat to add IDs durably.")
def settle(number, repo, owner, interval, max_minutes, stop, hold, resume, request_comment_id):
    """Poll NUMBER every minute; keep this foreground stream attached to the owner.

    Read evidence events, assess GitHub clearance under pr_merge_policy, and
    acknowledge handled event IDs. Pending unchanged snapshots are quiet.
    --stop/--hold work from another terminal while this process is polling.
    """
    if sum((stop, hold, resume)) > 1:
        raise click.ClickException("Choose only one of --stop, --hold, --resume")
    if request_comment_id and (stop or hold):
        raise click.ClickException("Add request comment IDs when starting or resuming, not with --hold/--stop")
    store = Store(repo, number, owner)
    if stop or hold:
        with store.lock():
            state = store.load()
            if state["status"] in {"active", "held"}:
                state["status"] = "stopped" if stop else "held"
                event = engine.emit(state, state["status"], "stop_monitor", time.time())
                store.save(state)
                output([event])
        return
    with store.lock(runner=True):
        with store.lock():
            state = store.load() if store.path.exists() else engine.fresh(
                store.repo, number, owner, time.time(), max_minutes)
            if resume:
                if state["status"] != "held":
                    raise click.ClickException("Only a held record can resume; limits and stops are preserved")
                state["status"] = "active"
            if request_comment_id and state["status"] not in {"active", "held"}:
                raise click.ClickException("Cannot add request comment IDs to an ended run")
            comment_ids = sorted(set(state.get("request_comment_ids", [])) | set(request_comment_id))
            if comment_ids != state.get("request_comment_ids", []):
                state.update(snapshot_id=None, history_snapshot_id=None, assessment=None, review="pending")
            state["request_comment_ids"] = comment_ids
            store.save(state)
            output([event for event in state["events"] if event["seq"] > state.get("acked", 0)])
        cwd = Path(os.environ.get("PT_CALLER_CWD") or os.getcwd())
        transport = ConditionalGhaTransport(cwd)
        while state["status"] == "active":
            if time.time() >= state["deadline"] or state["polls"] >= 240:
                with store.lock():
                    state = store.load()
                    events = guarded(engine.consume, state, state["snapshot"] or {}, time.time())
                    store.save(state)
                output(events)
                break
            tick_start = time.monotonic()
            # Collection is outside the transaction lock so hold/stop remain usable.
            transport.deadline = tick_start + 55
            snapshot = collect(store.repo, number, cwd, transport=transport,
                               request_comment_ids=state.get("request_comment_ids", []))
            with store.lock():
                state = store.load()
                events = guarded(engine.consume, state, snapshot, time.time())
                store.save(state)
            output(events)
            fatal = {key: error for key, error in snapshot["errors"].items()
                     if not (key in {"merge_check_runs", "merge_statuses"}
                             and error.get("kind") == "unavailable")
                     and not (key == "pr_identity" and error.get("kind") == "changed")}
            if fatal and state["status"] == "active":
                raise click.ClickException("GitHub evidence unavailable; inspect saved errors before restarting")
            while state["status"] == "active" and time.monotonic() - tick_start < interval:
                if time.time() >= state["deadline"]:
                    with store.lock():
                        state = store.load()
                        events = guarded(engine.consume, state, snapshot, time.time())
                        store.save(state)
                    output(events)
                    break
                time.sleep(1)
                with store.lock():
                    state = store.load()


@pr_group.command("status")
@target
def status(number, repo, owner):
    """Read durable state, raw GitHub evidence and replayable event IDs as JSON."""
    store = Store(repo, number, owner)
    with store.lock():
        click.echo(json.dumps(store.load(), indent=2, sort_keys=True))


@pr_group.command("assess")
@target
@click.option("--head", required=True)
@click.option("--snapshot", "snapshot_id", required=True)
@click.option("--review", required=True, type=click.Choice(["clean", "findings", "pending", "ambiguous"]))
@click.option("--ci", required=True, type=click.Choice(["satisfied", "not_configured", "pending", "failed", "unknown"]))
@click.option("--evidence", multiple=True, required=True, help="GitHub evidence URL; repeat as needed.")
@click.option("--summary", required=True, help="Policy reasoning; include local checks when CI is not configured.")
def assess(number, repo, owner, head, snapshot_id, review, ci, evidence, summary):
    """Record the owner's interpretation of external GitHub evidence, not a local PASS."""
    store = Store(repo, number, owner)
    with store.lock():
        state = store.load()
        events = guarded(engine.assess, state, head, snapshot_id, review, ci, list(evidence), summary,
                         now=time.time())
        store.save(state)
    output(events)


@pr_group.command("request")
@target
@click.option("--head", required=True)
@click.option("--kind", required=True, type=click.Choice(["initial", "thorough"]))
def request(number, repo, owner, head, kind):
    """Capture a PR-body baseline before an owner-triggered review; never triggers one."""
    store = Store(repo, number, owner)
    cwd = Path(os.environ.get("PT_CALLER_CWD") or os.getcwd())
    with store.lock():
        comment_ids = store.load().get("request_comment_ids", [])
    snapshot = collect(store.repo, number, cwd, request_comment_ids=comment_ids)
    with store.lock():
        state = store.load()
        if state.get("request_comment_ids", []) != comment_ids:
            raise click.ClickException("Request comment configuration changed during collection; inspect a fresh snapshot")
        observed = guarded(engine.consume, state, snapshot, time.time())
        # A rejected reservation must not erase newly observed acknowledgments,
        # head changes or limit events. Commit the observation independently.
        store.save(state)
        output(observed)
        events = guarded(engine.request, state, head, kind, time.time())
        store.save(state)
    output(events)


@pr_group.command("history")
@target
@click.option("--ledger", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--snapshot", "snapshot_id", required=True, help="Digest of the evidence inspected for this ledger.")
@click.option("--evidence", multiple=True, required=True)
@click.option("--summary", required=True)
def history(number, repo, owner, ledger, snapshot_id, evidence, summary):
    """Reconcile distinct GitHub executions from a complete, evidence-backed JSON ledger.

    Read docs/PR_SETTLE.md before recording history. Initial review counts;
    multiple objects from one execution do not create multiple cycles.
    """
    try:
        cycles = json.loads(ledger.read_text())
    except (OSError, ValueError) as exc:
        raise click.ClickException("Cannot read a valid JSON execution ledger") from exc
    store = Store(repo, number, owner)
    with store.lock():
        state = store.load()
        events = guarded(engine.reconcile, state, cycles, list(evidence), summary, time.time(),
                         snapshot_id=snapshot_id)
        store.save(state)
    output(events)


@pr_group.command("acknowledge")
@target
@click.option("--event", type=click.IntRange(min=1), required=True)
def acknowledge(number, repo, owner, event):
    """Acknowledge delivery through EVENT; restarts replay unacknowledged IDs."""
    store = Store(repo, number, owner)
    with store.lock():
        state = store.load()
        if event > len(state["events"]):
            raise click.ClickException("Event has not been emitted")
        state["acked"] = max(state.get("acked", 0), event)
        store.save(state)
