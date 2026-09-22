"""Read-only GitHub evidence collection; this module never grants merge approval.

``collect`` returns raw evidence with collection status complete/unknown/inconsistent.
Complete means the requested sources were read, not that CI or review passed.
Failed sources are None and have an explicit entry in ``errors``. The caller must
apply the review policy, persist request baselines, and resolve summary commit IDs.
"""
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import quote

CONNECTOR = "chatgpt-codex-connector[bot]"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class EvidenceError(Exception):
    """A source was unavailable or could not be collected completely."""

    def __init__(self, kind, message, *, http_status=None):
        super().__init__(message)
        self.kind = kind
        self.http_status = http_status

    def describe(self, endpoint):
        return {"kind": self.kind, "message": str(self), "endpoint": endpoint,
                "http_status": self.http_status}


class GhaTransport:
    """GET-only transport; the injected runner has subprocess.run's interface."""

    def __init__(self, cwd: Path, *, run=None, deadline=None):
        self.cwd = cwd
        self.run = run or subprocess.run
        self.deadline = deadline

    def get(self, endpoint, *, paginate=False):
        remaining = 30 if self.deadline is None else self.deadline - time.monotonic()
        if remaining <= 0:
            raise EvidenceError("timeout", "Collection deadline elapsed")
        command = ["gha", "api", "--method", "GET", "-H",
                   "Accept: application/vnd.github+json", endpoint]
        if paginate:
            command += ["--paginate", "--slurp"]
        try:
            result = self.run(command, cwd=self.cwd, capture_output=True, text=True,
                              check=True, timeout=min(30, remaining))
        except subprocess.TimeoutExpired as exc:
            raise EvidenceError("timeout", "GitHub API request timed out") from exc
        except OSError as exc:
            raise EvidenceError("unavailable", "Cannot execute gha") from exc
        except subprocess.CalledProcessError as exc:
            # Never echo stderr: an authentication failure may include credentials.
            match = re.search(r"\bHTTP (\d{3})\b", str(exc.stderr or ""))
            status = int(match[1]) if match else None
            try:
                body = json.loads(exc.stdout or "null")
            except (ValueError, TypeError):
                body = None
            if (status == 404 and endpoint.endswith("/protection")
                    and isinstance(body, dict) and body.get("message") == "Branch not protected"):
                raise EvidenceError("not_protected", "Branch not protected", http_status=404) from exc
            raise EvidenceError("http" if status else "command",
                                f"GitHub API request failed (exit {exc.returncode})",
                                http_status=status) from exc
        try:
            return json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise EvidenceError("invalid_json", "GitHub API returned invalid JSON") from exc


def _object(value):
    if not isinstance(value, dict):
        raise EvidenceError("shape", "Expected a JSON object")
    return value


def _pages(value, key=None):
    """Flatten --paginate --slurp, rejecting malformed or incomplete envelopes."""
    if not isinstance(value, list) or not value:
        raise EvidenceError("shape", "Expected a nonempty array of API pages")
    rows, totals = [], set()
    for page in value:
        if key:
            page = _object(page)
            total = page.get("total_count")
            if type(total) is not int or total < 0:
                raise EvidenceError("shape", "Missing valid pagination total_count")
            totals.add(total)
            page = page.get(key)
        if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
            raise EvidenceError("shape", "Expected an array of objects on every page")
        rows.extend(page)
    if key and totals != {len(rows)}:
        raise EvidenceError("incomplete", "Pagination totals do not match collected rows")
    return rows


def _pr(value, repo, number):
    value = _object(value)
    try:
        valid = (value["number"] == number and value["state"] in {"open", "closed"}
                 and type(value["draft"]) is bool and isinstance(value["html_url"], str)
                 and all(isinstance(value[side]["ref"], str)
                         and isinstance(value[side]["sha"], str)
                         and _SHA.fullmatch(value[side]["sha"]) for side in ("head", "base"))
                 and value["base"]["repo"]["full_name"].lower() == repo.lower()
                 and (value.get("merge_commit_sha") is None
                      or isinstance(value["merge_commit_sha"], str)
                      and _SHA.fullmatch(value["merge_commit_sha"])))
    except (KeyError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise EvidenceError("shape", "PR identity, head, base, or state is incomplete")
    return value


def _identity(pr):
    return [(pr[side]["sha"], pr[side]["ref"],
             (pr[side].get("repo") or {}).get("full_name")) for side in ("head", "base")]


def _actors(snapshot):
    """Authenticate actors against the exact REST bot account, retaining raw users."""
    account = snapshot["connector_account"] or {}
    canonical = (account.get("login") == CONNECTOR and account.get("type") == "Bot"
                 and type(account.get("id")) is int and bool(account.get("node_id")))
    evidence = []
    sources = {name: snapshot[name] for name in
               ("reviews", "issue_comments", "inline_comments", "pr_reactions")}
    sources.update({f"comment_reactions:{key}": rows
                    for key, rows in snapshot["comment_reactions"].items()})
    for source, rows in sources.items():
        for row in rows or []:
            actor = row.get("user") or {}
            if not isinstance(actor, dict):
                snapshot["errors"][f"actor:{source}:{row.get('id')}"] = EvidenceError(
                    "shape", "Evidence actor is not an object").describe(
                        snapshot["sources"][source]["endpoint"])
                actor = {}
            verified = bool(canonical and actor.get("login") == CONNECTOR
                            and actor.get("type") in {"Bot", "User"}
                            and actor.get("id") == account["id"]
                            and actor.get("node_id") == account["node_id"])
            # GitHub has exposed reaction actors as User; other evidence must say Bot.
            if "reactions" not in source and actor.get("type") != "Bot":
                verified = False
            evidence.append({"source": source, "id": row.get("id"),
                             "connector_verified": verified})
    return evidence


def collect(repo: str, number: int, cwd: Path, *, transport=None,
            request_comment_ids=(), total_timeout=55) -> dict:
    """Collect evidence without evaluating it, using at most four concurrent GETs.

    ``transport.get(endpoint, paginate=False)`` returns decoded JSON and raises
    EvidenceError for operational failure. Request comments must be explicitly
    recorded by the caller; this collector never guesses which comment triggered
    a review or reconstructs a missing reaction baseline. All times are UTC.
    """
    if not isinstance(repo, str) or not _REPO.fullmatch(repo):
        raise ValueError("repo must be owner/name")
    if type(number) is not int or number <= 0:
        raise ValueError("number must be a positive integer")
    if not 0 < total_timeout <= 300:
        raise ValueError("total_timeout must be between 0 and 300 seconds")
    comment_ids = tuple(dict.fromkeys(request_comment_ids))
    if any(type(value) is not int or value <= 0 for value in comment_ids):
        raise ValueError("request_comment_ids must contain positive integers")
    deadline = time.monotonic() + total_timeout
    client = transport or GhaTransport(cwd, deadline=deadline)
    now = lambda: datetime.now(timezone.utc).isoformat()
    snapshot = {"schema_version": 1, "repo": repo, "number": number,
                "started_at": now(), "status": "unknown", "gate_assessment": "not_performed",
                "head_sha": None, "merge_sha": None, "errors": {},
                "comment_reactions": {}, "sources": {}}
    prefix = f"repos/{repo}"
    pr_endpoint = f"{prefix}/pulls/{number}"

    def fetch(endpoint, paginate=False, key=None):
        data = client.get(endpoint, paginate=paginate)
        return _pages(data, key) if paginate else _object(data)

    def record(name, endpoint, task):
        snapshot["sources"][name] = {"endpoint": endpoint, "observed_at": now()}
        try:
            snapshot[name] = task()
        except EvidenceError as exc:
            if name == "branch_protection" and exc.kind == "not_protected":
                snapshot[name] = {"present": False, "reason": "Branch not protected",
                                  "http_status": 404}
            else:
                snapshot[name] = None
                snapshot["errors"][name] = exc.describe(endpoint)

    record("pr_start", pr_endpoint, lambda: _pr(fetch(pr_endpoint), repo, number))
    start = snapshot["pr_start"]
    jobs = {
        "reviews": (f"{pr_endpoint}/reviews?per_page=100", True, None),
        "issue_comments": (f"{prefix}/issues/{number}/comments?per_page=100", True, None),
        "inline_comments": (f"{pr_endpoint}/comments?per_page=100", True, None),
        "pr_reactions": (f"{prefix}/issues/{number}/reactions?per_page=100", True, None),
        "timeline": (f"{prefix}/issues/{number}/timeline?per_page=100", True, None),
        "workflows": (f"{prefix}/actions/workflows?per_page=100", True, "workflows"),
        "connector_account": (f"users/{quote(CONNECTOR, safe='')}", False, None),
    }
    for comment in comment_ids:
        jobs[f"comment_reactions:{comment}"] = (
            f"{prefix}/issues/comments/{comment}/reactions?per_page=100", True, None)
    dependent = ("check_runs", "statuses", "merge_check_runs", "merge_statuses",
                 "branch_protection", "branch_rules")
    for name in dependent:
        snapshot[name] = None
    if start:
        snapshot["head_sha"] = start["head"]["sha"]
        snapshot["merge_sha"] = start.get("merge_commit_sha")
        branch = quote(start["base"]["ref"], safe="")
        jobs["branch_protection"] = (f"{prefix}/branches/{branch}/protection", False, None)
        jobs["branch_rules"] = (f"{prefix}/rules/branches/{branch}?per_page=100", True, None)
        for label, sha in (("", snapshot["head_sha"]), ("merge_", snapshot["merge_sha"])):
            if sha:
                jobs[f"{label}check_runs"] = (
                    f"{prefix}/commits/{sha}/check-runs?filter=all&per_page=100", True, "check_runs")
                jobs[f"{label}statuses"] = (f"{prefix}/commits/{sha}/statuses?per_page=100", True, None)
    else:
        for name in dependent:
            snapshot["errors"][name] = EvidenceError(
                "unavailable", "PR identity unavailable; source not queried").describe(pr_endpoint)
    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pr-evidence")
    futures = {executor.submit(fetch, *args): (name, args[0]) for name, args in jobs.items()}
    done, pending = wait(futures, timeout=max(0, deadline - time.monotonic()))
    for future in done:
        name, endpoint = futures[future]
        record(name, endpoint, future.result)
    for future in pending:
        name, endpoint = futures[future]
        future.cancel()
        snapshot[name] = None
        snapshot["errors"][name] = EvidenceError("timeout", "Collection deadline elapsed").describe(endpoint)
    executor.shutdown(wait=False, cancel_futures=True)
    record("pr_end", pr_endpoint, lambda: _pr(fetch(pr_endpoint), repo, number))
    for comment in comment_ids:
        snapshot["comment_reactions"][str(comment)] = snapshot.pop(f"comment_reactions:{comment}")
    account = snapshot["connector_account"]
    if account and not (account.get("login") == CONNECTOR and account.get("type") == "Bot"
                        and type(account.get("id")) is int and account.get("node_id")):
        snapshot["errors"]["connector_account"] = EvidenceError(
            "identity", "Exact connector account could not be authenticated").describe(jobs["connector_account"][0])
    snapshot["actor_verification"] = _actors(snapshot)
    end = snapshot["pr_end"]
    if start and end and (_identity(start) != _identity(end)
                          or start.get("merge_commit_sha") != end.get("merge_commit_sha")
                          or start["state"] != end["state"] or start["draft"] != end["draft"]):
        snapshot["status"] = "inconsistent"
        snapshot["errors"]["pr_identity"] = EvidenceError(
            "changed", "PR head, base, merge commit, draft, or state changed during collection").describe(pr_endpoint)
    else:
        snapshot["status"] = "unknown" if snapshot["errors"] else "complete"
    snapshot["finished_at"] = now()
    return snapshot
