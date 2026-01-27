# Design Document: Kanban Board

## Overview

The Kanban Board feature extends project-tracker with a centralized task management system. It replaces scattered TODO.md files with a SQLite-backed Kanban board accessible through both a visual React interface and programmatic MCP tools. The design follows the existing project-tracker architecture (FastAPI backend, SQLite storage, React frontend) while adding drag-and-drop task management, project filtering, and productivity analytics.

**Key Design Principles:**
- **Single Source of Truth**: All tasks stored in SQLite, no file-based task storage
- **Local-First**: No external services, all data stays on the user's machine
- **Incremental Enhancement**: Extends existing infrastructure without breaking changes
- **AI-Friendly**: Programmatic access via MCP tools for agent task creation
- **Performance-First**: Sub-second load times, sub-200ms interactions

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (React)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Dashboard  │  │ Kanban Board │  │ Graph View   │      │
│  │   (Existing) │  │    (New)     │  │   (New)      │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
└─────────┼──────────────────┼──────────────────┼──────────────┘
          │                  │                  │
          │    HTTP/JSON     │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Backend (Python)                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Existing Routes    │  New Kanban Routes             │   │
│  │  /api/projects      │  /api/tasks                    │   │
│  │  /api/stats         │  /api/tasks/:id                │   │
│  │  /dashboard         │  /kanban                       │   │
│  │                     │  /kanban/:project              │   │
│  │                     │  /graph                        │   │
│  │                     │  /graph/:project               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              SQLite Database (tracker.db)                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Existing Tables    │  New Tables                    │   │
│  │  - projects         │  - tasks                       │   │
│  │  - cron_jobs        │  - task_history (for graphs)   │   │
│  │  - ai_agents        │                                │   │
│  │  - service_deps     │                                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
          ▲
          │
┌─────────┴───────────────────────────────────────────────────┐
│              MCP Server (Ollama MCP)                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  kanban_add_task(project, text, status, priority)    │   │
│  │  kanban_list_tasks(project?, status?)                │   │
│  │  kanban_update_task(id, updates)                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

**Task Creation (UI):**
1. User clicks "Add Task" button
2. React form captures: text, project, priority
3. POST /api/tasks with JSON payload
4. FastAPI validates input, checks for secrets
5. Insert into tasks table
6. Return task with ID
7. React updates board state

**Task Creation (MCP):**
1. AI agent calls kanban_add_task tool
2. MCP server validates parameters
3. HTTP POST to /api/tasks
4. Same validation and insertion as UI flow
5. Return task to agent

**Task Status Update (Drag-and-Drop):**
1. User drags task card to new column
2. React DnD library fires onDragEnd event
3. PATCH /api/tasks/:id with {status: "In Progress"}
4. FastAPI updates task, records history
5. Return updated task
6. React updates board state

**Productivity Graph:**
1. User navigates to /graph or /graph/:project
2. React requests GET /api/tasks/history?days=30&project=X
3. FastAPI queries task_history for completion events
4. Aggregate by day/week
5. Return time series data
6. React renders with Recharts

## Components and Interfaces

### Backend Components

#### 1. Database Schema Extensions

**tasks table:**
```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('Backlog', 'To Do', 'In Progress', 'Done')),
    project_id TEXT NOT NULL,
    priority TEXT CHECK(priority IN ('Critical', 'High', 'Medium', 'Low', NULL)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,  -- Set when moved to Done
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_completed ON tasks(completed_at) WHERE completed_at IS NOT NULL;
```

**task_history table (for productivity graphs):**
```sql
CREATE TABLE task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('created', 'status_changed', 'completed')),
    old_status TEXT,
    new_status TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX idx_history_timestamp ON task_history(timestamp);
CREATE INDEX idx_history_project ON task_history(project_id);
CREATE INDEX idx_history_event ON task_history(event_type);
```

#### 2. API Routes

**Task CRUD:**
- `POST /api/tasks` - Create task
  - Body: `{text, project_id, status?, priority?}`
  - Returns: Task object with ID
  - Validates: secret patterns, project exists, status valid

- `GET /api/tasks` - List tasks
  - Query params: `?project_id=X&status=Y`
  - Returns: Array of task objects
  - Supports filtering by project and status

- `GET /api/tasks/:id` - Get single task
  - Returns: Task object with full details

- `PATCH /api/tasks/:id` - Update task
  - Body: `{text?, status?, priority?}`
  - Returns: Updated task object
  - Records history entry on status change

- `DELETE /api/tasks/:id` - Delete task
  - Returns: Success confirmation

**Analytics:**
- `GET /api/tasks/history` - Get completion history
  - Query params: `?days=30&project_id=X`
  - Returns: Time series of completion events
  - Aggregated by day

**Page Routes:**
- `GET /kanban` - Kanban board view (all projects)
- `GET /kanban/:project` - Kanban board filtered to project
- `GET /graph` - Productivity graph (all projects)
- `GET /graph/:project` - Productivity graph for project

#### 3. Input Validation

**Secret Detection Patterns:**
```python
SECRET_PATTERNS = [
    r'sk-[a-zA-Z0-9]{32,}',           # OpenAI keys
    r'api[_-]?key[_-]?=\s*["\']?[\w-]+',  # Generic API keys
    r'\d{3}-\d{2}-\d{4}',             # SSN format
    r'[A-Z0-9]{20,}',                 # Generic long tokens
    r'password\s*=\s*["\']?[\w-]+',   # Passwords
]

def contains_secret(text: str) -> tuple[bool, str]:
    """Check if text contains secret patterns.
    
    Returns:
        (is_secret, pattern_matched)
    """
    for pattern in SECRET_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return (True, pattern)
    return (False, "")
```

**Validation Rules:**
- Task text: 1-1000 characters, no secrets
- Project ID: Must exist in projects table
- Status: Must be one of four valid values
- Priority: Must be one of four valid values or NULL

#### 4. Database Manager Extensions

```python
class DatabaseManager:
    # ... existing methods ...
    
    def add_task(
        self,
        text: str,
        project_id: str,
        status: str = "Backlog",
        priority: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new task."""
        # Validate inputs
        # Check for secrets
        # Insert into tasks table
        # Record history entry
        # Return task with ID
        
    def get_tasks(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get tasks with optional filtering."""
        
    def update_task(
        self,
        task_id: int,
        **updates
    ) -> Dict[str, Any]:
        """Update task fields."""
        # If status changed, record history
        # If moved to Done, set completed_at
        
    def get_task_history(
        self,
        days: int = 30,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get completion history for graphs."""
```

### Frontend Components

#### 1. Technology Stack

**Core Libraries:**
- **React 18** - UI framework (already in use)
- **Vite** - Build tool (matches tax-organizer pattern)
- **@dnd-kit/core** - Drag-and-drop library
  - Modern, lightweight, performant
  - Better accessibility than react-beautiful-dnd
  - Active maintenance (react-beautiful-dnd is deprecated)
- **Recharts** - Chart library for productivity graphs
  - React-native, composable components
  - SVG-based, responsive
  - Simple API for time series data
- **React Router** - Client-side routing for deep links

**Rationale for @dnd-kit:**
Based on research, @dnd-kit is the clear choice for 2025:
- react-beautiful-dnd is officially deprecated
- @dnd-kit is modern, actively maintained, and performant
- Better accessibility support out of the box
- Smaller bundle size, better tree-shaking

**Rationale for Recharts:**
- React-specific, composable API
- SVG rendering (crisp on all displays)
- Simple for time series (line/bar charts)
- Good documentation and examples

#### 2. Component Hierarchy

```
<App>
  <Router>
    <Navigation />
    <Routes>
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/kanban" element={<KanbanBoard />} />
      <Route path="/kanban/:project" element={<KanbanBoard />} />
      <Route path="/graph" element={<ProductivityGraph />} />
      <Route path="/graph/:project" element={<ProductivityGraph />} />
    </Routes>
  </Router>
</App>

<KanbanBoard>
  <ProjectSidebar
    projects={projects}
    selectedProjects={selectedProjects}
    onToggleProject={handleToggle}
    sortOrder={sortOrder}
    onChangeSortOrder={handleSort}
  />
  <Board>
    <AddTaskButton onClick={handleAddTask} />
    <Column status="Backlog">
      <TaskCard task={task} onDragEnd={handleDragEnd} />
      <TaskCard task={task} onDragEnd={handleDragEnd} />
    </Column>
    <Column status="To Do">
      <TaskCard task={task} onDragEnd={handleDragEnd} />
    </Column>
    <Column status="In Progress">
      <TaskCard task={task} onDragEnd={handleDragEnd} />
    </Column>
    <Column status="Done">
      <TaskCard task={task} onDragEnd={handleDragEnd} />
    </Column>
  </Board>
</KanbanBoard>

<ProductivityGraph>
  <ProjectFilter />
  <TimeRangeSelector />
  <ResponsiveContainer>
    <LineChart data={completionData}>
      <XAxis dataKey="date" />
      <YAxis />
      <Line dataKey="completed" stroke="#51cf66" />
    </LineChart>
  </ResponsiveContainer>
</ProductivityGraph>
```

#### 3. State Management

**Local State (React useState):**
- Current filter selections
- Sidebar collapsed state
- Task detail modal open/closed
- Form input values

**URL State (React Router):**
- Current route (/kanban, /kanban/:project)
- Project filter from URL params
- Graph time range from query params

**Server State (React Query or SWR):**
- Tasks list (cached, auto-refetch)
- Projects list (cached)
- Completion history (cached)

**Persistent State (localStorage):**
- Sidebar collapsed preference
- Sort order preference
- Selected projects (for quick restore)

#### 4. Drag-and-Drop Implementation

```typescript
import { DndContext, DragEndEvent, closestCenter } from '@dnd-kit/core';
import { SortableContext, useSortable } from '@dnd-kit/sortable';

function KanbanBoard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  
  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    
    if (!over) return;
    
    const taskId = active.id;
    const newStatus = over.id; // Column ID is the status
    
    // Optimistic update
    setTasks(prev => 
      prev.map(t => 
        t.id === taskId ? { ...t, status: newStatus } : t
      )
    );
    
    // Persist to server
    try {
      await updateTask(taskId, { status: newStatus });
    } catch (error) {
      // Revert on error
      fetchTasks();
    }
  };
  
  return (
    <DndContext onDragEnd={handleDragEnd} collisionDetection={closestCenter}>
      {/* Columns and cards */}
    </DndContext>
  );
}
```

### MCP Tool Interface

**Tool Definition:**
```json
{
  "name": "kanban_add_task",
  "description": "Create a new task in the Kanban board",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project": {
        "type": "string",
        "description": "Project ID (e.g., 'project-tracker')"
      },
      "text": {
        "type": "string",
        "description": "Task description (1-1000 characters)"
      },
      "status": {
        "type": "string",
        "enum": ["Backlog", "To Do", "In Progress", "Done"],
        "default": "Backlog",
        "description": "Initial task status"
      },
      "priority": {
        "type": "string",
        "enum": ["Critical", "High", "Medium", "Low"],
        "description": "Task priority (optional)"
      }
    },
    "required": ["project", "text"]
  }
}
```

**Implementation (Python MCP Server):**
```python
@mcp_server.tool()
async def kanban_add_task(
    project: str,
    text: str,
    status: str = "Backlog",
    priority: Optional[str] = None
) -> dict:
    """Create a new task in the Kanban board."""
    
    # Validate project exists
    db = DatabaseManager()
    if not db.get_project(project):
        raise ValueError(f"Project '{project}' not found")
    
    # Check for secrets
    is_secret, pattern = contains_secret(text)
    if is_secret:
        raise ValueError(f"Task text contains potential secret: {pattern}")
    
    # Create task
    task = db.add_task(
        text=text,
        project_id=project,
        status=status,
        priority=priority
    )
    
    return {
        "success": True,
        "task": task
    }
```

## Data Models

### Task Model

```python
@dataclass
class Task:
    id: int
    text: str
    status: Literal["Backlog", "To Do", "In Progress", "Done"]
    project_id: str
    priority: Optional[Literal["Critical", "High", "Medium", "Low"]]
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601
    completed_at: Optional[str]  # ISO 8601, set when moved to Done
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "status": self.status,
            "project_id": self.project_id,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at
        }
```

### Task History Model

```python
@dataclass
class TaskHistoryEntry:
    id: int
    task_id: int
    project_id: str
    event_type: Literal["created", "status_changed", "completed"]
    old_status: Optional[str]
    new_status: Optional[str]
    timestamp: str  # ISO 8601
```

### API Response Models

**Task List Response:**
```json
{
  "tasks": [
    {
      "id": 1,
      "text": "Implement drag-and-drop",
      "status": "In Progress",
      "project_id": "project-tracker",
      "priority": "High",
      "created_at": "2026-01-25T10:00:00Z",
      "updated_at": "2026-01-25T14:30:00Z",
      "completed_at": null
    }
  ],
  "total": 1
}
```

**Completion History Response:**
```json
{
  "history": [
    {
      "date": "2026-01-25",
      "completed": 5,
      "project_id": "project-tracker"
    },
    {
      "date": "2026-01-24",
      "completed": 3,
      "project_id": "project-tracker"
    }
  ],
  "total_completed": 8,
  "date_range": {
    "start": "2026-01-01",
    "end": "2026-01-25"
  }
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property Reflection

After analyzing all acceptance criteria, I identified the following redundancies:

**Redundancy Group 1: Task Creation**
- Properties 1.2 (task fields recorded) and 6.5 (task returned with ID) both validate task creation
- **Resolution**: Combine into single comprehensive property about task creation completeness

**Redundancy Group 2: Filtering**
- Properties 1.4 (query by project/status/priority) and 4.2 (toggle project filter) both test filtering
- **Resolution**: Keep separate - one tests API filtering, other tests UI filtering

**Redundancy Group 3: Persistence**
- Properties 3.3 (drag persists to DB), 8.4 (edit persists to DB), and 15.2 (transaction rollback) all test persistence
- **Resolution**: Combine drag and edit into single persistence property; keep rollback separate as error handling

**Redundancy Group 4: Counts**
- Properties 2.4 (column counts), 4.5 (project counts), and 10.4 (dashboard counts) all test counting
- **Resolution**: Combine into single comprehensive counting property

**Redundancy Group 5: URL State**
- Properties 9.2, 9.3, 9.4, 9.5 all test URL state management
- **Resolution**: Combine into single URL state synchronization property

**Redundancy Group 6: Secret Detection**
- Properties 6.4, 14.1, and 14.2 all test secret pattern detection
- **Resolution**: Combine into single secret validation property

**Redundancy Group 7: Timestamps**
- Property 8.5 (updated_at changes) is implied by property 1.2 (timestamps recorded)
- **Resolution**: Remove 8.5 as redundant

**Redundancy Group 8: Sorting**
- Properties 5.1 and 5.2 both test sorting
- **Resolution**: Combine into single sorting property

After reflection, reducing from 40+ testable criteria to 25 unique properties.

### Correctness Properties

Property 1: Task Creation Completeness
*For any* valid task data (text, project, status, priority), creating a task should result in a task object containing all provided fields plus generated fields (id, created_at, updated_at), and querying that task by ID should return the same data
**Validates: Requirements 1.2, 6.5**

Property 2: Query Filtering Accuracy
*For any* set of tasks with various projects, statuses, and priorities, querying with filter parameters should return only tasks matching all specified filters
**Validates: Requirements 1.4**

Property 3: UI Project Filtering
*For any* set of tasks across multiple projects, toggling project filters should show/hide exactly the tasks belonging to those projects
**Validates: Requirements 4.2**

Property 4: Task Counting Accuracy
*For any* distribution of tasks across projects and statuses, the displayed counts (column counts, project counts, dashboard counts) should match the actual number of tasks in each category
**Validates: Requirements 2.4, 4.5, 10.4, 10.3**

Property 5: Drag-and-Drop Status Update
*For any* task and any valid target status, dragging the task to a new column should update the task's status in the database and the UI should reflect the change
**Validates: Requirements 3.1, 3.3**

Property 6: Drag Operation Rollback
*For any* task, if a drag operation fails (network error, validation error), the task should revert to its original status and position
**Validates: Requirements 3.5**

Property 7: Task Detail Display
*For any* task, clicking the task card should display all task metadata (full text, project name, priority, created_at, updated_at)
**Validates: Requirements 8.1, 8.2**

Property 8: Task Edit Persistence
*For any* task, editing the task text should update the task in the database, update the updated_at timestamp, and the changes should persist across page reloads
**Validates: Requirements 8.4, 8.5**

Property 9: URL State Synchronization
*For any* view state (project filter, route), the URL should reflect that state, and navigating to that URL (via bookmark, back/forward, or direct entry) should restore the exact same view state
**Validates: Requirements 9.2, 9.3, 9.4, 9.5**

Property 10: Sidebar State Persistence
*For any* sidebar state (collapsed/expanded, sort order), that state should persist across browser sessions via localStorage
**Validates: Requirements 4.4, 5.4**

Property 11: Project Sorting Correctness
*For any* set of projects, sorting alphabetically should order by name (A-Z or Z-A), and sorting by task count should order by number of open tasks (most-first or least-first)
**Validates: Requirements 5.1, 5.2**

Property 12: Secret Pattern Detection
*For any* string containing secret patterns (API keys, SSNs, passwords), attempting to create a task with that text should either warn the user or block creation depending on confidence level
**Validates: Requirements 6.4, 14.1, 14.2**

Property 13: Form Validation
*For any* task creation form submission, if required fields (text, project) are missing, the form should reject submission and display validation errors
**Validates: Requirements 7.3, 7.4**

Property 14: Task Display Completeness
*For any* task, the task card should display truncated text, project label, and priority indicator (if priority is set)
**Validates: Requirements 2.2, 2.3**

Property 15: Form Submission Success
*For any* valid form submission (with text and project), a task should be created and immediately appear on the board in the correct column
**Validates: Requirements 7.5**

Property 16: Project Validation
*For any* task creation attempt with a non-existent project ID, the system should reject the creation and return an error
**Validates: Requirements 14.3**

Property 17: XSS Sanitization
*For any* task text containing HTML/JavaScript (script tags, event handlers), the system should sanitize the input before storage and display, preventing script execution
**Validates: Requirements 14.4**

Property 18: Transaction Rollback on Error
*For any* database write operation that fails mid-transaction, all changes in that transaction should be rolled back, leaving the database in its pre-operation state
**Validates: Requirements 15.2**

Property 19: Database Lock Retry
*For any* database operation that encounters a lock, the system should retry with exponential backoff until success or max retries reached
**Validates: Requirements 15.5**

Property 20: Migration Completeness
*For any* TODO.md file, after migration, the number of tasks in the database should equal the number of task items in the source file
**Validates: Requirements 11.6**

Property 21: Migration File Archival
*For any* TODO.md file, after successful migration, the file should be moved to an archive location and no longer exist in its original location
**Validates: Requirements 11.7**

Property 22: Graph Project Filtering
*For any* set of completed tasks across multiple projects, filtering the productivity graph by project should show only completion events for that project
**Validates: Requirements 12.3**

Property 23: Task Card Project Styling
*For any* task, the task card should have visual styling (color, badge) that corresponds to its project
**Validates: Requirements 2.3**

Property 24: MCP Tool Task Creation
*For any* valid MCP tool invocation with project and text parameters, a task should be created in the database and returned to the caller
**Validates: Requirements 6.2, 6.5**

Property 25: Dashboard Task Count Integration
*For any* project displayed on the dashboard, the open task count should match the number of tasks in Backlog, To Do, and In Progress statuses for that project
**Validates: Requirements 10.3, 10.4**

## Error Handling

### Error Categories

**1. Validation Errors (400 Bad Request)**
- Missing required fields (text, project)
- Invalid status value (not one of four valid statuses)
- Invalid priority value (not one of four valid priorities or null)
- Task text too long (>1000 characters)
- Task text too short (<1 character)
- Secret pattern detected in text
- Project ID does not exist

**Response Format:**
```json
{
  "error": "validation_error",
  "message": "Task text contains potential secret pattern",
  "details": {
    "field": "text",
    "pattern": "sk-[a-zA-Z0-9]{32,}"
  }
}
```

**2. Not Found Errors (404)**
- Task ID does not exist
- Project ID does not exist
- Route does not exist

**Response Format:**
```json
{
  "error": "not_found",
  "message": "Task with ID 123 not found"
}
```

**3. Database Errors (500 Internal Server Error)**
- SQLite connection failure
- Transaction rollback failure
- Constraint violation
- Disk full

**Response Format:**
```json
{
  "error": "database_error",
  "message": "Failed to create task",
  "details": {
    "operation": "INSERT",
    "table": "tasks"
  }
}
```

**4. Concurrency Errors (409 Conflict)**
- Task was modified by another process
- Optimistic locking failure

**Response Format:**
```json
{
  "error": "conflict",
  "message": "Task was modified by another process",
  "details": {
    "task_id": 123,
    "expected_version": 5,
    "actual_version": 6
  }
}
```

### Error Handling Strategies

**Frontend:**
- Display user-friendly error messages in toast notifications
- Revert optimistic updates on error
- Retry failed requests with exponential backoff (max 3 attempts)
- Log errors to console for debugging

**Backend:**
- Wrap all database operations in try-catch blocks
- Use SQLite transactions for multi-step operations
- Log all errors with context (user action, request ID, timestamp)
- Return appropriate HTTP status codes
- Never expose internal error details to client

**MCP Tool:**
- Validate all inputs before making HTTP requests
- Return structured error objects to agents
- Include actionable error messages
- Log all tool invocations and errors

### Retry Logic

**Database Lock Retry:**
```python
def retry_on_lock(func, max_retries=5):
    """Retry database operation on lock with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                if attempt < max_retries - 1:
                    sleep_time = 2 ** attempt * 0.1  # 0.1s, 0.2s, 0.4s, 0.8s, 1.6s
                    time.sleep(sleep_time)
                    continue
            raise
    raise Exception(f"Failed after {max_retries} retries")
```

**Network Retry (Frontend):**
```typescript
async function fetchWithRetry(url: string, options: RequestInit, maxRetries = 3) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch(url, options);
      if (response.ok) return response;
      if (response.status >= 500 && attempt < maxRetries - 1) {
        await sleep(2 ** attempt * 1000); // 1s, 2s, 4s
        continue;
      }
      throw new Error(`HTTP ${response.status}`);
    } catch (error) {
      if (attempt === maxRetries - 1) throw error;
      await sleep(2 ** attempt * 1000);
    }
  }
}
```

## Testing Strategy

### Dual Testing Approach

This feature requires both unit tests and property-based tests for comprehensive coverage:

**Unit Tests** validate:
- Specific examples and edge cases
- Integration between components
- Error conditions and edge cases
- UI component rendering

**Property Tests** validate:
- Universal properties across all inputs
- Comprehensive input coverage through randomization
- Invariants that must hold for all valid data

Both testing approaches are complementary and required. Unit tests catch concrete bugs in specific scenarios, while property tests verify general correctness across the input space.

### Property-Based Testing Configuration

**Library Selection:**
- **Python Backend**: Use `hypothesis` library for property-based testing
- **TypeScript Frontend**: Use `fast-check` library for property-based testing

**Test Configuration:**
- Minimum 100 iterations per property test (due to randomization)
- Each property test must reference its design document property
- Tag format: `# Feature: kanban-board, Property {number}: {property_text}`

**Example Property Test (Python):**
```python
from hypothesis import given, strategies as st
import pytest

@given(
    text=st.text(min_size=1, max_size=1000),
    project_id=st.sampled_from(["project-tracker", "image-workflow", "trading-copilot"]),
    status=st.sampled_from(["Backlog", "To Do", "In Progress", "Done"]),
    priority=st.one_of(st.none(), st.sampled_from(["Critical", "High", "Medium", "Low"]))
)
def test_task_creation_completeness(text, project_id, status, priority):
    """
    Feature: kanban-board, Property 1: Task Creation Completeness
    For any valid task data, creating a task should result in a task object
    containing all provided fields plus generated fields.
    """
    # Create task
    task = db.add_task(text=text, project_id=project_id, status=status, priority=priority)
    
    # Verify all fields present
    assert task["text"] == text
    assert task["project_id"] == project_id
    assert task["status"] == status
    assert task["priority"] == priority
    assert "id" in task
    assert "created_at" in task
    assert "updated_at" in task
    
    # Verify persistence
    retrieved = db.get_task(task["id"])
    assert retrieved == task
```

**Example Property Test (TypeScript):**
```typescript
import fc from 'fast-check';
import { describe, it, expect } from 'vitest';

describe('Feature: kanban-board, Property 9: URL State Synchronization', () => {
  it('should synchronize URL with view state', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('project-tracker', 'image-workflow', 'trading-copilot'),
        fc.array(fc.constantFrom('Backlog', 'To Do', 'In Progress', 'Done')),
        (project, statuses) => {
          // Set view state
          setProjectFilter(project);
          setStatusFilters(statuses);
          
          // Verify URL updated
          const url = new URL(window.location.href);
          expect(url.pathname).toContain(project);
          
          // Navigate away and back
          window.history.pushState({}, '', '/');
          window.history.back();
          
          // Verify state restored
          expect(getProjectFilter()).toBe(project);
          expect(getStatusFilters()).toEqual(statuses);
        }
      ),
      { numRuns: 100 }
    );
  });
});
```

### Unit Testing Strategy

**Backend Unit Tests:**
- Database operations (CRUD)
- Input validation
- Secret pattern detection
- Migration parsing logic
- API endpoint responses
- Error handling

**Frontend Unit Tests:**
- Component rendering
- User interactions (clicks, drags)
- Form validation
- State management
- Routing behavior

**Integration Tests:**
- End-to-end task creation flow
- Drag-and-drop with persistence
- Migration from TODO.md to database
- MCP tool integration

### Test Coverage Goals

- **Backend**: 90%+ line coverage
- **Frontend**: 80%+ line coverage
- **Property Tests**: All 25 properties implemented
- **Unit Tests**: All edge cases and error conditions covered

### Testing Tools

**Backend:**
- `pytest` - Test runner
- `hypothesis` - Property-based testing
- `pytest-cov` - Coverage reporting
- `sqlite3` - In-memory test database

**Frontend:**
- `vitest` - Test runner
- `fast-check` - Property-based testing
- `@testing-library/react` - Component testing
- `@testing-library/user-event` - User interaction simulation

### Continuous Integration

All tests must pass before merging:
- Run unit tests on every commit
- Run property tests on every PR
- Generate coverage reports
- Fail build if coverage drops below threshold
