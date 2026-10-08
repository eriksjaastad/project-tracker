import { useCallback, useEffect, useState } from 'react';
import { fetchCodebaseSize, isAbortError, refreshCodebaseSize } from '../api';
import type { CodebaseSizeReport } from '../types';
import { PageShell } from './PageShell';
import './CodebasePage.css';

const MINUS = '−';
const EMPTY = '—';

/** Signed value; a magnitude that rounds to zero carries no sign (never "-0.0"). */
function signed(value: number | null, digits: number): string {
  if (value === null) return EMPTY;
  const rounded = Number(value.toFixed(digits));
  if (rounded === 0) return (0).toFixed(digits);
  const text = Math.abs(rounded).toFixed(digits);
  return rounded > 0 ? `+${text}` : `${MINUS}${text}`;
}

const formatChange = (value: number | null) => signed(value, 0);
const formatScore = (value: number | null) => signed(value, 1);

export function CodebasePage() {
  const [report, setReport] = useState<CodebaseSizeReport | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setLoadError(null);
    try {
      const next = await fetchCodebaseSize(signal);
      if (signal?.aborted) return;
      setReport(next);
    } catch (failure) {
      if (isAbortError(failure) || signal?.aborted) return;
      setLoadError(failure instanceof Error ? failure.message : 'Codebase size unavailable');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function refresh() {
    setScanning(true);
    setRefreshError(null);
    try {
      const next = await refreshCodebaseSize();
      setReport(next);
      setLoadError(null);
    } catch (failure) {
      setRefreshError(failure instanceof Error ? failure.message : 'Refresh failed');
    } finally {
      setScanning(false);
    }
  }

  const actions = (
    <button type="button" onClick={() => void refresh()} disabled={scanning}>
      {scanning ? 'Scanning…' : 'Refresh'}
    </button>
  );

  return (
    <PageShell
      title="Codebase size"
      subtitle="Lines of code and docs per project, scored against the first recorded run."
      actions={actions}
      mainClassName="codebase-page"
    >
      {loading && !report && <p role="status">Loading codebase size…</p>}
      {loadError && (
        <div role="alert" className="codebase-error">
          <p>Could not load codebase size: {loadError}</p>
          <button type="button" onClick={() => void load()}>Retry</button>
        </div>
      )}
      {refreshError && (
        <p role="alert" className="codebase-error">
          Refresh failed: {refreshError}
          {report ? ' Showing the previous results.' : ''}
        </p>
      )}
      {report && (
        <>
          <div className="codebase-meta">
            <span>Baseline: {report.baseline_date ?? 'none yet'}</span>
            <span>Latest run: {report.latest_date ?? 'none yet'}</span>
          </div>
          <p className="codebase-formula">{report.formula}</p>
          {report.rows.length === 0 ? (
            <p className="codebase-empty">
              No runs yet {EMPTY} press Refresh to take the first snapshot; it becomes the baseline.
            </p>
          ) : (
            <div className="codebase-table-wrap">
              <table className="codebase-table">
                <thead>
                  <tr>
                    <th scope="col">Project</th>
                    <th scope="col">Code</th>
                    <th scope="col">Tests</th>
                    <th scope="col">Doc files</th>
                    <th scope="col">Doc lines</th>
                    <th scope="col">Last commit</th>
                    <th scope="col">Commits (90d)</th>
                    <th scope="col">Change since baseline</th>
                    <th scope="col">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {report.rows.map(row => (
                    <tr key={row.project}>
                      <th scope="row">{row.project}</th>
                      <td>{row.code}</td>
                      <td>{row.tests}</td>
                      <td>{row.doc_files}</td>
                      <td>{row.doc_lines}</td>
                      <td>{row.last_commit ?? EMPTY}</td>
                      <td>{row.commits_90d ?? EMPTY}</td>
                      <td>{formatChange(row.change)}</td>
                      <td>{formatScore(row.score)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row">TOTAL ({report.total.repos} repos)</th>
                    <td>{report.total.code}</td>
                    <td>{report.total.tests}</td>
                    <td>{report.total.doc_files}</td>
                    <td>{report.total.doc_lines}</td>
                    <td>{EMPTY}</td>
                    <td>{EMPTY}</td>
                    <td>{EMPTY}</td>
                    <td>{formatScore(report.total.score)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </>
      )}
    </PageShell>
  );
}
