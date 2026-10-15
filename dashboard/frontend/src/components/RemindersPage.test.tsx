import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { RemindersPage } from './RemindersPage';

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

function reminder(id: number, extra: Record<string, unknown> = {}) {
  return {
    id,
    name: `Item ${id}`,
    purpose: `Use ${id}`,
    location: `~/projects/item-${id}.md`,
    created_at: '2026-10-14T05:00:00+00:00',
    built_in_at: null,
    ...extra,
  };
}

function respond(body: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => body } as Response;
}

const LIST = {
  active: [reminder(1), reminder(2, { location: 'https://example.com/guide' })],
  built_in: [reminder(3, { built_in_at: '2026-10-15T00:00:00+00:00' })],
};

async function renderLoaded() {
  vi.mocked(fetch).mockResolvedValueOnce(respond(LIST));
  render(<RemindersPage />);
  await waitFor(() => expect(screen.getByText('Item 1')).toBeInTheDocument());
}

describe('RemindersPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders each reminder on one row, links only for URLs, built-in ones folded away', async () => {
    await renderLoaded();

    expect(screen.getByText('Use 1')).toBeInTheDocument();
    expect(screen.getByText('~/projects/item-1.md').tagName).toBe('CODE');
    expect(screen.getByRole('link', { name: 'https://example.com/guide' })).toHaveAttribute('target', '_blank');
    expect(screen.getAllByText('added 2026-10-14')).toHaveLength(2);
    expect(screen.getByText('Built in (1)')).toBeInTheDocument();
    expect(screen.queryByLabelText('Mark Item 3 built in')).not.toBeInTheDocument();
  });

  it('adds, marks built in and removes through the API, reloading after each', async () => {
    const user = userEvent.setup();
    await renderLoaded();
    vi.mocked(fetch).mockResolvedValue(respond(LIST));

    await user.type(screen.getByLabelText('Name'), 'Roadmap');
    await user.type(screen.getByLabelText('Path or link'), '~/r.md');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue(''));
    expect(fetch).toHaveBeenCalledWith('/api/reminders', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ name: 'Roadmap', purpose: '', location: '~/r.md' }),
    }));

    await waitFor(() => expect(screen.getByLabelText('Mark Item 1 built in')).toBeEnabled());
    await user.click(screen.getByLabelText('Mark Item 1 built in'));
    expect(fetch).toHaveBeenCalledWith('/api/reminders/1/built-in', { method: 'POST' });

    await waitFor(() => expect(screen.getByLabelText('Remove Item 2')).toBeEnabled());
    await user.click(screen.getByLabelText('Remove Item 2'));
    expect(fetch).toHaveBeenCalledWith('/api/reminders/2', { method: 'DELETE' });

    // One initial load, three writes, and a reload after each write.
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(7));
  });
});
