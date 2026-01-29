import { useState, useEffect } from 'react';
import type { TaskStatus, TaskPriority, Project, Task } from '../types';
import { fetchProjects, fetchTasks } from '../api';
import { Spinner } from './Spinner';
import './TaskForm.css';

interface TaskFormProps {
  onSubmit: (data: {
    text: string;
    projectId: string;
    status: TaskStatus;
    priority: TaskPriority | null;
    parentId?: number | null;
    blockedBy?: number[] | null;
  }) => Promise<void>;
  onCancel: () => void;
  initialProjectId?: string;
  initialStatus?: TaskStatus;
}

export function TaskForm({
  onSubmit,
  onCancel,
  initialProjectId,
  initialStatus = 'Backlog',
}: TaskFormProps) {
  const [text, setText] = useState('');
  const [projectId, setProjectId] = useState(initialProjectId || '');
  const [status, setStatus] = useState<TaskStatus>(initialStatus);
  const [priority, setPriority] = useState<TaskPriority | null>(null);
  const [parentId, setParentId] = useState<number | null>(null);
  const [blockedByInput, setBlockedByInput] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const STATUSES: TaskStatus[] = ['Backlog', 'To Do', 'In Progress', 'Review', 'Done'];
  const PRIORITIES: TaskPriority[] = ['Critical', 'High', 'Medium', 'Low'];

  useEffect(() => {
    const loadData = async () => {
      try {
        const [fetchedProjects, fetchedTasks] = await Promise.all([
          fetchProjects(),
          fetchTasks()
        ]);
        setProjects(fetchedProjects);
        setTasks(fetchedTasks);
        // If no initial project ID and projects exist, select first one
        if (!initialProjectId && fetchedProjects.length > 0) {
          setProjectId(fetchedProjects[0].id);
        }
      } catch (err) {
        console.error('Failed to load data:', err);
        setError('Failed to load projects and tasks');
      }
    };

    loadData();
  }, [initialProjectId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!text.trim()) {
      setError('Task text is required');
      return;
    }

    if (!projectId) {
      setError('Please select a project');
      return;
    }

    // Parse blocked_by
    let blockedBy: number[] | null = null;
    if (blockedByInput.trim()) {
      try {
        blockedBy = blockedByInput.split(',').map(id => parseInt(id.trim())).filter(id => !isNaN(id));
        if (blockedBy.length === 0) blockedBy = null;
      } catch {
        setError('Invalid task IDs in blocked-by field');
        return;
      }
    }

    setLoading(true);
    try {
      await onSubmit({
        text: text.trim(),
        projectId,
        status,
        priority,
        parentId,
        blockedBy,
      });
      // Reset form on success
      setText('');
      setPriority(null);
      setParentId(null);
      setBlockedByInput('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create task');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="task-form" onSubmit={handleSubmit}>
      <div className="task-form-header">
        <h2>Create New Task</h2>
        <button
          type="button"
          className="task-form-close"
          onClick={onCancel}
          aria-label="Close"
        >
          &times;
        </button>
      </div>

      {error && (
        <div className="task-form-error" role="alert">
          {error}
        </div>
      )}

      <div className="task-form-field">
        <label htmlFor="task-text" className="task-form-label">
          Task Description <span className="required">*</span>
        </label>
        <textarea
          id="task-text"
          className="task-form-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Enter task description..."
          rows={4}
          required
          disabled={loading}
        />
        <div className="task-form-char-count">
          {text.length} characters
        </div>
      </div>

      <div className="task-form-row">
        <div className="task-form-field">
          <label htmlFor="task-project" className="task-form-label">
            Project <span className="required">*</span>
          </label>
          <select
            id="task-project"
            className="task-form-select"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            required
            disabled={loading}
          >
            <option value="">Select a project...</option>
            {[...projects].sort((a, b) =>
              a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
            ).map((project) => (
              <option key={project.id} value={project.id}>
                {project.name || project.id}
              </option>
            ))}
          </select>
        </div>

        <div className="task-form-field">
          <label htmlFor="task-status" className="task-form-label">
            Status
          </label>
          <select
            id="task-status"
            className="task-form-select"
            value={status}
            onChange={(e) => setStatus(e.target.value as TaskStatus)}
            disabled={loading}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="task-form-row">
        <div className="task-form-field">
          <label htmlFor="task-priority" className="task-form-label">
            Priority
          </label>
          <select
            id="task-priority"
            className="task-form-select"
            value={priority || ''}
            onChange={(e) =>
              setPriority(e.target.value ? (e.target.value as TaskPriority) : null)
            }
            disabled={loading}
          >
            <option value="">None</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <div className="task-form-field">
          <label htmlFor="task-parent" className="task-form-label">
            Parent Task (optional)
          </label>
          <select
            id="task-parent"
            className="task-form-select"
            value={parentId || ''}
            onChange={(e) => setParentId(e.target.value ? parseInt(e.target.value) : null)}
            disabled={loading}
          >
            <option value="">None (top-level task)</option>
            {tasks.filter(t => t.parent_id === null && t.project_id === projectId).map((task) => (
              <option key={task.id} value={task.id}>
                #{task.id} - {task.text.substring(0, 40)}{task.text.length > 40 ? '...' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="task-form-field">
        <label htmlFor="task-blocked-by" className="task-form-label">
          Blocked By (optional)
        </label>
        <input
          id="task-blocked-by"
          type="text"
          className="task-form-select"
          value={blockedByInput}
          onChange={(e) => setBlockedByInput(e.target.value)}
          placeholder="Comma-separated task IDs (e.g., 4645, 4646)"
          disabled={loading}
        />
        <div className="task-form-hint">
          Enter task IDs this task depends on, separated by commas
        </div>
      </div>

      <div className="task-form-actions">
        <button
          type="button"
          className="task-form-button task-form-button-cancel"
          onClick={onCancel}
          disabled={loading}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="task-form-button task-form-button-submit"
          disabled={loading || !text.trim() || !projectId}
        >
          {loading ? (
            <>
              <Spinner size="small" />
              <span>Creating...</span>
            </>
          ) : (
            'Create Task'
          )}
        </button>
      </div>
    </form>
  );
}
