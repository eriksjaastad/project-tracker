import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HoloscapeProgressPage } from './HoloscapeProgressPage';

const base = {
  window: { start: '2026-09-20', end: '2026-09-23', timezone: 'America/New_York' },
  series: [
    { date: '2026-09-22', task_created: 0, task_completed: 1, review_entries: 0, review_bounces: 0 },
    { date: '2026-09-23', task_created: 2, task_completed: 0, review_entries: 1, review_bounces: 1 },
  ],
  sources: {
    board: { status: 'ok', fetched_at: '2026-09-23T12:00:00Z', coverage: 'Board events' },
    github: { status: 'loading', fetched_at: null, coverage: null },
    hermes: { status: 'unavailable', fetched_at: null, coverage: null },
    billing: { status: 'unavailable', fetched_at: null, coverage: 'No verified charges' },
  },
  pr: null,
  models: null,
  deepseek_cost_usd: null,
};

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('Holoscape progress', () => {
  it('shows source gaps separately from observed zero and keeps cost unknown', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => base }));
    render(<HoloscapeProgressPage />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading Holoscape sources');
    await waitFor(() => expect(screen.getByText(/Missing sources leave gaps/)).toBeInTheDocument());
    expect(screen.getByText('Unknown — no verified charge')).toBeInTheDocument();
    expect(screen.getByLabelText('Board flow daily time series')).toBeInTheDocument();
    expect(screen.getAllByText('Loading this source…')).toHaveLength(2);
    expect(screen.getAllByText('No verified data for this source or range.')).toHaveLength(9);
    expect(screen.getByText('CI workflow runs by current result')).toBeInTheDocument();
    expect(screen.getByText('Manager tokens')).toBeInTheDocument();
    expect(screen.getByText('Delegate tokens')).toBeInTheDocument();
    expect(screen.getByText('DeepSeek CLI tokens')).toBeInTheDocument();
    expect(screen.getByText('Delegate and DeepSeek sessions')).toBeInTheDocument();
    expect(screen.getByText('Worker session time')).toBeInTheDocument();
    expect(screen.getByText('DeepSeek cache-read tokens')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '7 days' }));
    expect(screen.getByRole('button', { name: '7 days' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('preserves the last view on a failed reload and retries via the control', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => base })
      .mockResolvedValueOnce({ ok: false, status: 503 });
    vi.stubGlobal('fetch', fetcher);
    render(<HoloscapeProgressPage />);
    await waitFor(() => expect(screen.getByText(/Missing sources leave gaps/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Refresh view' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('HTTP 503'));
    expect(screen.getByText('Unknown — no verified charge')).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('reads again at the failed-source retry interval', async () => {
    vi.useFakeTimers();
    const failedSource = {
      ...base,
      sources: {
        ...base.sources,
        github: { status: 'unavailable', fetched_at: null, refresh_error: 'GitHub refresh failed. Retrying shortly.' },
      },
    };
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => failedSource });
    vi.stubGlobal('fetch', fetcher);
    const { unmount } = render(<HoloscapeProgressPage />);
    await act(async () => { await Promise.resolve(); });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(59_999); });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(1); await Promise.resolve(); });
    expect(fetcher).toHaveBeenCalledTimes(2);
    unmount();
  });
});
