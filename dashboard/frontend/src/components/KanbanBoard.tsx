import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { DndContext, rectIntersection, useSensor, useSensors, PointerSensor } from '@dnd-kit/core';
import type { DragEndEvent } from '@dnd-kit/core';
import type { Task, TaskStatus, TaskPriority, TaskType } from '../types';
import { KANBAN_STATUSES, TASK_STATUS_LABELS } from '../types';
import { fetchTasks, updateTask, createTask, deleteTask } from '../api';
import { Column } from './Column';
import { Notification } from './Notification';
import { AddTaskButton } from './AddTaskButton';
import { TaskForm } from './TaskForm';
import { TaskDetailModal } from './TaskDetailModal';
import { ProjectFilterModal } from './ProjectFilterModal';
import { WarningBanner } from './WarningBanner';
import { Spinner } from './Spinner';
import { SkeletonCard } from './SkeletonCard';
import { IdeasSection } from './IdeasSection';
import { PageShell } from './PageShell';
import './KanbanBoard.css';

interface NotificationState {
  message: string;
  type: 'success' | 'error';
  visible: boolean;
}

interface SystemWarning {
  id: string;
  message: string;
  type: 'error' | 'warning' | 'info';
  actionLabel?: string;
  actionUrl?: string;
}

export function KanbanBoard() {
  const { project } = useParams<{ project?: string }>();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [searchTaskId, setSearchTaskId] = useState('');
  const [showProjectFilter, setShowProjectFilter] = useState(false);
  const [systemWarnings, setSystemWarnings] = useState<SystemWarning[]>([]);
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

  useEffect(() => {
    const loadWarnings = async () => {
      try {
        const response = await fetch('/api/system/warnings');
        if (!response.ok) {
          return;
        }
        const data = await response.json();
        if (Array.isArray(data.warnings)) {
          setSystemWarnings(data.warnings);
        }
      } catch {
        // Optional endpoint - ignore failures
      }
    };

    loadWarnings();
  }, []);

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

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;

    if (!over) {
      return;
    }

    const taskId = active.id as number;

    // Determine the target status - over.id could be a column status or a task ID
    let newStatus: TaskStatus;
    if (KANBAN_STATUSES.includes(over.id as TaskStatus)) {
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

    if (
      task.status === 'To Do' &&
      newStatus === 'In Progress' &&
      task.task_type === 'agent' &&
      !task.prompt
    ) {
      const proceed = confirm(
        'Agent task has no prompt. Move to In Progress anyway?'
      );
      if (!proceed) {
        return;
      }
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
    taskType: TaskType;
    parentId?: number | null;
    blockedBy?: number[] | null;
  }) => {
    try {
      const newTask = await createTask(
        data.text,
        data.projectId,
        data.status,
        data.priority,
        data.taskType,
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
  }, [showNotification]);

  // Group tasks by status (memoized for performance)
  const tasksByStatus = useMemo(() => {
    return KANBAN_STATUSES.reduce((acc, status) => {
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

  const headerActions = (
    <>
      <button
        className="project-filter-button"
        onClick={() => setShowProjectFilter(true)}
        type="button"
      >
        {project || 'All Projects'}
        <span className="project-filter-caret">▼</span>
      </button>
      <div className="task-search">
        <input
          type="text"
          placeholder="Search by #ID..."
          value={searchTaskId}
          onChange={(e) => setSearchTaskId(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              handleSearchTask();
            }
          }}
          className="task-search-input"
        />
        <button onClick={handleSearchTask} className="task-search-button" type="button">
          🔍
        </button>
      </div>
      <AddTaskButton onClick={() => setShowTaskForm(true)} />
      <button onClick={loadTasks} className="refresh-button" type="button">
        Refresh
      </button>
    </>
  );

  return (
    <PageShell title="Kanban Board" actions={headerActions}>
      {loading ? (
        <div className="kanban-board-loading">
          <div className="kanban-board-loading-content">
            <Spinner size="large" />
            <p>Loading tasks...</p>
          </div>
          <div className="kanban-board-skeleton">
            {KANBAN_STATUSES.map((status) => (
              <div key={status} className="column-skeleton">
                <div className="column-skeleton-header">
                  <h3>{TASK_STATUS_LABELS[status]}</h3>
                </div>
                <SkeletonCard count={3} />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="kanban-board">
          {systemWarnings.map((warning) => (
            <WarningBanner
              key={warning.id}
              message={warning.message}
              type={warning.type}
              onDismiss={() => setSystemWarnings(prev => prev.filter(w => w.id !== warning.id))}
              actionLabel={warning.actionLabel}
              onAction={
                warning.actionUrl
                  ? () => {
                    window.location.href = warning.actionUrl!;
                  }
                  : undefined
              }
            />
          ))}
          <DndContext
            sensors={sensors}
            collisionDetection={rectIntersection}
            onDragEnd={handleDragEnd}
          >
            <IdeasSection />
            <div className="kanban-board-content">
              {KANBAN_STATUSES.map((status) => (
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
          {showProjectFilter && (
            <ProjectFilterModal
              isOpen={showProjectFilter}
              onClose={() => setShowProjectFilter(false)}
              currentProject={project}
            />
          )}
        </div>
      )}
    </PageShell>
  );
}
