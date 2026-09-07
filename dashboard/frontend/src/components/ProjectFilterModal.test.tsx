import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProjectFilterModal } from './ProjectFilterModal';

vi.mock('../api', async (importOriginal) => ({
  // Spread the real module so isAbortError is the REAL implementation --
  // a hand-copied literal here would not notice if api.ts changed.
  ...(await importOriginal<typeof import('../api')>()),
  fetchProjects: vi.fn(),
}));

import { fetchProjects } from '../api';

function renderModal(isOpen: boolean) {
  return render(
    <MemoryRouter>
      <ProjectFilterModal isOpen={isOpen} onClose={() => {}} currentProject={undefined} />
    </MemoryRouter>,
  );
}

describe('ProjectFilterModal cancellation', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Never settles unless its signal aborts.
    vi.mocked(fetchProjects).mockImplementation((signal?: AbortSignal) =>
      new Promise((_resolve, reject) => {
        signal?.addEventListener('abort', () => {
          const err = new Error('Aborted');
          err.name = 'AbortError';
          reject(err);
        });
      }),
    );
  });

  it('keeps the loading state while a superseded request aborts and a new one is in flight', async () => {
    const { rerender } = renderModal(true);

    expect(screen.getByText('Loading projects...')).toBeTruthy();

    // Close, which aborts the in-flight request, then reopen, which starts a
    // fresh one. `return` inside catch does not skip `finally`, so an
    // unguarded `finally` clears loading for the request that was cancelled —
    // while the new request is still pending and there is nothing to show.
    await act(async () => {
      rerender(
        <MemoryRouter>
          <ProjectFilterModal isOpen={false} onClose={() => {}} currentProject={undefined} />
        </MemoryRouter>,
      );
    });
    await act(async () => {
      rerender(
        <MemoryRouter>
          <ProjectFilterModal isOpen onClose={() => {}} currentProject={undefined} />
        </MemoryRouter>,
      );
    });

    expect(fetchProjects).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('Loading projects...')).toBeTruthy();
  });
});
