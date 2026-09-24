import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { JobsPage } from './JobsPage';

globalThis.fetch = vi.fn() as typeof fetch;

vi.mock('./PageShell', () => ({
  PageShell: ({ children, title, subtitle }: { children: React.ReactNode; title: string; subtitle?: string }) => (
    <div>
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
      {children}
    </div>
  ),
}));

vi.mock('./Spinner', () => ({
  Spinner: () => <div>Loading...</div>,
}));

vi.mock('./Notification', () => ({
  Notification: ({ message }: { message: string }) => <div role="alert">{message}</div>,
}));

vi.mock('./JobStatsChart', () => ({
  JobStatsChart: () => <div data-testid="job-stats-chart">Job Stats Chart</div>,
}));

vi.mock('./CategoryTable', () => ({
  CategoryTable: () => <div data-testid="category-table">Category Table</div>,
}));

describe('JobsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('groups jobs by company', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 1,
            company: 'Acme Corp',
            title: 'Frontend Developer',
            url: 'https://example.com/job1',
            location: 'San Francisco',
            posted_date: '2026-09-20',
            first_seen: '2026-09-22',
            category: 'Frontend/React',
            source: 'ats_sweep',
            deleted_at: null,
            raw: null,
          },
          {
            id: 2,
            company: 'Acme Corp',
            title: 'Backend Engineer',
            url: 'https://example.com/job2',
            location: 'Remote',
            posted_date: '2026-09-21',
            first_seen: '2026-09-23',
            category: 'Backend',
            source: 'ats_sweep',
            deleted_at: null,
            raw: null,
          },
          {
            id: 3,
            company: 'Tech Inc',
            title: 'Full Stack Developer',
            url: 'https://example.com/job3',
            location: 'New York',
            posted_date: '2026-09-19',
            first_seen: '2026-09-21',
            category: 'Full Stack',
            source: 'hn',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('Tech Inc')).toBeInTheDocument();

    expect(screen.getByText('Frontend Developer')).toBeInTheDocument();
    expect(screen.getByText('Backend Engineer')).toBeInTheDocument();
    expect(screen.getByText('Full Stack Developer')).toBeInTheDocument();
  });

  it('deletes a job and removes it from view', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 1,
            company: 'Acme Corp',
            title: 'Frontend Developer',
            url: 'https://example.com/job1',
            location: 'San Francisco',
            posted_date: '2026-09-20',
            first_seen: '2026-09-22',
            category: 'Frontend/React',
            source: 'ats_sweep',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    expect(screen.getByText('Frontend Developer')).toBeInTheDocument();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ job: { id: 1, deleted_at: '2026-09-24T00:00:00Z' } }),
    } as Response);

    const deleteButton = screen.getByLabelText('Dismiss Frontend Developer');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(screen.queryByText('Frontend Developer')).not.toBeInTheDocument();
    });

    expect(screen.getByRole('alert')).toHaveTextContent('Job dismissed');
  });

  it('shows empty state when no jobs', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ jobs: [] }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    expect(screen.getByText('No open job listings')).toBeInTheDocument();
  });

  it('sets deleted_at via DELETE endpoint', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 5,
            company: 'Test Corp',
            title: 'Test Job',
            url: 'https://example.com/test',
            location: null,
            posted_date: null,
            first_seen: '2026-09-24',
            category: 'Other',
            source: 'manual',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Test Job')).toBeInTheDocument();
    });

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job: { id: 5, deleted_at: '2026-09-24T12:00:00Z' },
      }),
    } as Response);

    const deleteButton = screen.getByLabelText('Dismiss Test Job');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/jobs/5', { method: 'DELETE' });
    });

    expect(screen.queryByText('Test Job')).not.toBeInTheDocument();
  });

  it('shows error notification when jobs fail to load', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 500,
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load jobs');
  });

  it('shows error notification and keeps job in list when delete fails', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 7,
            company: 'Error Corp',
            title: 'Undeletable Job',
            url: 'https://example.com/job',
            location: 'Remote',
            posted_date: '2026-09-23',
            first_seen: '2026-09-24',
            category: 'Backend',
            source: 'ats_sweep',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Undeletable Job')).toBeInTheDocument();
    });

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 500,
    } as Response);

    const deleteButton = screen.getByLabelText('Dismiss Undeletable Job');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Failed to dismiss job');
    });

    expect(screen.getByText('Undeletable Job')).toBeInTheDocument();
  });

  it('loads and displays job stats chart when stats are available', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ jobs: [] }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          jobs_per_day: [{ date: '2026-09-20', count: 5 }],
          submissions_per_day: [{ date: '2026-09-21', count: 2 }],
          categories: [{ category: 'Frontend/React', count: 3 }],
        }),
      } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('job-stats-chart')).toBeInTheDocument();
      expect(screen.getByTestId('category-table')).toBeInTheDocument();
    });
  });

  it('handles stats loading failure gracefully', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ jobs: [] }),
      } as Response)
      .mockRejectedValueOnce(new Error('Stats unavailable'));

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId('job-stats-chart')).not.toBeInTheDocument();
      expect(screen.queryByTestId('category-table')).not.toBeInTheDocument();
    });
  });
});
