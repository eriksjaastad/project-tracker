import { useEffect, useState } from 'react';
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { fetchHoloscapeSeries, isAbortError } from '../api';
import type { HoloscapeSeriesDay, HoloscapeSeriesResponse, HoloscapeSource } from '../types';
import { PageShell } from './PageShell';
import './HoloscapeProgressPage.css';

type Metric = Exclude<keyof HoloscapeSeriesDay, 'date'>;
type Range = 7 | 14 | 'all';
type SeriesLine = { key: Metric; label: string; color: string };

const charts: Array<{ title: string; note: string; source: keyof HoloscapeSeriesResponse['sources']; lines: SeriesLine[] }> = [
  { title: 'Board flow', note: 'Daily Holoscape card events, including review returns.', source: 'board', lines: [
    { key: 'task_created', label: 'Created', color: '#68b5ff' },
    { key: 'task_completed', label: 'Completed', color: '#66d9a7' },
    { key: 'review_entries', label: 'Entered review', color: '#c2a5ff' },
    { key: 'review_bounces', label: 'Review bounces', color: '#ff9a83' },
  ] },
  { title: 'Repository activity', note: 'Daily commits, GitHub reviews, and PR starts and merges.', source: 'github', lines: [
    { key: 'commits', label: 'Commits', color: '#68b5ff' },
    { key: 'github_reviews', label: 'Reviews', color: '#c2a5ff' },
    { key: 'prs_opened', label: 'PRs opened', color: '#ffcc66' },
    { key: 'prs_merged', label: 'PRs merged', color: '#66d9a7' },
  ] },
  { title: 'CI workflow runs by current result', note: 'Run creation date; reruns update a run’s current result rather than add another event.', source: 'github', lines: [
    { key: 'ci_success', label: 'Success', color: '#66d9a7' },
    { key: 'ci_failure', label: 'Failure', color: '#ff9a83' },
    { key: 'ci_pending', label: 'Pending', color: '#ffcc66' },
    { key: 'ci_other', label: 'Other', color: '#aeb4c6' },
  ] },
  { title: 'Hermes manager sessions', note: 'Daily manager session starts.', source: 'hermes', lines: [
    { key: 'manager_sessions', label: 'Manager', color: '#68b5ff' },
  ] },
  { title: 'Delegate and DeepSeek sessions', note: 'Daily worker starts. DeepSeek CLI is separate from Hermes’s native delegates.', source: 'hermes', lines: [
    { key: 'delegate_sessions', label: 'Hermes delegates', color: '#c2a5ff' },
    { key: 'deepseek_cli_sessions', label: 'DeepSeek CLI', color: '#ffcc66' },
  ] },
  { title: 'Manager session time', note: 'Summed manager minutes for completed sessions; concurrent sessions may overlap.', source: 'hermes', lines: [
    { key: 'manager_session_minutes', label: 'Manager minutes', color: '#68b5ff' },
  ] },
  { title: 'Worker session time', note: 'Summed worker minutes for completed sessions; concurrent sessions may overlap.', source: 'hermes', lines: [
    { key: 'delegate_session_minutes', label: 'Delegate minutes', color: '#c2a5ff' },
    { key: 'deepseek_cli_session_minutes', label: 'DeepSeek CLI minutes', color: '#ffcc66' },
  ] },
  { title: 'Manager tokens', note: 'Daily input and output tokens recorded for Hermes manager sessions.', source: 'hermes', lines: [
    { key: 'manager_input_tokens', label: 'Manager input', color: '#68b5ff' },
    { key: 'manager_output_tokens', label: 'Manager output', color: '#3d7fcc' },
  ] },
  { title: 'Delegate tokens', note: 'Daily input and output tokens recorded for Hermes native delegates.', source: 'hermes', lines: [
    { key: 'delegate_input_tokens', label: 'Delegate input', color: '#c2a5ff' },
    { key: 'delegate_output_tokens', label: 'Delegate output', color: '#8d68d0' },
  ] },
  { title: 'DeepSeek CLI tokens', note: 'Daily input and output tokens; separate scale from Hermes. Counts are not dollars.', source: 'hermes', lines: [
    { key: 'deepseek_cli_input_tokens', label: 'DeepSeek input', color: '#ffcc66' },
    { key: 'deepseek_cli_output_tokens', label: 'DeepSeek output', color: '#d8993b' },
  ] },
  { title: 'DeepSeek cache-read tokens', note: 'Shown separately so large cache volume does not flatten input and output trends.', source: 'hermes', lines: [
    { key: 'deepseek_cli_cache_read_tokens', label: 'Cache read', color: '#e5dc9a' },
  ] },
  { title: 'Worker worktree references', note: 'Matching Hermes tool calls; a reference does not establish who launched or directed DeepSeek.', source: 'hermes', lines: [
    { key: 'worktree_references', label: 'Tool-call references', color: '#ff9a83' },
  ] },
];

function displayDate(value: string) {
  // ISO dates here are already in the observation timezone. Avoid UTC date parsing drift.
  const [, month, day] = value.split('-');
  return `${Number(month)}/${Number(day)}`;
}

function SourceCard({ name, source }: { name: string; source: HoloscapeSource }) {
  return <div className={`holoscape-source holoscape-source--${source.status}`}>
    <strong>{name}</strong><span>{source.status}{source.refreshing ? ' · refreshing' : ''}</span>
    <small>{source.fetched_at ? `Updated ${new Date(source.fetched_at).toLocaleString()}` : 'No verified snapshot yet'}</small>
    {source.coverage && <small>{source.coverage}</small>}
    {source.refresh_error && <small role="alert">Refresh failed: {source.refresh_error}</small>}
  </div>;
}

function SeriesChart({ title, note, source, lines, rows }: {
  title: string; note: string; source: HoloscapeSource; lines: SeriesLine[]; rows: HoloscapeSeriesDay[];
}) {
  const hasValues = rows.some(day => lines.some(line => typeof day[line.key] === 'number'));
  return <section className="holoscape-chart" aria-label={title}>
    <div className="holoscape-chart-heading"><h2>{title}</h2><span>{source.status}</span></div>
    <p>{note}</p>
    {hasValues ? <div className="holoscape-plot" role="img" aria-label={`${title} daily time series`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="#364052" strokeDasharray="3 3" />
          <XAxis dataKey="date" tickFormatter={displayDate} stroke="#acb5c3" minTickGap={16} />
          <YAxis stroke="#acb5c3" width={52} allowDecimals={title.endsWith('session time')} />
          <Tooltip labelFormatter={value => `${String(value)} · ${title}`} contentStyle={{ background: '#1e2530', border: '1px solid #47536a' }} />
          <Legend />
          {lines.map(line => <Line key={line.key} type="linear" dataKey={line.key} name={line.label}
            stroke={line.color} strokeWidth={2} dot={rows.length <= 14} connectNulls={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </div> : <p className="holoscape-chart-empty">{source.status === 'loading' ? 'Loading this source…' : 'No verified data for this source or range.'}</p>}
  </section>;
}

export function HoloscapeProgressPage() {
  const [data, setData] = useState<HoloscapeSeriesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<Range>('all');
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    let nextPoll: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const response = await fetchHoloscapeSeries(controller.signal);
        if (controller.signal.aborted) return;
        setData(response);
        setError(null);
        const pending = Object.values(response.sources).some(source => source.status === 'loading' || source.refreshing);
        nextPoll = setTimeout(load, pending ? 3000 : 5 * 60 * 1000);
      } catch (failure) {
        if (isAbortError(failure) || controller.signal.aborted) return;
        setError(failure instanceof Error ? failure.message : 'Holoscape feed unavailable');
        nextPoll = setTimeout(load, 30000);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => { controller.abort(); clearTimeout(nextPoll); };
  }, [revision]);

  const rows = range === 'all' ? data?.series ?? [] : data?.series.slice(-range) ?? [];
  const sourceNames: Array<[keyof HoloscapeSeriesResponse['sources'], string]> = [
    ['board', 'Project Tracker'], ['github', 'GitHub'], ['hermes', 'Hermes metadata'], ['billing', 'Billing'],
  ];

  return <PageShell title="Holoscape progress" subtitle="A live, temporary view of project activity over time. Full interpretation comes after the project finishes."
    actions={<button type="button" onClick={() => setRevision(value => value + 1)}>Refresh view</button>}
    mainClassName="holoscape-page">
    {loading && !data && <p role="status">Loading Holoscape sources…</p>}
    {error && <p role="alert" className="holoscape-error">{error}. {data ? 'Showing the last available view.' : 'Retrying shortly.'}</p>}
    {data && <>
      <div className="holoscape-intro">
        <p>Daily observations from {data.window.start} through {data.window.end} ({data.window.timezone}). Missing sources leave gaps; a plotted zero means the source loaded and observed no event.</p>
        <div className="holoscape-range" role="group" aria-label="Chart range">
          {([7, 14, 'all'] as const).map(value => <button key={value} type="button" aria-pressed={range === value}
            onClick={() => setRange(value)}>{value === 'all' ? 'All dates' : `${value} days`}</button>)}
        </div>
      </div>
      <div className="holoscape-sources" aria-label="Source freshness">
        {sourceNames.map(([key, label]) => <SourceCard key={key} name={label} source={data.sources[key]} />)}
      </div>
      <div className="holoscape-context">
        <div><strong>DeepSeek cost</strong><span>{data.deepseek_cost_usd === null ? 'Unknown — no verified charge' : `$${data.deepseek_cost_usd.toFixed(2)}`}</span></div>
        <div><strong>Holoscape PR</strong><span>{data.pr ? <><a href={data.pr.url}>View PR</a> · {data.pr.merged ? 'Merged' : data.pr.state} · {data.pr.commits} commits · {data.pr.reviews} reviews</> : 'GitHub snapshot pending'}</span></div>
        <div><strong>Recorded models</strong><span>{data.models && Object.keys(data.models).length
          ? Object.entries(data.models).map(([model, count]) => `${model}: ${count}`).join(' · ')
          : 'Hermes snapshot pending'}</span></div>
      </div>
      <div className="holoscape-grid">
        {charts.map(chart => <SeriesChart key={chart.title} title={chart.title} note={chart.note}
          source={data.sources[chart.source]} lines={chart.lines} rows={rows} />)}
      </div>
    </>}
  </PageShell>;
}
