# Requirements Document: Kanban Board

## Introduction

The Kanban Board feature transforms project-tracker from a read-only dashboard into an interactive task management system. It replaces scattered TODO.md files across 20+ projects with a centralized SQLite-backed Kanban board, providing both visual drag-and-drop management and programmatic access for AI agents. This feature maintains the local-first, single-user philosophy while adding the ability to create, organize, and track tasks across all projects from a unified interface.

## Glossary

- **Task**: A unit of work with text description, status, project association, priority, and timestamps
- **Kanban_Board**: Visual interface displaying tasks organized into status columns
- **Status_Column**: One of four workflow states: Backlog, To Do, In Progress, Done
- **Project_Filter**: Sidebar control to show/hide tasks by project
- **MCP_Tool**: Model Context Protocol tool enabling AI agents to create tasks programmatically
- **Migration_Tool**: One-time utility to import tasks from existing TODO.md files
- **Dashboard**: Existing project-tracker web interface at localhost:8000
- **Task_Card**: Visual representation of a task on the Kanban board
- **Deep_Link**: URL that encodes view state for bookmarking and sharing

## Requirements

### Requirement 1: Task Data Storage

**User Story:** As a developer, I want all tasks stored in a centralized database, so that I have a single source of truth across all projects.

#### Acceptance Criteria

1. THE System SHALL store tasks in SQLite database (tracker.db)
2. WHEN a task is created, THE System SHALL record text, status, project, priority, created timestamp, and updated timestamp
3. THE System SHALL support CRUD operations (create, read, update, delete) on tasks
4. THE System SHALL allow querying tasks by project, status, and priority
5. THE System SHALL use WAL mode for concurrent access

### Requirement 2: Kanban Board Display

**User Story:** As a developer, I want to see all tasks in a visual board layout, so that I can understand work status at a glance.

#### Acceptance Criteria

1. THE Kanban_Board SHALL display four Status_Columns: Backlog, To Do, In Progress, Done
2. WHEN displaying a task, THE Task_Card SHALL show truncated text, project label, and priority indicator
3. THE Kanban_Board SHALL color-code or badge tasks by source project
4. WHEN a Status_Column contains tasks, THE System SHALL display the task count for that column
5. THE Kanban_Board SHALL use the dark theme design system from image-workflow

### Requirement 3: Drag-and-Drop Task Movement

**User Story:** As a developer, I want to drag tasks between columns, so that I can update status visually without forms.

#### Acceptance Criteria

1. WHEN a user drags a Task_Card to a different Status_Column, THE System SHALL update the task status
2. THE System SHALL complete drag-and-drop operations within 200ms
3. WHEN a drag operation completes, THE System SHALL persist the status change to the database
4. THE System SHALL provide visual feedback during drag operations
5. WHEN a drag operation fails, THE System SHALL revert the task to its original position

### Requirement 4: Project Filtering

**User Story:** As a developer, I want to filter tasks by project, so that I can focus on specific work contexts.

#### Acceptance Criteria

1. THE System SHALL display a collapsible left sidebar with a list of all projects
2. WHEN a user toggles a project checkbox, THE Kanban_Board SHALL show or hide tasks from that project
3. THE System SHALL provide "Select All" and "Deselect All" controls
4. WHEN the sidebar is collapsed, THE System SHALL remember the collapsed state across sessions
5. THE System SHALL display task counts per project in the sidebar

### Requirement 5: Project Sorting

**User Story:** As a developer, I want to sort projects in the sidebar, so that I can organize by relevance or workload.

#### Acceptance Criteria

1. THE System SHALL support sorting projects alphabetically (A-Z and Z-A)
2. THE System SHALL support sorting projects by open task count (most first and least first)
3. WHEN a user changes sort order, THE System SHALL update the sidebar immediately
4. THE System SHALL remember the selected sort order across sessions

### Requirement 6: Task Creation via MCP Tool

**User Story:** As an AI agent, I want to create tasks programmatically, so that I can add work items from any project context.

#### Acceptance Criteria

1. THE System SHALL provide an MCP tool named "kanban_add_task"
2. WHEN the tool is invoked, THE System SHALL accept parameters: project, text, status (default: Backlog), priority (optional)
3. THE System SHALL complete task creation within 100ms
4. WHEN task text contains patterns resembling secrets, THE System SHALL warn or block creation
5. THE System SHALL return the created task with its assigned ID

### Requirement 7: Task Creation via Dashboard UI

**User Story:** As a developer, I want to add tasks manually from the dashboard, so that I can capture work without using AI agents.

#### Acceptance Criteria

1. THE Kanban_Board SHALL display an "Add Task" button
2. WHEN a user clicks "Add Task", THE System SHALL display a task creation form
3. THE System SHALL require task text and project selection
4. THE System SHALL allow optional priority selection
5. WHEN a user submits the form, THE System SHALL create the task and display it on the board

### Requirement 8: Task Detail View and Editing

**User Story:** As a developer, I want to view and edit task details, so that I can update descriptions and metadata.

#### Acceptance Criteria

1. WHEN a user clicks a Task_Card, THE System SHALL expand to show full text
2. THE System SHALL display project name, priority, created timestamp, and updated timestamp
3. THE System SHALL allow inline editing of task text
4. WHEN a user saves edits, THE System SHALL update the task in the database
5. THE System SHALL update the "updated timestamp" when task text changes

### Requirement 9: URL Routing and Deep Links

**User Story:** As a developer, I want URLs to reflect my current view, so that I can bookmark and share specific board states.

#### Acceptance Criteria

1. THE System SHALL support routes: /dashboard, /kanban, /kanban/:project, /graph, /graph/:project
2. WHEN a user navigates to /kanban/:project, THE System SHALL pre-filter the board to that project
3. THE System SHALL update the URL when filter state changes
4. WHEN a user uses browser back/forward, THE System SHALL restore the previous view state
5. THE System SHALL make all URLs bookmarkable

### Requirement 10: Dashboard Integration

**User Story:** As a developer, I want Kanban integrated into the existing dashboard, so that I have unified navigation.

#### Acceptance Criteria

1. THE System SHALL add a "Kanban" tab to the existing dashboard navigation
2. THE Dashboard SHALL display navigation: [Dashboard] [Kanban] [Graph]
3. THE Dashboard SHALL read task counts from the Kanban database
4. WHEN displaying project cards, THE Dashboard SHALL show open task counts from Kanban
5. THE System SHALL maintain consistent styling between Dashboard and Kanban views

### Requirement 11: TODO.md Migration

**User Story:** As a developer, I want to import existing TODO.md tasks, so that I can transition to Kanban without losing work.

#### Acceptance Criteria

1. THE Migration_Tool SHALL parse TODO.md files using the migration mapping
2. WHEN parsing "- [ ] Task" with no priority header, THE Migration_Tool SHALL set status to Backlog
3. WHEN parsing "- [ ] Task" under a priority header, THE Migration_Tool SHALL set status to To Do
4. WHEN parsing "- [~] Task" or tasks with 🔄 marker, THE Migration_Tool SHALL set status to In Progress
5. WHEN parsing "- [x] Task", THE Migration_Tool SHALL set status to Done
6. THE Migration_Tool SHALL verify import counts match source file counts
7. WHEN migration completes successfully, THE Migration_Tool SHALL archive TODO.md files

### Requirement 12: Productivity Insights

**User Story:** As a developer, I want to see completion trends over time, so that I can understand my productivity patterns.

#### Acceptance Criteria

1. THE System SHALL track when tasks move to Done status
2. THE System SHALL display a graph showing tasks completed over time
3. THE System SHALL support filtering graphs by project
4. THE System SHALL support viewing trends by week or month
5. THE System SHALL display the graph at route /graph and /graph/:project

### Requirement 13: Performance

**User Story:** As a developer, I want the board to load quickly, so that I can access tasks without delay.

#### Acceptance Criteria

1. THE System SHALL load all tasks in under 1 second
2. THE System SHALL complete drag-and-drop operations in under 200ms
3. THE System SHALL complete MCP tool writes in under 100ms
4. THE System SHALL handle at least 1000 tasks without performance degradation

### Requirement 14: Input Validation and Security

**User Story:** As a developer, I want the system to prevent accidental storage of secrets, so that I maintain security hygiene.

#### Acceptance Criteria

1. WHEN task text matches secret patterns (sk-, api_key=, SSN formats), THE System SHALL warn the user
2. THE System SHALL block task creation if high-confidence secret patterns are detected
3. THE System SHALL validate that project names exist in the database
4. THE System SHALL sanitize task text to prevent XSS attacks
5. THE System SHALL validate all user inputs before database operations

### Requirement 15: Data Integrity

**User Story:** As a developer, I want reliable data persistence, so that I never lose task information.

#### Acceptance Criteria

1. THE System SHALL use SQLite transactions for all write operations
2. WHEN a database write fails, THE System SHALL rollback the transaction
3. THE System SHALL log all database errors
4. THE System SHALL handle concurrent access gracefully using WAL mode
5. WHEN the database is locked, THE System SHALL retry operations with exponential backoff
