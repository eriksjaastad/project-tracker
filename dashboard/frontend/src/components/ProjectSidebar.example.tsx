/**
 * Example usage of ProjectSidebar component
 * 
 * This file demonstrates how to integrate ProjectSidebar into a KanbanBoard component.
 */

import React, { useState, useEffect } from 'react';
import { ProjectSidebar } from './ProjectSidebar';
import type { Project, SortOrder } from './ProjectSidebar';
import './ProjectSidebar.css';

const STORAGE_KEY_SELECTED_PROJECTS = 'kanban-selected-projects';

export const KanbanBoardExample: React.FC = () => {
  const [selectedProjects, setSelectedProjects] = useState<Set<string>>(() => {
    // Load selected projects from localStorage on mount
    const stored = localStorage.getItem(STORAGE_KEY_SELECTED_PROJECTS);
    if (stored) {
      try {
        const projectIds = JSON.parse(stored);
        return new Set(projectIds);
      } catch (error) {
        console.error('Error parsing stored selected projects:', error);
      }
    }
    return new Set<string>();
  });

  const [sortOrder, setSortOrder] = useState<SortOrder>('alphabetical');
  const [projects] = useState<Project[]>([]);

  // Persist selected projects to localStorage whenever they change
  useEffect(() => {
    const projectIds = Array.from(selectedProjects);
    localStorage.setItem(STORAGE_KEY_SELECTED_PROJECTS, JSON.stringify(projectIds));
  }, [selectedProjects]);

  const handleToggleProject = (projectId: string) => {
    setSelectedProjects(prev => {
      const next = new Set(prev);
      if (next.has(projectId)) {
        next.delete(projectId);
      } else {
        next.add(projectId);
      }
      return next;
    });
  };

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <ProjectSidebar
        projects={projects}
        selectedProjects={selectedProjects}
        onToggleProject={handleToggleProject}
        sortOrder={sortOrder}
        onChangeSortOrder={setSortOrder}
      />
      <div style={{ flex: 1, padding: '20px' }}>
        {/* Kanban board content goes here */}
        <h1>Kanban Board</h1>
        <p>Selected projects: {Array.from(selectedProjects).join(', ') || 'None'}</p>
      </div>
    </div>
  );
};
