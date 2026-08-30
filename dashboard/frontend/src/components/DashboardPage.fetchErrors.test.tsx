import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

import { DashboardPage } from './DashboardPage';

// Panels that fetch on their own — not under test here.
vi.mock('./CostPanel', () => ({ CostPanel: () => null }));
vi.mock('./ShadowPricingPanel', () => ({ ShadowPricingPanel: () => null }));

const BASE = {
  user: { login: 'testuser', name: 'Test', avatar_url: '', public_repos: 1, private_repos: 0 },
  repos: [],
  open_pull_requests: [],
  recent_commits: [],
  workflow_runs: [],
  branches: [],
  summary: {
    total_repos: 3,
    archived_repos: 0,
    open_prs: 3,
    draft_prs: 0,
    recent_commit_count: 0,
    repos_with_ci: 0,
    failing_ci: 0,
    fetch_errors: 0,
    repos_not_on_github: 0,
  },
  fetched_at: '2026-08-30T00:00:00Z',
  cached: false,
};

function mockApi(payload: unknown) {
  vi.stubGlobal('fetch', vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(payload) } as Response)
  ));
}

function renderPage() {
  return render(<MemoryRouter><DashboardPage /></MemoryRouter>);
}

describe('DashboardPage — repos not visible on GitHub', () => {
  beforeEach(() => vi.resetAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it('shows the not-on-GitHub count so lost access cannot be silent', async () => {
    // GitHub returns the same answer for "absent" and "you cannot see this",
    // so a lost `repo` scope surfaces here rather than as a failed fetch.
    mockApi({ ...BASE, summary: { ...BASE.summary, repos_not_on_github: 35 } });
    renderPage();

    await waitFor(() => expect(screen.getByText('Not on GitHub')).toBeInTheDocument());
    expect(screen.getByText('35')).toBeInTheDocument();
  });

  it('hides the card when every tracked repo was found', async () => {
    mockApi({ ...BASE, summary: { ...BASE.summary, repos_not_on_github: 0 } });
    renderPage();

    await waitFor(() => expect(screen.getByText('Repos')).toBeInTheDocument());
    expect(screen.queryByText('Not on GitHub')).not.toBeInTheDocument();
  });
});

describe('DashboardPage — incomplete data reporting', () => {
  beforeEach(() => vi.resetAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it('says nothing when every fetch succeeded', async () => {
    mockApi({ ...BASE, fetch_errors: [] });
    renderPage();

    await waitFor(() => expect(screen.getByText('Repos')).toBeInTheDocument());
    expect(screen.queryByText('Incomplete data')).not.toBeInTheDocument();
    expect(screen.queryByText('Failed fetches')).not.toBeInTheDocument();
  });

  it('surfaces failed fetches instead of implying the data is complete', async () => {
    // The #6749 shape one layer up: real PRs shown, but 2 repos unreachable.
    mockApi({
      ...BASE,
      fetch_errors: [
        'repo metadata for testuser/alpha',
        'CI runs for testuser/beta',
      ],
      summary: { ...BASE.summary, fetch_errors: 2 },
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('Incomplete data')).toBeInTheDocument());

    // Each failure is named, not just counted.
    expect(screen.getByText('repo metadata for testuser/alpha')).toBeInTheDocument();
    expect(screen.getByText('CI runs for testuser/beta')).toBeInTheDocument();

    // And it is visible in the summary grid, not buried.
    expect(screen.getByText('Failed fetches')).toBeInTheDocument();

    // Screen readers get it too — this is a degradation notice.
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('marks the header as incomplete so the counts are not read as totals', async () => {
    mockApi({
      ...BASE,
      fetch_errors: ['repo metadata for testuser/alpha'],
      summary: { ...BASE.summary, fetch_errors: 1 },
    });
    renderPage();

    await waitFor(() => expect(screen.getByText(/1 incomplete/)).toBeInTheDocument());
  });

  it('tolerates an API response with no fetch_errors key', async () => {
    // Older cached payloads predate the field.
    const { fetch_errors, ...withoutKey } = { ...BASE, fetch_errors: [] };
    void fetch_errors;
    mockApi(withoutKey);
    renderPage();

    await waitFor(() => expect(screen.getByText('Repos')).toBeInTheDocument());
    expect(screen.queryByText('Incomplete data')).not.toBeInTheDocument();
  });
});
