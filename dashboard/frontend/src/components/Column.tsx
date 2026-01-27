import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import type { Task, TaskStatus } from '../types';
import { TaskCard } from './TaskCard';
import './Column.css';

interface ColumnProps {
  status: TaskStatus;
  tasks: Task[];
  onTaskClick?: (task: Task) => void;
}

const statusLabels: Record<TaskStatus, string> = {
  'Backlog': 'Backlog',
  'To Do': 'To Do',
  'In Progress': 'In Progress',
  'Review': 'Review',
  'Done': 'Done',
};

export function Column({ status, tasks, onTaskClick }: ColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: status,
  });

  const taskIds = tasks.map(task => task.id);

  return (
    <div
      ref={setNodeRef}
      className={`column ${isOver ? 'drag-over' : ''}`}
      data-status={status}
    >
      <div className="column-header">
        <h3 className="column-title">{statusLabels[status]}</h3>
        <span className="column-count">{tasks.length}</span>
      </div>
      <SortableContext items={taskIds} strategy={verticalListSortingStrategy}>
        <div className="column-content">
          {tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onClick={onTaskClick ? () => onTaskClick(task) : undefined}
            />
          ))}
        </div>
      </SortableContext>
    </div>
  );
}
