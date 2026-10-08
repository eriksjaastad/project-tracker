import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { VolunteerPage } from './VolunteerPage';

globalThis.fetch = vi.fn() as typeof fetch;

vi.mock('./PageShell', () => ({
  PageShell: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div>
      <h1>{title}</h1>
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

function role(id: number, extra: Record<string, unknown> = {}) {
  return {
    id,
    company: `Org ${id}`,
    title: `Role ${id}`,
    url: `https://example.org/forms/${id}`,
    location: 'Remote',
    posted_date: null,
    first_seen: '2026-10-01',
    volunteering_since: null,
    ...extra,
  };
}

function respond(body: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => body } as Response;
}

function section(name: string) {
  return within(screen.getByRole('region', { name }));
}

describe('VolunteerPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders the three sections with direct links that open in a new tab', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(respond({
      current: [role(1, { volunteering_since: '2026-09-01T00:00:00+00:00' })],
      applied: [role(2, { last_submitted_at: '2026-10-02T12:00:00+00:00' })],
      possible: [role(3)],
      possible_stale: [],
    }));

    render(<VolunteerPage />);

    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });
    expect(fetch).toHaveBeenCalledWith('/api/volunteer');
    expect(section('Currently volunteering').getByText('Role 1')).toBeInTheDocument();
    expect(section('Currently volunteering').getByText('since 2026-09-01')).toBeInTheDocument();
    expect(section('Applied').getByText('applied 2026-10-02')).toBeInTheDocument();
    const link = section('Possible').getByRole('link', { name: 'Role 3' });
    expect(link).toHaveAttribute('href', 'https://example.org/forms/3');
    expect(link).toHaveAttribute('target', '_blank');
    expect(section('Possible').getByLabelText('Dismiss Role 3')).toBeInTheDocument();
  });

  it('dismisses a possible listing through the Jobs soft delete', async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValueOnce(respond({
      current: [], applied: [], possible: [role(3), role(4)], possible_stale: [],
    }));
    render(<VolunteerPage />);
    await waitFor(() => expect(screen.getByText('Role 3')).toBeInTheDocument());

    vi.mocked(fetch).mockResolvedValueOnce(respond({ job: { id: 3 } }));
    await user.click(screen.getByLabelText('Dismiss Role 3'));

    expect(fetch).toHaveBeenLastCalledWith('/api/jobs/3', { method: 'DELETE' });
    await waitFor(() => expect(screen.queryByText('Role 3')).not.toBeInTheDocument());
    expect(screen.getByText('Role 4')).toBeInTheDocument();
  });

  it('keeps the listing when the dismiss fails', async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValueOnce(respond({
      current: [], applied: [], possible: [role(3)], possible_stale: [],
    }));
    render(<VolunteerPage />);
    await waitFor(() => expect(screen.getByText('Role 3')).toBeInTheDocument());

    vi.mocked(fetch).mockResolvedValueOnce(respond({}, false));
    await user.click(screen.getByLabelText('Dismiss Role 3'));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Failed to dismiss listing'));
    expect(screen.getByText('Role 3')).toBeInTheDocument();
  });

  it('moves a possible role to Applied, then to Currently volunteering', async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValueOnce(respond({
      current: [], applied: [], possible: [role(5)], possible_stale: [],
    }));
    render(<VolunteerPage />);
    await waitFor(() => expect(screen.getByText('Role 5')).toBeInTheDocument());

    vi.mocked(fetch).mockResolvedValueOnce(respond({ submission: { id: 1 } }));
    await user.click(screen.getByLabelText('Mark Role 5 as submitted'));
    expect(fetch).toHaveBeenLastCalledWith('/api/jobs/5/submissions', expect.objectContaining({ method: 'POST' }));
    await waitFor(() => expect(section('Applied').getByText('Role 5')).toBeInTheDocument());
    expect(section('Possible').queryByText('Role 5')).not.toBeInTheDocument();

    vi.mocked(fetch).mockResolvedValueOnce(respond({ job: { id: 5 } }));
    await user.click(screen.getByLabelText('Started volunteering at Org 5'));
    expect(fetch).toHaveBeenLastCalledWith('/api/jobs/5/volunteering', { method: 'POST' });
    await waitFor(() => expect(section('Currently volunteering').getByText('Role 5')).toBeInTheDocument());
    expect(section('Applied').queryByText('Role 5')).not.toBeInTheDocument();
  });

  it('limits Possible to the top 25 and hides stale listings behind a count', async () => {
    const user = userEvent.setup();
    const possible = Array.from({ length: 27 }, (_, i) => role(100 + i));
    vi.mocked(fetch).mockResolvedValueOnce(respond({
      current: [], applied: [], possible, possible_stale: [role(900)],
    }));
    render(<VolunteerPage />);
    await waitFor(() => expect(screen.getByText('Role 100')).toBeInTheDocument());

    expect(screen.getByText('Role 124')).toBeInTheDocument();
    expect(screen.queryByText('Role 125')).not.toBeInTheDocument();
    expect(screen.getByText('1 older listing hidden')).toBeInTheDocument();
    expect(screen.queryByText('Role 900')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Show all 27' }));
    expect(screen.getByText('Role 126')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Show older listings' }));
    expect(screen.getByText('Role 900')).toBeInTheDocument();
  });
});
