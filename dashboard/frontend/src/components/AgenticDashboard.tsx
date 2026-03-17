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
import {
  fetchAgenticSummary,
  fetchMarkers,
  createMarker,
  updateMarker,
  deleteMarker,
  fetchProjects,
} from '../api';
import type { AgenticMarker, AgenticSeriesEntry, AgenticSummaryResponse, Project } from '../types';
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

  // Marker state
  const [markers, setMarkers] = useState<AgenticMarker[]>([]);
  const [newDate, setNewDate] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [newAgent, setNewAgent] = useState('');
  const [markerError, setMarkerError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDate, setEditDate] = useState('');
  const [editLabel, setEditLabel] = useState('');
  const [editAgent, setEditAgent] = useState('');

  useEffect(() => {
    async function load() {
      try {
        const [projectData, markerData] = await Promise.all([fetchProjects(), fetchMarkers()]);
        setProjects(projectData.slice().sort((a, b) => a.name.localeCompare(b.name)));
        setMarkers(markerData);
      } catch (err) {
        console.error('Failed to load initial data:', err);
      }
    }
    load();
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

  // Marker handlers
  async function handleAddMarker() {
    setMarkerError(null);
    if (!newDate || !newLabel.trim()) {
      setMarkerError('Date and label are required.');
      return;
    }
    try {
      const created = await createMarker(newDate, newLabel.trim(), newAgent.trim() || undefined);
      setMarkers(prev => [...prev, created].sort((a, b) => a.date.localeCompare(b.date)));
      setNewDate('');
      setNewLabel('');
      setNewAgent('');
    } catch (err) {
      setMarkerError(err instanceof Error ? err.message : 'Failed to add marker');
    }
  }

  function startEdit(marker: AgenticMarker) {
    setEditingId(marker.id);
    setEditDate(marker.date);
    setEditLabel(marker.label);
    setEditAgent(marker.agent || '');
  }

  async function handleSaveEdit(id: string) {
    setMarkerError(null);
    try {
      const updated = await updateMarker(id, {
        date: editDate,
        label: editLabel.trim(),
        agent: editAgent.trim() || undefined,
      });
      setMarkers(prev =>
        prev.map(m => (m.id === id ? updated : m)).sort((a, b) => a.date.localeCompare(b.date))
      );
      setEditingId(null);
    } catch (err) {
      setMarkerError(err instanceof Error ? err.message : 'Failed to save marker');
    }
  }

  async function handleDeleteMarker(id: string) {
    setMarkerError(null);
    try {
      await deleteMarker(id);
      setMarkers(prev => prev.filter(m => m.id !== id));
    } catch (err) {
      setMarkerError(err instanceof Error ? err.message : 'Failed to delete marker');
    }
  }

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
                    {markers.map((marker) => (
                      <ReferenceLine
                        key={marker.id}
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
          </>
        )}

        {/* Marker management — always rendered, independent of chart loading */}
        <section className="agentic-markers">
          <h2>Workflow Markers</h2>
          <p className="markers-description">
            Flag significant events (new agent, workflow change, Mac Mini sessions) to explain
            metric shifts. <span className="marker-auto-hint">Auto markers from the sync daemon will appear here too.</span>
          </p>

          {markerError && <div className="marker-error">{markerError}</div>}

          <div className="marker-add-form" id="marker-add-form">
            <input
              id="marker-date"
              type="date"
              value={newDate}
              onChange={e => setNewDate(e.target.value)}
              placeholder="Date"
            />
            <input
              id="marker-label"
              type="text"
              value={newLabel}
              maxLength={120}
              onChange={e => setNewLabel(e.target.value)}
              placeholder="Label (e.g. Added Mac Mini)"
            />
            <input
              id="marker-agent"
              type="text"
              value={newAgent}
              onChange={e => setNewAgent(e.target.value)}
              placeholder="Agent (optional)"
            />
            <button
              id="marker-add-btn"
              type="button"
              onClick={handleAddMarker}
              className="btn-primary btn-small"
            >
              Add Marker
            </button>
          </div>

          {markers.length === 0 ? (
            <div className="markers-empty">No markers yet. Add one above to annotate the chart.</div>
          ) : (
            <ul className="marker-list">
              {markers.map(marker => (
                <li key={marker.id} className="marker-row">
                  {editingId === marker.id ? (
                    <div className="marker-edit-row">
                      <input
                        type="date"
                        value={editDate}
                        onChange={e => setEditDate(e.target.value)}
                      />
                      <input
                        type="text"
                        value={editLabel}
                        maxLength={120}
                        onChange={e => setEditLabel(e.target.value)}
                      />
                      <input
                        type="text"
                        value={editAgent}
                        placeholder="Agent (optional)"
                        onChange={e => setEditAgent(e.target.value)}
                      />
                      <button
                        type="button"
                        onClick={() => handleSaveEdit(marker.id)}
                        className="btn-primary btn-small"
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingId(null)}
                        className="btn-small"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div className="marker-display-row">
                      <span className="marker-date">{marker.date}</span>
                      <span className="marker-label">{marker.label}</span>
                      {marker.agent && <span className="marker-agent">{marker.agent}</span>}
                      <span className={`marker-source marker-source--${marker.source}`}>
                        {marker.source}
                      </span>
                      {marker.source === 'manual' && (
                        <>
                          <button
                            type="button"
                            onClick={() => startEdit(marker)}
                            className="btn-small"
                            title="Edit marker"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteMarker(marker.id)}
                            className="btn-small btn-danger"
                            title="Delete marker"
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="agentic-notes">
          <h2>Notes & Next Steps</h2>
          <ul>
            <li>Metrics are based on status transitions in task_history.</li>
            <li>Bounce rate is a proxy for autonomy reliability, not a perfect first-pass metric.</li>
            <li>Future: split by agent vs manual tasks, and add per-project trend comparisons.</li>
            <li>Future: Mac Mini sessions will write auto markers once brain.db is hosted.</li>
          </ul>
        </section>
      </div>
    </PageShell>
  );
}
