#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.40", "api-trust-tracker"]
#
# [tool.uv.sources]
# api-trust-tracker = { path = "../../synth-insight-labs/api-cost-tracker/client" }
# ///
#
# NOTE: the api-trust-tracker source path assumes the standard laptop layout
# (sibling repos under ~/projects). If this script is ever run on the Mac Mini
# for Auxesis, that path must be adjusted to the Mini's checkout layout.
"""
card_factory_grok.py — Card Factory driven by xAI grok-build-0.1.

A standalone agentic-coding test (Stage 2, local) for grok-build-0.1: it runs
the SAME Card Factory job as the Sonnet `card-factory` agent, but through
grok-build's native OpenAI-compatible tool-calling loop instead of the
`claude` CLI. The point is to judge grok's tool-use reliability, multi-turn
behaviour, and per-call latency on a real, low-stakes local task before
wiring it into Auxesis on the Mac Mini.

Shadow mode by default: it does NOT touch the board. It prints the cards it
WOULD create and writes them to a markdown file for side-by-side comparison
against the Sonnet card-factory. Pass --commit to actually create cards; those
are tagged `[Card Factory][grok]` so they are filterable and reversible.

Run (XAI_API_KEY comes from Doppler — never hardcode):
    doppler run -p synth-insight-labs -c prd -- \
        uv run scripts/card_factory_grok.py --project <name>
    doppler run -p synth-insight-labs -c prd -- \
        uv run scripts/card_factory_grok.py --project <name> --commit
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from api_trust_tracker import track  # cost-tracking wrapper (governance-required)

# ── Paths (derived, never hardcoded — governance M1) ──────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_TRACKER = SCRIPT_DIR.parent
PROJECTS_ROOT = PROJECT_TRACKER.parent
PT = PROJECT_TRACKER / "pt"
SCAN_SCRIPT = SCRIPT_DIR / "card-factory-scan.py"
LOG_DIR = PROJECT_TRACKER / "logs"

# ── Model config ──────────────────────────────────────────────────────────────
MODEL = "grok-build-0.1"
BASE_URL = "https://api.x.ai/v1"
MAX_ITERS = 20          # cost-doctrine call cap
MAX_FILE_BYTES = 40_000  # cap a single read so one file can't blow the context
PRICE_IN_PER_1M = 1.00
PRICE_OUT_PER_1M = 2.00

# Mirror the agent def's skip list so grok scans the same surface.
SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".next", "dist",
    "build", ".mypy_cache", ".pytest_cache", ".ruff_cache", "logs", "data",
    ".claude", "checkouts", "third_party",
}

SYSTEM_PROMPT = """\
You are the Card Factory running on grok-build-0.1. You scan ONE project's \
committed source code and produce Kanban cards describing real, verifiable \
work for a floor manager. You are a scanner, not a planner: find work, do not \
design solutions, do not modify any code.

Work in this order, using the provided tools:
1. `existing_cards` — read what is already on the board. NEVER propose anything \
   an existing card already covers, even partially.
2. `read_file` on the project's CLAUDE.md — understand what the project is and \
   its rules. (If it has none, do Tier 1 only.)
3. `git_log` — see recent activity; do not propose work that is actively in \
   progress.
4. `run_tier1_scan` — deterministic housekeeping findings (unused imports, \
   orphan files, dead deps, etc.). For each finding worth a card, call \
   `propose_card` with tier=1, priority="Low".
5. Your own Tier 2 analysis — read a few key source files and reason about \
   optimization / refactor / error-handling opportunities. Each Tier 2 card \
   MUST include concrete rationale (what, where, why). Call `propose_card` with \
   tier=2, priority="Medium".

Quality rules:
- Tier 1: 5 cards MAX. Tier 2: 3-5 cards MAX. Be selective.
- Be specific: name files and line numbers. "Fix unused imports" is bad; \
  "Remove 3 unused imports in src/utils.py: os, json, datetime" is good.
- Only propose things that are OBJECTIVELY verifiable or carry clear rationale. \
  If unsure, skip it.
- Do NOT propose style preferences, file-size/disk observations, or work on \
  uncommitted code.

When you have proposed every card you intend to, reply with a one-paragraph \
summary and STOP calling tools. Do not ask questions; you run unattended.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "existing_cards",
            "description": "List existing Kanban cards for the project so you avoid duplicates.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Return the last 20 commit subject lines for the project.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tier1_scan",
            "description": "Run the deterministic Tier 1 housekeeping scanner and return its JSON findings.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at a path relative to the project root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to project root. Use '.' for the root."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file relative to the project root (truncated if large).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to project root."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_card",
            "description": "Record a card you want created. In shadow mode it is logged, not created.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tier": {"type": "integer", "enum": [1, 2], "description": "1=housekeeping, 2=optimization"},
                    "title": {"type": "string", "description": "Specific, verifiable card title (no prefix; it is added for you)."},
                    "rationale": {"type": "string", "description": "What/where/why. Required for Tier 2."},
                    "priority": {"type": "string", "enum": ["Low", "Medium"]},
                },
                "required": ["tier", "title", "priority"],
            },
        },
    },
]


def _safe_path(project_root: Path, rel: str) -> Path:
    """Resolve a model-supplied relative path, refusing escapes outside the project."""
    candidate = (project_root / rel).resolve()
    if candidate != project_root and project_root not in candidate.parents:
        raise ValueError(f"path escapes project root: {rel}")
    return candidate


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> str:
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return out.strip()


def make_tool_handlers(project: str, project_root: Path):
    """Build the dispatch table; propose_card writes into `proposals`."""
    proposals: list[dict] = []

    def existing_cards() -> str:
        return _run([str(PT), "tasks", "-p", project]) or "(no cards)"

    def git_log() -> str:
        return _run(["git", "-C", str(project_root), "log", "--oneline", "-20"]) or "(no history)"

    def run_tier1_scan() -> str:
        out = _run(["uv", "run", str(SCAN_SCRIPT), str(project_root), "--json"])
        return out or "{}"

    def list_dir(path: str) -> str:
        target = _safe_path(project_root, path)
        if not target.is_dir():
            return f"(not a directory: {path})"
        entries = []
        for child in sorted(target.iterdir()):
            if child.name in SKIP_DIRS:
                continue
            entries.append(child.name + ("/" if child.is_dir() else ""))
        return "\n".join(entries) or "(empty)"

    def read_file(path: str) -> str:
        target = _safe_path(project_root, path)
        if not target.is_file():
            return f"(not a file: {path})"
        data = target.read_bytes()[:MAX_FILE_BYTES]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return f"(not UTF-8 text: {path})"
        if target.stat().st_size > MAX_FILE_BYTES:
            text += f"\n... [truncated at {MAX_FILE_BYTES} bytes]"
        return text

    def propose_card(tier: int, title: str, priority: str, rationale: str = "") -> str:
        proposals.append(
            {"tier": tier, "title": title, "priority": priority, "rationale": rationale}
        )
        return f"recorded Tier {tier} card ({len(proposals)} so far)"

    handlers = {
        "existing_cards": existing_cards,
        "git_log": git_log,
        "run_tier1_scan": run_tier1_scan,
        "list_dir": list_dir,
        "read_file": read_file,
        "propose_card": propose_card,
    }
    return handlers, proposals


def run(project: str, commit: bool) -> int:
    project_root = (PROJECTS_ROOT / project).resolve()
    if not (project_root / ".git").is_dir():
        print(f"ERROR: {project} is not a git project under {PROJECTS_ROOT}", file=sys.stderr)
        return 1

    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        print("ERROR: XAI_API_KEY not set (run via `doppler run -p synth-insight-labs -c prd -- ...`)", file=sys.stderr)
        return 1

    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    handlers, proposals = make_tool_handlers(project, project_root)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Scan the project '{project}' at {project_root}. Follow the 5-step protocol and propose cards."},
    ]

    tok_in = tok_out = tool_calls = 0
    t0 = time.perf_counter()
    final_text = ""

    for iteration in range(1, MAX_ITERS + 1):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
        )
        track(resp, "xai", project="project-tracker", caller="card-factory-grok")
        if resp.usage:
            tok_in += resp.usage.prompt_tokens
            tok_out += resp.usage.completion_tokens

        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            final_text = msg.content or ""
            print(f"[iter {iteration}] grok finished (no more tool calls).")
            break

        for tc in msg.tool_calls:
            tool_calls += 1
            name = tc.function.name
            try:
                kwargs = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                print(
                    f"[iter {iteration}] WARNING: malformed JSON args for "
                    f"{name!r}: {tc.function.arguments!r}",
                    file=sys.stderr,
                )
                kwargs = {}
            handler = handlers.get(name)
            if handler is None:
                result = f"(unknown tool: {name})"
            else:
                try:
                    result = handler(**kwargs)
                except Exception as exc:  # surface tool errors back to the model
                    result = f"ERROR: {exc}"
            print(f"[iter {iteration}] tool: {name}({kwargs}) -> {str(result)[:80].replace(chr(10), ' ')}")
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": str(result)}
            )
    else:
        print(f"WARNING: hit MAX_ITERS={MAX_ITERS} cap before grok finished.", file=sys.stderr)

    wall = time.perf_counter() - t0
    cost = tok_in / 1e6 * PRICE_IN_PER_1M + tok_out / 1e6 * PRICE_OUT_PER_1M

    # ── Output ────────────────────────────────────────────────────────────────
    print("\n=== card-factory-grok proposals ===")
    for p in proposals:
        print(f"  [Tier {p['tier']}/{p['priority']}] {p['title']}")
        if p["rationale"]:
            print(f"      ↳ {p['rationale']}")
    print(
        f"\nmodel={MODEL}  proposals={len(proposals)}  tool_calls={tool_calls}  "
        f"tokens={tok_in}+{tok_out}  est_cost=${cost:.4f}  wall={wall:.1f}s"
    )
    if final_text:
        print(f"\nsummary: {final_text}")

    LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    report = LOG_DIR / f"card-factory-grok-{project}-{stamp}.md"
    lines = [
        f"# card-factory-grok — {project}",
        f"\n*{stamp} UTC · model={MODEL} · {len(proposals)} cards · "
        f"{tool_calls} tool calls · {tok_in}+{tok_out} tok · ${cost:.4f} · {wall:.1f}s*\n",
    ]
    for p in proposals:
        lines.append(f"- **[Tier {p['tier']}/{p['priority']}]** {p['title']}")
        if p["rationale"]:
            lines.append(f"  - {p['rationale']}")
    if final_text:
        lines.append(f"\n## grok summary\n\n{final_text}")
    report.write_text("\n".join(lines) + "\n")
    print(f"\nreport: {report}")

    # ── Commit mode ─────────────────────────────────────────────────────────
    if commit:
        print("\n=== creating cards (--commit) ===")
        created = failed = 0
        for p in proposals:
            title = f"[Card Factory][grok] {p['title']}"
            out = _run([str(PT), "tasks", "create", title, "-p", project, "--priority", p["priority"]])
            last = out.splitlines()[-1] if out else ""
            if "Created task" in out:
                created += 1
            else:
                failed += 1
                last = f"FAILED: {last or '(no output)'}"
            print(f"  {last}")
        print(f"\ncreated={created} failed={failed}")
        if failed:
            print("WARNING: some cards were not created — see output above.", file=sys.stderr)
            return 1
    else:
        print("\n(shadow mode — no cards created; pass --commit to create them)")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Card Factory via grok-build-0.1 (native tool-calling).")
    ap.add_argument("--project", required=True, help="Project name under ~/projects (must be a git repo).")
    ap.add_argument("--commit", action="store_true", help="Actually create cards (tagged [grok]). Default: shadow/dry-run.")
    args = ap.parse_args()
    return run(args.project, args.commit)


if __name__ == "__main__":
    sys.exit(main())
