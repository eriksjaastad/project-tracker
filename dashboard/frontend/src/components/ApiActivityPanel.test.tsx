import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiActivityPanel } from './ApiActivityPanel';
import { summarizeActivity } from '../utils/apiActivity';

const row = { provider: 'anthropic', model: 'haiku', project: 'alpha', timestamp: '2026-09-06T12:00:00', estimated_cost_usd: '0.02' };

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('API activity', () => {
  it('groups service and project, excludes other days, and keeps the latest call', () => {
    const groups = summarizeActivity([
      row, { ...row, timestamp: '2026-09-06T13:00:00', estimated_cost_usd: '0.03' },
      { ...row, project: 'beta', estimated_cost_usd: null },
      { ...row, timestamp: '2026-09-07T00:00:00' },
      { ...row, timestamp: 'invalid' },
    ], '2026-09-06');
    expect(groups).toHaveLength(2);
    expect(groups[0]).toMatchObject({ project: 'alpha', calls: 2, cost: 0.05, lastSeen: '2026-09-06T13:00:00' });
    expect(groups[1].unpriced).toBe(true);
  });

  it('reports HTTP failure as unavailable, not as no activity', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    render(<ApiActivityPanel />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('unavailable'));
    expect(screen.queryByText(/No calls recorded/)).not.toBeInTheDocument();
  });

  it('marks malformed prices as incomplete instead of coercing them into money', () => {
    for (const value of [' ', true, false, [], {}]) {
      const result = summarizeActivity([{ ...row, estimated_cost_usd: value as unknown as string }], '2026-09-06');
      expect(result[0]).toMatchObject({ unpriced: true, cost: 0 });
    }
  });

  it('moves the default day forward across local midnight', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-06T23:59:30'));
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal('fetch', fetcher);
    await act(async () => { render(<ApiActivityPanel />); });
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
    expect(screen.getByLabelText('API activity day')).toHaveValue('2026-09-07');
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('rejects malformed provider data before rendering it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [{ ...row, provider: {} }] }));
    render(<ApiActivityPanel />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('unavailable'));
  });

  it('warns when the source truncates records', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => Array(5000).fill(row) }));
    render(<ApiActivityPanel />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Partial results'));
  });

  it('refreshes without overlap and aborts on unmount', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal('fetch', fetcher);
    const view = await act(async () => render(<ApiActivityPanel />));
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
    expect(fetcher).toHaveBeenCalledTimes(2);
    const signal = fetcher.mock.calls[1][1].signal;
    view.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(120000); });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('cancels an old date request and ignores its late response', async () => {
    let resolve: (response: unknown) => void = () => {};
    const fetcher = vi.fn()
      .mockReturnValueOnce(new Promise(r => { resolve = r; }))
      .mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal('fetch', fetcher);
    render(<ApiActivityPanel />);
    const signal = fetcher.mock.calls[0][1].signal;
    fireEvent.change(screen.getByLabelText('API activity day'), { target: { value: '2026-01-01' } });
    expect(signal.aborted).toBe(true);
    await waitFor(() => expect(screen.getByText(/No calls recorded/)).toBeInTheDocument());
    await act(async () => resolve({ ok: true, json: async () => [row] }));
    expect(screen.queryByText('alpha')).not.toBeInTheDocument();
  });
});
