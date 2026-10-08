import { useCallback, useEffect, useRef, useState } from 'react';
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

  // Only the newest request may update the page: a load still in flight when
  // Refresh is pressed would otherwise land after it and show older data.
  const generation = useRef(0);
  const inflightLoad = useRef<AbortController | null>(null);

  const claim = useCallback(() => {
    inflightLoad.current?.abort();
    inflightLoad.current = null;
    generation.current += 1;
    return generation.current;
  }, []);

  const load = useCallback(async () => {
    const gen = claim();
    const controller = new AbortController();
    inflightLoad.current = controller;
    setLoading(true);
    setLoadError(null);
    try {
      const next = await fetchCodebaseSize(controller.signal);
      if (gen !== generation.current) return;
      setReport(next);
    } catch (failure) {
      if (isAbortError(failure) || gen !== generation.current) return;
      setLoadError(failure instanceof Error ? failure.message : 'Codebase size unavailable');
    } finally {
      if (gen === generation.current) setLoading(false);
    }
  }, [claim]);

  useEffect(() => {
    void load();
    return () => { claim(); };
  }, [load, claim]);

  async function refresh() {
    const gen = claim();
    setLoading(false);
    setScanning(true);
    setRefreshError(null);
    try {
      const next = await refreshCodebaseSize();
      if (gen !== generation.current) return;
      setReport(next);
      setLoadError(null);
    } catch (failure) {
      if (gen !== generation.current) return;
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
