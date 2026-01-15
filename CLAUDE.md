# CLAUDE.md - AI Collaboration Instructions

## 🛑 IMPORTANT: READ AGENTS.md FIRST
`AGENTS.md` is the universal source of truth for this project. Always consult it for project-specific rules, tech stack, and execution commands.

## 📚 Required Reading
1. **[[AGENTS.md]]** - Source of Truth for AI Agents (Read this first!)
2. **[[README.md]]** - Project overview and quick start
3. **[[TODO.md]]** - Project status and completed tasks
4. **[[00_Index_project-tracker]]** - Project index and metadata

## 📋 Project Summary
**What this project does:**
Centralized dashboard and CLI tool for tracking the status, health, and resource usage of all projects in the workspace. It auto-discovers projects and enforces documentation standards.

**Current status:**
Complete (MVP + Phase 4 enhancements). 

**Key constraints:**
- 100% Local (no cloud dependencies).
- $0 Monthly Cost.
- Mandatory `00_Index_*.md` files.

## 🛠 Coding Standards
- **Language:** Python 3.11+
- **Type Hints:** Mandatory for all public functions.
- **Error Handling:** No silent failures. Always log exceptions with context.
- **SQL Safety:** Use parameterized queries for all SQLite operations.
- **Logging:** Use the `logger.py` module for all logging.

## 🚀 Key Commands
- **Install Hooks:** `ln -sf ../../scripts/git-pre-commit.sh .git/hooks/pre-commit`
- **Launch Dashboard:** `./pt launch`
- **Full Project Scan:** `./pt scan`
- **List Projects:** `./pt list`
- **Run Tests:** `pytest tests/`

---

## Code Review and Validation

### When to Request a Code Review

Request architectural review, security audit, or performance analysis when:
- Making significant architectural decisions
- Implementing security-critical code paths
- Before merging major features
- When unsure about design approach

### How to Request a Review

**Step 1: Create review request**
```bash
# Use the template
cp "./Documents/templates/CODE_REVIEW.md.template" ./CODE_REVIEW_REQUEST.md

# Edit CODE_REVIEW_REQUEST.md:
# - Fill out "Definition of Done" section
# - Describe what you want reviewed
# - Specify review focus (architecture/security/performance)
```

**Step 2: Run multi-AI review**
```bash
# cd "."
source venv/bin/activate
# ...
```

**Step 3: Review results**
- Reviews saved to: `./review_outputs/round_1/CODE_REVIEW_*.md`
- Copy relevant reviews to: `Documents/archives/reviews/`

### How to Validate Your Work

Run validation to check for common issues:

```bash
# Quick safety check (< 1 second)
python "./scripts/warden_audit.py" --root . --fast

# Full project validation
python "./scripts/validate_project.py" project-tracker
```

**What validation catches:**
- ✅ Hardcoded absolute paths (`[USER_HOME]/...`, `/home/...`)
- ✅ Exposed secrets (API keys like `sk-...`, `AIza...`)
- ✅ Missing required files (00_Index_*.md, AGENTS.md, etc.)
- ✅ Invalid project structure

**Best practice:** Validate before major commits or before requesting code reviews.

### Learn More

- **Full Protocol:** `./Documents/REVIEWS_AND_GOVERNANCE_PROTOCOL.md`
- **Pattern Docs:** `./Documents/patterns/code-review-standard.md`
- **Review Prompts:** `./prompts/active/document_review/`

---
*This file follows the [[00_Index_project-scaffolding]] collaboration pattern.*


<!-- project-scaffolding template appended -->

# CLAUDE.md - AI Collaboration Instructions

> **Purpose:** Project-specific instructions for AI assistants (Claude, ChatGPT, etc.)  
> **Audience:** AI collaborators and human developers

---

## 📚 Required Reading Before Writing Code

**You MUST read these files:**

1. **README.md** - Project overview and quick start
2. **This file (CLAUDE.md)** - Coding standards and safety rules
3. **Documents/ARCHITECTURE_OVERVIEW.md** - System design (if exists)
4. **.cursorrules** - Project-specific Cursor rules (if exists)

---

## Project Summary

**What this project does:**
[Brief 2-3 sentence description of the project's purpose]

**Current status:**
[Layer/phase complete, what's working, what's next]

**Key constraints:**
[Any important limitations - budget, performance, privacy, etc.]

---

## Project Structure

```
[PROJECT_NAME]/
├── README.md                  # Project overview
├── CLAUDE.md                  # This file
├── TODO.md                    # Current work (if exists)
├── ROADMAP.md                 # Long-term vision (if exists)
│
├── [main_code_directory]/     # Primary codebase
│   ├── core/                  # Core functionality
│   ├── utils/                 # Utility functions
│   └── tools/                 # CLI tools/scripts
│
├── config/                    # Configuration files
├── data/                      # Data storage
│   └── logs/                  # Log files
│
└── Documents/                 # Documentation
    ├── ARCHITECTURE.md        # Architecture & operations
    ├── guides/                # How-to documents
    ├── reference/             # Standards & knowledge
    └── safety/                # Safety systems
```

---

## Coding Standards

### Language & Version

**[Language]:** [Version] (e.g., Python 3.11+)

### Code Style

[Specify your style preferences. For Python example:]

```python
# Modern Python 3.11+ type hints
from typing import Any

# ✅ CORRECT - Use built-in generics
data: dict[str, Any] = {}
items: list[int] = []
value: str | None = None

# ❌ WRONG - Don't use typing module classes
from typing import Dict, List, Optional  # NO!
data: Dict[str, Any] = {}
value: Optional[str] = None
```

### Required Practices

- **Type hints:** All functions must have type hints
- **Docstrings:** Public functions and classes
- **Error handling:** Explicit exception handling (no bare except)
- **Logging:** Use logging module, not print statements (except CLI tools)
- **File paths:** Use `pathlib.Path`, not `os.path`
- **Markdown links:** Use relative paths, never absolute (`../../other-project/file.md` not `[absolute_path]/.../file.md`)

### Code Organization

**Library code** (`utils/`, `core/`):
- ✅ Use logging
- ✅ Raise exceptions with context
- ✅ Comprehensive type hints
- ❌ No print statements
- ❌ No sys.exit()

**CLI tools** (`tools/`, scripts):
- ✅ Print statements OK
- ✅ sys.exit() OK
- ✅ User-facing messages
- ❌ Still need error handling

---

## Safety Rules

### 🔴 NEVER Modify These:

[List files/directories that are append-only or read-only]

**Example:**
1. **`data/[critical_data]/`** - Append-only archives, never modify existing files
2. **[Source data files]** - Read-only, never write to original data
3. **`.env` files** - Don't commit, don't log contents

### 🟡 Be Careful With These:

[List files that need special care]

**Example:**
1. **API calls** - Add retry logic, track costs
2. **Database migrations** - Test on copy first
3. **Config files** - Validate before deploying

### ✅ Safe to Modify:

[List what's freely editable]

**Example:**
1. **Code files** - All code in `[main_directory]/`
2. **Documentation** - All `Documents/**/*.md`
3. **Tests** - All test files
4. **Scripts** - Development/utility scripts

---

## Data Integrity Rules

[If your project has critical data, specify protection patterns]

**Example for append-only data:**

```python
import tempfile
import shutil
from pathlib import Path

def save_data_safely(target_path: Path, data: str) -> None:
    """
    Atomic write - won't corrupt if interrupted.
    
    Pattern: Write to temp file, validate, then atomic rename.
    """
    temp_fd, temp_path = tempfile.mkstemp(
        suffix=target_path.suffix, 
        dir=target_path.parent
    )
    try:
        with open(temp_fd, 'w') as f:
            f.write(data)
        
        # Atomic rename (POSIX guarantee)
        shutil.move(temp_path, target_path)
    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        raise
```

---

## Validation Commands

**Run these before committing:**

[Specify your validation steps]

**Example for Python:**

```bash
# Check syntax
python -m py_compile [main_directory]/**/*.py

# Type checking (if using mypy)
mypy [main_directory] --ignore-missing-imports

# Linting (if using ruff)
ruff check [main_directory]/

# Tests (if you have them)
pytest tests/
```

---

## Code Review and Validation

### When to Request a Code Review

Request architectural review, security audit, or performance analysis when:
- Making significant architectural decisions
- Implementing security-critical code paths
- Before merging major features
- When unsure about design approach

### How to Request a Review

**Step 1: Create review request**
```bash
# Use the template
cp "./templates/CODE_REVIEW.md.template" ./CODE_REVIEW_REQUEST.md

# Edit CODE_REVIEW_REQUEST.md:
# - Fill out "Definition of Done" section
# - Describe what you want reviewed
# - Specify review focus (architecture/security/performance)
```

**Step 2: Run multi-AI review**
```bash
cd "$SCAFFOLDING"
source venv/bin/activate
python scaffold_cli.py review --type document --input /path/to/your/CODE_REVIEW_REQUEST.md --round 1
```

**Step 3: Review results**
- Reviews saved to: `./review_outputs/round_1/CODE_REVIEW_*.md`
- Copy relevant reviews to: `Documents/archives/reviews/`

### How to Validate Your Work

Run validation to check for common issues:

```bash
# Quick safety check (< 1 second)
python "./scripts/warden_audit.py" --root . --fast

# Full project validation
python "./scripts/validate_project.py" "$(basename $(pwd))"
```

**What validation catches:**
- ✅ Hardcoded absolute paths (`[absolute_path]/...`, `/home/...`)
- ✅ Exposed secrets (API keys like `sk-...`, `AIza...`)
- ✅ Missing required files (00_Index_*.md, AGENTS.md, etc.)
- ✅ Invalid project structure

**Best practice:** Validate before major commits or before requesting code reviews.

### Learn More

- **Full Protocol:** `./REVIEWS_AND_GOVERNANCE_PROTOCOL.md`
- **Pattern Docs:** `./Documents/patterns/code-review-standard.md`
- **Review Prompts:** `./prompts/active/document_review/`

---

## Common Patterns

[Provide frequently-used code patterns specific to your project]

**Example patterns:**

### Loading Configuration

```python
from pathlib import Path
import json

def load_config(config_name: str) -> dict:
    """Load configuration file from config/ directory."""
    config_path = Path(__file__).parent.parent / "config" / f"{config_name}.json"
    return json.loads(config_path.read_text())
```

### Error Handling with Retry

```python
import time
from typing import TypeVar, Callable

T = TypeVar('T')

def retry_on_failure(
    func: Callable[[], T], 
    max_retries: int = 3,
    backoff: float = 2.0
) -> T:
    """Retry function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = backoff ** attempt
            print(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...")
            time.sleep(wait_time)
```

### Logging Setup

```python
import logging
from pathlib import Path

def setup_logging(log_file: str = "app.log") -> logging.Logger:
    """Configure logging to file and console."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # File handler
    log_path = Path("data/logs") / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.INFO)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger
```

---

## API Usage Guidelines

[If your project uses external APIs]

**Cost tracking example:**

```python
def call_api_with_cost_tracking(prompt: str) -> tuple[str, float]:
    """
    Call API and return (response, cost_usd).
    
    Token costs (example for gpt-4o-mini):
    - Input: $0.150 per 1M tokens
    - Output: $0.600 per 1M tokens
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    
    usage = response.usage
    cost = (usage.prompt_tokens * 0.00015 + 
            usage.completion_tokens * 0.0006) / 1000
    
    return response.choices[0].message.content, cost
```

**Daily budget:** [Specify limits]  
**Alert threshold:** [When to warn]

---

## Testing Philosophy

**What to test:**
- ✅ Data parsers (fragile, easy to break)
- ✅ Business logic (critical calculations)
- ✅ Data integrity checks
- ✅ API integrations (when feasible)

**What NOT to test:**
- ❌ One-off scripts (not reused)
- ❌ Simple CRUD operations (unless critical)
- ❌ UI tools (manual testing OK for early stages)

**Testing approach:**
- **Layer 1:** Manual testing, establish patterns
- **Layer 2+:** Automated tests for proven patterns

---

## Git Workflow

### What to Commit

- ✅ Code changes
- ✅ Documentation updates
- ✅ Configuration files (without secrets)
- ✅ New data files (if tracked)

### What NOT to Commit

- ❌ `.env` files (API keys, secrets)
- ❌ Log files (`*.log`)
- ❌ `__pycache__/`, `*.pyc`
- ❌ Virtual environments (`venv/`, `.venv/`)
- ❌ Large data files (use .gitignore or LFS)

### Commit Message Format

[Specify your preferred format]

**Example:**

```
[Component] Brief description

- Change 1
- Change 2
- Change 3

Notes: Additional context if needed
```

---

## Working with This AI

### Context Management

**If this is a long session:**
- Remind me of safety rules periodically
- Ask before modifying critical data
- Confirm destructive operations

**If you notice mistakes:**
- Tell me immediately
- I can fix them quickly
- Better to catch early than compound errors

### Communication Preferences

- **Be direct** - Tell me what you need
- **Provide examples** - Show, don't just tell
- **Ask questions** - If my solution doesn't make sense
- **Correct me** - I learn from your feedback

---

## Questions? Check These First:

1. **README.md** - Project overview
2. **Documents/ARCHITECTURE_OVERVIEW.md** - System design (if exists)
3. **ROADMAP.md** - Long-term vision (if exists)
4. **TODO.md** - Current work priorities (if exists)
5. **This file** - When in doubt about safety/standards

---

## When in Doubt:

1. **Ask before modifying critical data**
2. **Test on small subset before batch operations**
3. **Check costs before running expensive operations**
4. **Document non-obvious decisions**
5. **Update this file if patterns change**

---

*This template is based on the [project-scaffolding](https://github.com/eriksjaastad/project-scaffolding) CLAUDE.md pattern.*

**Remember:** Safety first, clarity second, cleverness last.


<!-- project-scaffolding template appended -->


## Related Documentation

- [[CODE_QUALITY_STANDARDS]] - code standards
- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[architecture_patterns]] - architecture
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering
- [[queue_processing_guide]] - queue/workflow


- [[CODE_QUALITY_STANDARDS]] - code standards
- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[ai_model_comparison]] - AI models
- [[case_studies]] - examples
- [[performance_optimization]] - performance
- [[project_planning]] - planning/roadmap
- [[sales_strategy]] - sales/business
- [[security_patterns]] - security
- [[testing_strategy]] - testing/QA


- [[CODE_QUALITY_STANDARDS]] - code standards
- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[architecture_patterns]] - architecture
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering
- [[queue_processing_guide]] - queue/workflow


- [[CODE_QUALITY_STANDARDS]] - code standards
- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[project-scaffolding/README]] - Project Scaffolding
- [[project-tracker/README]] - Project Tracker


- [[CODE_QUALITY_STANDARDS]] - code standards
- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[architecture_patterns]] - architecture
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering
- [[queue_processing_guide]] - queue/workflow


- [[CODE_QUALITY_STANDARDS]] - code standards
- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[ai_model_comparison]] - AI models
- [[case_studies]] - examples
- [[performance_optimization]] - performance
- [[project_planning]] - planning/roadmap
- [[sales_strategy]] - sales/business
- [[security_patterns]] - security
- [[testing_strategy]] - testing/QA


- [[CODE_QUALITY_STANDARDS]] - code standards
- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

- [[architecture_patterns]] - architecture
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[prompt_engineering_guide]] - prompt engineering
- [[queue_processing_guide]] - queue/workflow


- [[CODE_QUALITY_STANDARDS]] - code standards
- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure

