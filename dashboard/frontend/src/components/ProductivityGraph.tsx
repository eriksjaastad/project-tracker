import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { fetchTaskHistory, fetchProjects, isAbortError } from '../api';
import type { TaskHistoryEntry } from '../types';
import './ProductivityGraph.css';

type TimeRange = 'week' | 'month';

interface Project {
  id: string;
  name: string;
}

export function ProductivityGraph() {
  const { project: projectParam } = useParams<{ project?: string }>();
  const [selectedProject, setSelectedProject] = useState<string | undefined>(projectParam);
  const [timeRange, setTimeRange] = useState<TimeRange>('month');
  const [history, setHistory] = useState<TaskHistoryEntry[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalCompleted, setTotalCompleted] = useState(0);

  // Update selectedProject when URL param changes
  useEffect(() => {
    setSelectedProject(projectParam);
  }, [projectParam]);

  // Fetch projects on mount
  useEffect(() => {
    const controller = new AbortController();
    async function loadProjects() {
      try {
        const projectsData = await fetchProjects(controller.signal);
        setProjects(projectsData);
      } catch (err) {
        if (isAbortError(err)) {
          return;
        }
        console.error('Failed to load projects:', err);
      }
    }
    loadProjects();
    return () => controller.abort();
  }, []);

  // Fetch history when filters change
  useEffect(() => {
    const controller = new AbortController();
    async function loadHistory() {
      setLoading(true);
      setError(null);

      try {
        const days = timeRange === 'week' ? 7 : 30;
        const data = await fetchTaskHistory(days, selectedProject, controller.signal);
        setHistory(data.history);
        setTotalCompleted(data.total_completed);
      } catch (err) {
        if (isAbortError(err)) {
          return;
        }
        setError(err instanceof Error ? err.message : 'Failed to load history');
        console.error('Failed to load task history:', err);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    loadHistory();
    return () => controller.abort();
  }, [selectedProject, timeRange]);

  // Transform history data for Recharts
  // Group by date and sum completions across all projects if no project filter
  const chartData = (() => {
    const dataMap = new Map<string, number>();
    
    history.forEach(entry => {
      const current = dataMap.get(entry.date) || 0;
      dataMap.set(entry.date, current + entry.completed);
    });
    
    // Convert to array and sort by date
    return Array.from(dataMap.entries())
      .map(([date, completed]) => ({ date, completed }))
      .sort((a, b) => a.date.localeCompare(b.date));
  })();

  // Format date for display (e.g., "Jan 25")
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="productivity-graph">
      <div className="graph-header">
        <h1>Productivity Graph</h1>
        <div className="graph-controls">
          <div className="control-group">
            <label htmlFor="project-filter">Project:</label>
            <select
              id="project-filter"
              value={selectedProject || ''}
              onChange={(e) => setSelectedProject(e.target.value || undefined)}
            >
              <option value="">All Projects</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>
          
          <div className="control-group">
            <label>Time Range:</label>
            <div className="time-range-buttons">
              <button
                className={timeRange === 'week' ? 'active' : ''}
                onClick={() => setTimeRange('week')}
              >
                Week
              </button>
              <button
                className={timeRange === 'month' ? 'active' : ''}
                onClick={() => setTimeRange('month')}
              >
                Month
              </button>
            </div>
          </div>
        </div>
      </div>

      {loading && <div className="loading">Loading...</div>}
      {error && <div className="error">Error: {error}</div>}

      {!loading && !error && (
        <>
          <div className="graph-stats">
            <div className="stat">
              <span className="stat-label">Total Completed:</span>
              <span className="stat-value">{totalCompleted}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Time Range:</span>
              <span className="stat-value">
                {timeRange === 'week' ? 'Last 7 days' : 'Last 30 days'}
              </span>
            </div>
          </div>

          {chartData.length === 0 ? (
            <div className="no-data">
              <p>No completion data available for the selected filters.</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="date"
                  tickFormatter={formatDate}
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis />
                <Tooltip
                  labelFormatter={(value) => `Date: ${formatDate(value)}`}
                  formatter={(value) => [value, 'Completed']}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="completed"
                  stroke="#51cf66"
                  strokeWidth={2}
                  dot={{ fill: '#51cf66', r: 4 }}
                  name="Tasks Completed"
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </>
      )}
    </div>
  );
}
