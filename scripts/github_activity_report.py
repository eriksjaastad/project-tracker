"""Read-only, dated GitHub PR activity report across account identities.

GitHub search finds PRs with activity in a local calendar day. The review list
for each candidate is then read directly from its repository. A review object
is not a Codex execution: reaction-only and summary-only reviews live in other
API surfaces and are deliberately left to the separate review-history work.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo


API_TIMEOUT = 45
CARD_RE = re.compile(r"\(#(\d{4,})\)\s*$")
TASK_RE = re.compile(r"^#(\d+)\s")
API_REPO_PREFIX = "https://api.github.com/repos/"
SEARCH_FIELDS = ("created", "updated", "closed", "merged")


class ReportError(RuntimeError):
    """A source was incomplete, unavailable, or did not match its contract."""


def _run(command: list[str], timeout: int = API_TIMEOUT, *,
         cwd: str | None = None) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=timeout, check=True, cwd=cwd)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReportError(f"Source command failed: {command[0]} {command[1]}") from exc
    return result.stdout


def _api(path: str, fields: dict[str, str] | None = None) -> object:
    command = ["gha", "api", "-X", "GET", path]
    for key, value in (fields or {}).items():
        command.extend(["-f", f"{key}={value}"])
    try:
        return json.loads(_run(command))
    except json.JSONDecodeError as exc:
        raise ReportError(f"GitHub returned invalid JSON for {path}") from exc


def _instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReportError(f"Invalid GitHub timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ReportError(f"Unzoned GitHub timestamp: {value}")
    return parsed.astimezone(timezone.utc)


def _window(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    return start, end


def _repo_and_number(item: dict, owner: str) -> tuple[str, int]:
    url = item.get("repository_url", "")
    repo = url.removeprefix(API_REPO_PREFIX) if url.startswith(API_REPO_PREFIX) else ""
    number = item.get("number")
    if not repo.startswith(f"{owner}/") or repo.count("/") != 1 or not isinstance(number, int):
        raise ReportError(f"Invalid or out-of-scope PR in GitHub search: {url}")
    if not isinstance(item.get("pull_request"), dict):
        raise ReportError(f"Search result is not a PR: {repo}#{number}")
    return repo, number


def _pt_cards() -> set[str] | None:
    try:
        # pt otherwise infers the current project from the report's checkout.
        # Archived Done cards require a second, explicit retention view.
        output = _run(["pt", "tasks", "--all"], timeout=90, cwd="/")
        output += "\n" + _run(["pt", "tasks", "--all", "--archived"],
                               timeout=90, cwd="/")
    except ReportError:
        return None
    return {match.group(1) for line in output.splitlines()
            if (match := TASK_RE.match(line))}


def collect(owner: str, day: date, zone_name: str, *, api=_api,
            cards: set[str] | None = None,
            codex_reported_reviews: int | None = None) -> dict:
    """Return a source-labeled snapshot; `api` is injectable for tests."""
    try:
        zone = ZoneInfo(zone_name)
    except KeyError as exc:
        raise ReportError(f"Unknown time zone: {zone_name}") from exc
    start, end = _window(day, zone)
    candidates: dict[tuple[str, int], dict] = {}
    # Bind the injectable API only around collection, avoiding any global patch.
    for field in SEARCH_FIELDS:
        lower = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        # A PR reviewed on a historical day can have been updated again since.
        # Search every PR currently updated *after* that day for review
        # candidates; retain only events submitted inside the exact window.
        if field == "updated":
            qualifier = f"updated:>={lower}"
        else:
            # Include the next midnight to avoid losing fractional seconds.
            upper = end.strftime("%Y-%m-%dT%H:%M:%SZ")
            qualifier = f"{field}:{lower}..{upper}"
        query = f"user:{owner} is:pr {qualifier}"
        total = None
        found = 0
        for page in range(1, 11):
            data = api("search/issues", {"q": query, "per_page": "100", "page": str(page)})
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ReportError(f"Invalid GitHub search shape for {field}")
            if data.get("incomplete_results") is not False:
                raise ReportError(f"GitHub search incomplete for {field}")
            count = data.get("total_count")
            if not isinstance(count, int) or count >= 1000:
                raise ReportError(f"GitHub search capped or invalid for {field}: {count}")
            if total is None:
                total = count
            elif count != total:
                raise ReportError(f"GitHub search changed during pagination for {field}")
            for item in data["items"]:
                candidates[_repo_and_number(item, owner)] = item
            found += len(data["items"])
            if found >= total:
                break
            if not data["items"]:
                raise ReportError(f"GitHub search ended early for {field}")
        if found != total:
            raise ReportError(f"GitHub search lost results for {field}: {found}/{total}")

    rows = []
    review_ids = set()
    for (repo, number), item in sorted(candidates.items()):
        pull = item["pull_request"]
        created = _instant(item.get("created_at"))
        merged = _instant(pull.get("merged_at"))
        if created is None:
            raise ReportError(f"Missing creation time for {repo}#{number}")
        title = item.get("title") or ""
        card_match = CARD_RE.search(title)
        card = card_match.group(1) if card_match else None
        reviews = []
        for page in range(1, 101):
            batch = api(f"repos/{repo}/pulls/{number}/reviews",
                        {"per_page": "100", "page": str(page)})
            if not isinstance(batch, list):
                raise ReportError(f"Invalid reviews for {repo}#{number}")
            for review in batch:
                submitted = _instant(review.get("submitted_at"))
                if submitted is None or not start <= submitted < end:
                    continue
                review_id = review.get("id")
                if not isinstance(review_id, int) or review_id in review_ids:
                    raise ReportError(f"Missing or duplicate review ID for {repo}#{number}")
                review_ids.add(review_id)
                reviews.append({
                    "id": review_id,
                    "actor": (review.get("user") or {}).get("login") or "(deleted account)",
                    "url": review.get("html_url") or
                           f"https://github.com/{repo}/pull/{number}#pullrequestreview-{review_id}",
                    "state": review.get("state"),
                })
            if len(batch) < 100:
                break
        else:
            raise ReportError(f"Review pagination exceeded 100 pages for {repo}#{number}")
        lifecycle = []
        for page in range(1, 101):
            batch = api(f"repos/{repo}/issues/{number}/events",
                        {"per_page": "100", "page": str(page)})
            if not isinstance(batch, list):
                raise ReportError(f"Invalid lifecycle events for {repo}#{number}")
            for event in batch:
                if event.get("event") in {"closed", "merged", "reopened"}:
                    when = _instant(event.get("created_at"))
                    if when is None:
                        raise ReportError(f"Missing lifecycle time for {repo}#{number}")
                    lifecycle.append((event["event"], when))
            if len(batch) < 100:
                break
        else:
            raise ReportError(f"Lifecycle pagination exceeded 100 pages for {repo}#{number}")
        # A merge emits a merged event followed by a closed event, sometimes
        # one second later. Earlier closes remain visible after a reopen.
        merged_closure_pending = False
        closed_unmerged = False
        for kind, when in sorted(lifecycle, key=lambda entry: entry[1]):
            if kind == "merged":
                merged_closure_pending = True
            elif kind == "reopened":
                merged_closure_pending = False
            elif kind == "closed":
                if not merged_closure_pending and start <= when < end:
                    closed_unmerged = True
                merged_closure_pending = False
        row = {
            "repo": repo, "number": number, "title": title,
            "url": item.get("html_url") or f"https://github.com/{repo}/pull/{number}",
            "author": (item.get("user") or {}).get("login") or "(deleted account)",
            "opened": start <= created < end,
            "merged": merged is not None and start <= merged < end,
            "closed_unmerged": closed_unmerged,
            "open_as_of": item.get("state") == "open",
            "card_ref": card,
            "local_card_match": card in cards if card and cards is not None else None,
            "reviews": reviews,
        }
        if row["opened"] or row["merged"] or row["closed_unmerged"] or reviews:
            rows.append(row)
    return {
        "owner": owner, "date": day.isoformat(), "timezone": zone_name,
        "window_utc": [start.isoformat(), end.isoformat()],
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_queries": list(SEARCH_FIELDS),
        "candidate_count": len(candidates),
        "pt_available": cards is not None,
        "review_cycles": None,
        "codex_subscription_analytics": (
            {"reported_reviews": codex_reported_reviews,
             "source": "Erik-reported Codex UI count; UI export and period definition unavailable"}
            if codex_reported_reviews is not None else None),
        "pull_requests": rows,
    }


def render(report: dict) -> str:
    rows = report["pull_requests"]
    opened = sum(row["opened"] for row in rows)
    merged = sum(row["merged"] for row in rows)
    closed = sum(row["closed_unmerged"] for row in rows)
    review_count = sum(len(row["reviews"]) for row in rows)
    reviewed_prs = sum(bool(row["reviews"]) for row in rows)
    by_repo: dict[str, Counter] = defaultdict(Counter)
    by_author: dict[str, Counter] = defaultdict(Counter)
    review_actors = Counter()
    for row in rows:
        for key in ("opened", "merged", "closed_unmerged"):
            by_repo[row["repo"]][key] += int(row[key])
            by_author[row["author"]][key] += int(row[key])
        for review in row["reviews"]:
            review_actors[review["actor"]] += 1
            by_repo[row["repo"]]["reviews"] += 1
    lines = [
        f"# GitHub activity: {report['date']} ({report['timezone']})",
        "",
        f"Snapshot: {report['as_of_utc']}. Window (UTC, end exclusive): "
        f"{report['window_utc'][0]} to {report['window_utc'][1]}. "
        f"Repository owner: [`{report['owner']}`](https://github.com/{report['owner']}).",
        "",
        f"**{len(rows)} distinct PR{'s' if len(rows) != 1 else ''} with activity "
        f"(from {report['candidate_count']} queried candidates); {opened} opened, "
        f"{merged} merged, {closed} closed without merge; "
        f"{review_count} submitted review object{'s' if review_count != 1 else ''} "
        f"on {reviewed_prs} distinct PR{'s' if reviewed_prs != 1 else ''}.** "
        "A PR may appear in more than one event count. Review objects are not "
        "Codex review executions.",
        "",
        "## By PR author",
        "",
        "| GitHub actor | Opened | Merged | Closed unmerged |",
        "| --- | ---: | ---: | ---: |",
    ]
    for actor, counts in sorted(by_author.items()):
        lines.append(f"| {actor} | {counts['opened']} | {counts['merged']} | "
                     f"{counts['closed_unmerged']} |")
    lines += ["", "## By repository", "",
              "| Repository | Opened | Merged | Closed unmerged | Review objects |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for repo, counts in sorted(by_repo.items()):
        lines.append(f"| [`{repo}`](https://github.com/{repo}/pulls) | "
                     f"{counts['opened']} | {counts['merged']} | "
                     f"{counts['closed_unmerged']} | {counts['reviews']} |")
    lines += ["", "## Review actors", "",
              "| GitHub actor | Submitted review objects |",
              "| --- | ---: |"]
    for actor, count in sorted(review_actors.items()):
        lines.append(f"| {actor} | {count} |")
    lines += ["", "## PR evidence", "",
              "| PR | Author | Opened | Merged | Closed unmerged | "
              "Reviews today | PT card |",
              "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        card = "—"
        if row["card_ref"]:
            match = row["local_card_match"]
            label = ("local match" if match else
                     "no local match" if match is False else "PT unavailable")
            card = f"#{row['card_ref']} ({label})"
        lines.append(
            f"| [{row['repo']}#{row['number']}]({row['url']}) | {row['author']} | "
            f"{int(row['opened'])} | {int(row['merged'])} | "
            f"{int(row['closed_unmerged'])} | {len(row['reviews'])} | {card} |")
    reviewed = [row for row in rows if row["reviews"]]
    lines += ["", "## Review-object evidence", ""]
    for row in reviewed:
        links = ", ".join(
            f"[{review['id']}]({review['url']}) ({review['actor']})"
            for review in row["reviews"])
        lines.append(f"- [{row['repo']}#{row['number']}]({row['url']}): {links}")
    if not reviewed:
        lines.append("No submitted review objects in the candidate set.")
    unmerged = [row for row in rows if row["open_as_of"]]
    lines += ["", "## Still open among candidate PRs", ""]
    lines += ([f"- [{row['repo']}#{row['number']}]({row['url']}) — "
               f"{row['title'].replace(chr(10), ' ').replace(chr(13), ' ')}"
               for row in unmerged] or ["None in this candidate set."])
    lines += [
        "", "## Source coverage and limits", "",
        "- GitHub Search: all PRs under the named owner matching created, "
        "closed, or merged in this day's UTC window, plus PRs whose current "
        "updated time is at or after the window's start. The latter keeps "
        "historical review candidates after later PR updates; only activity "
        "inside the requested day appears in the tables. Each search "
        "must be complete and below GitHub's 1,000-result cap; otherwise the "
        "command fails. Repository visibility is limited to the active `gha` "
        "credential and GitHub search indexing. Review discovery assumes "
        "a submitted review advances the PR's updated time. This is a multi-request "
        "snapshot, not an atomic export; activity during collection can move "
        "between queries.",
        "- Reviews: paginated GitHub PR review objects for those candidate PRs, "
        "filtered by submitted time. Reviews on PRs absent from the candidate "
        "set are not measured. Review comments, issue comments, reactions, "
        "requested reviews, and Codex completion summaries are not counted.",
        "- Closed without merge: paginated issue lifecycle events for candidate "
        "PRs. A merge's `merged` then `closed` pair is excluded; a previous "
        "unmerged close remains counted after a reopen. The total counts "
        "distinct PRs with at least one such close in the window.",
        "- Actor attribution: opened, merged, and closed PR totals are grouped "
        "by the PR author; this report does not identify the person or bot "
        "who clicked merge or close. Review totals use the review object's actor.",
        "- Distinct Codex review executions: **unknown** pending ai-memory "
        "#7413 and Project Tracker #7417. Multiple review objects can belong "
        "to one execution; a reaction-only completion can have no review object.",
        "- PT linkage: a trailing `(#card)` in the PR title is compared with "
        "unscoped `pt tasks --all` and `pt tasks --all --archived` when "
        "available. Display IDs are machine-local: even a local match is "
        "not a verified cross-machine card identity or proof that the PR "
        "delivered the card. "
        + ("The local PT index was available." if report["pt_available"]
           else "The local PT index was unavailable."),
        "- Codex subscription analytics: "
        + (f"Erik reported a code review count of "
           f"{report['codex_subscription_analytics']['reported_reviews']} "
           "in the Codex UI for 'today'; the exact UI period, "
           "export, and counting rule are unavailable. GitHub shows "
           f"{review_count} submitted review objects on {reviewed_prs} candidate "
           "PRs in the stated window. This is a visible discrepancy between "
           "different, non-equivalent measures, not a computed missing-review count."
           if report["codex_subscription_analytics"] else
           "**not collected**. Do not equate GitHub review objects with a "
           "subscription counter or infer missing work from a dashboard number."),
        "- Counts are events and PRs, not features, lines of code, labor, "
        "GitHub personal-profile credit, or model authorship. No identity "
        "migration or historical rewrite was performed.",
        "",
        "Reproduce from this repository: "
        f"`uv run scripts/github_activity_report.py "
        f"--date {report['date']} --timezone {report['timezone']} "
        f"--owner {report['owner']}"
        + (f" --codex-reported-reviews "
           f"{report['codex_subscription_analytics']['reported_reviews']}"
           if report["codex_subscription_analytics"] else "")
        + "`. A later run can differ because the "
        "day may still be in progress or GitHub indexing/state changed.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--timezone", default="America/New_York")
    parser.add_argument("--owner", default="eriksjaastad")
    parser.add_argument("--output", type=Path, help="Write Markdown to this path")
    parser.add_argument("--json-output", type=Path, help="Write source snapshot JSON")
    parser.add_argument("--codex-reported-reviews", type=int, metavar="N",
                        help="Externally reported Codex UI count; labeled unverified")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.owner):
        parser.error("owner must be a GitHub login")
    if args.codex_reported_reviews is not None and args.codex_reported_reviews < 0:
        parser.error("Codex reported review count must be nonnegative")
    try:
        report = collect(args.owner, args.date, args.timezone, cards=_pt_cards(),
                         codex_reported_reviews=args.codex_reported_reviews)
        markdown = render(report)
    except ReportError as exc:
        parser.exit(1, f"github activity report: {exc}\n")
    if args.output:
        args.output.write_text(markdown)
    else:
        print(markdown)
    if args.json_output:
        args.json_output.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
