# Local Model Learnings: project-tracker

> **Purpose:** Institutional memory for working with local AI models (Ollama) in project-tracker
> **Created:** January 10, 2026
> **Updated:** January 12, 2026
> **Pattern:** From project-scaffolding/Documents/reference/LOCAL_MODEL_LEARNINGS.md

---

## 🚨 CRITICAL FINDING: Workers Not Writing Files (Jan 12, 2026)

**Discovery:** Local models (Workers) were NOT directly writing code to files. They were outputting code TEXT, and the Floor Manager was writing it to files.

**What we thought was happening:**
- Worker receives prompt → Worker writes code to file → Worker verifies

**What was ACTUALLY happening:**
- Worker receives prompt → Worker outputs code text → Floor Manager writes text to file

**Why this matters:**
- Workers can't execute bash commands (`cp`, `chmod`, `ls`)
- Workers can only generate text output
- Any prompt asking Workers to "run" or "execute" will fail
- Phase 4 prompts worked because they asked for CODE OUTPUT, not command execution

**Impact:**
- All prompts asking Workers to execute commands need restructuring
- File copies should be done by Floor Manager (no intelligence needed)
- Code generation prompts should ask for OUTPUT, not execution

**Status:** UNRESOLVED - Needs architectural review after canary projects complete.

---

## Why This Document Exists

Local models are a black box. When they fail or succeed, the knowledge evaporates between sessions. This document captures:
- What works and what doesn't
- Model-specific quirks
- Prompt patterns that improve results
- Failure modes to avoid

**Goal:** Stop re-learning the same lessons. Make prompts better over time.

---

## Model Profiles

### DeepSeek-R1 (14b)

**Best for:**
- Complex reasoning tasks
- Multi-step problem solving
- Code generation (with caveats)

**Known limitations:**
- Timeout issues on long tasks (observed Jan 10, 2026). Requires 300s+ for large file writes.
- Reasoning overhead: Can spend 60-120s "thinking" before generating, consuming timeout budget.
- Connection management: Sometimes fails to close streams properly, leading to false-positive timeouts.

**Prompt tips that work:**
- Be explicit about output format
- Break complex tasks into steps
- Include examples when possible

---

### Qwen 2.5 / Qwen 3 (4b, 14b)

**Best for:**
- General-purpose tasks
- Fast code generation (significantly less reasoning overhead than R1)
- Repetitive boilerplate and integration tasks

**Known limitations:**
- Lacks the deep "safety awareness" and self-correction of DeepSeek-R1.
- May hallucinate imports or skip constraints if not explicitly repeated.

**Prompt tips that work:**
- Include CONSTRAINTS section with DO NOT rules
- Provide reference code to copy/adapt
- Keep tasks focused (single function per prompt)

---

### Llama 3.2 (3b)

**Best for:**
- Speed-critical tasks
- Simple classification
- High-volume filtering

**Known limitations:**
- Lower quality on complex tasks
- May miss nuance

**Prompt tips that work:**
- Keep prompts short and direct
- Binary yes/no questions work well

---

## Prompt Pattern Library

### Pattern: Acceptance Criteria Checklist
**What:** Structure prompts with explicit checkboxes for the model to verify against.
**Why it works:** Local models respond well to concrete, binary success criteria. Reduces ambiguity.

### Pattern: Context Bridge
**What:** Explicitly provide file contents and context rather than assuming the model can find them.
**Why it works:** Local models don't have tool access like cloud models. They need context spoon-fed.

### Pattern: Micro-Task Decomposition
**What:** Break tasks into the smallest possible atomic units (5-10 min each) rather than larger cohesive tasks (20-30 min).
**Why it works:** Reasoning models like DeepSeek-R1 spend significant time in their "thinking" phase before generating output. Smaller tasks let the model complete both reasoning AND generation within the timeout window.

### Pattern: Explicit DO NOT Constraints
**What:** Add a prominent "CONSTRAINTS" section listing what the model should NOT do.
**Why it works:** Prevents scope creep and hallucination.

### Pattern: 3-Strike Escalation Rule
**What:** A strict protocol for handling Worker timeouts or failures.

### Pattern: Incremental Diff Style
**What:** Asking models to provide only the code delta (using `Edit` or `StrReplace` parameters) rather than rewriting the entire file.

### Pattern: Raw Output Limitation
**What:** Local models (qwen3, deepseek-r1) cannot reliably output "raw code only" even when explicitly instructed.

### Pattern: Context Bridge Size Limit
**What:** Keep code examples in Context Bridge sections under 30 lines.

### Pattern: Prompt Brevity Principle
**What:** Keep worker prompts focused and minimal (100-200 lines ideal).

### Pattern: Code-First Prompting
**What:** Show the exact code to write, not just describe what to write.

### Pattern: INDEX for Multi-Prompt Work
**What:** When you have 5+ related prompts for a feature, create an INDEX document.

---

## Failure Log

| Date | Model | Task | Failure Mode | Resolution |
|------|-------|------|--------------|------------|
| Jan 10, 2026 | DeepSeek-R1 | Warden enhancement | Timeout on complex tasks | Floor Manager took over |
| Jan 10, 2026 | DeepSeek-R1/Qwen | Global Rules Injection | Multiple timeouts on integration | Floor Manager manual merge |
| Jan 10, 2026 | Qwen 3 (14b) | Pre-Commit Hook | Success | First test of Learning Loop Pattern |
| Jan 11, 2026 | qwen3:4b | Agent Dispatcher A1 | Timeout - analysis loop | Strike 1, escalated to Strike 2 |
| Jan 11, 2026 | deepseek-r1:14b | Agent Dispatcher A1 | Timeout at line 115 | Strike 2, escalated to Strike 3 (HALT). Split into A1a/A1b/A1c |
| Jan 11, 2026 | qwen3:4b, deepseek-r1:14b | Backup Audit B1a | Output corruption | Strike 3, FM Direct execution |

---

## Session Observations

### January 11, 2026 - Phase 4 Telemetry Work (project-tracker)

**Models Used:**
- [x] DeepSeek-R1
- [x] Qwen 2.5 Coder

**Observations:**
- All 9 prompts completed (Groups 1, 2, 3 all done)
- Local models executed tasks as specified in prompts
- Code structure matches what was requested

**Issues Encountered:**

#### 🚨 CRITICAL: Hardcoded Paths Copied from Prompts
- **What happened:** Local models copied the hardcoded absolute paths from the reference code snippets in the prompts
- **Files affected:** `telemetry_reader.py`, `cron_health.py`
- **Lesson:** Local models copy what they see. If reference code has bad patterns, they'll reproduce them.

#### Silent Failure in hygiene_detector.py
- **What happened:** `except Exception: return []` with no logging
- **Root cause:** Prompt didn't specify error handling requirements

#### Missing Memory Guards
- **What happened:** telemetry_reader.py reads entire file without size limits
- **Root cause:** Prompt didn't include memory guard requirement from CODE_QUALITY_STANDARDS

**What Worked:**
- Micro-task decomposition (5-min tasks) - all completed without timeout
- Acceptance criteria checklists - models followed them
- Consistent logging pattern - all files use same logger setup
- Type hints - all functions properly typed

### Jan 10, 2026 - Warden Enhancement Sprint (project-scaffolding)
- (Merged learnings integrated into Pattern Library)

---

## Learning Debt Tracker

| Learning | Documented | Compiled Into | Preventable Failures |
|----------|------------|---------------|---------------------|
| 300s timeout for file-heavy | ✅ Jan 10 | ❌ Not in templates | 2 |
| Use python3 on macOS | ✅ Jan 10 | ❌ Not in templates | 1 |
| StrReplace over full rewrites | ✅ Jan 10 | ❌ Not in templates | 1 |
| Micro-task decomposition | ✅ Jan 10 | ❌ Not in templates | 1 |
| Explicit DO NOT constraints | ✅ Jan 10 | ❌ Not in templates | 1 |
| Context Bridge <30 lines | ✅ Jan 11 | ❌ Not in templates | 2 |
| Raw output corruption | ✅ Jan 11 | ❌ Not in templates | 3 |

---

## Improvement Backlog
- [x] Test if breaking tasks into smaller chunks helps DeepSeek timeout issues → YES
- [ ] Compare same prompt across DeepSeek vs Qwen for quality
- [ ] Create prompt templates optimized for each model tier
- [ ] Implement "Downstream Harm Estimate" in prompts

---

## Related Documents
- `Documents/patterns/learning-loop-pattern.md`
- `AGENTS.md` - Caretaker Role

---

*This is a living document. Update it when you learn something new about local models.*


## Related Documentation

- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[cost_management]] - cost management
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering


- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[case_studies]] - examples
- [[orchestration_patterns]] - orchestration
- [[performance_optimization]] - performance


- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[cost_management]] - cost management
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering


- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[project-scaffolding/README]] - Project Scaffolding
- [[project-tracker/README]] - Project Tracker


- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[cost_management]] - cost management
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering


- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[case_studies]] - examples
- [[orchestration_patterns]] - orchestration
- [[performance_optimization]] - performance


- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[cost_management]] - cost management
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering


- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

