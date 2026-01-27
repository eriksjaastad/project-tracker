# Implementation Plan: Kanban Board

## Overview

This implementation plan breaks down the Kanban Board feature into discrete, incremental tasks. The approach follows a backend-first strategy: establish the data layer and API, then build the React frontend, and finally add MCP integration and migration tools. Each task builds on previous work, with property-based tests integrated throughout to catch errors early.

**Technology Stack:**
- Backend: Python, FastAPI, SQLite
- Frontend: React 18, TypeScript, Vite, @dnd-kit/core, Recharts
- Testing: pytest + hypothesis (backend), vitest + fast-check (frontend)
- MCP: Python MCP server integration

## Tasks

- [ ] 1. Database Schema and Core API
  - [ ] 1.1 Extend database schema with tasks and task_history tables
    - Add tasks table with all fields (id, text, status, project_id, priority, timestamps)
    - Add task_history table for tracking status changes
    - Create indexes for performance (project_id, status, completed_at)
    - Enable WAL mode for concurrent access
    - _Requirements: 1.1, 1.2, 1.5_

  - [ ] 1.2 Write property test for task creation completeness
    - **Property 1: Task Creation Completeness**
    - **Validates: Requirements 1.2, 6.5**
    - Generate random task data (text, project, status, priority)
    - Create task and verify all fields present (including generated id, timestamps)
    - Query task by ID and verify data matches
    - _Requirements: 1.2, 6.5_

  - [ ] 1.3 Implement DatabaseManager methods for task CRUD
    - add_task(text, project_id, status, priority) -> Task
    - get_tasks(project_id?, status?) -> List[Task]
    - get_task(task_id) -> Task
    - update_task(task_id, **updates) -> Task
    - delete_task(task_id) -> bool
    - Record history entries on status changes
    - _Requirements: 1.2, 1.3, 1.4_

  - [ ] 1.4 Write property test for query filtering accuracy
    - **Property 2: Query Filtering Accuracy**
    - **Validates: Requirements 1.4**
    - Generate random tasks with various projects, statuses, priorities
    - Query with different filter combinations
    - Verify results match filter criteria
    - _Requirements: 1.4_

  - [ ] 1.5 Implement input validation and secret detection
    - Create SECRET_PATTERNS list with regex patterns
    - Implement contains_secret(text) -> (bool, str)
    - Validate task text length (1-1000 chars)
    - Validate status and priority enums
    - Validate project_id exists
    - _Requirements: 6.4, 14.1, 14.2, 14.3_

  - [ ] 1.6 Write property test for secret pattern detection
    - **Property 12: Secret Pattern Detection**
    - **Validates: Requirements 6.4, 14.1, 14.2**
    - Generate strings with secret patterns (API keys, SSNs, passwords)
    - Attempt to create tasks with secret text
    - Verify warnings or blocks occur
    - _Requirements: 6.4, 14.1, 14.2_

  - [ ] 1.7 Write property test for project validation
    - **Property 16: Project Validation**
    - **Validates: Requirements 14.3**
    - Generate random non-existent project IDs
    - Attempt to create tasks with invalid projects
    - Verify rejection with appropriate error
    - _Requirements: 14.3_

- [ ] 2. FastAPI Routes and Error Handling
  - [ ] 2.1 Implement POST /api/tasks endpoint
    - Accept JSON body: {text, project_id, status?, priority?}
    - Validate inputs using validation functions
    - Call DatabaseManager.add_task()
    - Return task object with 201 status
    - Handle validation errors with 400 responses
    - _Requirements: 6.1, 6.2, 7.5_

  - [ ] 2.2 Implement GET /api/tasks endpoint
    - Accept query params: ?project_id=X&status=Y
    - Call DatabaseManager.get_tasks() with filters
    - Return array of task objects
    - _Requirements: 1.4_

  - [ ] 2.3 Implement GET /api/tasks/:id endpoint
    - Parse task_id from URL
    - Call DatabaseManager.get_task()
    - Return task object or 404
    - _Requirements: 8.1, 8.2_

  - [ ] 2.4 Implement PATCH /api/tasks/:id endpoint
    - Accept JSON body with updates: {text?, status?, priority?}
    - Validate updates
    - Call DatabaseManager.update_task()
    - Return updated task object
    - _Requirements: 3.1, 8.4, 8.5_

  - [ ] 2.5 Write property test for task edit persistence
    - **Property 8: Task Edit Persistence**
    - **Validates: Requirements 8.4, 8.5**
    - Generate random tasks
    - Edit task text via API
    - Verify database updated
    - Verify updated_at timestamp changed
    - Reload and verify persistence
    - _Requirements: 8.4, 8.5_

  - [ ] 2.6 Implement DELETE /api/tasks/:id endpoint
    - Parse task_id from URL
    - Call DatabaseManager.delete_task()
    - Return 204 on success
    - _Requirements: 1.3_

  - [ ] 2.7 Implement error handling middleware
    - Catch validation errors -> 400 responses
    - Catch not found errors -> 404 responses
    - Catch database errors -> 500 responses
    - Log all errors with context
    - Return structured error JSON
    - _Requirements: 15.3_

  - [ ] 2.8 Write property test for transaction rollback
    - **Property 18: Transaction Rollback on Error**
    - **Validates: Requirements 15.2**
    - Simulate database write failures
    - Verify transaction rollback
    - Verify database state unchanged
    - _Requirements: 15.2_

  - [ ] 2.9 Write property test for database lock retry
    - **Property 19: Database Lock Retry**
    - **Validates: Requirements 15.5**
    - Simulate database lock conditions
    - Verify retry with exponential backoff
    - Verify eventual success or max retries
    - _Requirements: 15.5_

- [ ] 3. Checkpoint - Backend Core Complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. React Frontend Setup and Basic UI
  - [ ] 4.1 Initialize React project with Vite and TypeScript
    - Create frontend directory structure
    - Install dependencies: react, react-dom, typescript, vite
    - Configure tsconfig.json
    - Set up Vite config with proxy to FastAPI backend
    - _Requirements: 2.1_

  - [ ] 4.2 Install UI dependencies
    - Install @dnd-kit/core, @dnd-kit/sortable for drag-and-drop
    - Install recharts for graphs
    - Install react-router-dom for routing
    - Install design system CSS (from image-workflow)
    - _Requirements: 2.5, 3.1, 12.2_

  - [ ] 4.3 Create Navigation component with tabs
    - Implement [Dashboard] [Kanban] [Graph] navigation
    - Use React Router Links
    - Apply dark theme styling
    - _Requirements: 10.1, 10.2_

  - [ ] 4.4 Write unit test for navigation rendering
    - Verify all three tabs render
    - Verify correct routes
    - _Requirements: 10.1, 10.2_

  - [ ] 4.5 Create basic KanbanBoard component structure
    - Set up component with ProjectSidebar and Board
    - Fetch tasks from /api/tasks
    - Display loading state
    - _Requirements: 2.1_

  - [ ] 4.6 Create Column component for status columns
    - Render four columns: Backlog, To Do, In Progress, Done
    - Display column titles
    - Display task count per column
    - _Requirements: 2.1, 2.4_

  - [ ] 4.7 Write property test for task counting accuracy
    - **Property 4: Task Counting Accuracy**
    - **Validates: Requirements 2.4, 4.5, 10.3, 10.4**
    - Generate random task distributions
    - Render board
    - Verify column counts match actual task counts
    - Verify project counts match
    - Verify dashboard counts match
    - _Requirements: 2.4, 4.5, 10.3, 10.4_

- [ ] 5. Task Cards and Display
  - [ ] 5.1 Create TaskCard component
    - Display truncated text (max 100 chars)
    - Display project label badge
    - Display priority indicator (color dot or border)
    - Apply project-specific styling
    - _Requirements: 2.2, 2.3_

  - [ ] 5.2 Write property test for task display completeness
    - **Property 14: Task Display Completeness**
    - **Validates: Requirements 2.2, 2.3**
    - Generate random tasks
    - Render task cards
    - Verify truncated text displayed
    - Verify project label present
    - Verify priority indicator present (if priority set)
    - _Requirements: 2.2, 2.3_

  - [ ] 5.3 Write property test for task card project styling
    - **Property 23: Task Card Project Styling**
    - **Validates: Requirements 2.3**
    - Generate tasks from different projects
    - Render task cards
    - Verify each card has project-specific styling
    - _Requirements: 2.3_

  - [ ] 5.4 Implement task detail modal
    - Show full task text on click
    - Display all metadata (project, priority, timestamps)
    - Allow inline editing of text
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ] 5.5 Write property test for task detail display
    - **Property 7: Task Detail Display**
    - **Validates: Requirements 8.1, 8.2**
    - Generate random tasks
    - Click task cards
    - Verify all metadata displayed
    - _Requirements: 8.1, 8.2_

- [ ] 6. Drag-and-Drop Implementation
  - [ ] 6.1 Integrate @dnd-kit/core with KanbanBoard
    - Wrap board in DndContext
    - Configure collision detection
    - Implement onDragEnd handler
    - _Requirements: 3.1_

  - [ ] 6.2 Make TaskCard draggable
    - Use useSortable hook
    - Add drag handle
    - Show visual feedback during drag
    - _Requirements: 3.1, 3.4_

  - [ ] 6.3 Make Column droppable
    - Configure as drop target
    - Highlight on drag over
    - _Requirements: 3.1_

  - [ ] 6.4 Implement optimistic updates for drag operations
    - Update local state immediately on drag
    - Send PATCH request to backend
    - Revert on error
    - _Requirements: 3.1, 3.5_

  - [ ] 6.5 Write property test for drag-and-drop status update
    - **Property 5: Drag-and-Drop Status Update**
    - **Validates: Requirements 3.1, 3.3**
    - Generate random tasks
    - Simulate drag to different columns
    - Verify status updated in database
    - Verify UI reflects change
    - _Requirements: 3.1, 3.3_

  - [ ] 6.6 Write property test for drag operation rollback
    - **Property 6: Drag Operation Rollback**
    - **Validates: Requirements 3.5**
    - Generate random tasks
    - Simulate drag operations that fail
    - Verify task reverts to original status
    - Verify UI reverts to original position
    - _Requirements: 3.5_

- [ ] 7. Project Sidebar and Filtering
  - [ ] 7.1 Create ProjectSidebar component
    - Fetch projects from /api/projects
    - Display project list with checkboxes
    - Implement "Select All" / "Deselect All" buttons
    - Make sidebar collapsible
    - _Requirements: 4.1, 4.3_

  - [ ] 7.2 Implement project filtering logic
    - Track selected projects in state
    - Filter tasks based on selected projects
    - Update board when filters change
    - _Requirements: 4.2_

  - [ ] 7.3 Write property test for UI project filtering
    - **Property 3: UI Project Filtering**
    - **Validates: Requirements 4.2**
    - Generate tasks across multiple projects
    - Toggle project filters
    - Verify only selected project tasks shown
    - _Requirements: 4.2_

  - [ ] 7.4 Display task counts per project in sidebar
    - Calculate open task count per project
    - Display count badge next to project name
    - _Requirements: 4.5_

  - [ ] 7.5 Implement project sorting
    - Add sort dropdown (Alphabetical A-Z, Z-A, Task Count High-Low, Low-High)
    - Sort project list based on selection
    - _Requirements: 5.1, 5.2_

  - [ ] 7.6 Write property test for project sorting correctness
    - **Property 11: Project Sorting Correctness**
    - **Validates: Requirements 5.1, 5.2**
    - Generate projects with random names and task counts
    - Test alphabetical sorting (A-Z, Z-A)
    - Test task count sorting (most-first, least-first)
    - Verify correct order
    - _Requirements: 5.1, 5.2_

  - [ ] 7.7 Implement sidebar state persistence
    - Save collapsed state to localStorage
    - Save sort order to localStorage
    - Restore on page load
    - _Requirements: 4.4, 5.4_

  - [ ] 7.8 Write property test for sidebar state persistence
    - **Property 10: Sidebar State Persistence**
    - **Validates: Requirements 4.4, 5.4**
    - Set sidebar state (collapsed, sort order)
    - Reload page
    - Verify state restored from localStorage
    - _Requirements: 4.4, 5.4_

- [ ] 8. Checkpoint - Frontend Core Complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Task Creation UI
  - [ ] 9.1 Create AddTaskButton component
    - Display "Add Task" button on board
    - Open modal on click
    - _Requirements: 7.1_

  - [ ] 9.2 Create TaskForm component
    - Input field for task text
    - Dropdown for project selection
    - Dropdown for priority (optional)
    - Submit and cancel buttons
    - _Requirements: 7.2, 7.3, 7.4_

  - [ ] 9.3 Implement form validation
    - Require text and project fields
    - Show validation errors
    - Disable submit if invalid
    - _Requirements: 7.3, 7.4_

  - [ ] 9.4 Write property test for form validation
    - **Property 13: Form Validation**
    - **Validates: Requirements 7.3, 7.4**
    - Submit forms with missing required fields
    - Verify rejection and error display
    - Submit forms with all required fields
    - Verify acceptance
    - _Requirements: 7.3, 7.4_

  - [ ] 9.5 Implement form submission
    - POST to /api/tasks
    - Handle success: close modal, refresh board
    - Handle errors: display error message
    - _Requirements: 7.5_

  - [ ] 9.6 Write property test for form submission success
    - **Property 15: Form Submission Success**
    - **Validates: Requirements 7.5**
    - Generate valid form data
    - Submit form
    - Verify task created
    - Verify task appears on board in correct column
    - _Requirements: 7.5_

- [ ] 10. URL Routing and Deep Links
  - [ ] 10.1 Set up React Router routes
    - /dashboard -> Dashboard component
    - /kanban -> KanbanBoard component (all projects)
    - /kanban/:project -> KanbanBoard component (filtered)
    - /graph -> ProductivityGraph component (all projects)
    - /graph/:project -> ProductivityGraph component (filtered)
    - _Requirements: 9.1_

  - [ ] 10.2 Implement URL-based project filtering
    - Read :project param from URL
    - Pre-filter board to that project
    - Update URL when filter changes
    - _Requirements: 9.2, 9.3_

  - [ ] 10.3 Write property test for URL state synchronization
    - **Property 9: URL State Synchronization**
    - **Validates: Requirements 9.2, 9.3, 9.4, 9.5**
    - Set view state (project filter, route)
    - Verify URL reflects state
    - Navigate to URL (bookmark, back/forward)
    - Verify view state restored
    - _Requirements: 9.2, 9.3, 9.4, 9.5_

- [ ] 11. Dashboard Integration
  - [ ] 11.1 Update Dashboard component to show task counts
    - Fetch task counts from /api/tasks
    - Display open task count per project
    - Add link to /kanban/:project
    - _Requirements: 10.3, 10.4_

  - [ ] 11.2 Write property test for dashboard task count integration
    - **Property 25: Dashboard Task Count Integration**
    - **Validates: Requirements 10.3, 10.4**
    - Generate random tasks across projects
    - Render dashboard
    - Verify open task counts match (Backlog + To Do + In Progress)
    - _Requirements: 10.3, 10.4_

- [ ] 12. Productivity Graph
  - [ ] 12.1 Implement GET /api/tasks/history endpoint
    - Accept query params: ?days=30&project_id=X
    - Query task_history for completion events
    - Aggregate by day
    - Return time series data
    - _Requirements: 12.1, 12.2_

  - [ ] 12.2 Create ProductivityGraph component
    - Fetch completion history from API
    - Use Recharts LineChart
    - Display tasks completed over time
    - _Requirements: 12.2_

  - [ ] 12.3 Add project filter to graph
    - Dropdown to select project
    - Update graph when project changes
    - Update URL with project param
    - _Requirements: 12.3_

  - [ ] 12.4 Write property test for graph project filtering
    - **Property 22: Graph Project Filtering**
    - **Validates: Requirements 12.3**
    - Generate completed tasks across projects
    - Filter graph by project
    - Verify only that project's completions shown
    - _Requirements: 12.3_

  - [ ] 12.5 Add time range selector
    - Buttons for Week / Month views
    - Update graph data based on selection
    - _Requirements: 12.4_

- [ ] 13. Checkpoint - UI Complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. MCP Tool Integration
  - [ ] 14.1 Create MCP server tool definition
    - Define kanban_add_task tool
    - Specify input schema (project, text, status, priority)
    - Document tool usage
    - _Requirements: 6.1, 6.2_

  - [ ] 14.2 Implement kanban_add_task tool handler
    - Validate inputs
    - Check for secrets
    - POST to /api/tasks
    - Return task object to agent
    - _Requirements: 6.1, 6.2, 6.4, 6.5_

  - [ ] 14.3 Write property test for MCP tool task creation
    - **Property 24: MCP Tool Task Creation**
    - **Validates: Requirements 6.2, 6.5**
    - Generate random valid tool invocations
    - Call tool
    - Verify task created in database
    - Verify task returned to caller
    - _Requirements: 6.2, 6.5_

  - [ ] 14.4 Add kanban_list_tasks tool (optional)
    - List tasks with optional filters
    - Return array of tasks
    - _Requirements: 1.4_

  - [ ] 14.5 Add kanban_update_task tool (optional)
    - Update task by ID
    - Return updated task
    - _Requirements: 3.1, 8.4_

- [ ] 15. TODO.md Migration Tool
  - [ ] 15.1 Create migration script
    - Scan for TODO.md files in all projects
    - Parse markdown checkboxes
    - Map to Kanban statuses using migration mapping
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ] 15.2 Implement parsing logic
    - Parse "- [ ] Task" -> Backlog (no priority header)
    - Parse "- [ ] Task" under priority header -> To Do
    - Parse "- [~] Task" or 🔄 -> In Progress
    - Parse "- [x] Task" -> Done
    - Extract project from file path
    - _Requirements: 11.2, 11.3, 11.4, 11.5_

  - [ ] 15.3 Write property test for migration completeness
    - **Property 20: Migration Completeness**
    - **Validates: Requirements 11.6**
    - Generate random TODO.md files
    - Run migration
    - Verify task count in database matches source file
    - _Requirements: 11.6_

  - [ ] 15.4 Implement file archival
    - Move TODO.md to .archive/ directory after migration
    - Verify file no longer in original location
    - _Requirements: 11.7_

  - [ ] 15.5 Write property test for migration file archival
    - **Property 21: Migration File Archival**
    - **Validates: Requirements 11.7**
    - Run migration on TODO.md files
    - Verify files moved to archive
    - Verify files not in original location
    - _Requirements: 11.7_

  - [ ] 15.6 Add dry-run mode for migration
    - Preview what would be migrated
    - Don't write to database or move files
    - Output summary report
    - _Requirements: 11.6_

- [ ] 16. XSS Protection and Security
  - [ ] 16.1 Implement XSS sanitization
    - Sanitize task text before storage
    - Escape HTML/JavaScript in display
    - Use DOMPurify or similar library
    - _Requirements: 14.4_

  - [ ] 16.2 Write property test for XSS sanitization
    - **Property 17: XSS Sanitization**
    - **Validates: Requirements 14.4**
    - Generate task text with XSS payloads (script tags, event handlers)
    - Create tasks
    - Verify sanitization before storage
    - Verify safe display (no script execution)
    - _Requirements: 14.4_

- [ ] 17. Final Integration and Polish
  - [ ] 17.1 Add loading states and spinners
    - Show loading during API calls
    - Show skeleton screens for initial load
    - _Requirements: 2.1_

  - [ ] 17.2 Add error toast notifications
    - Display user-friendly error messages
    - Auto-dismiss after 5 seconds
    - _Requirements: Error Handling_

  - [ ] 17.3 Add keyboard shortcuts (optional)
    - 'n' to open new task form
    - 'Escape' to close modals
    - Arrow keys to navigate tasks
    - _Requirements: None (enhancement)_

  - [ ] 17.4 Optimize performance
    - Implement virtual scrolling for large task lists
    - Debounce filter changes
    - Memoize expensive computations
    - _Requirements: 13.1, 13.4_

  - [ ] 17.5 Add accessibility features
    - ARIA labels for drag-and-drop
    - Keyboard navigation support
    - Screen reader announcements
    - _Requirements: None (best practice)_

- [ ] 18. Final Checkpoint - Complete Feature
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tests are required (no optional tests per user request)
- Each property test references its design document property number
- Tasks build incrementally - each step validates before moving forward
- Checkpoints ensure quality gates at major milestones
- Backend-first approach establishes solid foundation
- Property tests catch edge cases across input space
- Unit tests validate specific examples and integration points
