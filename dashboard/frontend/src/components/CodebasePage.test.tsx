import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CodebasePage } from './CodebasePage';
import type { CodebaseSizeReport, CodebaseSizeRow } from '../types';

const FORMULA = 'score = (baseline_lean − current_lean) / baseline_lean × 100';

function row(over: Partial<CodebaseSizeRow>): CodebaseSizeRow {
  return {
    project: 'p', code: 0, tests: 0, doc_files: 0, doc_lines: 0, last_commit: '2026-10-01',
    commits_90d: 4, error: null, score: null, baseline_lean: null, change: null, ...over,
  };
}

const report: CodebaseSizeReport = {
  baseline_date: '2026-10-01',
  latest_date: '2026-10-08',
  formula: FORMULA,
  rows: [
    row({ project: 'alpha', code: 900, tests: 300, doc_files: 4, doc_lines: 100, change: -340, score: 25.04 }),
    row({ project: 'beta', code: 500, change: 120, score: -3.2 }),
    row({ project: 'gamma', code: 50, change: 0, score: -0.04 }),
    row({ project: 'delta', code: 10, last_commit: null, commits_90d: null }),
  ],
  total: { code: 1460, tests: 300, doc_files: 4, doc_lines: 100, repos: 4, score: 12.5 },
};

const empty: CodebaseSizeReport = {
  baseline_date: null, latest_date: null, formula: FORMULA, rows: [],
  total: { code: 0, tests: 0, doc_files: 0, doc_lines: 0, repos: 0, score: null },
};

function reply(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body };
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('CodebasePage', () => {
  it('renders header, formula, rows sorted as given, and the total', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(report)));
    render(<CodebasePage />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading');
    await screen.findByText('alpha');
    expect(screen.getByText('Baseline: 2026-10-01')).toBeInTheDocument();
    expect(screen.getByText('Latest run: 2026-10-08')).toBeInTheDocument();
    expect(screen.getByText(FORMULA)).toBeInTheDocument();
    const alpha = within(screen.getByText('alpha').closest('tr')!);
    expect(alpha.getByText('−340')).toBeInTheDocument();
    expect(alpha.getByText('+25.0')).toBeInTheDocument();
    const beta = within(screen.getByText('beta').closest('tr')!);
    expect(beta.getByText('+120')).toBeInTheDocument();
    expect(beta.getByText('−3.2')).toBeInTheDocument();
    const total = within(screen.getByText(/^TOTAL/).closest('tr')!);
    expect(total.getByText('1460')).toBeInTheDocument();
    expect(total.getByText('+12.5')).toBeInTheDocument();
    const names = screen.getAllByRole('rowheader').map(h => h.textContent);
    expect(names.slice(0, 4)).toEqual(['alpha', 'beta', 'gamma', 'delta']);
  });

  it('shows an em dash for null change and score, and never -0.0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(report)));
    const { container } = render(<CodebasePage />);
    await screen.findByText('delta');
    const delta = within(screen.getByText('delta').closest('tr')!);
    expect(delta.getAllByText('—')).toHaveLength(4); // last commit, commits, change, score
    const cells = within(screen.getByText('gamma').closest('tr')!).getAllByRole('cell').map(c => c.textContent);
    expect(cells[6]).toBe('0'); // change 0
    expect(cells[7]).toBe('0.0'); // -0.04 rounds to 0.0, unsigned
    expect(container.textContent).not.toMatch(/-0\.0|−0\.0/);
  });

  it('shows the empty state when there are no runs yet', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(empty)));
    render(<CodebasePage />);
    await screen.findByText(/No runs yet/);
    expect(screen.getByText(/it becomes the baseline/)).toBeInTheDocument();
    expect(screen.getByText('Baseline: none yet')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows a load error, not an empty table, when the load fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply({ detail: 'Table is missing' }, false, 500)));
    render(<CodebasePage />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Table is missing');
    expect(screen.queryByText(/No runs yet/)).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('replaces the table with the refresh response and disables the button while scanning', async () => {
    let finish: (value: unknown) => void = () => {};
    const fetcher = vi.fn()
      .mockResolvedValueOnce(reply(empty))
      .mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    vi.stubGlobal('fetch', fetcher);
    const user = userEvent.setup();
    render(<CodebasePage />);
    await screen.findByText(/No runs yet/);
    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(screen.getByRole('button', { name: 'Scanning…' })).toBeDisabled();
    expect(fetcher).toHaveBeenLastCalledWith('/api/codebase-size/refresh', { method: 'POST' });
    finish(reply(report));
    await screen.findByText('alpha');
    expect(screen.queryByText(/No runs yet/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled();
  });

  it('shows the refresh error and keeps the previous rows on failure', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(reply(report))
      .mockResolvedValueOnce(reply({ detail: 'Scan failed for 1 repo(s): broken' }, false, 502));
    vi.stubGlobal('fetch', fetcher);
    const user = userEvent.setup();
    render(<CodebasePage />);
    await screen.findByText('alpha');
    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Scan failed for 1 repo(s): broken'));
    expect(screen.getByText('alpha')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled();
  });
});
