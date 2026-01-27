import { useState, useEffect } from 'react';
import type { TaskStatus, TaskPriority, Project } from '../types';
import { fetchProjects } from '../api';
import { Spinner } from './Spinner';
import './TaskForm.css';

interface TaskFormProps {
  onSubmit: (data: {
    text: string;
    projectId: string;
    status: TaskStatus;
    priority: TaskPriority | null;
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
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const STATUSES: TaskStatus[] = ['Backlog', 'To Do', 'In Progress', 'Review', 'Done'];
  const PRIORITIES: TaskPriority[] = ['Critical', 'High', 'Medium', 'Low'];

  useEffect(() => {
    const loadProjects = async () => {
      try {
        const fetchedProjects = await fetchProjects();
        setProjects(fetchedProjects);
        // If no initial project ID and projects exist, select first one
        if (!initialProjectId && fetchedProjects.length > 0) {
          setProjectId(fetchedProjects[0].id);
        }
      } catch (err) {
        console.error('Failed to load projects:', err);
        setError('Failed to load projects');
      }
    };

    loadProjects();
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

    if (text.length > 1000) {
      setError('Task text must be 1000 characters or less');
      return;
    }

    setLoading(true);
    try {
      await onSubmit({
        text: text.trim(),
        projectId,
        status,
        priority,
      });
      // Reset form on success
      setText('');
      setPriority(null);
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
          maxLength={1000}
          required
          disabled={loading}
        />
        <div className="task-form-char-count">
          {text.length} / 1000 characters
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
            {projects.map((project) => (
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
