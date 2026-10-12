import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CostPanel } from './CostPanel';

globalThis.fetch = vi.fn() as typeof fetch;

function respond(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

// Answers the three cost endpoints by path.
function serve(bodies: { daily: unknown; providers: unknown; projects: unknown }, status = 200) {
  vi.mocked(fetch).mockImplementation(async input => {
    const url = String(input);
    if (url.startsWith('/api/costs/daily')) return respond(bodies.daily, status);
    if (url.startsWith('/api/costs/providers')) return respond(bodies.providers, status);
    return respond(bodies.projects, status);
  });
}

describe('CostPanel', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it.each([502, 200])('says the tracker is unavailable on an error body (HTTP %i), not $0.00 or "no data"', async status => {
    // What dashboard/app.py's proxy returns when the cost tracker is unreachable;
    // the proxy passes the tracker's own status through, so a 200 is possible.
    const down = { error: 'Cost tracker unavailable', data: [] };
    serve({ daily: down, providers: down, projects: down }, status);
    render(<CostPanel />);

    expect(await screen.findByText('Cost tracker unavailable')).toBeInTheDocument();
    expect(screen.queryByText('No API cost data yet')).not.toBeInTheDocument();
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument();
  });

  it('says the tracker is unavailable on a failing status even when the body looks like data', async () => {
    serve({ daily: [], providers: [], projects: [] }, 500);
    render(<CostPanel />);

    expect(await screen.findByText('Cost tracker unavailable')).toBeInTheDocument();
    expect(screen.queryByText('No API cost data yet')).not.toBeInTheDocument();
  });

  it('treats a response it cannot read as an error rather than an empty month', async () => {
    serve({ daily: { rows: [] }, providers: [], projects: [] });
    render(<CostPanel />);

    expect(await screen.findByText('Cost tracker unavailable')).toBeInTheDocument();
  });

  it('shows the totals and breakdowns from both response shapes', async () => {
    serve({
      // The live tracker sends total_cost as a string.
      daily: [
        { date: '2026-10-11', calls: 3, total_tokens: 1_500, total_cost: '2.000000' },
        { date: '2026-10-12', calls: 2, total_tokens: 1_000, total_cost: '3.000000' },
      ],
      providers: { data: [{ provider: 'openrouter', calls: 5, total_tokens: 2_500, total_cost: 5 }] },
      projects: [{ project: 'project-tracker', calls: 5, total_tokens: 2_500, total_cost: 5 }],
    });
    render(<CostPanel />);

    expect(await screen.findByText('Total Spend')).toBeInTheDocument();
    expect(screen.getAllByText('$5.00').length).toBeGreaterThan(0);
    expect(screen.getByText('$2.50')).toBeInTheDocument();
    expect(screen.getByText('openrouter')).toBeInTheDocument();
    expect(screen.getByText('project-tracker')).toBeInTheDocument();
  });
});
