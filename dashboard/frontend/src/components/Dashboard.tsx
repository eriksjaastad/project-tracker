import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchProjects, fetchTasks } from '../api';
import type { Project, TaskStatus } from '../types';
import './Dashboard.css';

interface ProjectTaskCount {
  projectId: string;
  projectName: string;
  openTaskCount: number;
}

export function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [taskCounts, setTaskCounts] = useState<ProjectTaskCount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch projects
      const fetchedProjects = await fetchProjects();
      setProjects(fetchedProjects);

      // Fetch task counts for each project
      const counts: ProjectTaskCount[] = [];
      for (const project of fetchedProjects) {
        try {
          const tasks = await fetchTasks(project.id);
          // Count open tasks (Backlog, To Do, In Progress)
          const openStatuses: TaskStatus[] = ['Backlog', 'To Do', 'In Progress'];
          const openCount = tasks.filter(task => 
            openStatuses.includes(task.status)
          ).length;
          
          counts.push({
            projectId: project.id,
            projectName: project.name || project.id,
            openTaskCount: openCount,
          });
        } catch (err) {
          // If fetching tasks fails for a project, continue with 0 count
          console.warn(`Failed to fetch tasks for project ${project.id}:`, err);
          counts.push({
            projectId: project.id,
            projectName: project.name || project.id,
            openTaskCount: 0,
          });
        }
      }

      // Sort by open task count (descending), then by project name
      counts.sort((a, b) => {
        if (b.openTaskCount !== a.openTaskCount) {
          return b.openTaskCount - a.openTaskCount;
        }
        return a.projectName.localeCompare(b.projectName);
      });

      setTaskCounts(counts);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="dashboard-loading">
        <p>Loading dashboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-error">
        <p>Error: {error}</p>
        <button onClick={loadDashboardData}>Retry</button>
      </div>
    );
  }

  const totalOpenTasks = taskCounts.reduce((sum, count) => sum + count.openTaskCount, 0);
  const projectsWithTasks = taskCounts.filter(c => c.openTaskCount > 0).length;

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Project Dashboard</h1>
        <div className="dashboard-stats">
          <div className="stat-card">
            <div className="stat-value">{totalOpenTasks}</div>
            <div className="stat-label">Total Open Tasks</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{projectsWithTasks}</div>
            <div className="stat-label">Projects with Tasks</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{projects.length}</div>
            <div className="stat-label">Total Projects</div>
          </div>
        </div>
      </div>

      <div className="dashboard-content">
        <div className="projects-section">
          <h2>Projects</h2>
          {taskCounts.length === 0 ? (
            <p className="no-projects">No projects found.</p>
          ) : (
            <div className="projects-list">
              {taskCounts.map(({ projectId, projectName, openTaskCount }) => (
                <div key={projectId} className="project-card">
                  <div className="project-card-header">
                    <h3 className="project-name">{projectName}</h3>
                    <span className={`task-count ${openTaskCount > 0 ? 'has-tasks' : 'no-tasks'}`}>
                      {openTaskCount} {openTaskCount === 1 ? 'task' : 'tasks'}
                    </span>
                  </div>
                  <div className="project-card-actions">
                    <Link 
                      to={`/kanban/${projectId}`}
                      className="btn btn-primary"
                    >
                      View Kanban Board
                    </Link>
                    <Link 
                      to={`/graph/${projectId}`}
                      className="btn btn-secondary"
                    >
                      View Graph
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="quick-actions">
          <h2>Quick Actions</h2>
          <div className="action-buttons">
            <Link to="/kanban" className="btn btn-primary btn-large">
              View All Tasks
            </Link>
            <Link to="/graph" className="btn btn-secondary btn-large">
              View Productivity Graph
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
