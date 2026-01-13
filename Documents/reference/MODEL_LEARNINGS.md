# Local Model Learnings: project-tracker

> **Purpose:** Institutional memory for working with local AI models in this project
> **Created:** January 11, 2026
> **Pattern:** From project-scaffolding/Documents/reference/LOCAL_MODEL_LEARNINGS.md

---

## Model Profiles

### DeepSeek-R1 (14b)
**Best for:** Complex reasoning, multi-step problem solving, code generation

**Known Limitations:**
- Timeout issues on long tasks (needs 300s+ for large file writes)
- Reasoning overhead: 60-120s "thinking" before generating
- Connection management: Sometimes fails to close streams properly

**Prompt Tips:**
- Explicit output format
- Break into small steps (5-10 min micro-tasks)
- Include examples of expected output

---

### Qwen 2.5 Coder
**Best for:** Fast code generation, boilerplate, less reasoning overhead

**Known Limitations:**
- May hallucinate imports
- Less safety-aware than DeepSeek
- Needs explicit constraints

**Prompt Tips:**
- Include CONSTRAINTS section with DO NOT rules
- Provide reference code to copy/adapt
- Keep tasks focused (single function per prompt)

---

### Llama 3.2 (3b)
**Best for:** Speed-critical, simple classification, high-volume filtering

**Known Limitations:**
- Lower quality on complex tasks
- May miss nuance

**Prompt Tips:**
- Keep prompts short and direct
- Binary yes/no questions work best

---

## Failure Log

| Date | Model | Task | What Happened | Resolution |
|------|-------|------|---------------|------------|
| | | | | |

---

## Prompt Patterns That Work

### 1. Acceptance Criteria Checklist
Local models respond well to binary success criteria. Structure as checkbox list:
```markdown
### 🎯 [ACCEPTANCE CRITERIA]
- [ ] **Functional:** Code correctly implements X
- [ ] **Syntax:** File passes linting
- [ ] **Standards:** Uses pathlib.Path
- [ ] **Verification:** Tests pass
```

### 2. Constraints Section
Prevents scope creep and hallucination:
```markdown
### CONSTRAINTS (READ FIRST)
- DO NOT implement any parsing logic yet
- DO NOT change existing imports
- FOLLOW the pattern from existing file exactly
```

### 3. Reference Code Snippet
Reduces model invention - give them code to copy:
```markdown
### Reference Code Snippet
```python
# Exact code for them to integrate
def function_name():
    pass
```
```

---

## Prompt Anti-Patterns

### ❌ Vague Instructions
- "Make it work better" → Model guesses what "better" means
- Fix: Specific criteria with binary pass/fail

### ❌ Large File Rewrites
- Asking model to rewrite entire file → Timeouts, inconsistency
- Fix: Use StrReplace/diff style, one function at a time

### ❌ Missing Context
- Not providing existing code patterns → Model invents incompatible style
- Fix: Include reference to existing file patterns

---

## Session Notes

### January 11, 2026 - Phase 4 Telemetry Work

**Models Used:**
- [x] DeepSeek-R1
- [x] Qwen 2.5 Coder
- [ ] Other: ___

**Observations:**
- All 9 prompts completed (Groups 1, 2, 3 all done)
- Local models executed tasks as specified in prompts
- Code structure matches what was requested

**Issues Encountered:**

#### 🚨 CRITICAL: Hardcoded Paths Copied from Prompts
- **What happened:** Local models copied the hardcoded absolute paths from the reference code snippets in the prompts
- **Files affected:** `telemetry_reader.py`, `cron_health.py`
- **Root cause:** The prompts I (Claude) wrote included hardcoded paths in the "Reference Code Snippet" sections
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

**Prevention for Future Prompts:**

1. **Reference code must be portable:**
```python
# GOOD - Use in prompts
TELEMETRY_PATH = Path(os.getenv("TELEMETRY_PATH", "default/path"))

# BAD - Never use in prompts
TELEMETRY_PATH = Path("$HOME/...")
```

2. **Include CODE_QUALITY_STANDARDS rules in prompts:**
   - Add constraint: "Must follow CODE_QUALITY_STANDARDS.md Rule #1 (no silent failures)"
   - Add constraint: "Must follow CODE_QUALITY_STANDARDS.md Rule #4 (no hardcoded paths)"

3. **Add explicit memory guard requirement for file processing:**
   - "Add MAX_ENTRIES constant to prevent OOM on large files"

---

*Update this document after each session with local models.*
