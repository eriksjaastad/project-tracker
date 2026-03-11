// Task and related types for Kanban Board

export type TaskStatus =
  | 'Backlog'
  | 'TRIAGED'
  | 'READY_FOR_PATCH'
  | 'To Do'
  | 'In Progress'
  | 'PR_READY'
  | 'Review'
  | 'Done'
  | 'Cancelled';

export type TaskType = 'manual' | 'agent';

export const TASK_STATUSES: TaskStatus[] = [
  'Backlog',
  'TRIAGED',
  'READY_FOR_PATCH',
  'To Do',
  'In Progress',
  'PR_READY',
  'Review',
  'Done',
  'Cancelled',
];

// UI display statuses (original five-column Kanban)
export const KANBAN_STATUSES: TaskStatus[] = [
  'Backlog',
  'To Do',
  'In Progress',
  'Review',
  'Done',
];

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  Backlog: 'Backlog',
  TRIAGED: 'Triaged',
  READY_FOR_PATCH: 'Ready for Patch',
  'To Do': 'To Do',
  'In Progress': 'In Progress',
  PR_READY: 'PR Ready',
  Review: 'Review',
  Done: 'Done',
  Cancelled: 'Cancelled',
};

export const TASK_TYPES: TaskType[] = ['manual', 'agent'];

export const TASK_TYPE_LABELS: Record<TaskType, string> = {
  manual: 'Manual',
  agent: 'Agent',
};
export type TaskPriority = 'Critical' | 'High' | 'Medium' | 'Low';

export interface Task {
  id: number;
  text: string;
  status: TaskStatus;
  project_id: string;
  priority: TaskPriority | null;
  task_type: TaskType;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  prompt: string | null;
  title: string | null;
  notes: string | null;
  commit_sha: string | null;
  category: string | null;
  review_comment: string | null;

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

export interface NavigationItem {
  id: string;
  label: string;
  href: string;
  match_prefixes: string[];
  navigation_type: 'document' | 'spa';
  active?: boolean;
}

export interface NavigationResponse {
  title: string;
  items: NavigationItem[];
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

export interface AgenticSeriesEntry {
  date: string;
  review_bounces: number;
  review_promotions: number;
  review_entries: number;
}

export interface AgenticSummaryResponse {
  summary: {
    review_bounces: number;
    review_promotions: number;
    review_entries: number;
    bounce_rate: number;
    promotion_rate: number;
  };
  series: AgenticSeriesEntry[];
  markers: {
    date: string;
    label: string;
  }[];
  date_range: {
    start: string;
    end: string;
  };
  project_id?: string | null;
}

// Ideas (Task #4583)
export interface Idea {
  id: number;
  text: string;
  created_at: string;
  updated_at: string;
}
