# PR settle monitor

Tracking card: #7354. The September 19 event-driven watcher missed a completed
review for about 48 minutes. The replacement polls GitHub about once a minute
while the owning agent remains engaged. Each repository and PR has independent
state; a new head invalidates the previous assessment.

## Delivery plan

The pickup estimate exceeded 800 substantive lines including failure tests, so
the work was split before implementation:

1. #7448: independently testable, read-only GitHub evidence collection.
2. #7454: conditional transport, split when page-level revalidation and failure
   tests pushed the combined monitor estimate above the sizing threshold.
3. #7449: persistent polling, owner handoff, controls, counters and CLI wiring.

The collector and conditional transport are supporting APIs. The monitor command
is not available until #7449 lands. #7354 stays open until all parts are complete.

## Collector contract

`scripts.pr_evidence.collect(repo, number, cwd)` collects a JSON-serializable
snapshot using the managed `gha` identity selected by the caller's repository.
It retains complete paginated review objects, issue comments, inline comments,
PR reactions, timeline, checks and commit statuses, plus CI configuration and
connector identity. Explicit request-comment IDs also collect their reactions.
Every API call is read-only and bounded; collection errors remain visible.

The snapshot retains full PR head and base information before and after
collection. A change makes the snapshot inconsistent. A successful collection
is evidence availability, **not a clean review or permission to merge**. GitHub
does not provide an atomic transaction across these endpoints. Matching start
and end heads cannot by themselves establish an unchanged review cycle.

Consumers must preserve source errors, raw evidence IDs, URLs and timestamps.
They must not interpret a missing or inaccessible source as an empty result,
drop older findings before understanding their clearance, or treat a reaction's
display login as authenticated identity. No local publication marker is read.

## Owner and gate boundary

The monitor will deliver evidence to the actively waiting owner. The owner must
read `pt info get pr_merge_policy`, classify the GitHub result and record the
supporting evidence against the exact head. Arbitrary review prose is not a
machine-readable approval protocol. A completion candidate, recorded local
assessment or resolved thread cannot manufacture external reviewer clearance.

Reaction-only clearance still needs the policy's pre-request baseline, request
object, authenticated fresh reaction, unchanged-head history and absence of
contradictory findings. The collector cannot reconstruct observations that were
never made. CI also requires the repository's workflow and approval rules;
an empty check list does not mean CI is unconfigured.

No collector operation requests reviews, changes draft state, posts messages or
merges. The owning agent performs authorized actions through the existing PR
workflow, including the final head comparison and regular merge commit.

## Conditional transport

`scripts.pr_conditional.ConditionalGhaTransport` can be passed as `transport` to
`collect`. Reset its `deadline` to a bounded `time.monotonic()` deadline before
each collection. Its process-local cache revalidates every page independently;
a 304 response reuses that page's body and pagination links, then still checks
the next page. A changed 200 response replaces both body and links. Errors never
substitute cached success; absent validators require ordinary GETs.

This avoids relying on PR update timestamps or reaction counts, which cannot
establish that every old comment and reaction is unchanged. Authenticated 304s
[do not consume primary quota](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).
Secondary limits still apply. Pagination is restricted to the same GitHub API
resource, and all commands use the caller's managed `gha` identity.

## Validation

Run `uv run pytest tests/test_pr_evidence.py -q`. Synthetic transport fixtures
exercise pagination, unavailable or malformed responses, head changes and
identity verification without touching GitHub or the Kanban database. A live
read-only smoke check establishes transport compatibility; it cannot prove that
every review format has been interpreted correctly, because interpretation is
deliberately the owner's responsibility.

Initial smoke evidence on merged PR #195: complete collection in 3.7 seconds;
24 reviews, 31 inline comments, one PR reaction and two head checks. The
reaction actor arrived as `User` and matched the separately resolved connector
Bot account. This validates the observed API shape, not approval for another PR.
