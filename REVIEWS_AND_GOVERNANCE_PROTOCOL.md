# Ecosystem governance and review protocol

Updated: 2026-09-23. Rehomed from project-scaffolding on 2026-09-18.

This document adds project governance and evaluation guidance. The current
review rules live in the shared `AGENTS.md` block and the
[full code review protocol](https://github.com/eriksjaastad/agent-runtime-config/blob/main/docs/code-review-protocol.md).
Publishing and merging follow the
[PR review and merge policy](https://github.com/eriksjaastad/agent-runtime-config/blob/main/docs/pr-review-policy.md),
also installed as `pt info get pr_merge_policy`. When this document and those
sources disagree about review cycles, evidence or gates, follow the shared
sources. Codex is primary; the same standards apply to Claude local reviewers.
Installing instructions is evidence of delivery, not evidence that a review
found every relevant defect.

## What to review

Start with propagation sources (`templates/`, `AGENTS.md`, `CLAUDE.md`), then
execution-critical code (`scripts/`, `scaffold/`, hooks), then reference docs.
This is an order of attention, not a claim that docs have no consequences.
Trace the change to the card, user request or PRD. Account for each requirement
as implemented, explicitly deferred or deliberately removed with a reason;
check the original contract as well as any compressed PR description. A written
exclusion cannot excuse failure of a workflow the change claims to support.

Run applicable mechanical checks, then finish the independent judgment audit
even when a scan fails. A mechanical failure prevents a local PASS; it does not
hide other findings. Check the actual entry point, affected callers and
consumers, the status protocol, and at least one representative end-to-end
value trace when a change crosses boundaries. For a found defect, inspect its
related forms before reporting so one review returns the complete supported
set. Test both the failing case and legitimate counterpart with safe synthetic
inputs. Name relevant behavior that passing tests never exercise. Separate
observations from inference and untested concerns.

Pin a local or delegated verdict to the exact reviewed commit. A local PASS is
preflight evidence only; independent local code-reviewer clearance on the unchanged
recorded head and green CI remain separate merge gates. Persist distinct review
cycles, including failed or stalled ones, across sessions and PRs for the same work
item. At the third cycle, freeze edits, pushes and further requests until its result
is known. A clean third review may merge if all gates pass. Findings on the third
require discussion with Erik before more fixes or another request. Do not reset the
count by changing agent, branch or PR. The shared PR policy defines the detailed
evidence and wait rules.

## Safety and authorization

- **Paths and writes.** Validate externally supplied paths before writing to
  global or external locations. For a bulk or hard-to-reverse operation, provide
  a preview or dry-run path when the command's contract calls for one. Use atomic
  replacement where partial output could corrupt critical state. Do not impose
  one whitelist or a mandatory `--dry-run` flag on every ordinary write.
- **Database changes.** Follow this repository's `AGENTS.md` four-line gate
  before destructive database operations. Document foreign-key and cascade
  effects before a `DELETE` lands. Use the application API and its backup path
  for authorized row deletion; do not invent cleanup. Additive migrations are
  governed by their own exception. A backup does not itself authorize deletion.
- **Auto-repair.** State which failures may be retried, how many times, and
  what a failed repair reports. Evaluate reversibility, user-facing changes,
  stateful data and the risk of masking the cause. Back up state when needed,
  preserve an audit trail, and obtain approval where the specific operation
  requires it. Avoid a blanket rule that every formatting fix or notification
  requires human approval or a particular messaging service.
- **Subprocesses.** Use a timeout and inspect completion. `check=True` is useful
  when any nonzero status is failure; explicitly handle expected nonzero results
  when they carry a valid status contract. Never turn an unexpected failure into
  silent success.
- **Silent failures.** Distinguish a genuine empty result from an inability to
  inspect. Report operation failures to the caller or log them under a documented
  best-effort contract. Do not require warnings for every valid empty scan or
  exception wrappers around every filesystem iterator.
- **Portability and secrets.** Flag machine-specific paths used by executable
  code or prescribed setup, and real credentials in files. Incident evidence,
  examples, synthetic fixtures and documented placeholders are different from
  runtime dependencies. Resolve rendered deliverables and runtime config before
  publication; source templates can retain placeholders.

## Tests and operational checks

Use assertions about behavior and relevant failure outcomes, not type/non-null
assertions alone. Isolate destructive or external calls; exercise the real
boundary where safe. A fixture needs the structure required for the behavior
under test, not an entire production tree. Mocks are useful for unavailable or
unsafe dependencies; they are not a substitute for checking a safe real entry
point. Validate generated frontmatter against the target project's taxonomy
when the change generates frontmatter. Test path traversal and unbounded scans
where user input or scale makes them relevant. Bounded or cached scans can be
appropriate; zero results are only alarming when the contract expects items.

At card pickup, estimate substantive PR size and split naturally separable
work likely to exceed roughly 800 lines. At local pre-push review, inspect the
actual diff against the base and document a coherent exception if it remains
materially above the roughly 500-line target. Generated files, lockfiles,
vendored code and mechanical snapshots do not count as substantive lines.
Keep related work together when splitting would create artificial micro-PRs.

## Evidence cues for applicable checks

The shared `AGENTS.md` rules define the checks. This table preserves the
protocol's evidence column for a local reviewer: mark a check **not applicable**
with a reason when the diff does not touch it, and **not checked** with the
coverage gap when an environment prevents it. Executed behavior and file/line
citations matter more than a pasted search result.

| ID | Check | Evidence to record when applicable |
|----|-------|------------------------------------|
| M1/M4 | Portable paths and rendered placeholders | Cite the executable/configuration use or rendered output; classify examples and source templates separately. |
| M2/E2 | Unexpected or silent failure | Trace the failing operation to caller-visible result or documented best-effort log, with file/line and an exercised case. |
| M3 | Credentials | Record a names-only or redacted scan and the changed files checked; never paste secret values. |
| M5 | Static JavaScript redeclarations | Name changed `static` JS paths and the required ESLint exit status, or state that none changed. |
| T1/T2 | Inverse tests and meaningful assertions | Name a failing case, a legitimate counterpart, the passing tests' dark territory, and the behavioral assertions examined. |
| E1 | Status contract | Show the actual caller protocol and observed return/JSON decision for a failure path. |
| H1 | Subprocess integrity | Cite timeout and expected/nonexpected return-code handling; exercise a bounded failure path where safe. |
| H5–H7 | Deletion and cleanup | List affected foreign keys/cascades, the user requirement authorizing cleanup, and the backup/approval evidence required for the operation. |
| H10 | Boundary trace | Follow one representative input through parser/context, storage or subprocess, and public output; include a safe counterpart. |
| A1–A4 | Auto-repair | Record the requested repair tier, retry cap, observable failure, and backup/notification or approval evidence where its effect requires them. |
| T5 | Requirement traceability | List each original requirement as implemented, deferred or descoped with its reason and test/evidence reference. |
| R1 | Review result | Record exact commit SHA, complete findings or clean result, coverage gaps, and the native GitHub or local report location. |

## Measure review coverage before broad rollout

Use a bounded historical pilot before claiming that revised instructions
improve first-review coverage:

1. Freeze the contract, base/head SHAs, diff, affected entry point and known
   environment limits. Keep later reviews and held-out findings away from the
   independent reviewer.
2. Have the reviewer submit one complete report before revealing historical
   findings. Preserve its exact text and commit-pinned verdict. A list of
   checklist words or a PASS without behavioral probes is not coverage.
3. Compare *finding families* against historically supported, in-scope cases.
   Record supported new findings, false positives, untested areas and cases that
   need an unavailable environment. Replay against the base and prior reviewed
   head before calling a defect inherited or fix-induced.
4. Record change size and semantic breadth alongside recall. A review can miss
   a defect because the supported behavior became too broad for a bounded model;
   better instruction delivery alone cannot settle that design question.
5. Keep the denominator honest: retrospectively found defects are a lower
   bound on defects present, not proof of complete recall. A single case pilot
   cannot establish a portfolio-wide rate. Expand only after reviewing misses
   and false blocks, then use a fresh held-out case for a further claim.

The bounded pilot and its limitations are recorded in
[the September 23 review pilot](docs/REVIEW_COVERAGE_PILOT_2026-09-23.md).
