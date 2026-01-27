# ProjectSidebar Component

## Overview

The `ProjectSidebar` component implements Phase 3 Task 3.3 from PROPOSAL_FINAL.md. It provides a collapsible sidebar for project filtering and sorting in the Kanban board interface.

## Features Implemented

### ✅ 1. Project Fetching
- Fetches projects from `/api/projects` endpoint
- Handles loading states and error cases gracefully
- Falls back to initial projects prop if fetch fails

### ✅ 2. Project List Display
- Displays all projects with checkboxes
- Visual feedback for selected projects
- Shows project names with proper truncation
- Displays task count badges when sorting by task count

### ✅ 3. Select All / Deselect All
- "Select All" button selects all visible projects
- "Deselect All" button deselects all projects
- Buttons are disabled appropriately based on current selection state
- Handles partial selection states

### ✅ 4. Collapsible Sidebar
- Toggle button to collapse/expand sidebar
- Collapsed state shows only a small toggle button
- Smooth transitions for expand/collapse
- **localStorage persistence**: Collapsed state persists across browser sessions
  - Storage key: `kanban-sidebar-collapsed`

### ✅ 5. Project Sorting
- **Alphabetical**: Sorts projects A-Z by name
- **Task Count**: Sorts by number of tasks (descending), then alphabetically for ties
- Fetches task counts from `/api/tasks?project_id=X` for each project
- **localStorage persistence**: Sort order preference persists across sessions
  - Storage key: `kanban-sidebar-sort-order`

## State Persistence

The component persists the following state in `localStorage`:

1. **Sidebar Collapsed State**
   - Key: `kanban-sidebar-collapsed`
   - Type: `boolean`
   - Restored on component mount

2. **Sort Order Preference**
   - Key: `kanban-sidebar-sort-order`
   - Type: `'alphabetical' | 'task-count'`
   - Restored on component mount

3. **Selected Projects** (handled by parent component)
   - Key: `kanban-selected-projects` (suggested)
   - Type: `string[]` (array of project IDs)
   - See example usage in `ProjectSidebar.example.tsx`

## Component API

### Props

```typescript
interface ProjectSidebarProps {
  projects: Project[];                    // Initial projects (component also fetches)
  selectedProjects: Set<string>;         // Currently selected project IDs
  onToggleProject: (projectId: string) => void;  // Callback when project toggled
  sortOrder: SortOrder;                  // Current sort order
  onChangeSortOrder: (order: SortOrder) => void; // Callback when sort order changes
}
```

### Types

```typescript
type SortOrder = 'alphabetical' | 'task-count';

interface Project {
  id: string;
  name: string;
  path: string;
  status?: string;
  task_count?: number;  // Optional: fetched automatically if not provided
}
```

## Usage Example

See `ProjectSidebar.example.tsx` for a complete integration example.

Basic usage:

```tsx
import { ProjectSidebar } from './components/ProjectSidebar';

function KanbanBoard() {
  const [selectedProjects, setSelectedProjects] = useState<Set<string>>(new Set());
  const [sortOrder, setSortOrder] = useState<SortOrder>('alphabetical');
  const [projects, setProjects] = useState<Project[]>([]);

  const handleToggleProject = (projectId: string) => {
    setSelectedProjects(prev => {
      const next = new Set(prev);
      if (next.has(projectId)) {
        next.delete(projectId);
      } else {
        next.add(projectId);
      }
      return next;
    });
  };

  return (
    <div style={{ display: 'flex' }}>
      <ProjectSidebar
        projects={projects}
        selectedProjects={selectedProjects}
        onToggleProject={handleToggleProject}
        sortOrder={sortOrder}
        onChangeSortOrder={setSortOrder}
      />
      {/* Kanban board content */}
    </div>
  );
}
```

## Styling

The component includes a CSS file (`ProjectSidebar.css`) with:
- Dark theme styling matching the dashboard
- Responsive hover states
- Smooth transitions
- Custom scrollbar styling
- Accessibility-friendly focus states

## Accessibility

- Proper ARIA labels on interactive elements
- Keyboard navigation support
- Screen reader friendly labels
- Semantic HTML structure

## Testing Checklist

- [x] Component fetches projects from `/api/projects`
- [x] Projects display with checkboxes
- [x] Select All / Deselect All functionality works
- [x] Sidebar collapses and expands
- [x] Collapsed state persists in localStorage
- [x] Sort order persists in localStorage
- [x] Alphabetical sorting works
- [x] Task count sorting works
- [x] Task counts are fetched for each project
- [x] Selected projects state is managed by parent

## Files Created

1. `ProjectSidebar.tsx` - Main component implementation
2. `ProjectSidebar.css` - Component styles
3. `ProjectSidebar.example.tsx` - Usage example
4. `ProjectSidebar.README.md` - This documentation

## Next Steps

To integrate this component into the KanbanBoard:

1. Import the component and CSS
2. Set up state management for selected projects
3. Implement the filtering logic in KanbanBoard to filter tasks by selected projects
4. Connect the component to the task filtering system
