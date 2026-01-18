# Code Quality Standards

> **Purpose:** Establish hard rules for code quality across all projects  
> **Last Updated:** January 7, 2026  
> **Status:** MANDATORY - These are not suggestions

---

## 🚨 Critical Rule #0: EVERY PROJECT MUST HAVE AN INDEX FILE

### The Rule

**EVERY project MUST have a `00_Index_[ProjectName].md` file in its root directory.**

### Why This Exists

**Projects without indexes are invisible and forgotten.** We've had:
- Projects started and abandoned without documentation
- Forgotten what a project does 3 months later
- Duplicate work because we didn't know a project existed
- No way to search or organize 36+ projects
- Lost context on tech decisions and architecture

---

## 🚨 Critical Rule #1: NO SILENT FAILURES (Error Laundering Ban)

### The Rule

**NEVER use `except: pass` or `except Exception: pass` without logging.**

### Why This Exists (The Scar)
**Silent failures are UNTRUSTWORTHY failures.** We've had multiple projects where:
- Parsing silently failed → wrong data in database → bad decisions
- File operations silently failed → data loss not discovered until weeks later  
- API calls silently failed → features appeared to work but didn't
- Integration issues silently failed → wasted hours debugging "phantom" problems

### The "Error Laundering" Ban
Any code that catches an exception and continues without either (a) fixing the issue, (b) logging the error with context, or (c) raising a more specific exception is considered **Toxic**.

---

## 🚨 Critical Rule #2: INDUSTRIAL SUBPROCESS INTEGRITY

### The Rule
All `subprocess.run()` calls must include `check=True` and a reasonable `timeout`.

### Why This Exists (The "Hanging" Scar)
We have had scripts hang indefinitely in CI or background loops because a subprocess (like `yt-dlp` or `ollama`) became unresponsive. Unbounded subprocesses are resource leaks.

---

## 🚨 Critical Rule #3: MEMORY & SCALING GUARDS

### The Rule
Any script that aggregates or processes unbounded data (e.g., `synthesis.py` loading a whole library) MUST implement size guards or a Map-Reduce strategy to prevent Out-Of-Memory (OOM) crashes and LLM context overflows.

### Why This Exists (The "Context Ceiling" Scar)
As the `analyze-youtube-videos` library grew, simple string concatenation caused the script to crash once it exceeded 128k tokens. 

### What to Do
#### ❌ BAD: Unbounded Accumulation
```python
aggregated_text = ""
for file in library.glob("*.md"):
    aggregated_text += file.read_text() # ❌ Scaling failure at 100+ files
```

#### ✅ GOOD: Size-Aware Batching
```python
MAX_TOKENS = 100000
current_tokens = 0
for file in library.glob("*.md"):
    content = file.read_text()
    if current_tokens + len(content)//4 > MAX_TOKENS:
        # Trigger Map-Reduce or truncate
        break
    aggregated_text += content
```

---

## 🚨 Critical Rule #4: INPUT SANITIZATION & PATH SAFETY

### The Rule
**ALL user-provided strings used in file paths (titles, slugs, categories) MUST be sanitized using a `safe_slug()` function to prevent Path Traversal and shell injection.**

### Prompt Reference Safety
When crafting prompts or reference code snippets for models, **absolute paths must never be included** in examples or instructions. Local models will literally copy absolute paths from prompts into generated code, which violates portability.

**Prohibited Practice:**
```python
# ❌ NEVER do this in a prompt
TELEMETRY_PATH = "$PROJECTS_ROOT/..."
```

**Recommended Practice:**
```python
# ✅ ALWAYS do this in a prompt
TELEMETRY_PATH = Path(os.getenv("TELEMETRY_PATH", "default/path"))
```

### Why This Exists (The "Clobber" Scar)
In the `bridge.py` review of Jan 2026, it was discovered that an attacker could provide a skill name like `../../Documents/Secrets` which would cause the script to write files outside the project root. Additionally, session logs showed models copying the Floor Manager's absolute paths literally into new code files.

### What to Do
#### ❌ BAD: Direct Slug Construction
```python
slug = title.lower().replace(" ", "-") # ❌ Malicious '../' strings will bypass this
target_path = GLOBAL_LIBRARY_PATH / slug
```

#### ✅ GOOD: Sanitized Path Safety
```python
import re
import unicodedata

def safe_slug(text: str) -> str:
    """Sanitize string for safe file path usage."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[-\s]+', '-', text)

# Usage:
slug = safe_slug(title)
target_path = (GLOBAL_LIBRARY_PATH / slug).resolve()
if not target_path.is_relative_to(GLOBAL_LIBRARY_PATH.resolve()):
    raise ValueError("Security Alert: Path Traversal detected.")
```

---

## 🚨 Critical Rule #5: PORTABLE CONFIGURATION (.env.example)

### The Rule
Every project MUST include a `.env.example` file. This file must be the "Documentation by Example" for the project.

### Why This Exists (The "Machine-Lock" Scar)
If a project is cloned from GitHub without a `.env.example`, the developer has to guess which environment variables are needed. If the project uses absolute paths for things like `SKILLS_LIBRARY_PATH`, the project is "locked" to a specific machine.

### What to Do
1. Create a `.env.example` with relative path defaults (e.g., `SKILLS_LIBRARY_PATH=$PROJECTS_ROOT/agent-skills-library`).
2. Include a `check_environment()` function in your `config.py` that verifies the presence of required variables and provides a "Human-Actionable" error message if they are missing.

---

## 🔍 Rule #6: Use Python logging Module

### The Rule
**Use Python's `logging` module, not print() for debugging or errors.**

---

## 📝 Rule #7: Type Hints for Public Functions

### The Rule
**All public functions must have type hints for parameters and return values.**

---

## ✅ Code Quality Checklist
*(Standard checks for every commit)*

- [ ] No silent `except: pass`
- [ ] Subprocess `check=True` and `timeout` present
- [ ] Memory/Scaling guards for large reads
- [ ] Input sanitization with `safe_slug()`
- [ ] `.env.example` relative paths verified
- [ ] Public functions typed

---

## 📚 Industry Alignment

These standards align with production AI safety patterns used by Google DeepMind, Anthropic, OpenAI, and Microsoft. For detailed patterns on:
- Input validation and guardrails
- Defense-in-depth architectures
- Tool execution safety
- Observability and tracing

See: [trustworthy_ai_report.md](../../project-scaffolding/Documents/reports/trustworthy_ai_report.md)

**Key takeaway:** Our "scar tissue" approach (building protections after learning what breaks) is a lightweight version of industry red teaming and incident response patterns.

---

**Version:** 1.2.3
**Established:** January 7, 2026
**Trigger:** Scaffolding v2 review found pervasive portability and safety violations. Refined Jan 11 to include Prompt Reference Safety.

## Related Documentation

- [[CODE_QUALITY_STANDARDS]] - code standards
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[LOCAL_MODEL_LEARNINGS]] - local AI
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
- [[trustworthy_ai_report]] - AI safety
- [[architecture_patterns]] - architecture
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering
- [[case_studies]] - examples
- [[security_patterns]] - security
- [[video_analysis_tools]] - video analysis
- [[agent-skills-library/README]] - Agent Skills
- [[analyze-youtube-videos/README]] - YouTube Analyzer
- [[project-scaffolding/README]] - Project Scaffolding
