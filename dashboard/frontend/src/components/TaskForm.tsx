import { useState, useEffect } from 'react';
import type { TaskStatus, TaskPriority, Project, Task, TaskType } from '../types';
import { KANBAN_STATUSES, TASK_STATUS_LABELS, TASK_TYPE_LABELS } from '../types';
import { fetchProjects, fetchTaskPolicy, fetchTasks } from '../api';
import { Spinner } from './Spinner';
import './TaskForm.css';

interface TaskFormProps {
  onSubmit: (data: {
    text: string;
    projectId: string;
    status: TaskStatus;
    priority: TaskPriority | null;
    taskType: TaskType;
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
  const [taskType, setTaskType] = useState<TaskType>('manual');
  const [parentId, setParentId] = useState<number | null>(null);
  const [blockedByInput, setBlockedByInput] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [blockedProjectReasons, setBlockedProjectReasons] = useState<Record<string, string | null>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const PRIORITIES: TaskPriority[] = ['Critical', 'High', 'Medium', 'Low'];
  const eligibleProjects = [...projects]
    .filter((project) => project.can_create_cards !== false)
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));

  useEffect(() => {
    const loadData = async () => {
      try {
        const [projectData, taskData, taskPolicy] = await Promise.all([
          fetchProjects(),
          fetchTasks(),
          fetchTaskPolicy(),
        ]);
        setProjects(projectData);
        setTasks(taskData);
        setBlockedProjectReasons(taskPolicy.blocked_project_reasons || {});
        const allowedProjects = projectData.filter((project) => project.can_create_cards !== false);

        if (initialProjectId) {
          setProjectId(initialProjectId);
        } else if (allowedProjects.length > 0) {
          setProjectId(allowedProjects[0].id);
        } else {
          setProjectId('');
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

    const selectedProject = projects.find((project) => project.id === projectId);
    const blockedReason =
      selectedProject?.can_create_cards === false
        ? selectedProject.blocked_card_reason
        : blockedProjectReasons[projectId];
    if (blockedReason) {
      setError(blockedReason || `Cards cannot be created for project '${projectId}'`);
      return;
    }

    // Parse blocked_by
    let blockedBy: number[] | null = null;
    if (blockedByInput.trim()) {
      try {
        blockedBy = blockedByInput
          .split(',')
          .map((rawId) => parseInt(rawId.trim().replace('#', ''), 10))
          .filter((id) => !isNaN(id))
          .map((enteredId) => {
            const matchedTask = tasks.find((task) => (task.display_id ?? task.id) === enteredId || task.id === enteredId);
            return matchedTask ? matchedTask.id : enteredId;
          });
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
        taskType,
        parentId,
        blockedBy,
      });
      // Reset form on success
      setText('');
      setPriority(null);
      setTaskType('manual');
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
            {eligibleProjects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.portfolio_label ? `${project.portfolio_label} ` : ''}{project.name || project.id}
              </option>
            ))}
          </select>
          {eligibleProjects.length === 0 && (
            <div className="task-form-char-count">No card-enabled projects are available.</div>
          )}
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
            {KANBAN_STATUSES.map((s) => (
              <option key={s} value={s}>
                {TASK_STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>

        <div className="task-form-field">
          <label htmlFor="task-type" className="task-form-label">
            Task Type
          </label>
          <label className="task-type-toggle">
            <input
              id="task-type"
              type="checkbox"
              checked={taskType === 'agent'}
              onChange={(e) => setTaskType(e.target.checked ? 'agent' : 'manual')}
              disabled={loading}
            />
            <span className="task-type-slider" aria-hidden="true" />
            <span className="task-type-text">
              {TASK_TYPE_LABELS[taskType]}
            </span>
          </label>
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
                #{task.display_id ?? task.id} - {task.text.substring(0, 40)}{task.text.length > 40 ? '...' : ''}
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
