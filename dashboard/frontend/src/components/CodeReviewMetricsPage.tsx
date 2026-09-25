import { useEffect, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  BarChart,
  Bar,
  Cell,
} from 'recharts';
import { PageShell } from './PageShell';
import { Spinner } from './Spinner';
import { Notification } from './Notification';
import './CodeReviewMetricsPage.css';

interface CodeReviewMetrics {
  available: boolean;
  message?: string;
  rounds_per_pr: Array<{ date: string; avg_rounds: number; pr_count: number }>;
  findings_per_round: Array<{ round: number; avg_findings: number }>;
  severity_distribution: Array<{ severity: string; count: number }>;
  time_to_first_review: Array<{ date: string; avg_hours: number }>;
  inter_round_latency: Array<{ round: number; avg_hours: number }>;
  merged_never_reviewed: number;
  reviewer_comparison: {
    available: boolean;
    message?: string;
    codex?: { rounds: number; findings: number };
    claude?: { rounds: number; findings: number };
  } | null;
  repos: string[];
  window: { days: number; repo: string | null };
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ff6b6b',
  high: '#ff9a83',
  medium: '#ffcc66',
  low: '#68b5ff',
  unspecified: '#aeb4c6',
};

function displayDate(value: string) {
  const [, month, day] = value.split('-');
  return `${Number(month)}/${Number(day)}`;
}

export function CodeReviewMetricsPage() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<CodeReviewMetrics | null>(null);
  const [notification, setNotification] = useState<{
    message: string;
    type: 'success' | 'error';
  } | null>(null);
  const [days, setDays] = useState(90);
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);

  useEffect(() => {
    loadMetrics();
  }, [days, selectedRepo]);

  async function loadMetrics() {
    try {
      const params = new URLSearchParams();
      params.append('days', String(days));
      if (selectedRepo) {
        params.append('repo', selectedRepo);
      }

      const response = await fetch(`/api/code-review-metrics?${params}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const metricsData = await response.json();
      setData(metricsData);
    } catch (error) {
      console.error('Failed to load code-review metrics:', error);
      setNotification({
        message: 'Failed to load code-review metrics',
        type: 'error',
      });
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <PageShell title="Code Review Metrics" subtitle="AI code review performance from ai-memory">
        <div className="code-review-loading">
          <Spinner size="large" />
        </div>
      </PageShell>
    );
  }

  if (!data || !data.available) {
    return (
      <PageShell title="Code Review Metrics" subtitle="AI code review performance from ai-memory">
        <div className="code-review-unavailable">
          <p>{data?.message || 'Code review metrics are not yet available.'}</p>
          <p className="code-review-hint">
            The <code>code_reviews</code> and <code>code_review_findings</code> tables
            in ai-memory's <code>brain.db</code> must exist and contain data.
          </p>
        </div>
      </PageShell>
    );
  }

  const hasRoundsData = data.rounds_per_pr.length > 0;
  const hasFindingsData = data.findings_per_round.length > 0;
  const hasSeverityData = data.severity_distribution.length > 0;

  return (
    <PageShell
      title="Code Review Metrics"
      subtitle="AI code review performance from ai-memory"
    >
      {notification && (
        <Notification
          message={notification.message}
          type={notification.type}
          onClose={() => setNotification(null)}
        />
      )}

      <div className="code-review-controls">
        <label>
          Lookback window:
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={30}>30 days</option>
            <option value={60}>60 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
            <option value={365}>365 days</option>
          </select>
        </label>
        {data.repos.length > 0 && (
          <label>
            Repository:
            <select
              value={selectedRepo || ''}
              onChange={(e) => setSelectedRepo(e.target.value || null)}
            >
              <option value="">All repos</option>
              {data.repos.map((repo) => (
                <option key={repo} value={repo}>
                  {repo}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <section className="code-review-chart" aria-label="Rounds per PR over time">
        <div className="code-review-chart-heading">
          <h2>Rounds per PR</h2>
          <p>Average review rounds required per pull request over time</p>
        </div>
        {hasRoundsData ? (
          <div
            className="code-review-plot"
            role="img"
            aria-label="Rounds per PR time series"
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={data.rounds_per_pr}
                margin={{ top: 8, right: 8, left: 0, bottom: 4 }}
              >
                <CartesianGrid stroke="#364052" strokeDasharray="3 3" />
                <XAxis
                  dataKey="date"
                  tickFormatter={displayDate}
                  stroke="#acb5c3"
                  minTickGap={16}
                />
                <YAxis stroke="#acb5c3" width={52} />
                <Tooltip
                  labelFormatter={(value) => String(value)}
                  contentStyle={{ background: '#1e2530', border: '1px solid #47536a' }}
                  formatter={(value, name, props) => {
                    if (name === 'avg_rounds' && value !== undefined) {
                      const prCount = (props as { payload: { pr_count: number } }).payload.pr_count;
                      return [
                        `${Number(value).toFixed(2)} rounds (n=${prCount} PRs)`,
                        'Avg Rounds',
                      ];
                    }
                    return [value, name];
                  }}
                />
                <Legend />
                <Line
                  type="linear"
                  dataKey="avg_rounds"
                  name="Avg Rounds"
                  stroke="#68b5ff"
                  strokeWidth={2}
                  dot={data.rounds_per_pr.length <= 14}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="code-review-chart-empty">
            No rounds-per-PR data for the selected window
          </p>
        )}
      </section>

      <section className="code-review-chart" aria-label="Findings per round">
        <div className="code-review-chart-heading">
          <h2>Findings per Round</h2>
          <p>Average findings reported in each review round</p>
        </div>
        {hasFindingsData ? (
          <div
            className="code-review-plot"
            role="img"
            aria-label="Findings per round chart"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={data.findings_per_round}
                margin={{ top: 8, right: 8, left: 0, bottom: 4 }}
              >
                <CartesianGrid stroke="#364052" strokeDasharray="3 3" />
                <XAxis dataKey="round" stroke="#acb5c3" label={{ value: 'Round', position: 'insideBottom', offset: -5 }} />
                <YAxis stroke="#acb5c3" width={52} />
                <Tooltip
                  contentStyle={{ background: '#1e2530', border: '1px solid #47536a' }}
                />
                <Legend />
                <Bar dataKey="avg_findings" name="Findings" fill="#c2a5ff" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="code-review-chart-empty">
            No findings-per-round data for the selected window
          </p>
        )}
      </section>

      <section className="code-review-chart" aria-label="Severity distribution">
        <div className="code-review-chart-heading">
          <h2>Finding Severity Distribution</h2>
          <p>Breakdown of findings by severity level</p>
        </div>
        {hasSeverityData ? (
          <div
            className="code-review-plot"
            role="img"
            aria-label="Severity distribution chart"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={data.severity_distribution}
                margin={{ top: 8, right: 8, left: 0, bottom: 4 }}
              >
                <CartesianGrid stroke="#364052" strokeDasharray="3 3" />
                <XAxis dataKey="severity" stroke="#acb5c3" />
                <YAxis stroke="#acb5c3" width={52} />
                <Tooltip
                  contentStyle={{ background: '#1e2530', border: '1px solid #47536a' }}
                  formatter={(value) => {
                    if (value !== undefined) {
                      const total = data.severity_distribution.reduce((sum, item) => sum + item.count, 0);
                      const pct = ((Number(value) / total) * 100).toFixed(1);
                      return [`${value} (${pct}%, n=${total})`, 'Count'];
                    }
                    return [value, 'Count'];
                  }}
                />
                <Legend />
                <Bar dataKey="count" name="Count">
                  {data.severity_distribution.map((entry) => (
                    <Cell
                      key={entry.severity}
                      fill={SEVERITY_COLORS[entry.severity.toLowerCase()] || '#aeb4c6'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="code-review-chart-empty">
            No severity distribution data for the selected window
          </p>
        )}
      </section>

      <section className="code-review-chart" aria-label="Merged without review">
        <div className="code-review-chart-heading">
          <h2>Gate Health: Merged Without Review</h2>
          <p>
            Pull requests merged without independent code review (gate-health indicator)
          </p>
        </div>
        <div className="code-review-stat">
          <div className="code-review-stat-value">
            {data.merged_never_reviewed}
          </div>
          <div className="code-review-stat-label">
            PRs merged without review in the last {days} days
          </div>
        </div>
      </section>

      <section className="code-review-chart" aria-label="Reviewer comparison">
        <div className="code-review-chart-heading">
          <h2>Reviewer Comparison</h2>
          <p>Codex vs Claude review performance (from #7416)</p>
        </div>
        {data.reviewer_comparison && data.reviewer_comparison.available ? (
          <div className="code-review-comparison">
            <div className="code-review-comparison-item">
              <h3>Codex</h3>
              <p>Avg Rounds: {data.reviewer_comparison.codex?.rounds || 'N/A'}</p>
              <p>Avg Findings: {data.reviewer_comparison.codex?.findings || 'N/A'}</p>
            </div>
            <div className="code-review-comparison-item">
              <h3>Claude</h3>
              <p>Avg Rounds: {data.reviewer_comparison.claude?.rounds || 'N/A'}</p>
              <p>Avg Findings: {data.reviewer_comparison.claude?.findings || 'N/A'}</p>
            </div>
          </div>
        ) : (
          <div className="code-review-unavailable">
            <p>
              {data.reviewer_comparison?.message ||
                'Reviewer comparison not yet available'}
            </p>
            <p className="code-review-hint">
              This section requires implementation of card #7416 (Claude vs Codex
              comparison). Once that card is complete, comparison metrics will appear
              here automatically.
            </p>
          </div>
        )}
      </section>
    </PageShell>
  );
}
