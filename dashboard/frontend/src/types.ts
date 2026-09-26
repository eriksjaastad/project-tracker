// Task and related types for Kanban Board

export type TaskStatus =
  | 'Backlog'
  | 'To Do'
  | 'In Progress'
  | 'Review'
  | 'Done';

export type TaskType = 'manual' | 'agent';

export const TASK_STATUSES: TaskStatus[] = [
  'Backlog',
  'To Do',
  'In Progress',
  'Review',
  'Done',
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
  'To Do': 'To Do',
  'In Progress': 'In Progress',
  Review: 'Review',
  Done: 'Done',
};

export const TASK_TYPES: TaskType[] = ['manual', 'agent'];

export const TASK_TYPE_LABELS: Record<TaskType, string> = {
  manual: 'Manual',
  agent: 'Agent',
};
export type TaskPriority = 'Critical' | 'High' | 'Medium' | 'Low';

export interface Task {
  id: number;
  display_id?: number | null;
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
  parent_display_id?: number | null;
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
  blocked_by_display_ids?: number[];
  blocking_tasks?: Task[];
  is_blocked?: boolean;
  incomplete_blocking_ids?: number[];
  incomplete_blocking_display_ids?: number[];
  // Blocker ids that resolve to no task at all. Distinct from
  // incomplete_blocking_ids: those name real unfinished work, these name a
  // broken reference. Both set is_blocked, but only one is fixable by doing
  // the blocking task (#6924).
  unresolved_blocking_ids?: number[];
  sequence_order: number | null;

  // File attachments (#5216)
  attachments?: Attachment[];
}

export interface Attachment {
  id: number;
  task_id: number;
  filename: string;
  stored_name: string;
  mime_type: string | null;
  size_bytes: number;
  uploaded_at: string;
  uploaded_by: string;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  status: string;
  can_create_cards?: boolean;
  blocked_card_reason?: string | null;
  portfolio_group?: string | null;
  portfolio_label?: string | null;
  portfolio_parent?: string | null;
}

export interface NavigationItem {
  id: string;
  label: string;
  href: string;
  match_prefixes: string[];
  navigation_type: 'document' | 'spa';
  active?: boolean;
  children?: NavigationItem[];
}

export interface NavigationResponse {
  title: string;
  items: NavigationItem[];
}

export interface HoloscapeSeriesDay {
  date: string;
  task_created: number | null;
  task_completed: number | null;
  review_entries: number | null;
  review_bounces: number | null;
  commits: number | null;
  github_reviews: number | null;
  prs_opened: number | null;
  prs_merged: number | null;
  ci_success: number | null;
  ci_failure: number | null;
  ci_pending: number | null;
  ci_other: number | null;
  manager_sessions: number | null;
  delegate_sessions: number | null;
  deepseek_cli_sessions: number | null;
  worktree_references: number | null;
  manager_session_minutes: number | null;
  delegate_session_minutes: number | null;
  deepseek_cli_session_minutes: number | null;
  manager_input_tokens: number | null;
  manager_output_tokens: number | null;
  delegate_input_tokens: number | null;
  delegate_output_tokens: number | null;
  deepseek_cli_input_tokens: number | null;
  deepseek_cli_output_tokens: number | null;
  deepseek_cli_cache_read_tokens: number | null;
}

export interface HoloscapeSource {
  status: 'ok' | 'stale' | 'loading' | 'unavailable';
  fetched_at: string | null;
  refreshing?: boolean;
  refresh_error?: string | null;
  coverage?: string | null;
}

export interface HoloscapeSeriesResponse {
  window: { start: string; end: string; timezone: string };
  series: HoloscapeSeriesDay[];
  sources: Record<'board' | 'github' | 'hermes' | 'billing', HoloscapeSource>;
  pr: {
    url: string;
    state: string;
    merged: boolean;
    head_sha: string;
    created_at: string;
    merged_at: string | null;
    commits: number;
    reviews: number;
    cohort_pull_requests?: number;
    workflow_names?: string[];
  } | null;
  models: Record<string, number> | null;
  deepseek_cost_usd: number | null;
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
  markers: AgenticMarker[];
  date_range: {
    start: string;
    end: string;
  };
  project_id?: string | null;
}

export interface AgenticMarker {
  id: string;       // UUID generated on creation
  date: string;     // ISO YYYY-MM-DD
  label: string;    // Display text (max 120 chars)
  source: 'manual' | 'auto';  // manual = user-created, auto = sync daemon
  agent?: string;   // Which agent the marker is about (optional)
}

// Tool invocation stats (WebSearch tracking)
export interface ToolStatsByDate {
  date: string;
  total: number;
}

export interface ToolStatsByProject {
  date: string;
  project: string;
  count: number;
}

export interface ToolStatsByModel {
  date: string;
  model: string;
  count: number;
}

export interface ToolStatsResponse {
  by_date: ToolStatsByDate[];
  by_project: ToolStatsByProject[];
  by_model: ToolStatsByModel[];
  projects: string[];
  models: string[];
}

// Bash error rate (stuck score)
export interface BashStatsByDate {
  date: string;
  error_rate: number;
  total: number;
  errors: number;
}

export interface BashStatsByProject {
  date: string;
  project: string;
  error_rate: number;
}

export interface BashStatsSummary {
  total: number;
  errors: number;
  error_rate: number;
  retries: number;
  retry_rate: number;
  hook_blocks: number;
  hook_block_rate: number;
  auth_errors: number;
  auth_error_rate: number;
}

export interface BashStatsAnomalyByDate {
  date: string;
  retries: number;
  hook_blocks: number;
  auth_errors: number;
  usage_errors: number;
}

export interface BashStatsErrorKind {
  error_kind: string;
  count: number;
}

export interface BashStatsPrefixStat {
  command_prefix: string;
  total: number;
  errors: number;
  hook_blocks: number;
  auth_errors: number;
}

export interface BashStatsCallerTypeStat {
  caller_type: string;
  total: number;
  errors: number;
  error_rate: number;
}

export interface BashStatsResponse {
  by_date: BashStatsByDate[];
  by_project: BashStatsByProject[];
  projects: string[];
  summary?: BashStatsSummary;
  anomalies_by_date?: BashStatsAnomalyByDate[];
  error_kinds?: BashStatsErrorKind[];
  top_prefixes?: BashStatsPrefixStat[];
  by_caller_type?: BashStatsCallerTypeStat[];
}

// Ideas (Task #4583)
export interface Idea {
  id: number;
  text: string;
  created_at: string;
  updated_at: string;
}
