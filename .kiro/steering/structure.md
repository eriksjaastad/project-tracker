# Code Structure and Organization

> **Purpose:** Define how code is organized and how components interact.

---

## Directory Structure

```
project-root/
  src/
    __init__.py
    core/               # Business logic (domain layer)
      models.py         # Data models (Pydantic)
      rules.py          # Business rules and validation
      calculations.py   # Core calculations
    api/                # API layer (FastAPI)
      routes/
        expenses.py
        reports.py
      deps.py           # Dependency injection
    cli/                # CLI layer (Click/Typer)
      commands/
    db/                 # Database layer
      database.py       # DB connection and session
      queries.py        # Query builders
    utils/              # Utilities
      file_ops.py       # File operations
      logging.py        # Logging setup
  tests/
    unit/               # Unit tests (mirror src/ structure)
    integration/        # Integration tests
    fixtures/           # Test fixtures
  docs/
    core/               # Core documentation
    guides/             # How-to guides
  .kiro/                # Kiro specs and steering
  .cursorrules          # Cursor AI rules
  CLAUDE.md             # Claude Code instructions
```

---

## Layer Responsibilities

### **Core Layer** (Business Logic)
**Responsibility:** Domain logic, business rules, calculations

**Rules:**
- ✅ No dependencies on API/CLI layers
- ✅ No direct database calls (use repository pattern)
- ✅ Pure functions where possible
- ✅ All business logic here

**Example:**
```python
# src/core/calculations.py
def calculate_depreciation(
    cost: Decimal,
    method: DepreciationMethod,
    years: int
) -> Decimal:
    """Pure business logic - no side effects"""
    ...
```

---

### **API Layer**
**Responsibility:** HTTP endpoints, request/response handling

**Rules:**
- ✅ Thin layer - delegate to core
- ✅ Handle HTTP concerns only (status codes, validation)
- ✅ No business logic

**Example:**
```python
# src/api/routes/expenses.py
@router.post("/expenses/classify")
async def classify_expense(
    expense: ExpenseRequest,
    classifier: Classifier = Depends(get_classifier)
) -> ExpenseResponse:
    """API layer - orchestration only"""
    result = classifier.classify(expense)
    return ExpenseResponse(category=result.category)
```

---

### **CLI Layer**
**Responsibility:** Command-line interface, user interaction

**Rules:**
- ✅ Thin layer - delegate to core
- ✅ Handle CLI concerns only (prompts, output formatting)
- ✅ No business logic

---

### **Database Layer**
**Responsibility:** Data persistence, queries

**Rules:**
- ✅ Use repository pattern
- ✅ Hide database details from core
- ✅ Use transactions

**Example:**
```python
# src/db/repository.py
class ExpenseRepository:
    def get_by_year(self, year: int) -> list[Expense]:
        """Repository pattern - abstracts DB"""
        ...
```

---

## Component Communication

### **Data Flow**

```
CLI/API → Core (Business Logic) → Database
   ↓          ↓                        ↓
Output   Calculations              Persistence
```

### **Dependency Direction**

- CLI/API → Core (allowed)
- Core → Database (via repository, allowed)
- Core → CLI/API (❌ NOT allowed)

---

## Module Organization

### **models.py**
- Pydantic models
- Data validation
- Serialization/deserialization

### **rules.py**
- Business rules
- Classification logic
- Validation rules

### **calculations.py**
- Financial calculations
- Statistical operations
- Pure functions

---

## Naming Conventions

**Files:**
- `snake_case.py` for all Python files
- `PascalCase` for classes
- `snake_case` for functions/variables

**Classes:**
- Services: `ClassificationService`
- Models: `Expense`, `Transaction`
- Repositories: `ExpenseRepository`

**Functions:**
- Verbs for actions: `calculate_total()`, `validate_expense()`
- Boolean functions: `is_valid()`, `has_classification()`

---

## Import Organization

```python
# Standard library
import os
from pathlib import Path

# Third-party
from fastapi import FastAPI
from pydantic import BaseModel

# Local - absolute imports only
from src.core.models import Expense
from src.db.repository import ExpenseRepository
```

**Rules:**
- Use absolute imports (not relative)
- Group imports (stdlib, third-party, local)
- Sort alphabetically within groups

---

## Configuration Management

**Environment Variables:**
- Use `.env` for local config
- Never commit `.env`
- Document all env vars in `.env.example`

**Config File:**
```python
# src/config.py
from pydantic import BaseSettings

class Settings(BaseSettings):
    database_url: str
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
```

---

**Last Updated:** [Date]  
**Maintained By:** Architecture team

