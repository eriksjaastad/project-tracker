import { useEffect, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { fetchAgenticSummary, fetchProjects } from '../api';
import type { AgenticSeriesEntry, AgenticSummaryResponse, Project } from '../types';
import { PageShell } from './PageShell';
import './AgenticDashboard.css';

type TimeRange = 'week' | 'month';

export function AgenticDashboard() {
  const [timeRange, setTimeRange] = useState<TimeRange>('month');
  const [selectedProject, setSelectedProject] = useState<string | undefined>(undefined);
  const [projects, setProjects] = useState<Project[]>([]);
  const [summary, setSummary] = useState<AgenticSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadProjects() {
      try {
        const data = await fetchProjects();
        const sorted = data.slice().sort((a, b) => {
          return a.name.localeCompare(b.name);
        });
        setProjects(sorted);
      } catch (err) {
        console.error('Failed to load projects:', err);
      }
    }
    loadProjects();
  }, []);

  useEffect(() => {
    async function loadSummary() {
      setLoading(true);
      setError(null);
      try {
        const days = timeRange === 'week' ? 7 : 30;
        const data = await fetchAgenticSummary(days, selectedProject);
        setSummary(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load agentic summary');
        console.error('Failed to load agentic summary:', err);
      } finally {
        setLoading(false);
      }
    }

    loadSummary();
  }, [timeRange, selectedProject]);

  const chartData = (summary?.series || []).map((entry: AgenticSeriesEntry) => ({
    date: entry.date,
    bounces: entry.review_bounces,
    promotions: entry.review_promotions,
    entries: entry.review_entries,
  }));

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const bounceRate = summary?.summary.bounce_rate ?? 0;
  const promotionRate = summary?.summary.promotion_rate ?? 0;

  const headerActions = (
    <div className="agentic-controls">
      <div className="control-group">
        <label htmlFor="agentic-project">Project</label>
        <select
          id="agentic-project"
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
        <label>Time Range</label>
        <div className="time-range-buttons">
          <button
            className={timeRange === 'week' ? 'active' : ''}
            onClick={() => setTimeRange('week')}
            type="button"
          >
            Week
          </button>
          <button
            className={timeRange === 'month' ? 'active' : ''}
            onClick={() => setTimeRange('month')}
            type="button"
          >
            Month
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <PageShell
      title="Agentic Autonomy"
      subtitle="Early signal on how often agent work clears Review without bouncing."
      actions={headerActions}
      headerWidth="narrow"
      contentWidth="narrow"
    >
      <div className="agentic-dashboard">
        {loading && <div className="agentic-loading">Loading agentic metrics...</div>}
        {error && <div className="agentic-error">Error: {error}</div>}

        {!loading && !error && summary && (
          <>
            <section className="agentic-stats">
              <div className="stat-card">
                <span className="stat-label">Review Bounce Rate (proxy)</span>
                <span className="stat-value">{(bounceRate * 100).toFixed(1)}%</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Review Promotion Rate</span>
                <span className="stat-value">{(promotionRate * 100).toFixed(1)}%</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Review Bounces</span>
                <span className="stat-value">{summary.summary.review_bounces}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Review Promotions</span>
                <span className="stat-value">{summary.summary.review_promotions}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Review Entries</span>
                <span className="stat-value">{summary.summary.review_entries}</span>
              </div>
            </section>

            <section className="agentic-chart">
              <div className="chart-header">
                <h2>Review Flow Over Time</h2>
                <p>
                  Source: task_history (Review → In Progress = bounce, Review → Done = promotion)
                </p>
              </div>
              {chartData.length === 0 ? (
                <div className="agentic-empty">No review history for the selected range.</div>
              ) : (
                <ResponsiveContainer width="100%" height={360}>
                  <LineChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={formatDate}
                      angle={-40}
                      textAnchor="end"
                      height={70}
                    />
                    <YAxis />
                    <Tooltip
                      labelFormatter={(value) => `Date: ${formatDate(value as string)}`}
                    />
                    <Legend />
                    {(summary.markers || []).map((marker) => (
                      <ReferenceLine
                        key={marker.date + marker.label}
                        x={marker.date}
                        stroke="#ffd43b"
                        strokeDasharray="4 4"
                        label={{
                          value: marker.label,
                          position: 'insideTopRight',
                          fill: '#ffd43b',
                          fontSize: 12,
                        }}
                      />
                    ))}
                    <Line
                      type="monotone"
                      dataKey="entries"
                      stroke="#4f9dff"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      name="Review Entries"
                    />
                    <Line
                      type="monotone"
                      dataKey="promotions"
                      stroke="#51cf66"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      name="Review Promotions"
                    />
                    <Line
                      type="monotone"
                      dataKey="bounces"
                      stroke="#ff6b6b"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      name="Review Bounces"
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </section>

            <section className="agentic-notes">
              <h2>Notes & Next Steps</h2>
              <ul>
                <li>Metrics are based on status transitions in task_history.</li>
                <li>Bounce rate is a proxy for autonomy reliability, not a perfect first-pass metric.</li>
                <li>Add workflow markers in data/agentic_markers.json (date + label).</li>
                <li>Future: split by agent vs manual tasks, and add per-project trend comparisons.</li>
              </ul>
            </section>
          </>
        )}
      </div>
    </PageShell>
  );
}
