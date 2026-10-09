import { render, screen, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProjectsProvider } from '../hooks/ProjectsProvider';
import { CalendarPage } from './CalendarPage';

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  fetchCalendarEvents: vi.fn(),
  fetchCalendarCrons: vi.fn(),
  fetchProjects: vi.fn(),
}));

import { fetchCalendarCrons, fetchCalendarEvents, fetchProjects } from '../api';

function abortable(signal?: AbortSignal) {
  return new Promise<never>((_resolve, reject) => {
    signal?.addEventListener('abort', () => {
      const err = new Error('Aborted');
      err.name = 'AbortError';
      reject(err);
    });
  });
}

describe('CalendarPage load', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(fetchCalendarCrons).mockResolvedValue([]);
    vi.mocked(fetchProjects).mockResolvedValue([{ id: 'p', name: 'Proj' }] as never);
  });

  it('shows the loading text, then the page, with projects in the filter', async () => {
    vi.mocked(fetchCalendarEvents).mockResolvedValue([]);
    render(<CalendarPage />, { wrapper: ProjectsProvider });
    expect(screen.getByText('Loading calendar…')).toBeTruthy();
    expect(await screen.findByRole('option', { name: 'Proj' })).toBeTruthy();
    expect(screen.queryByText('Loading calendar…')).toBeNull();
  });

  it('still blocks the page with the projects error when projects fail, as when fetched together', async () => {
    vi.mocked(fetchCalendarEvents).mockResolvedValue([]);
    vi.mocked(fetchProjects).mockRejectedValue(new Error('projects down'));
    render(<CalendarPage />, { wrapper: ProjectsProvider });
    expect(await screen.findByText('Error: projects down')).toBeTruthy();
    expect(screen.queryByText('Loading calendar…')).toBeNull();
  });

  it('shows the events error and aborts the request on unmount', async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(fetchCalendarEvents).mockImplementation((_p, s) => { signal = s; return abortable(s); });
    const { unmount } = render(<CalendarPage />, { wrapper: ProjectsProvider });
    await act(async () => {});
    expect(screen.getByText('Loading calendar…')).toBeTruthy();
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it('shows the events error text', async () => {
    vi.mocked(fetchCalendarEvents).mockRejectedValue(new Error('events down'));
    render(<CalendarPage />, { wrapper: ProjectsProvider });
    expect(await screen.findByText('Error: events down')).toBeTruthy();
  });
});
