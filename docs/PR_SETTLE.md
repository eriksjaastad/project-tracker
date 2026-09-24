# PR settle monitor

After opening a ready PR or updating its head, start the foreground monitor and
keep the owning agent attached until the work settles. This is the normal PR
follow-through for project-tracker; other floor managers can use the same `pt`
command from their repository. Read `pt info get pr_merge_policy` first; the
[shared policy](https://github.com/eriksjaastad/agent-runtime-config/blob/main/docs/pr-review-policy.md)
still controls review requests, evidence, CI and merging.

## Start and respond

Example for project-tracker PR #197 (substitute your repository, PR and unique
agent/session ID):

```bash
pt pr settle 197 --repo eriksjaastad/project-tracker --owner session-7354
```

The default interval is 60 seconds, with a three-hour total deadline. Keep the
foreground process attached to the agent's tool session and consume its output;
do not launch it with `&`, discard stdout or end the owning agent's turn while
waiting. A flushed JSON event reaches the attached consumer. It does **not** wake
an idle agent. No existing runtime API here guarantees that wake operation.

Each event names its owner, repository, PR, full head, snapshot digest, counters,
sequence number and next action. Unchanged pending evidence is quiet. New review,
reaction, finding, CI or head evidence prompts the owner to read the saved snapshot:

```bash
pt pr status 197 --repo eriksjaastad/project-tracker --owner session-7354
```

Apply the shared policy to **all** external evidence. Record the current full
`head` and `snapshot_id`, the review result (`clean`, `findings`, `pending`,
`ambiguous`), CI result (`satisfied`, `not_configured`, `pending`, `failed`,
`unknown`), supporting GitHub URLs and your reasoning using `pt pr assess --help`.
The command requires `--head`, `--snapshot`, `--review`, `--ci`, repeatable
`--evidence`, and `--summary`, as well as the target arguments above. For
unconfigured CI, the summary must identify workflow/requirements evidence and
local checks. An empty check list is insufficient.

An assessment records the owner's interpretation of GitHub evidence; it is not a
local reviewer PASS. The command validates attribution to the saved snapshot,
not the meaning of arbitrary review prose or whether a supplied URL proves the
claim. The owner must establish those facts. Missing collection sources prevent
a clean assessment. New evidence on the same head also invalidates an assessment.

`recheck_and_merge` means the monitoring handoff is settled. The PR may still be
open. Re-read current GitHub head, findings, CI, holds and approval requirements,
then use the policy's normal merge commit pinned to the reviewed full SHA. The
monitor never merges, requests reviews or changes draft state.

## Execution history and review requests

The review policy counts **independent local review cycles** (distinct code-reviewer
subagent runs on exact committed HEAD), including the initial review. It does not
count findings, commits or the number of review/comment/reaction objects. The owner
must reconcile the complete history before requesting another review or recording
clean clearance. For a newly ready PR, include its initial execution; for inherited
work, carry its existing history forward. Never reset the count by changing agents,
branches or PRs.

Use `pt pr history` with the target arguments, `--ledger` pointing to a JSON array,
`--snapshot` set to the digest you inspected, repeatable `--evidence` GitHub URLs
and `--summary` explaining the reconciliation. A changed snapshot requires reading
the new evidence before reconciling again.
Each execution record has a stable `id`, full `head`, `status` (`requested`,
`acknowledged`, `completed`, `rejected`, `unknown`), numeric Unix `at`, GitHub
`evidence` URLs and a `summary`. An acknowledged record also requires its
observed Unix `acknowledged_at`; retain that timestamp in later updates. Keep
the generated `reserved-N` ID when updating a reserved request. Group objects
from the same execution using their request/acknowledgment evidence. A confirmed rejection is not an execution;
uncertainty must be recorded as unknown and escalated, not omitted. Existing
execution IDs cannot disappear from subsequent ledgers. The CLI records the
owner's evidence assessment; it cannot infer execution boundaries from prose.

For an existing PR needing a review, record a fresh **pre-request** PR-body
baseline with `pt pr request`, `--head` and `--kind initial` (or `thorough` after
completed feedback). This reserves an execution before the owner triggers it;
it never calls a GitHub review trigger itself. Recording after the trigger cannot
repair a missing pre-request observation. For a newly created ready PR, retain
creation time, full head and the new-object empty baseline when creating it.
Those observations remain necessary for reaction-only clearance.

Only a successful `request` command with a `request_baseline` event reserves a
review. An inactive run, expired budget or concurrent evidence update can reject
the command; do not trigger GitHub after a failure. Inspect the saved state and
reconcile fresh evidence before trying again within the existing limits.
`assess` also fails when no assessment was recorded. Successful clean assessments
can end the run, and a recorded third-finding assessment can escalate it.

The request record retains its snapshot, time and existing reaction IDs. For a
comment-based request, add `--request-comment-id 123456` to `pt pr settle`; repeat
the option for more comments. The IDs persist across restarts and are included
in every poll and `pt pr request` baseline collection. To add IDs while running,
use `--hold`, wait for the foreground process to exit, then `--resume` with the
new IDs. Existing IDs and budgets are preserved; do not combine IDs with
`--hold` or `--stop`.

Configuring an ID enables observation; it does not manufacture a pre-request
baseline after posting. When a newly created comment itself requests review,
the owner must retain its creation time, full head and empty initial reaction
baseline under the shared policy. Reactions on a comment absent from the recorded
request baseline remain raw evidence, even when posted after the reservation.
Use `pt pr history` to reconcile acknowledgment with external creation/baseline
proof; adding the ID alone cannot attribute it to an execution. A thumbs-up alone
never grants clearance; head lookups and commit/push history still need inspection.

At five silent minutes, stop and ask Erik to resolve whether an execution began.
There is no automatic silent retry. The canonical policy permits a retry only
with affirmative evidence of rejection/no execution, a known count below the
hold and no active attempt. An acknowledged but incomplete review gets fifteen
minutes before escalation. These limits never establish approval.

**A clean third review can merge; a third review with remaining findings stops.**
While the third execution runs, stop edits, commits, pushes and further review
requests. If reserving the third request, perform only that recorded trigger.
Read its completed result and reconcile the execution ledger against the current
snapshot. When the third review is clean on the unchanged current head and CI
and all other merge requirements are satisfied, record that assessment and use
the normal merge handoff. No extra human approval is required just because it
was the third review.

If the third result still has findings, is ambiguous, or requires more changes,
stop and discuss the pattern with Erik. Do not fix, push or request a fourth
review without his explicit direction. Pending review or CI is not clearance;
continue the bounded wait. An uncertain execution count stops requests. A raw
thumbs-up is an assessment candidate and still requires the full evidence checks.
This is Erik's clarification: "If you get a clean third review, then you get to
merge it." It supersedes the earlier unconditional clean-third human hold.

For `notify_erik_and_stop`, the attached owner tells Erik **once**, deduplicating
the event ID. Include repository, PR URL, head, CI, execution count/evidence,
outstanding findings and the next-step recommendation. The monitor persists and
emits this instruction; it has no direct messaging or idle-agent wake integration.
No pending tick pages Erik.

## Controls and durable delivery

Use the same target arguments with `pt pr settle --hold` or `--stop` from another
terminal. Draft state also holds the run. `--resume` resumes only a held record
within its original deadline; it does not reset budgets. Stops, completed handoffs
and escalations are terminal. After escalation, Erik directs the next work
outside that ended run; retain its ledger. Neither an automatic retry nor deleting
state releases a stop for unresolved findings.

Acknowledge handled events with `pt pr acknowledge` and `--event` (the sequence
number). Restarts replay unacknowledged IDs, so delivery is at least once; the
owner must deduplicate before external actions. A broken output pipe ends the
foreground run. The saved event remains available through `status`.

State lives under `~/.project-tracker/pr-settle/<github-owner>/<repository-name>/<PR>/state.json`.
The `--owner` agent/session ID is stored inside the record, not in its path.
`PT_PR_SETTLE_DIR` overrides the root for isolated tests. Repository names are
canonicalized. A per-PR process lease prevents duplicate monitors; a separate
short transaction lock allows concurrent control/assessment commands. Ten
repositories have ten independent records. An owner mismatch or corrupt state
is an error, never permission to reset counters. API/auth/rate failures remain
visible and stop polling; investigate before restarting. A temporarily missing
GitHub test-merge SHA remains pending collection evidence.

Collections happen outside the state lock so controls remain responsive. Before
saving a collection, both the monitor and request command check for intervening
evidence updates. A stale monitor result is discarded; a stale request fails
without replacing newer evidence or reserving an execution.

## Evidence and validation

The September 19 event watcher missed a completed review for about 48 minutes.
Polling complete evidence removes that event-delivery dependency while preserving
the requirement for an attached owner. Every API page is revalidated, including
old comment edits and individual reaction identities. Authenticated HTTP 304s
[do not consume primary quota](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api),
reducing idle cost across projects. Each process has its own cache; errors never
substitute cached success. Unsupported validators require ordinary requests.

The collector captures head/base/test-merge identity before and after collection,
retains raw evidence and authenticates the connector account. GitHub offers no
atomic transaction across endpoints: matching boundary heads alone do not prove
an unchanged review cycle. Complete collection is not approval.

Run `uv run pytest tests/test_pr_evidence.py tests/test_pr_conditional.py tests/test_pr_settle_state.py tests/test_pr_settle_cli.py -q`.
Tests cover pending-to-owner-handoff, stale attribution, same-head changes,
restart-persistent caps, ten independent records, lock contention and failures.
Live smoke on PRs #195/#197 exercised real collection and conditional responses.
The delivery test uses an attached consumer; no idle-agent wake is claimed.
