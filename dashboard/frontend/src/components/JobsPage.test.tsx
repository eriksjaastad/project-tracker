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
  CategoryTable: ({ categories }: { categories: Array<{ category: string; count: number }> }) => (
    <div data-testid="category-table">
      {categories.map(cat => (
        <span key={cat.category} data-testid={`category-count-${cat.category}`}>
          {cat.category}: {cat.count}
        </span>
      ))}
    </div>
  ),
}));

// Creates a promise this test controls the resolution of, so it can
// interleave two in-flight requests in a specific order.
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(res => {
    resolve = res;
  });
  return { promise, resolve };
}

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

  it('queues agent prompt and shows success notification', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 10,
            company: 'Test Inc',
            title: 'Senior Engineer',
            url: 'https://example.com/job10',
            location: 'Remote',
            posted_date: '2026-09-25',
            first_seen: '2026-09-25',
            category: 'Backend',
            source: 'manual',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Senior Engineer')).toBeInTheDocument();
    });

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        job_id: 10,
        message: 'Agent prompt queued successfully',
      }),
    } as Response);

    const agentButton = screen.getByLabelText('Queue agent prompt for Senior Engineer');
    await user.click(agentButton);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/jobs/10/agent-prompt', { method: 'POST' });
    });

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Agent prompt queued successfully');
    });
  });

  it('shows error when agent prompt queueing fails', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 11,
            company: 'Error Inc',
            title: 'Test Job',
            url: 'https://example.com/job11',
            location: 'Remote',
            posted_date: '2026-09-25',
            first_seen: '2026-09-25',
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
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Failed to queue agent prompt: Agent not available' }),
    } as Response);

    const agentButton = screen.getByLabelText('Queue agent prompt for Test Job');
    await user.click(agentButton);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Failed to queue agent prompt: Agent not available');
    });
  });

  it('submits a job and removes it from view', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 20,
            company: 'Submit Corp',
            title: 'Submittable Job',
            url: 'https://example.com/job20',
            location: 'Remote',
            posted_date: '2026-09-25',
            first_seen: '2026-09-25',
            category: 'Backend',
            source: 'manual',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Submittable Job')).toBeInTheDocument();
    });

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        submission: { id: 1, job_id: 20, submitted_at: '2026-09-25T12:00:00+00:00' },
      }),
    } as Response);

    const submitButton = screen.getByLabelText('Mark Submittable Job as submitted');
    await user.click(submitButton);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/jobs/20/submissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
    });

    await waitFor(() => {
      expect(screen.queryByText('Submittable Job')).not.toBeInTheDocument();
    });

    expect(screen.getByRole('alert')).toHaveTextContent('Job marked as submitted');
  });

  it('sends exactly one POST when the submit button is double-clicked', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 21,
            company: 'Double Click Inc',
            title: 'Fast Clicker Job',
            url: 'https://example.com/job21',
            location: 'Remote',
            posted_date: '2026-09-25',
            first_seen: '2026-09-25',
            category: 'Backend',
            source: 'manual',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Fast Clicker Job')).toBeInTheDocument();
    });

    let resolveSubmit: (value: Response) => void = () => {};
    vi.mocked(fetch).mockImplementationOnce(
      () =>
        new Promise<Response>(resolve => {
          resolveSubmit = resolve;
        })
    );

    const submitButton = screen.getByLabelText('Mark Fast Clicker Job as submitted');
    await user.dblClick(submitButton);

    expect(submitButton).toBeDisabled();

    resolveSubmit({
      ok: true,
      json: async () => ({
        submission: { id: 2, job_id: 21, submitted_at: '2026-09-25T12:00:00+00:00' },
      }),
    } as Response);

    await waitFor(() => {
      expect(screen.queryByText('Fast Clicker Job')).not.toBeInTheDocument();
    });

    const submissionPosts = vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => url === '/api/jobs/21/submissions');
    expect(submissionPosts).toHaveLength(1);
  });

  it('shows error notification and keeps job in list when submit fails', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 22,
            company: 'Flaky Corp',
            title: 'Unsubmittable Job',
            url: 'https://example.com/job22',
            location: 'Remote',
            posted_date: '2026-09-25',
            first_seen: '2026-09-25',
            category: 'Backend',
            source: 'manual',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Unsubmittable Job')).toBeInTheDocument();
    });

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 500,
    } as Response);

    const submitButton = screen.getByLabelText('Mark Unsubmittable Job as submitted');
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Failed to submit job');
    });

    expect(screen.getByText('Unsubmittable Job')).toBeInTheDocument();
    expect(submitButton).not.toBeDisabled();
  });

  it('removes both rows when two submits overlap and resolve out of order', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 30,
            company: 'Overlap Inc',
            title: 'Job A',
            url: 'https://example.com/jobA',
            location: 'Remote',
            posted_date: '2026-09-25',
            first_seen: '2026-09-25',
            category: 'Backend',
            source: 'manual',
            deleted_at: null,
            raw: null,
          },
          {
            id: 31,
            company: 'Overlap Inc',
            title: 'Job B',
            url: 'https://example.com/jobB',
            location: 'Remote',
            posted_date: '2026-09-25',
            first_seen: '2026-09-25',
            category: 'Backend',
            source: 'manual',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Job A')).toBeInTheDocument();
      expect(screen.getByText('Job B')).toBeInTheDocument();
    });

    const submitA = deferred<Response>();
    const submitB = deferred<Response>();
    const statsRefresh = { ok: true, json: async () => ({ jobs_per_day: [], submissions_per_day: [], categories: [] }) } as Response;

    vi.mocked(fetch).mockImplementation((url: string | URL | Request) => {
      if (url === '/api/jobs/30/submissions') return submitA.promise;
      if (url === '/api/jobs/31/submissions') return submitB.promise;
      if (url === '/api/jobs/stats') return Promise.resolve(statsRefresh);
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    await user.click(screen.getByLabelText('Mark Job A as submitted'));
    await user.click(screen.getByLabelText('Mark Job B as submitted'));

    // Resolve the second submission first, then the first — the opposite
    // of request order — to prove removal doesn't depend on resolve order.
    submitB.resolve({
      ok: true,
      json: async () => ({ submission: { id: 2, job_id: 31 } }),
    } as Response);

    await waitFor(() => {
      expect(screen.queryByText('Job B')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Job A')).toBeInTheDocument();

    submitA.resolve({
      ok: true,
      json: async () => ({ submission: { id: 1, job_id: 30 } }),
    } as Response);

    await waitFor(() => {
      expect(screen.queryByText('Job A')).not.toBeInTheDocument();
    });
    expect(screen.queryByText('Job B')).not.toBeInTheDocument();
  });

  it('removes both rows when a submit and a delete overlap on different jobs', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 32,
            company: 'Mixed Co',
            title: 'Job To Submit',
            url: 'https://example.com/jobSubmit',
            location: 'Remote',
            posted_date: '2026-09-25',
            first_seen: '2026-09-25',
            category: 'Backend',
            source: 'manual',
            deleted_at: null,
            raw: null,
          },
          {
            id: 33,
            company: 'Mixed Co',
            title: 'Job To Delete',
            url: 'https://example.com/jobDelete',
            location: 'Remote',
            posted_date: '2026-09-25',
            first_seen: '2026-09-25',
            category: 'Backend',
            source: 'manual',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Job To Submit')).toBeInTheDocument();
      expect(screen.getByText('Job To Delete')).toBeInTheDocument();
    });

    const submitReq = deferred<Response>();
    const deleteReq = deferred<Response>();
    const statsRefresh = { ok: true, json: async () => ({ jobs_per_day: [], submissions_per_day: [], categories: [] }) } as Response;

    vi.mocked(fetch).mockImplementation((url: string | URL | Request, options?: RequestInit) => {
      if (url === '/api/jobs/32/submissions') return submitReq.promise;
      if (url === '/api/jobs/33' && options?.method === 'DELETE') return deleteReq.promise;
      if (url === '/api/jobs/stats') return Promise.resolve(statsRefresh);
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    await user.click(screen.getByLabelText('Mark Job To Submit as submitted'));
    await user.click(screen.getByLabelText('Dismiss Job To Delete'));

    // The delete (issued second) resolves first.
    deleteReq.resolve({
      ok: true,
      json: async () => ({ job: { id: 33, deleted_at: '2026-09-26T00:00:00Z' } }),
    } as Response);

    await waitFor(() => {
      expect(screen.queryByText('Job To Delete')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Job To Submit')).toBeInTheDocument();

    submitReq.resolve({
      ok: true,
      json: async () => ({ submission: { id: 3, job_id: 32 } }),
    } as Response);

    await waitFor(() => {
      expect(screen.queryByText('Job To Submit')).not.toBeInTheDocument();
    });
    expect(screen.queryByText('Job To Delete')).not.toBeInTheDocument();
  });

  it('refetches stats after a successful submit and the displayed count changes', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          jobs: [
            {
              id: 40,
              company: 'Stats Co',
              title: 'Countable Job',
              url: 'https://example.com/job40',
              location: 'Remote',
              posted_date: '2026-09-25',
              first_seen: '2026-09-25',
              category: 'Backend',
              source: 'manual',
              deleted_at: null,
              raw: null,
            },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          jobs_per_day: [],
          submissions_per_day: [],
          categories: [{ category: 'Backend', count: 5 }],
        }),
      } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('category-count-Backend')).toHaveTextContent('Backend: 5');
    });

    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ submission: { id: 5, job_id: 40 } }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          jobs_per_day: [],
          submissions_per_day: [{ date: '2026-09-25', count: 1 }],
          categories: [{ category: 'Backend', count: 4 }],
        }),
      } as Response);

    await user.click(screen.getByLabelText('Mark Countable Job as submitted'));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/jobs/stats');
    });

    await waitFor(() => {
      expect(screen.getByTestId('category-count-Backend')).toHaveTextContent('Backend: 4');
    });

    const statsCalls = vi.mocked(fetch).mock.calls.filter(([url]) => url === '/api/jobs/stats');
    expect(statsCalls).toHaveLength(2);
  });

  it('discards a stale stats response that resolves after a newer refresh', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          jobs: [
            {
              id: 41,
              company: 'Race Co',
              title: 'Job One',
              url: 'https://example.com/job41',
              location: 'Remote',
              posted_date: '2026-09-25',
              first_seen: '2026-09-25',
              category: 'Backend',
              source: 'manual',
              deleted_at: null,
              raw: null,
            },
            {
              id: 42,
              company: 'Race Co',
              title: 'Job Two',
              url: 'https://example.com/job42',
              location: 'Remote',
              posted_date: '2026-09-25',
              first_seen: '2026-09-25',
              category: 'Backend',
              source: 'manual',
              deleted_at: null,
              raw: null,
            },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          jobs_per_day: [],
          submissions_per_day: [],
          categories: [{ category: 'Backend', count: 9 }],
        }),
      } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('category-count-Backend')).toHaveTextContent('Backend: 9');
    });

    const submitOne = deferred<Response>();
    const submitTwo = deferred<Response>();
    const staleStats = deferred<Response>();
    const freshStats = deferred<Response>();
    let statsCallCount = 0;

    vi.mocked(fetch).mockImplementation((url: string | URL | Request) => {
      if (url === '/api/jobs/41/submissions') return submitOne.promise;
      if (url === '/api/jobs/42/submissions') return submitTwo.promise;
      if (url === '/api/jobs/stats') {
        statsCallCount += 1;
        return statsCallCount === 1 ? staleStats.promise : freshStats.promise;
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    await user.click(screen.getByLabelText('Mark Job One as submitted'));
    submitOne.resolve({
      ok: true,
      json: async () => ({ submission: { id: 10, job_id: 41 } }),
    } as Response);
    // Let handleSubmit's continuation run far enough to issue the first
    // (older) stats refresh before the second submit issues the next one.
    await waitFor(() => expect(statsCallCount).toBe(1));

    await user.click(screen.getByLabelText('Mark Job Two as submitted'));
    submitTwo.resolve({
      ok: true,
      json: async () => ({ submission: { id: 11, job_id: 42 } }),
    } as Response);
    await waitFor(() => expect(statsCallCount).toBe(2));

    // The newer (second) request resolves first with the fresh count...
    freshStats.resolve({
      ok: true,
      json: async () => ({
        jobs_per_day: [],
        submissions_per_day: [],
        categories: [{ category: 'Backend', count: 7 }],
      }),
    } as Response);

    await waitFor(() => {
      expect(screen.getByTestId('category-count-Backend')).toHaveTextContent('Backend: 7');
    });

    // ...and the older request's stale response arrives late. It must not
    // overwrite the fresher count that already landed.
    staleStats.resolve({
      ok: true,
      json: async () => ({
        jobs_per_day: [],
        submissions_per_day: [],
        categories: [{ category: 'Backend', count: 999 }],
      }),
    } as Response);

    // Give the stale response's continuation a chance to run, then assert
    // it did not win.
    await new Promise(resolve => setTimeout(resolve, 10));
    expect(screen.getByTestId('category-count-Backend')).toHaveTextContent('Backend: 7');
  });

  it('disables agent button while queueing prompt', async () => {
    const user = userEvent.setup();

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jobs: [
          {
            id: 12,
            company: 'Test Corp',
            title: 'Engineer',
            url: 'https://example.com/job12',
            location: 'Remote',
            posted_date: '2026-09-25',
            first_seen: '2026-09-25',
            category: 'Backend',
            source: 'manual',
            deleted_at: null,
            raw: null,
          },
        ],
      }),
    } as Response);

    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Engineer')).toBeInTheDocument();
    });

    vi.mocked(fetch).mockImplementationOnce(() => 
      new Promise(resolve => setTimeout(() => 
        resolve({
          ok: true,
          json: async () => ({ success: true, job_id: 12, message: 'Queued' }),
        } as Response),
        100
      ))
    );

    const agentButton = screen.getByLabelText('Queue agent prompt for Engineer');
    expect(agentButton).not.toBeDisabled();

    await user.click(agentButton);

    expect(agentButton).toBeDisabled();
    expect(agentButton).toHaveTextContent('...');

    await waitFor(() => {
      expect(agentButton).not.toBeDisabled();
      expect(agentButton).toHaveTextContent('🤖');
    });
  });
});
