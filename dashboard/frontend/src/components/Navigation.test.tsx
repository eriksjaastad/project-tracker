import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { NavigationResponse } from '../types';
import { Navigation } from './Navigation';

const navigationFixture: NavigationResponse = {
  title: 'Project Tracker',
  items: [
    {
      id: 'morning',
      label: 'Morning',
      href: '/morning',
      match_prefixes: ['/morning'],
      navigation_type: 'spa',
    },
    {
      id: 'dashboard',
      label: 'Dashboard',
      href: '/dashboard',
      match_prefixes: ['/dashboard', '/project'],
      navigation_type: 'spa',
    },
    {
      id: 'group-kanban',
      label: 'Kanban',
      href: '/kanban',
      match_prefixes: ['/kanban', '/calendar'],
      navigation_type: 'spa',
      children: [
        { id: 'kanban', label: 'Board', href: '/kanban', match_prefixes: ['/kanban'], navigation_type: 'spa' },
        { id: 'calendar', label: 'Calendar', href: '/calendar', match_prefixes: ['/calendar'], navigation_type: 'spa' },
      ],
    },
    {
      id: 'group-jobs',
      label: 'Jobs',
      href: '/jobs',
      match_prefixes: ['/jobs', '/jobs/submitted'],
      navigation_type: 'spa',
      children: [
        { id: 'jobs', label: 'Listings', href: '/jobs', match_prefixes: ['/jobs'], navigation_type: 'spa' },
        {
          id: 'jobs-submitted',
          label: 'Submissions',
          href: '/jobs/submitted',
          match_prefixes: ['/jobs/submitted'],
          navigation_type: 'spa',
        },
      ],
    },
    {
      id: 'group-agents',
      label: 'Agents',
      href: '/agent-chat',
      match_prefixes: ['/agent-chat', '/agentic', '/code-reviews', '/holoscape'],
      navigation_type: 'spa',
      children: [
        { id: 'agent-chat', label: 'Chat', href: '/agent-chat', match_prefixes: ['/agent-chat'], navigation_type: 'spa' },
        { id: 'agentic', label: 'Autonomy', href: '/agentic', match_prefixes: ['/agentic'], navigation_type: 'spa' },
        { id: 'code-reviews', label: 'Code reviews', href: '/code-reviews', match_prefixes: ['/code-reviews'], navigation_type: 'spa' },
        {
          id: 'holoscape',
          label: 'Holoscape progress (temporary)',
          href: '/holoscape',
          match_prefixes: ['/holoscape'],
          navigation_type: 'spa',
        },
      ],
    },
    {
      id: 'group-memory',
      label: 'Memory',
      href: '/memory',
      match_prefixes: ['/memory', '/graph'],
      navigation_type: 'document',
      children: [
        { id: 'memory', label: 'Memory', href: '/memory', match_prefixes: ['/memory'], navigation_type: 'document' },
        { id: 'graph', label: 'Graph', href: '/graph', match_prefixes: ['/graph'], navigation_type: 'document' },
      ],
    },
  ],
};

const apiState = vi.hoisted(() => ({ navigation: null as NavigationResponse | null }));

vi.mock('../api', () => ({
  fetchNavigation: vi.fn(() => Promise.resolve(apiState.navigation)),
  isAbortError: () => false,
}));

function renderNavigation(initialPath = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Navigation />
    </MemoryRouter>
  );
}

describe('Navigation', () => {
  beforeEach(() => {
    apiState.navigation = navigationFixture;
    Object.defineProperty(window, '__PT_NAVIGATION__', {
      value: navigationFixture,
      configurable: true,
      writable: true,
    });
  });

  it('renders six compact top-level entries from the shared payload', () => {
    const { container } = renderNavigation('/dashboard');

    const topLevelLinks = container.querySelectorAll('.navigation-links .nav-link');
    expect(topLevelLinks).toHaveLength(6);
    expect(Array.from(topLevelLinks).map(link => link.textContent)).toEqual([
      'Morning',
      'Dashboard',
      'Kanban',
      'Jobs',
      'Agents',
      'Memory',
    ]);
  });

  it('opens a group menu on caret click and closes it on a second click', () => {
    renderNavigation('/kanban');

    const caret = screen.getByRole('button', { name: 'Kanban menu' });
    expect(caret).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(caret);
    expect(caret).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('menuitem', { name: 'Board' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Calendar' })).toBeInTheDocument();

    fireEvent.click(caret);
    expect(caret).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes the open menu on Escape and returns focus to the caret', () => {
    renderNavigation('/kanban');

    const caret = screen.getByRole('button', { name: 'Kanban menu' });
    fireEvent.click(caret);
    expect(caret).toHaveAttribute('aria-expanded', 'true');

    fireEvent.keyDown(caret, { key: 'Escape' });
    expect(caret).toHaveAttribute('aria-expanded', 'false');
    expect(caret).toHaveFocus();
  });

  it('only keeps one group menu open at a time', () => {
    renderNavigation('/kanban');

    const kanbanCaret = screen.getByRole('button', { name: 'Kanban menu' });
    const jobsCaret = screen.getByRole('button', { name: 'Jobs menu' });

    fireEvent.click(kanbanCaret);
    expect(kanbanCaret).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(jobsCaret);
    expect(kanbanCaret).toHaveAttribute('aria-expanded', 'false');
    expect(jobsCaret).toHaveAttribute('aria-expanded', 'true');
  });

  it('marks the Jobs parent and the Submissions item active on /jobs/submitted', () => {
    renderNavigation('/jobs/submitted');

    expect(screen.getByRole('link', { name: 'Jobs' }).className).toContain('active');
    expect(screen.getByRole('menuitem', { name: 'Submissions' }).className).toContain('active');
    // The more specific sibling wins, matching the server's build_navigation.
    expect(screen.getByRole('menuitem', { name: 'Listings' }).className).not.toContain('active');
  });
});
