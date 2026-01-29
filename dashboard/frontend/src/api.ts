// API client for Kanban Board

import type { Task, TaskStatus, TaskPriority, TaskHistoryResponse } from './types';

const API_BASE = '/api';

/**
 * Enhanced fetch with error handling and retry logic.
 */
async function fetchWithErrorHandling(
  url: string,
  options: RequestInit = {},
  retries = 3
): Promise<Response> {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const response = await fetch(url, options);

      // Retry on 5xx errors
      if (response.status >= 500 && attempt < retries - 1) {
        await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
        continue;
      }

      return response;
    } catch (error) {
      if (attempt === retries - 1) {
        throw error;
      }
      await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
    }
  }

  throw new Error('Failed to fetch after retries');
}

export async function fetchTasks(projectId?: string, status?: TaskStatus): Promise<Task[]> {
  const params = new URLSearchParams();
  if (projectId) params.append('project_id', projectId);
  if (status) params.append('status', status);

  const url = `${API_BASE}/tasks${params.toString() ? '?' + params.toString() : ''}`;

  try {
    const response = await fetchWithErrorHandling(url);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to fetch tasks: ${response.statusText}`);
    }

    const data = await response.json();
    return data.tasks || [];
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to fetch tasks');
  }
}

export async function updateTask(
  taskId: number,
  updates: {
    text?: string;
    title?: string | null;
    notes?: string | null;
    commit_sha?: string | null;
    category?: string | null;
    status?: TaskStatus;
    priority?: TaskPriority | null;
    parent_id?: number | null;
    blocked_by?: number[] | null;
  }
): Promise<Task> {
  try {
    const response = await fetchWithErrorHandling(`${API_BASE}/tasks/${taskId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(updates),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to update task: ${response.statusText}`);
    }

    return response.json();
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to update task');
  }
}

export async function createTask(
  text: string,
  projectId: string,
  status: TaskStatus = 'Backlog',
  priority?: TaskPriority | null,
  parentId?: number | null,
  blockedBy?: number[] | null
): Promise<Task> {
  try {
    const response = await fetchWithErrorHandling(`${API_BASE}/tasks`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text,
        project_id: projectId,
        status,
        priority,
        parent_id: parentId,
        blocked_by: blockedBy,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to create task: ${response.statusText}`);
    }

    return response.json();
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to create task');
  }
}

export async function deleteTask(taskId: number): Promise<void> {
  try {
    const response = await fetchWithErrorHandling(`${API_BASE}/tasks/${taskId}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to delete task: ${response.statusText}`);
    }
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to delete task');
  }
}

export async function deleteDoneTasks(projectId?: string): Promise<{ deleted: number }> {
  const params = new URLSearchParams();
  if (projectId) params.append('project_id', projectId);

  const url = `${API_BASE}/tasks/done${params.toString() ? '?' + params.toString() : ''}`;

  try {
    const response = await fetchWithErrorHandling(url, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to delete done tasks: ${response.statusText}`);
    }

    return response.json();
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to delete done tasks');
  }
}

export async function fetchProjects(): Promise<any[]> {
  try {
    const response = await fetchWithErrorHandling(`${API_BASE}/projects`);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to fetch projects: ${response.statusText}`);
    }

    const data = await response.json();
    return data.projects || [];
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to fetch projects');
  }
}

export async function fetchTaskHistory(days: number = 30, projectId?: string): Promise<TaskHistoryResponse> {
  const params = new URLSearchParams();
  params.append('days', days.toString());
  if (projectId) params.append('project_id', projectId);

  const url = `${API_BASE}/tasks/history?${params.toString()}`;

  try {
    const response = await fetchWithErrorHandling(url);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to fetch history: ${response.statusText}`);
    }

    return response.json();
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to fetch task history');
  }
}

// ==================== IDEAS API (Task #4583) ====================

import type { Idea } from './types';

export async function fetchIdeas(): Promise<Idea[]> {
  try {
    const response = await fetchWithErrorHandling(`${API_BASE}/ideas`);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to fetch ideas: ${response.statusText}`);
    }

    const data = await response.json();
    return data.ideas || [];
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to fetch ideas');
  }
}

export async function createIdea(text: string): Promise<Idea> {
  try {
    const response = await fetchWithErrorHandling(`${API_BASE}/ideas`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to create idea: ${response.statusText}`);
    }

    return response.json();
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to create idea');
  }
}

export async function updateIdea(ideaId: number, text: string): Promise<Idea> {
  try {
    const response = await fetchWithErrorHandling(`${API_BASE}/ideas/${ideaId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to update idea: ${response.statusText}`);
    }

    return response.json();
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to update idea');
  }
}

export async function deleteIdea(ideaId: number): Promise<void> {
  try {
    const response = await fetchWithErrorHandling(`${API_BASE}/ideas/${ideaId}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || errorData.detail || `Failed to delete idea: ${response.statusText}`);
    }
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to delete idea');
  }
}
