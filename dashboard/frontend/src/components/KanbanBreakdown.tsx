import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import './KanbanBreakdown.css';

const BOARD_COLUMNS = ['Backlog', 'To Do', 'In Progress', 'Review'] as const;

type BoardColumn = (typeof BOARD_COLUMNS)[number];

interface ProjectCount {
  project_id: string;
  project: string;
  count: number;
}

interface BreakdownData {
  statuses: string[];
  columns: Record<string, ProjectCount[]>;
  totals: Record<string, number>;
  generated_at: string;
}

// Enough rows to cover every column but Backlog, which is the pile being
// worked down and the one worth expanding deliberately.
const ROW_LIMIT = 12;
const POLL_MS = 60000;

function Column({ status, entries, expanded }: {
  status: BoardColumn;
  entries: ProjectCount[];
  expanded: boolean;
}) {
  const visible = expanded ? entries : entries.slice(0, ROW_LIMIT);
  const hidden = entries.length - visible.length;
  const total = entries.reduce((sum, entry) => sum + entry.count, 0);

  return (
    <div className="breakdown-column">
      <div className="breakdown-column-header">
        <span className="breakdown-column-title">{status}</span>
        <span className="breakdown-column-total">{total}</span>
      </div>
      {entries.length === 0 ? (
        <p className="breakdown-empty">No cards</p>
      ) : (
        <ul className="breakdown-list">
          {visible.map(entry => (
            <li key={entry.project_id} className="breakdown-row">
              <Link
                to={`/kanban/${entry.project_id}`}
                className="breakdown-project"
                title={entry.project}
              >
                {entry.project}
              </Link>
              <span className="breakdown-count">{entry.count}</span>
            </li>
          ))}
        </ul>
      )}
      {hidden > 0 && <p className="breakdown-more">+{hidden} more</p>}
    </div>
  );
}

export function KanbanBreakdown() {
  const [data, setData] = useState<BreakdownData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const toggle = useCallback(() => setExpanded(value => !value), []);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;

    async function load() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      try {
        const response = await fetch('/api/kanban/breakdown', { signal: controller.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const next: BreakdownData = await response.json();
        if (disposed) return;
        setData(next);
        setError(null);
      } catch {
        if (disposed) return;
        // A failed fetch must not read as an empty board — the last good
        // counts stay on screen and the failure is named.
        setError('Board counts are unavailable. Retrying shortly.');
      } finally {
        clearTimeout(timeout);
        if (!disposed) {
          setLoading(false);
          timer = setTimeout(load, POLL_MS);
        }
      }
    }

    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, []);

  const hasMore = BOARD_COLUMNS.some(status => (data?.columns?.[status]?.length || 0) > ROW_LIMIT);
  const openCards = data
    ? BOARD_COLUMNS.reduce((sum, status) => sum + (data.totals?.[status] || 0), 0)
    : 0;

  return (
    <section className="dashboard-section breakdown-section" aria-label="Kanban board breakdown">
      <h2>
        Kanban Board
        {data && <span className="breakdown-subtitle">{openCards} open cards</span>}
      </h2>
      {error && <p className="breakdown-error" role="alert">{error}{data ? ' Showing the last counts.' : ''}</p>}
      {!data ? (
        <p className="breakdown-empty">{loading ? 'Loading board counts…' : 'Board counts are unavailable.'}</p>
      ) : (
        <>
          <div className="breakdown-columns">
            {BOARD_COLUMNS.map(status => (
              <Column
                key={status}
                status={status}
                entries={data.columns?.[status] || []}
                expanded={expanded}
              />
            ))}
          </div>
          {hasMore && (
            <button className="expand-button" onClick={toggle}>
              {expanded ? 'Show top projects' : 'Show every project'}
            </button>
          )}
        </>
      )}
    </section>
  );
}
