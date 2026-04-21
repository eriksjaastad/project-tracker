import React, { useState, useEffect, useMemo } from 'react';
import { Spinner } from './Spinner';

export type SortOrder = 'alphabetical' | 'task-count';

export interface Project {
  id: string;
  name: string;
  path: string;
  status?: string;
  task_count?: number; // Optional: will be fetched separately if not provided
  portfolio_group?: string | null;
  portfolio_label?: string | null;
  portfolio_parent?: string | null;
}

import { groupByPortfolio } from '../utils/portfolio';

interface ProjectSidebarProps {
  projects: Project[];
  selectedProjects: Set<string>;
  onToggleProject: (projectId: string) => void;
  sortOrder: SortOrder;
  onChangeSortOrder: (order: SortOrder) => void;
}

const STORAGE_KEY_COLLAPSED = 'kanban-sidebar-collapsed';
const STORAGE_KEY_SORT_ORDER = 'kanban-sidebar-sort-order';

/**
 * ProjectSidebar Component
 * 
 * Displays a collapsible sidebar with project filtering and sorting capabilities.
 * Features:
 * - Fetch projects from /api/projects
 * - Display project list with checkboxes
 * - "Select All" / "Deselect All" functionality
 * - Collapsible sidebar with localStorage persistence
 * - Project sorting (Alphabetical, Task Count)
 */
export const ProjectSidebar: React.FC<ProjectSidebarProps> = ({
  projects: initialProjects,
  selectedProjects: externalSelectedProjects,
  onToggleProject,
  sortOrder: externalSortOrder,
  onChangeSortOrder,
}) => {
  // Local state
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    const stored = localStorage.getItem(STORAGE_KEY_COLLAPSED);
    return stored ? JSON.parse(stored) : false;
  });

  const [projects, setProjects] = useState<Project[]>(initialProjects);
  const [loading, setLoading] = useState<boolean>(false);
  const [taskCounts, setTaskCounts] = useState<Record<string, number>>({});

  // Load sort order from localStorage on mount
  useEffect(() => {
    const storedSortOrder = localStorage.getItem(STORAGE_KEY_SORT_ORDER);
    if (storedSortOrder && (storedSortOrder === 'alphabetical' || storedSortOrder === 'task-count')) {
      onChangeSortOrder(storedSortOrder as SortOrder);
    }
  }, [onChangeSortOrder]);

  // Persist collapsed state to localStorage
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY_COLLAPSED, JSON.stringify(isCollapsed));
  }, [isCollapsed]);

  // Persist sort order to localStorage
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY_SORT_ORDER, externalSortOrder);
  }, [externalSortOrder]);

  // Fetch projects from API
  useEffect(() => {
    const fetchProjects = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/projects');
        if (!response.ok) {
          throw new Error(`Failed to fetch projects: ${response.statusText}`);
        }
        const data = await response.json();
        setProjects(data.projects || []);
      } catch (error) {
        console.error('Error fetching projects:', error);
        // Keep initial projects if fetch fails
      } finally {
        setLoading(false);
      }
    };

    fetchProjects();
  }, []);

  // Fetch task counts for each project
  useEffect(() => {
    const fetchTaskCounts = async () => {
      const counts: Record<string, number> = {};

      // Fetch tasks for each project in parallel
      const promises = projects.map(async (project) => {
        try {
          const response = await fetch(`/api/tasks?project_id=${encodeURIComponent(project.id)}`);
          if (response.ok) {
            const data = await response.json();
            counts[project.id] = data.total || 0;
          } else {
            counts[project.id] = 0;
          }
        } catch (error) {
          console.error(`Error fetching task count for ${project.id}:`, error);
          counts[project.id] = 0;
        }
      });

      await Promise.all(promises);
      setTaskCounts(counts);
    };

    if (projects.length > 0) {
      fetchTaskCounts();
    }
  }, [projects]);

  // Sort projects based on current sort order
  const sortedProjects = useMemo(() => {
    const projectsWithCounts = projects.map(project => ({
      ...project,
      task_count: taskCounts[project.id] ?? project.task_count ?? 0,
    }));

    const sorted = [...projectsWithCounts];

    if (externalSortOrder === 'alphabetical') {
      sorted.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
    } else if (externalSortOrder === 'task-count') {
      sorted.sort((a, b) => {
        // Sort by task count (descending), then alphabetically for ties
        if (b.task_count !== a.task_count) {
          return (b.task_count ?? 0) - (a.task_count ?? 0);
        }
        return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
      });
    }

    return sorted;
  }, [projects, taskCounts, externalSortOrder]);

  const groupedProjects = useMemo(() => groupByPortfolio(sortedProjects), [sortedProjects]);

  // Select All / Deselect All handlers
  const handleSelectAll = () => {
    sortedProjects.forEach(project => {
      if (!externalSelectedProjects.has(project.id)) {
        onToggleProject(project.id);
      }
    });
  };

  const handleDeselectAll = () => {
    sortedProjects.forEach(project => {
      if (externalSelectedProjects.has(project.id)) {
        onToggleProject(project.id);
      }
    });
  };

  const allSelected = sortedProjects.length > 0 && sortedProjects.every(p => externalSelectedProjects.has(p.id));
  const someSelected = sortedProjects.some(p => externalSelectedProjects.has(p.id)) && !allSelected;

  if (isCollapsed) {
    return (
      <div className="project-sidebar collapsed">
        <button
          className="sidebar-toggle"
          onClick={() => setIsCollapsed(false)}
          aria-label="Expand sidebar"
          title="Expand sidebar"
        >
          ▶
        </button>
      </div>
    );
  }

  return (
    <div className="project-sidebar">
      <div className="sidebar-header">
        <h2>Projects</h2>
        <button
          className="sidebar-toggle"
          onClick={() => setIsCollapsed(true)}
          aria-label="Collapse sidebar"
          title="Collapse sidebar"
        >
          ◀
        </button>
      </div>

      <div className="sidebar-controls">
        <div className="select-all-controls">
          <button
            className="btn-select-all"
            onClick={handleSelectAll}
            disabled={allSelected}
            aria-label="Select all projects"
          >
            Select All
          </button>
          <button
            className="btn-deselect-all"
            onClick={handleDeselectAll}
            disabled={!someSelected && !allSelected}
            aria-label="Deselect all projects"
          >
            Deselect All
          </button>
        </div>

        <div className="sort-controls">
          <label htmlFor="sort-order">Sort by:</label>
          <select
            id="sort-order"
            value={externalSortOrder}
            onChange={(e) => onChangeSortOrder(e.target.value as SortOrder)}
            aria-label="Sort order"
          >
            <option value="alphabetical">Alphabetical</option>
            <option value="task-count">Task Count</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="sidebar-loading">
          <Spinner size="small" />
          <span>Loading projects...</span>
        </div>
      ) : (
        <div className="project-list" role="listbox" aria-label="Project filter list">
          {sortedProjects.length === 0 ? (
            <div className="no-projects">No projects found</div>
          ) : (
            groupedProjects.map((group) => (
              <div key={group.key} className="project-group">
                {group.key !== 'default' && (
                  <div className="project-group-title">
                    {group.projects[0]?.portfolio_label || `[${group.key}]`} {group.title}
                  </div>
                )}
                {group.projects.map((project) => {
                  const isSelected = externalSelectedProjects.has(project.id);
                  const taskCount = taskCounts[project.id] ?? project.task_count ?? 0;

                  return (
                    <div
                      key={project.id}
                      className={`project-item ${isSelected ? 'selected' : ''}`}
                      role="option"
                      aria-selected={isSelected}
                    >
                      <label className="project-checkbox-label">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => onToggleProject(project.id)}
                          aria-label={`Toggle ${project.name}`}
                        />
                        {project.portfolio_label && (
                          <span className="project-badge">{project.portfolio_label}</span>
                        )}
                        <span className="project-name">{project.name}</span>
                        {externalSortOrder === 'task-count' && (
                          <span className="task-count-badge" aria-label={`${taskCount} tasks`}>
                            {taskCount}
                          </span>
                        )}
                      </label>
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>
      )}

      <div className="sidebar-footer">
        <div className="selected-count">
          {externalSelectedProjects.size} of {sortedProjects.length} selected
        </div>
      </div>
    </div>
  );
};

export default ProjectSidebar;
