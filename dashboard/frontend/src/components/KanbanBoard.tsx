import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { DndContext, closestCenter, useSensor, useSensors, PointerSensor } from '@dnd-kit/core';
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core';
import type { Task, TaskStatus, TaskPriority } from '../types';
import { fetchTasks, updateTask, createTask, deleteTask, deleteDoneTasks } from '../api';
import { Column } from './Column';
import { Notification } from './Notification';
import { AddTaskButton } from './AddTaskButton';
import { TaskForm } from './TaskForm';
import { TaskDetailModal } from './TaskDetailModal';
import { Spinner } from './Spinner';
import { SkeletonCard } from './SkeletonCard';
import { IdeasSection } from './IdeasSection';
import './KanbanBoard.css';

const STATUSES: TaskStatus[] = ['Backlog', 'To Do', 'In Progress', 'Review', 'Done'];

interface NotificationState {
  message: string;
  type: 'success' | 'error';
  visible: boolean;
}

export function KanbanBoard() {
  const { project } = useParams<{ project?: string }>();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [_draggedTask, setDraggedTask] = useState<Task | null>(null);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [searchTaskId, setSearchTaskId] = useState('');
  const [notification, setNotification] = useState<NotificationState>({
    message: '',
    type: 'success',
    visible: false,
  });

  const showNotification = useCallback((message: string, type: 'success' | 'error') => {
    setNotification({ message, type, visible: true });
  }, []);

  const loadTasks = useCallback(async () => {
    try {
      setLoading(true);
      // Filter by project if URL parameter is present
      const fetchedTasks = await fetchTasks(project);
      setTasks(fetchedTasks);
    } catch (error) {
      console.error('Failed to load tasks:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to load tasks';
      showNotification(errorMessage, 'error');
    } finally {
      setLoading(false);
    }
  }, [project, showNotification]);

  // Load tasks on mount and when project param changes
  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  const handleSearchTask = () => {
    const taskId = parseInt(searchTaskId.replace('#', ''));
    if (isNaN(taskId)) {
      showNotification('Please enter a valid task ID', 'error');
      return;
    }
    const task = tasks.find(t => t.id === taskId);
    if (task) {
      setSelectedTask(task);
      setSearchTaskId('');
    } else {
      showNotification(`Task #${taskId} not found`, 'error');
    }
  };

  const handleDragStart = (event: DragStartEvent) => {
    const task = tasks.find(t => t.id === event.active.id);
    setDraggedTask(task || null);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setDraggedTask(null);

    if (!over) {
      return;
    }

    const taskId = active.id as number;

    // Determine the target status - over.id could be a column status or a task ID
    let newStatus: TaskStatus;
    if (STATUSES.includes(over.id as TaskStatus)) {
      // Dropped on a column
      newStatus = over.id as TaskStatus;
    } else {
      // Dropped on another task - get that task's status
      const targetTask = tasks.find(t => t.id === over.id);
      if (!targetTask) {
        return;
      }
      newStatus = targetTask.status;
    }

    // Find the task being moved
    const task = tasks.find(t => t.id === taskId);
    if (!task) {
      return;
    }

    // Don't do anything if dropped in the same column
    if (task.status === newStatus) {
      return;
    }

    // Store original state for potential rollback
    const originalTasks = [...tasks];

    // Optimistic update: Update local state immediately
    setTasks(prev =>
      prev.map(t =>
        t.id === taskId ? { ...t, status: newStatus } : t
      )
    );

    // Persist to server
    try {
      await updateTask(taskId, { status: newStatus });
      showNotification(`Task moved to ${newStatus}`, 'success');
    } catch (error) {
      // Revert on error
      console.error('Failed to update task:', error);
      setTasks(originalTasks);
      showNotification(
        `Failed to move task: ${error instanceof Error ? error.message : 'Unknown error'}`,
        'error'
      );
    }
  };

  const handleCreateTask = useCallback(async (data: {
    text: string;
    projectId: string;
    status: TaskStatus;
    priority: TaskPriority | null;
    parentId?: number | null;
    blockedBy?: number[] | null;
  }) => {
    try {
      const newTask = await createTask(
        data.text,
        data.projectId,
        data.status,
        data.priority,
        data.parentId,
        data.blockedBy
      );
      setTasks(prev => [...prev, newTask]);
      setShowTaskForm(false);
      showNotification('Task created successfully', 'success');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to create task';
      showNotification(errorMessage, 'error');
      throw error; // Let TaskForm handle the error display
    }
  }, [showNotification]);

  const handleTaskClick = (task: Task) => {
    setSelectedTask(task);
  };

  const handleTaskUpdate = () => {
    loadTasks(); // Reload tasks to get updated data
    setSelectedTask(null);
  };

  const handleTaskDelete = useCallback(async (taskId: number) => {
    try {
      await deleteTask(taskId);
      setTasks(prev => prev.filter(t => t.id !== taskId));
      showNotification('Task deleted successfully', 'success');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to delete task';
      showNotification(errorMessage, 'error');
      throw error; // Let TaskDetailModal handle the error display
    }
  }, []);

  const handleDeleteDone = useCallback(async () => {
    const doneCount = tasks.filter(t => t.status === 'Done').length;
    if (doneCount === 0) {
      showNotification('No Done tasks to delete', 'error');
      return;
    }

    if (!confirm(`Delete ${doneCount} Done task(s)?`)) {
      return;
    }

    try {
      const result = await deleteDoneTasks(project);
      setTasks(prev => prev.filter(t => t.status !== 'Done'));
      showNotification(`Deleted ${result.deleted} Done task(s)`, 'success');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to delete done tasks';
      showNotification(errorMessage, 'error');
    }
  }, [tasks, project, showNotification]);

  // Group tasks by status (memoized for performance)
  const tasksByStatus = useMemo(() => {
    return STATUSES.reduce((acc, status) => {
      acc[status] = tasks.filter(task => task.status === status);
      return acc;
    }, {} as Record<TaskStatus, Task[]>);
  }, [tasks]);

  // Require 8px of movement before drag starts, so clicks work
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  if (loading) {
    return (
      <div className="kanban-board-loading">
        <div className="kanban-board-loading-content">
          <Spinner size="large" />
          <p>Loading tasks...</p>
        </div>
        <div className="kanban-board-skeleton">
          {STATUSES.map((status) => (
            <div key={status} className="column-skeleton">
              <div className="column-skeleton-header">
                <h3>{status}</h3>
              </div>
              <SkeletonCard count={3} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="kanban-board">
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="kanban-board-header">
          <h1>Kanban Board{project ? ` - ${project}` : ''}</h1>
          <div className="kanban-board-header-actions">
            <div className="task-search">
              <input
                type="text"
                placeholder="Search by #ID..."
                value={searchTaskId}
                onChange={(e) => setSearchTaskId(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSearchTask()}
                className="task-search-input"
              />
              <button onClick={handleSearchTask} className="task-search-button">
                🔍
              </button>
            </div>
            <AddTaskButton onClick={() => setShowTaskForm(true)} />
            <button onClick={handleDeleteDone} className="delete-done-button">
              Delete Done
            </button>
            <button onClick={loadTasks} className="refresh-button">
              Refresh
            </button>
          </div>
        </div>
        <IdeasSection />
        <div className="kanban-board-content">
          {STATUSES.map((status) => (
            <Column
              key={status}
              status={status}
              tasks={tasksByStatus[status]}
              onTaskClick={handleTaskClick}
            />
          ))}
        </div>
      </DndContext>
      {notification.visible && (
        <Notification
          message={notification.message}
          type={notification.type}
          onClose={() => setNotification(prev => ({ ...prev, visible: false }))}
        />
      )}
      {showTaskForm && (
        <div className="modal-overlay" onClick={() => setShowTaskForm(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <TaskForm
              onSubmit={handleCreateTask}
              onCancel={() => setShowTaskForm(false)}
              initialProjectId={project}
            />
          </div>
        </div>
      )}
      {selectedTask && (
        <TaskDetailModal
          task={selectedTask}
          onClose={() => setSelectedTask(null)}
          onUpdate={handleTaskUpdate}
          onDelete={handleTaskDelete}
        />
      )}
    </div>
  );
}
