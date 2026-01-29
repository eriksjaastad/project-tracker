// Task and related types for Kanban Board

export type TaskStatus = 'Backlog' | 'To Do' | 'In Progress' | 'Review' | 'Done';
export type TaskPriority = 'Critical' | 'High' | 'Medium' | 'Low';

export interface Task {
  id: number;
  text: string;
  status: TaskStatus;
  project_id: string;
  priority: TaskPriority | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  prompt: string | null;
  title: string | null;
  notes: string | null;
  commit_sha: string | null;
  category: string | null;

  // Parent-child relationships (Task #4645)
  parent_id: number | null;
  subtasks?: Task[];
  subtask_progress?: {
    total: number;
    done: number;
    percent: number;
  };
  parent?: Task;

  // Task dependencies (Task #4579)
  blocked_by: string | null;  // JSON array as string
  blocked_by_ids?: number[];
  blocking_tasks?: Task[];
  is_blocked?: boolean;
  incomplete_blocking_ids?: number[];
  sequence_order: number | null;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  status: string;
}

export interface TaskHistoryEntry {
  date: string;
  completed: number;
  project_id?: string;
}

export interface TaskHistoryResponse {
  history: TaskHistoryEntry[];
  total_completed: number;
  date_range: {
    start: string;
    end: string;
  };
}

// Ideas (Task #4583)
export interface Idea {
  id: number;
  text: string;
  created_at: string;
  updated_at: string;
}
