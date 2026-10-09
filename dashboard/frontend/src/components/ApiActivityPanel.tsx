import { useState } from 'react';
import { usePolling } from '../hooks/usePolling';
import './ApiActivityPanel.css';
import { summarizeActivity } from '../utils/apiActivity';
import type { Usage, Activity } from '../utils/apiActivity';

const LIMIT = 5000;

function localDate() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function ApiActivityPanel() {
  const [day, setDay] = useState(localDate);
  const [followToday, setFollowToday] = useState(true);
  type Snapshot = { day: string; rows: Activity[]; limited: boolean; fetchedAt: string };

  const { data: snapshot, error: failure, loading: fetching } = usePolling<Snapshot>(async (signal) => {
    if (!day) return undefined;
    if (followToday && day !== localDate()) {
      // The calendar day rolled over; the new `day` restarts the poll.
      setDay(localDate());
      return undefined;
    }
    const since = new Date(`${day}T00:00:00`).toISOString();
    const response = await fetch(`/api/costs/usage?since=${encodeURIComponent(since)}&limit=${LIMIT}`, { signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const rows: Usage[] = await response.json();
    if (!Array.isArray(rows) || rows.some(row => !row || typeof row !== 'object'
      || typeof row.timestamp !== 'string'
      || [row.provider, row.service, row.model, row.project].some(value => value != null && typeof value !== 'string'))) {
      throw new Error('Invalid usage response');
    }
    return { day, rows: summarizeActivity(rows, day), limited: rows.length >= LIMIT, fetchedAt: new Date().toISOString() };
  }, 60000, [day, followToday], { timeoutMs: 15000 });
  const data = snapshot?.day === day ? snapshot : null;
  const error = failure !== null;

  return (
    <section className="dashboard-section api-activity">
      <div className="api-activity-header">
        <h2>Daily API Activity</h2>
        <label>Day <input type="date" aria-label="API activity day" value={day} max={localDate()} onChange={event => {
          if (event.target.value) {
            setDay(event.target.value);
            setFollowToday(event.target.value === localDate());
          }
        }} /></label>
      </div>
      <p>Observed calls from reporting projects. APIs without usage tracking will not appear. Dates use your local time.</p>
      <div role="status" className="api-activity-status">
        {fetching && <span>◷ Fetching API activity… </span>}
        {data && <span>Checked {new Date(data.fetchedAt).toLocaleTimeString()} · refreshes every minute</span>}
      </div>
      {error && <p role="alert">API activity is unavailable. {data ? 'Showing previous results. ' : ''}Retrying every minute.</p>}
      {data?.limited && <p role="alert">Partial results: only the latest {LIMIT.toLocaleString()} calls since this day were returned. Earlier calls may be missing.</p>}
      {data && data.rows.length === 0 && <p>No calls recorded for this day{data.limited ? ' in the returned sample' : ''}.</p>}
      {!!data?.rows.length && (
        <div className="api-activity-scroll">
          <table>
            <thead><tr><th>Provider / API</th><th>Project</th><th>Calls</th><th>Estimated cost</th><th>Last observed</th></tr></thead>
            <tbody>{data.rows.map(row => (
              <tr key={JSON.stringify([row.provider, row.service, row.project])}>
                <td>{row.provider}<small>{row.service}</small></td>
                <td>{row.project}</td><td>{row.calls.toLocaleString()}</td>
                <td>{row.unpriced ? 'Incomplete pricing' : `$${row.cost.toFixed(4)}`}</td>
                <td><time dateTime={row.lastSeen}>{new Date(row.lastSeen).toLocaleString()}</time></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}
