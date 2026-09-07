import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { KanbanBoard } from './KanbanBoard';

vi.mock('../api', async (importOriginal) => ({
  // Spread the real module so isAbortError is the REAL implementation --
  // a hand-copied literal here would not notice if api.ts changed.
  ...(await importOriginal<typeof import('../api')>()),
  fetchTasks: vi.fn(),
  fetchProjects: vi.fn(),
  updateTask: vi.fn(),
  createTask: vi.fn(),
  deleteTask: vi.fn(),
}));

vi.mock('./Column', () => ({ Column: () => <div data-testid="column" /> }));
vi.mock('./Notification', () => ({ Notification: () => null }));
vi.mock('./TaskForm', () => ({ TaskForm: () => null }));
vi.mock('./TaskDetailModal', () => ({ TaskDetailModal: () => null }));
vi.mock('./ProjectFilterModal', () => ({ ProjectFilterModal: () => null }));
vi.mock('./WarningBanner', () => ({ WarningBanner: () => null }));
vi.mock('./Spinner', () => ({ Spinner: () => <div>Loading</div> }));
vi.mock('./SkeletonCard', () => ({ SkeletonCard: () => <div /> }));
vi.mock('./IdeasSection', () => ({ IdeasSection: () => null }));

import { fetchProjects, fetchTasks } from '../api';

describe('KanbanBoard', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(fetchTasks).mockResolvedValue([]);
  });

  it('hides the add task button on blocked projects', async () => {
    vi.mocked(fetchProjects).mockResolvedValue([
      { id: 'project-tracker', name: 'Project Tracker', path: '/tmp/project-tracker', status: 'active', can_create_cards: false, blocked_card_reason: "Cards cannot be created for project 'project-tracker'" },
    ]);

    render(
      <MemoryRouter initialEntries={['/kanban/project-tracker']}>
        <Routes>
          <Route path="/kanban/:project" element={<KanbanBoard />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(fetchProjects).toHaveBeenCalled();
    });

    expect(screen.queryByRole('button', { name: /add task/i })).not.toBeInTheDocument();
  });

  it('shows the add task button on allowed projects', async () => {
    vi.mocked(fetchProjects).mockResolvedValue([
      { id: 'smart-invoice-workflow', name: 'Smart Invoice Workflow', path: '/tmp/smart-invoice-workflow', status: 'active', can_create_cards: true, blocked_card_reason: null },
    ]);

    render(
      <MemoryRouter initialEntries={['/kanban/smart-invoice-workflow']}>
        <Routes>
          <Route path="/kanban/:project" element={<KanbanBoard />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByRole('button', { name: /add task/i })).toBeInTheDocument();
  });
});
