import { useMemo } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { Task } from '../types';
import { sanitizeText } from '../utils/sanitize';
import './TaskCard.css';

interface TaskCardProps {
  task: Task;
  onClick?: () => void;
}

export function TaskCard({ task, onClick }: TaskCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  // Sanitize and truncate text (React automatically escapes, but we ensure safety)
  const truncatedText = useMemo(() => {
    const text = sanitizeText(task.text);
    return text.length > 100 ? text.substring(0, 100) + '...' : text;
  }, [task.text]);

  const priorityColors: Record<string, string> = {
    Critical: 'var(--critical)',     // #dc2626 - dark alarm red
    High: 'var(--danger)',           // #ff6b6b - red
    Medium: 'var(--success)',        // #51cf66 - green
    Low: 'var(--accent)',            // #4f9dff - blue
  };

  const priorityColor = task.priority ? priorityColors[task.priority] : undefined;

  const handleClick = (e: React.MouseEvent) => {
    // Don't trigger click when dragging
    if (!isDragging && onClick) {
      e.stopPropagation();
      onClick();
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`task-card ${isDragging ? 'dragging' : ''} ${onClick ? 'clickable' : ''}`}
      {...attributes}
      {...listeners}
      onClick={handleClick}
    >
      {priorityColor && (
        <div
          className="task-card-priority-indicator"
          style={{ backgroundColor: priorityColor }}
        />
      )}
      <div className="task-card-content">
        <p className="task-card-text" title={task.title ? task.text : undefined}>
          {task.title || truncatedText}
        </p>
        <div className="task-card-meta">
          <span className="task-card-project">{task.project_id}</span>
          {task.category && (
            <span className="task-card-category" title="Category">
              {task.category}
            </span>
          )}
          {task.prompt && (
            <span className="task-card-prompt-indicator" title="Has agent prompt">
              🤖
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
