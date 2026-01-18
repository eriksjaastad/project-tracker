# Missing Tests for project-tracker

This document outlines the missing test coverage for the project-tracker application, based on the v2 code review, current architecture, and identified gaps. Addressing these gaps will improve the reliability, stability, and security of the application.

## 1. Discovery Modules

These modules are responsible for discovering and extracting information about projects.

- [ ] **git_metadata.py**:
    - [ ] Tests for accurately parsing git log output.
    - [ ] Tests for detecting the last commit hash and timestamp.
    - [ ] Tests for handling different git repository states (e.g., detached HEAD).
    - [ ] Tests for edge cases in commit messages (e.g., unusual characters).
- [ ] **cron_monitor.py**:
    - [ ] Tests for parsing various crontab formats (including non-standard ones).
    - [ ] Tests for detecting scheduled tasks with different frequencies (e.g., daily, weekly, monthly).
    - [ ] Tests for handling errors during crontab parsing.
    - [ ] Tests for identifying the user associated with each cron job.
- [ ] **external_resources_parser.py**:
    - [ ] Tests for parsing `EXTERNAL_RESOURCES.md` files with different structures.
    - [ ] Tests for extracting resource names, URLs, and descriptions.
    - [ ] Tests for handling malformed or incomplete `EXTERNAL_RESOURCES.md` files.
    - [ ] Tests for different resource types (e.g., databases, APIs, cloud services).
- [ ] **agent_registry.py**:
    - [ ] Tests for successfully executing agent commands.
    - [ ] Tests for handling agent command timeouts.
    - [ ] Tests for validating agent command output.
    - [ ] Tests for looking up agents in the registry based on different criteria.
    - [ ] Tests for handling cases where an agent is not found in the registry.
- [ ] **telemetry_reader.py**:
    - [ ] Tests for parsing JSONL telemetry logs with different formats.
    - [ ] Tests for calculating costs based on telemetry data.
    - [ ] Tests for handling missing or invalid telemetry data.
    - [ ] Tests for aggregating telemetry data over different time periods.
    - [ ] Tests for different telemetry sources.

## 2. Database Operations

These tests cover the interaction with the database.

- [ ] **DatabaseManager**:
    - [ ] Tests for creating, reading, updating, and deleting projects.
    - [ ] Tests for creating, reading, updating, and deleting alerts.
    - [ ] Tests for creating, reading, updating, and deleting cron jobs.
    - [ ] Tests for handling database connection errors.
    - [ ] Tests for data validation before writing to the database.
    - [ ] Tests for handling concurrent database access.
- [ ] **Schema Migrations**:
    - [ ] Tests for the initial database schema creation.
    - [ ] Tests for applying schema updates without data loss.
    - [ ] Tests for rolling back schema updates.
    - [ ] Tests for handling errors during schema migrations.
    - [ ] Tests for different database versions.

## 3. Web Dashboard (Integration Tests)

These tests ensure the web dashboard functions correctly.

- [ ] **FastAPI Endpoints**:
    - [ ] Tests for the `/` (home) endpoint.
    - [ ] Tests for the `/project/{id}` (project details) endpoint.
    - [ ] Tests for the `/api/create-index/{id}` (create index) endpoint.
    - [ ] Tests for different HTTP methods (e.g., GET, POST, PUT, DELETE).
    - [ ] Tests for authentication and authorization.
- [ ] **Template Rendering**:
    - [ ] Tests to ensure templates render correctly with various project states (e.g., active, inactive, error).
    - [ ] Tests for displaying project metadata.
    - [ ] Tests for displaying alerts and cron jobs.
    - [ ] Tests for handling missing or invalid data in templates.
    - [ ] Tests for different user roles and permissions.
- [ ] **Error Handling**:
    - [ ] Tests for 404 errors (page not found).
    - [ ] Tests for 500 errors (internal server error).
    - [ ] Tests for displaying user-friendly error messages.
    - [ ] Tests for logging errors.

## 4. CLI Tool (pt.py)

These tests cover the command-line interface.

- [ ] **Command Line Interface**:
    - [ ] Tests for the `scan` command.
    - [ ] Tests for the `list` command.
    - [ ] Tests for the `launch` command.
    - [ ] Tests for the `init` command.
    - [ ] Tests for command-line argument parsing.
    - [ ] Tests for displaying help messages.
- [ ] **Configuration Handling**:
    - [ ] Tests for loading configuration from `config.py`.
    - [ ] Tests for loading configuration from environment variables.
    - [ ] Tests for merging configuration from multiple sources.
    - [ ] Tests for handling missing or invalid configuration values.
    - [ ] Tests for default configuration values.

## 5. Security & Validation

These tests ensure the application is secure and data is valid.

- [ ] **warden_audit.py**:
    - [ ] Tests for detecting dangerous patterns (e.g., SQL injection, cross-site scripting).
    - [ ] Tests for detecting hardcoded paths and credentials.
    - [ ] Tests for handling different code styles and languages.
    - [ ] Tests for false positive and false negative rates.
- [ ] **validate_project.py**:
    - [ ] Tests for validating project structure against defined rules.
    - [ ] Tests for validating project metadata.
    - [ ] Tests for handling invalid or missing project files.
    - [ ] Tests for different project types and configurations.
    - [ ] Tests for custom validation rules.

## Priority Recommendations:

1. **Integration Tests for `pt scan`**: This is the most critical path that populates the database.  Focus on end-to-end testing of the scanning process, including discovery, parsing, and database storage.
2. **API Tests for `agent_dispatcher`**: Ensure that running agents from the dashboard works and handles timeouts correctly.  This includes testing the API endpoints responsible for agent execution and monitoring.

## Related Documentation

- [[CODE_REVIEW_ANTI_PATTERNS]] - code review
- [[DOPPLER_SECRETS_MANAGEMENT]] - secrets management
- [[PROJECT_STRUCTURE_STANDARDS]] - project structure
- [[architecture_patterns]] - architecture
- [[automation_patterns]] - automation
- [[cost_management]] - cost management
- [[dashboard_architecture]] - dashboard/UI
- [[database_setup]] - database
- [[error_handling_patterns]] - error handling
- [[security_patterns]] - security
- [[project-tracker/README]] - Project Tracker
