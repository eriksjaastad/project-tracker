import { render, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LoopMonitor } from './LoopMonitor';

describe('LoopMonitor cancellation', () => {
  let signals: AbortSignal[];

  beforeEach(() => {
    vi.useFakeTimers();
    signals = [];
    // Every poll hangs forever unless its own signal aborts, so a tick that
    // starts is still in flight when the next one fires.
    vi.stubGlobal('fetch', vi.fn((_url: string, init?: RequestInit) => {
      const signal = init?.signal as AbortSignal | undefined;
      if (signal) signals.push(signal);
      return new Promise<Response>((_resolve, reject) => {
        signal?.addEventListener('abort', () => {
          const err = new Error('Aborted');
          err.name = 'AbortError';
          reject(err);
        });
      });
    }));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('aborts every in-flight poll on unmount, not just the most recent', async () => {
    const { unmount } = render(<LoopMonitor refreshInterval={1000} />);

    // First tick fires on mount and never settles. Drive two more ticks so
    // three requests are simultaneously in flight.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(signals).toHaveLength(3);
    expect(signals.every(s => !s.aborted)).toBe(true);

    await act(async () => {
      unmount();
    });

    // Holding only the latest controller would leave the first two orphaned:
    // nothing could abort them, and they would setState after unmount.
    const orphaned = signals.filter(s => !s.aborted);
    expect(orphaned).toHaveLength(0);
  });

  it('stops polling after unmount', async () => {
    const { unmount } = render(<LoopMonitor refreshInterval={1000} />);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(signals).toHaveLength(2);

    await act(async () => {
      unmount();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(signals).toHaveLength(2);
  });
});
