import { useEffect, useState } from 'react';
import { isAbortError } from '../api';
import './CostPanel.css';

interface DailyEntry {
  date: string;
  total_calls: number;
  total_tokens: number;
  total_cost: number;
}

interface ProviderEntry {
  provider: string;
  total_calls: number;
  total_tokens: number;
  total_cost: number;
}

interface ProjectEntry {
  project: string;
  total_calls: number;
  total_tokens: number;
  total_cost: number;
}

interface CostData {
  daily: DailyEntry[];
  providers: ProviderEntry[];
  projects: ProjectEntry[];
}

type UnknownRow = Record<string, unknown>;

function formatCost(cost: number): string {
  if (cost < 0.01) return '<$0.01';
  return `$${cost.toFixed(2)}`;
}

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(0)}K`;
  return tokens.toString();
}

export function CostPanel() {
  const [data, setData] = useState<CostData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const since = new Date();
    since.setDate(since.getDate() - 30);
    const sinceStr = since.toISOString().split('T')[0];

    Promise.all([
      fetch(`/api/costs/daily?days=30`, { signal: controller.signal }).then(r => r.json()),
      fetch(`/api/costs/providers?since=${sinceStr}`, { signal: controller.signal }).then(r => r.json()),
      fetch(`/api/costs/projects?since=${sinceStr}`, { signal: controller.signal }).then(r => r.json()),
    ])
      .then(([daily, providers, projects]) => {
        // Handle both direct arrays and wrapped responses
        const toArray = (value: unknown): UnknownRow[] => {
          if (Array.isArray(value)) {
            return value.filter((row): row is UnknownRow => typeof row === 'object' && row !== null);
          }
          if (typeof value === 'object' && value !== null && Array.isArray((value as { data?: unknown }).data)) {
            return (value as { data: unknown[] }).data.filter(
              (row): row is UnknownRow => typeof row === 'object' && row !== null
            );
          }
          return [];
        };
        const toNumber = (value: unknown): number => {
          if (typeof value === 'number') {
            return Number.isFinite(value) ? value : 0;
          }
          if (typeof value === 'string') {
            const parsed = Number(value);
            return Number.isFinite(parsed) ? parsed : 0;
          }
          return 0;
        };
        const coerceDaily = (rows: UnknownRow[]): DailyEntry[] =>
          rows.map((row) => ({
            date: typeof row.date === 'string' ? row.date : '',
            total_calls: toNumber(row.calls ?? row.total_calls),
            total_tokens: toNumber(row.total_tokens),
            total_cost: toNumber(row.total_cost),
          }));
        const coerceProviders = (rows: UnknownRow[]): ProviderEntry[] =>
          rows.map((row) => ({
            provider: typeof row.provider === 'string' ? row.provider : 'unknown',
            total_calls: toNumber(row.calls ?? row.total_calls),
            total_tokens: toNumber(row.total_tokens),
            total_cost: toNumber(row.total_cost),
          }));
        const coerceProjects = (rows: UnknownRow[]): ProjectEntry[] =>
          rows.map((row) => ({
            project: typeof row.project === 'string' ? row.project : '',
            total_calls: toNumber(row.calls ?? row.total_calls),
            total_tokens: toNumber(row.total_tokens),
            total_cost: toNumber(row.total_cost),
          }));
        setData({
          daily: coerceDaily(toArray(daily)),
          providers: coerceProviders(toArray(providers)),
          projects: coerceProjects(toArray(projects)),
        });
        setLoading(false);
      })
      .catch(err => {
        if (isAbortError(err)) {
          return;
        }
        setError(err.message);
        setLoading(false);
      });

    return () => controller.abort();
  }, []);

  if (loading) {
    return (
      <div className="dashboard-section cost-panel">
        <h2>API Costs (30d)</h2>
        <div className="cost-loading">Loading cost data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-section cost-panel">
        <h2>API Costs (30d)</h2>
        <div className="cost-unavailable">Cost tracker unavailable</div>
      </div>
    );
  }

  const daily = data?.daily || [];
  const providers = data?.providers || [];
  const projects = data?.projects || [];

  const totalCost = daily.reduce((sum, d) => sum + d.total_cost, 0);
  const totalTokens = daily.reduce((sum, d) => sum + d.total_tokens, 0);
  const totalCalls = daily.reduce((sum, d) => sum + d.total_calls, 0);
  const dailyAvg = daily.length > 0 ? totalCost / daily.length : 0;

  const isEmpty = daily.length === 0 && providers.length === 0;

  if (isEmpty) {
    return (
      <div className="dashboard-section cost-panel">
        <h2>API Costs (30d)</h2>
        <div className="cost-empty">
          <div className="cost-empty-icon">--</div>
          <div className="cost-empty-text">No API cost data yet</div>
          <div className="cost-empty-hint">
            Instrument callers with track() to start collecting data
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-section cost-panel">
      <h2>API Costs (30d)</h2>

      {/* Summary cards */}
      <div className="cost-summary">
        <div className="cost-stat">
          <span className="cost-stat-value">{formatCost(totalCost)}</span>
          <span className="cost-stat-label">Total Spend</span>
        </div>
        <div className="cost-stat">
          <span className="cost-stat-value">{formatCost(dailyAvg)}</span>
          <span className="cost-stat-label">Daily Avg</span>
        </div>
        <div className="cost-stat">
          <span className="cost-stat-value">{formatTokens(totalTokens)}</span>
          <span className="cost-stat-label">Tokens</span>
        </div>
        <div className="cost-stat">
          <span className="cost-stat-value">{totalCalls.toLocaleString()}</span>
          <span className="cost-stat-label">API Calls</span>
        </div>
      </div>

      {/* Sparkline - simple bar chart of daily costs */}
      {daily.length > 1 && (
        <div className="cost-sparkline">
          {daily.slice(-14).map((d, i) => {
            const maxCost = Math.max(...daily.slice(-14).map(x => x.total_cost));
            const height = maxCost > 0 ? (d.total_cost / maxCost) * 100 : 0;
            return (
              <div
                key={i}
                className="cost-bar"
                style={{ height: `${Math.max(height, 2)}%` }}
                title={`${d.date}: ${formatCost(d.total_cost)}`}
              />
            );
          })}
        </div>
      )}

      {/* Provider breakdown */}
      {providers.length > 0 && (
        <div className="cost-breakdown">
          <h3>By Provider</h3>
          {providers
            .sort((a, b) => b.total_cost - a.total_cost)
            .map((p, i) => (
              <div key={i} className="cost-row">
                <span className="cost-row-name">{p.provider}</span>
                <span className="cost-row-tokens">{formatTokens(p.total_tokens)}</span>
                <span className="cost-row-cost">{formatCost(p.total_cost)}</span>
              </div>
            ))}
        </div>
      )}

      {/* Project breakdown */}
      {projects.length > 0 && (
        <div className="cost-breakdown">
          <h3>By Project</h3>
          {projects
            .sort((a, b) => b.total_cost - a.total_cost)
            .slice(0, 8)
            .map((p, i) => (
              <div key={i} className="cost-row">
                <span className="cost-row-name">{p.project || 'unattributed'}</span>
                <span className="cost-row-tokens">{formatTokens(p.total_tokens)}</span>
                <span className="cost-row-cost">{formatCost(p.total_cost)}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
