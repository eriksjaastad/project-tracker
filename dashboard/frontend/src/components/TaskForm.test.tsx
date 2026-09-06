import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { TaskForm } from './TaskForm';

vi.mock('../api', () => ({
  fetchProjects: vi.fn(),
  fetchTasks: vi.fn(),
  fetchTaskPolicy: vi.fn(),
  isAbortError: (error: unknown) => error instanceof Error && error.name === 'AbortError',
}));

import { fetchProjects, fetchTaskPolicy, fetchTasks } from '../api';

describe('TaskForm', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('filters blocked projects out of the project selector', async () => {
    vi.mocked(fetchProjects).mockResolvedValue([
      { id: 'project-tracker', name: 'Project Tracker', path: '/tmp/project-tracker', status: 'active', can_create_cards: false, blocked_card_reason: "Cards cannot be created for project 'project-tracker'" },
      { id: 'smart-invoice-workflow', name: 'Smart Invoice Workflow', path: '/tmp/smart-invoice-workflow', status: 'active', can_create_cards: true, blocked_card_reason: null },
    ]);
    vi.mocked(fetchTasks).mockResolvedValue([]);
    vi.mocked(fetchTaskPolicy).mockResolvedValue({
      blocked_project_ids: ['project-tracker'],
      blocked_project_reasons: { 'project-tracker': "Cards cannot be created for project 'project-tracker'" },
    });

    render(
      <TaskForm
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onCancel={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/project/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('option', { name: 'Smart Invoice Workflow' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Project Tracker' })).not.toBeInTheDocument();
  });

  it('shows a blocking error and prevents submit when a blocked project id is forced into the form state', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    vi.mocked(fetchProjects).mockResolvedValue([
      { id: 'project-tracker', name: 'Project Tracker', path: '/tmp/project-tracker', status: 'active', can_create_cards: false, blocked_card_reason: "Cards cannot be created for project 'project-tracker'" },
      { id: 'smart-invoice-workflow', name: 'Smart Invoice Workflow', path: '/tmp/smart-invoice-workflow', status: 'active', can_create_cards: true, blocked_card_reason: null },
    ]);
    vi.mocked(fetchTasks).mockResolvedValue([]);
    vi.mocked(fetchTaskPolicy).mockResolvedValue({
      blocked_project_ids: ['project-tracker'],
      blocked_project_reasons: { 'project-tracker': "Cards cannot be created for project 'project-tracker'" },
    });

    render(<TaskForm onSubmit={onSubmit} onCancel={vi.fn()} initialProjectId="project-tracker" />);

    await waitFor(() => {
      expect(screen.getByLabelText(/task description/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/task description/i), {
      target: { value: 'Blocked project test task' },
    });

    fireEvent.submit(screen.getByRole('button', { name: /create task/i }).closest('form')!);

    expect(await screen.findByRole('alert')).toHaveTextContent("Cards cannot be created for project 'project-tracker'");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
