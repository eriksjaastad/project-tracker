# Technical Standards

> **Purpose:** Define technical constraints, patterns, and standards for this project.

---

## Language & Framework

**Primary Stack:**
- Language: [Python 3.11+, TypeScript, etc.]
- Framework: [FastAPI, React, etc.]
- Database: [PostgreSQL, SQLite, etc.]

**Type System:**
- Use modern typing: `dict`, `list`, `str | None` (not `Dict`, `List`, `Optional`)
- All functions must have type hints
- Use Pydantic for data validation

---

## Architecture Patterns

**Core Patterns:**
1. **Layer-by-layer development** - Build incrementally useful layers
2. **Privacy-first** - Local data storage, API-only for processing
3. **Append-only archives** - Never modify historical data
4. **Read-only source data** - Original files are immutable

**Project Structure:**
```
project/
  src/
    core/       # Business logic
    api/        # API endpoints
    cli/        # Command-line interface
    models/     # Data models
  tests/
    unit/
    integration/
  docs/
```

---

## Code Style

**Python:**
- Use `ruff` for linting
- Use `mypy` for type checking
- Line length: 100 characters
- Use descriptive variable names (no single letters except iterators)

**Error Handling:**
- Use custom exceptions for domain errors
- Never use bare `except:`
- Log errors with context

**Documentation:**
- All public functions have docstrings
- Complex logic has inline comments explaining "why", not "what"

---

## Safety Rules

**Data Integrity:**
- ✅ **NEVER modify source data in-place**
- ✅ **All operations must be reversible**
- ✅ **Use atomic writes** (write to temp, then rename)
- ✅ **Validate before persisting**

**File Operations:**
- Use `send2trash()` instead of `os.remove()`
- Create backups before destructive operations
- Log all file operations

**Database:**
- Use transactions for multi-step operations
- Validate foreign keys
- Never use raw SQL without parameterization

---

## Performance Guidelines

**Targets:**
- API response time: < 200ms (p95)
- Batch processing: < 60s for 10k records
- Memory usage: < 500MB

**Optimization:**
- Profile before optimizing
- Use generators for large datasets
- Cache expensive computations

---

## Testing Strategy

**Coverage:**
- 90%+ coverage for business logic
- 70%+ coverage for API/CLI layers
- 100% coverage for financial calculations

**Test Types:**
- Unit tests for all business logic
- Property-based tests for critical paths (Hypothesis)
- Integration tests for API endpoints
- Performance tests for batch operations

---

## Dependencies

**Dependency Policy:**
- Prefer standard library over external deps
- Pin all dependency versions
- Document why each dependency is needed
- Audit dependencies quarterly for security

---

## Git Workflow

**Branch Strategy:**
- `main` - production-ready code
- `feature/name` - new features
- No direct commits to `main`

**Commit Messages:**
- Format: `type: description`
- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Include ticket/issue number if applicable

---

**Last Updated:** [Date]  
**Enforced By:** `.cursorrules`, `CLAUDE.md`, code reviews

