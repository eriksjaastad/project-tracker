# Model-seat fixtures

Project Tracker has one active, repository-owned model seat. When a calendar
event with a prompt fires, `scripts/hooks/calendar_poller.py` assembles the
event context and invokes the model configured by `PT_AGENT_MODEL` through
`ollama run`. The repository default is `qwen2.5-coder:7b`.

The fixtures exercise the prompt with operational pressure already documented
in tracked project files: board review, architecture review, service health,
backup safety, replication readiness, and destructive-operation cautions.
Each row records its source file and an exact source excerpt. The expected
output is a compact review rubric for free text: facts the response must cover
and claims it must not make. Labels are deliberately reviewable in git; sealed
runs are process-isolated by the deterministic split and
`MODEL_BENCH_UNSEAL=1` gate.

The calendar model receives text only. It has no tools, database connection,
or shell access, so a response must describe analysis or proposed actions and
must not claim that it executed them. The poller retains at most 2,000 output
characters.

Excluded from seats:

- `scripts/card_factory_grok.py`: standalone Stage-2/shadow agentic-coding experiment, not an operational project chair
- `scripts/doc_audit_v2.py`: dormant legacy automation; its launchd job is not installed and its historical dependency is absent
- `scripts/card-factory.sh` and `scripts/portfolio-architecture-review.sh`: real workflows whose model definitions and pins are owned outside this repository
- provider catalogs, cost/shadow-pricing records, comments, examples, and tests: metadata rather than model invocation jobs

No production pin or runtime file changes are part of this card.
