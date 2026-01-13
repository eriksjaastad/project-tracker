# Missing Tests for project-tracker

Based on the v2 code review and current architecture, the following test coverage gaps exist:

## 1. Discovery Modules
- [ ] **git_metadata.py**: Tests for git log parsing and last commit detection.
- [ ] **cron_monitor.py**: Tests for parsing crontab and detecting scheduled tasks.
- [ ] **external_resources_parser.py**: Tests for parsing `EXTERNAL_RESOURCES.md`.
- [ ] **agent_registry.py**: Tests for agent command execution and registry lookups.
- [ ] **telemetry_reader.py**: Tests for parsing JSONL telemetry logs and cost calculation.

## 2. Database Operations
- [ ] **DatabaseManager**: Tests for CRUD operations on projects, alerts, and cron jobs.
- [ ] **Schema Migrations**: Tests for database initialization and future schema updates.

## 3. Web Dashboard (Integration Tests)
- [ ] **FastAPI Endpoints**: Tests for `/`, `/project/{id}`, and `/api/create-index/{id}`.
- [ ] **Template Rendering**: Tests to ensure templates render correctly with various project states.
- [ ] **Error Handling**: Tests for 404s and 500s on the dashboard.

## 4. CLI Tool (pt.py)
- [ ] **Command Line Interface**: Tests for `scan`, `list`, `launch`, and `init` commands.
- [ ] **Configuration Handling**: Tests for loading `config.py` and environment variables.

## 5. Security & Validation
- [ ] **warden_audit.py**: Tests for detecting dangerous patterns and hardcoded paths.
- [ ] **validate_project.py**: Tests for project structure validation rules.

## Priority Recommendations:
1. **Integration Tests for `pt scan`**: This is the most critical path that populates the database.
2. **API Tests for `agent_dispatcher`**: Ensure that running agents from the dashboard works and handles timeouts correctly.
