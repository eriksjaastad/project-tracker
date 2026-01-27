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
