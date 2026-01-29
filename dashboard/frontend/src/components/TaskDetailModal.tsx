import { useState, useEffect } from 'react';
import type { Task, TaskStatus, TaskPriority, Project } from '../types';
import { updateTask, fetchProjects } from '../api';
import './TaskDetailModal.css';

interface TaskDetailModalProps {
  task: Task | null;
  onClose: () => void;
  onUpdate: () => void;
  onDelete?: (taskId: number) => Promise<void>;
}

export function TaskDetailModal({
  task,
  onClose,
  onUpdate,
  onDelete,
}: TaskDetailModalProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedText, setEditedText] = useState('');
  const [editedTitle, setEditedTitle] = useState('');
  const [editedNotes, setEditedNotes] = useState('');
  const [editedCommitSha, setEditedCommitSha] = useState('');
  const [editedCategory, setEditedCategory] = useState('');
  const [editedStatus, setEditedStatus] = useState<TaskStatus>('Backlog');
  const [editedPriority, setEditedPriority] = useState<TaskPriority | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const STATUSES: TaskStatus[] = ['Backlog', 'To Do', 'In Progress', 'Review', 'Done'];
  const PRIORITIES: TaskPriority[] = ['Critical', 'High', 'Medium', 'Low'];

  useEffect(() => {
    if (task) {
      setEditedText(task.text);
      setEditedTitle(task.title || '');
      setEditedNotes(task.notes || '');
      setEditedCommitSha(task.commit_sha || '');
      setEditedCategory(task.category || '');
      setEditedStatus(task.status);
      setEditedPriority(task.priority);
      setIsEditing(false);
      setError(null);
    }
  }, [task]);

  useEffect(() => {
    const loadProjects = async () => {
      try {
        const fetchedProjects = await fetchProjects();
        setProjects(fetchedProjects);
      } catch (err) {
        console.error('Failed to load projects:', err);
      }
    };

    loadProjects();
  }, []);

  if (!task) {
    return null;
  }

  const project = projects.find((p) => p.id === task.project_id);

  const handleSave = async () => {
    if (!editedText.trim()) {
      setError('Task text cannot be empty');
      return;
    }


    setLoading(true);
    setError(null);

    try {
      await updateTask(task.id, {
        text: editedText.trim(),
        title: editedTitle.trim() || null,
        notes: editedNotes.trim() || null,
        commit_sha: editedCommitSha.trim() || null,
        category: editedCategory.trim() || null,
        status: editedStatus,
        priority: editedPriority,
      });
      setIsEditing(false);
      onUpdate();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update task');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setEditedText(task.text);
    setEditedTitle(task.title || '');
    setEditedNotes(task.notes || '');
    setEditedCommitSha(task.commit_sha || '');
    setEditedCategory(task.category || '');
    setEditedStatus(task.status);
    setEditedPriority(task.priority);
    setIsEditing(false);
    setError(null);
  };

  const handleDelete = async () => {
    if (!onDelete) return;

    const confirmed = window.confirm(
      'Are you sure you want to delete this task? This action cannot be undone.'
    );

    if (!confirmed) return;

    setDeleting(true);
    setError(null);

    try {
      await onDelete(task.id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete task');
    } finally {
      setDeleting(false);
    }
  };

  const priorityColors: Record<string, string> = {
    Critical: 'var(--critical)',
    High: 'var(--danger)',
    Medium: 'var(--success)',
    Low: 'var(--accent)',
  };

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
    }
  };

  return (
    <div className="task-detail-modal-overlay" onClick={onClose}>
      <div
        className="task-detail-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="task-detail-modal-header">
          <div className="task-detail-header-left">
            <h2>Task Details</h2>
            <button
              className="task-id-copy-button"
              onClick={() => {
                navigator.clipboard.writeText(`#${task.id}`);
                // Could show a toast notification here
              }}
              title="Copy task ID"
            >
              #{task.id}
            </button>
          </div>
          <button
            className="task-detail-modal-close"
            onClick={onClose}
            aria-label="Close modal"
          >
            ×
          </button>
        </div>

        {error && (
          <div className="task-detail-modal-error" role="alert">
            {error}
          </div>
        )}

        <div className="task-detail-modal-content">
          {isEditing ? (
            <>
              <div className="task-detail-field">
                <label className="task-detail-label">
                  Title (short name for card)
                </label>
                <input
                  type="text"
                  className="task-detail-select"
                  value={editedTitle}
                  onChange={(e) => setEditedTitle(e.target.value)}
                  placeholder="Optional short title..."
                  maxLength={100}
                  disabled={loading}
                />
              </div>

              <div className="task-detail-field">
                <label className="task-detail-label">
                  Task Description <span className="required">*</span>
                </label>
                <textarea
                  className="task-detail-textarea"
                  value={editedText}
                  onChange={(e) => setEditedText(e.target.value)}
                  rows={6}
                  disabled={loading}
                />
                <div className="task-detail-char-count">
                  {editedText.length} characters
                </div>
              </div>

              <div className="task-detail-field">
                <label className="task-detail-label">
                  Notes (internal)
                </label>
                <textarea
                  className="task-detail-textarea"
                  value={editedNotes}
                  onChange={(e) => setEditedNotes(e.target.value)}
                  rows={4}
                  placeholder="Optional notes, context, or comments..."
                  disabled={loading}
                />
              </div>

              <div className="task-detail-field">
                <label className="task-detail-label">
                  Commit SHA / PR Link
                </label>
                <input
                  type="text"
                  className="task-detail-select"
                  value={editedCommitSha}
                  onChange={(e) => setEditedCommitSha(e.target.value)}
                  placeholder="Optional commit hash or PR URL..."
                  disabled={loading}
                  style={{ fontFamily: 'monospace', fontSize: '0.9rem' }}
                />
              </div>

              <div className="task-detail-row">
                <div className="task-detail-field">
                  <label className="task-detail-label">Status</label>
                  <select
                    className="task-detail-select"
                    value={editedStatus}
                    onChange={(e) =>
                      setEditedStatus(e.target.value as TaskStatus)
                    }
                    disabled={loading}
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="task-detail-field">
                  <label className="task-detail-label">Priority</label>
                  <select
                    className="task-detail-select"
                    value={editedPriority || ''}
                    onChange={(e) =>
                      setEditedPriority(
                        e.target.value
                          ? (e.target.value as TaskPriority)
                          : null
                      )
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

                <div className="task-detail-field">
                  <label className="task-detail-label">Category</label>
                  <input
                    type="text"
                    className="task-detail-select"
                    value={editedCategory}
                    onChange={(e) => setEditedCategory(e.target.value)}
                    placeholder="e.g. ui, api, database..."
                    disabled={loading}
                  />
                </div>
              </div>
            </>
          ) : (
            <>
              {task.title && (
                <div className="task-detail-field">
                  <label className="task-detail-label">Title</label>
                  <div className="task-detail-value">{task.title}</div>
                </div>
              )}

              <div className="task-detail-field">
                <label className="task-detail-label">Task Description</label>
                <div className="task-detail-text">{task.text}</div>
              </div>

              {task.notes && (
                <div className="task-detail-field">
                  <label className="task-detail-label">Notes</label>
                  <div className="task-detail-text">{task.notes}</div>
                </div>
              )}

              {task.prompt && (
                <div className="task-detail-field">
                  <label className="task-detail-label">Agent Prompt</label>
                  <div className="task-detail-prompt">{task.prompt}</div>
                </div>
              )}

              <div className="task-detail-row">
                <div className="task-detail-field">
                  <label className="task-detail-label">Project</label>
                  <div className="task-detail-value">
                    {project?.name || task.project_id}
                  </div>
                </div>

                <div className="task-detail-field">
                  <label className="task-detail-label">Status</label>
                  <div className="task-detail-value">{task.status}</div>
                </div>
              </div>

              <div className="task-detail-row">
                <div className="task-detail-field">
                  <label className="task-detail-label">Priority</label>
                  <div className="task-detail-value">
                    {task.priority ? (
                      <span
                        className="task-detail-priority-badge"
                        style={{
                          backgroundColor:
                            priorityColors[task.priority] || 'transparent',
                        }}
                      >
                        {task.priority}
                      </span>
                    ) : (
                      'None'
                    )}
                  </div>
                </div>

                {task.category && (
                  <div className="task-detail-field">
                    <label className="task-detail-label">Category</label>
                    <div className="task-detail-value">
                      <span className="task-detail-category-badge">
                        {task.category}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              <div className="task-detail-field">
                <label className="task-detail-label">Created</label>
                <div className="task-detail-value">
                  {formatDate(task.created_at)}
                </div>
              </div>

              {task.updated_at !== task.created_at && (
                <div className="task-detail-field">
                  <label className="task-detail-label">Last Updated</label>
                  <div className="task-detail-value">
                    {formatDate(task.updated_at)}
                  </div>
                </div>
              )}

              {task.completed_at && (
                <div className="task-detail-field">
                  <label className="task-detail-label">Completed</label>
                  <div className="task-detail-value">
                    {formatDate(task.completed_at)}
                  </div>
                </div>
              )}

              {task.commit_sha && (
                <div className="task-detail-field">
                  <label className="task-detail-label">Commit/PR</label>
                  <div className="task-detail-value" style={{ fontFamily: 'monospace' }} title={task.commit_sha}>
                    {task.commit_sha.substring(0, 12)}
                  </div>
                </div>
              )}

              {/* Parent task indicator (Task #4645) */}
              {task.parent_id && (
                <div className="task-detail-field">
                  <label className="task-detail-label">Parent Task</label>
                  <div className="task-detail-value">
                    <span className="task-detail-link">#{task.parent_id}</span>
                    {task.parent && <span className="task-detail-muted"> - {task.parent.text.substring(0, 50)}</span>}
                  </div>
                </div>
              )}

              {/* Subtasks list (Task #4645) */}
              {task.subtasks && task.subtasks.length > 0 && (
                <div className="task-detail-field">
                  <label className="task-detail-label">
                    Subtasks ({task.subtask_progress?.done}/{task.subtask_progress?.total})
                  </label>
                  <div className="task-detail-subtasks">
                    {task.subtasks.map((subtask) => (
                      <div key={subtask.id} className="task-detail-subtask-item">
                        <span className={`subtask-status-${subtask.status.toLowerCase().replace(' ', '-')}`}>
                          {subtask.status === 'Done' ? '✅' : subtask.status === 'In Progress' ? '●' : '○'}
                        </span>
                        <span>#{subtask.id} - {subtask.text.substring(0, 60)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Blocking tasks (Task #4579) */}
              {task.blocking_tasks && task.blocking_tasks.length > 0 && (
                <div className="task-detail-field">
                  <label className="task-detail-label">
                    {task.is_blocked ? '🔒 Blocked By (incomplete)' : 'Blocked By'}
                  </label>
                  <div className="task-detail-blocking-tasks">
                    {task.blocking_tasks.map((blocker) => (
                      <div key={blocker.id} className={`task-detail-blocker-item ${blocker.status !== 'Done' ? 'blocker-incomplete' : ''}`}>
                        <span>#{blocker.id} - {blocker.text.substring(0, 60)}</span>
                        <span className="blocker-status">[{blocker.status}]</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="task-detail-modal-actions">
          {isEditing ? (
            <>
              <button
                className="task-detail-button task-detail-button-cancel"
                onClick={handleCancel}
                disabled={loading}
              >
                Cancel
              </button>
              <button
                className="task-detail-button task-detail-button-save"
                onClick={handleSave}
                disabled={loading || !editedText.trim()}
              >
                {loading ? 'Saving...' : 'Save Changes'}
              </button>
            </>
          ) : (
            <>
              {onDelete && (
                <button
                  className="task-detail-button task-detail-button-delete"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? 'Deleting...' : 'Delete Task'}
                </button>
              )}
              <button
                className="task-detail-button task-detail-button-edit"
                onClick={() => setIsEditing(true)}
              >
                Edit Task
              </button>
            </>
          )}
        </div>
      </div >
    </div >
  );
}
