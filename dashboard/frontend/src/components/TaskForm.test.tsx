import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { TaskForm } from './TaskForm';
import { ACCEPTANCE_CRITERIA_TEMPLATE } from '../utils/checklist';

vi.mock('../api', async (importOriginal) => ({
  // Spread the real module so isAbortError is the REAL implementation --
  // a hand-copied literal here would not notice if api.ts changed.
  ...(await importOriginal<typeof import('../api')>()),
  fetchProjects: vi.fn(),
  fetchTasks: vi.fn(),
  fetchTaskPolicy: vi.fn(),
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

  it('prefills the acceptance-criteria field with the unfilled checklist template', async () => {
    vi.mocked(fetchProjects).mockResolvedValue([
      { id: 'smart-invoice-workflow', name: 'Smart Invoice Workflow', path: '/tmp/smart-invoice-workflow', status: 'active', can_create_cards: true, blocked_card_reason: null },
    ]);
    vi.mocked(fetchTasks).mockResolvedValue([]);
    vi.mocked(fetchTaskPolicy).mockResolvedValue({ blocked_project_ids: [], blocked_project_reasons: {} });

    render(<TaskForm onSubmit={vi.fn()} onCancel={vi.fn()} initialProjectId="smart-invoice-workflow" />);

    await waitFor(() => {
      expect(screen.getByLabelText(/acceptance criteria/i)).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/acceptance criteria/i)).toHaveValue(ACCEPTANCE_CRITERIA_TEMPLATE);
  });

  it('blocks submit when the acceptance-criteria field is left as the unfilled template', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    vi.mocked(fetchProjects).mockResolvedValue([
      { id: 'smart-invoice-workflow', name: 'Smart Invoice Workflow', path: '/tmp/smart-invoice-workflow', status: 'active', can_create_cards: true, blocked_card_reason: null },
    ]);
    vi.mocked(fetchTasks).mockResolvedValue([]);
    vi.mocked(fetchTaskPolicy).mockResolvedValue({ blocked_project_ids: [], blocked_project_reasons: {} });

    render(<TaskForm onSubmit={onSubmit} onCancel={vi.fn()} initialProjectId="smart-invoice-workflow" />);

    await waitFor(() => {
      expect(screen.getByLabelText(/task description/i)).toBeInTheDocument();
    });

    await userEvent.type(screen.getByLabelText(/task description/i), 'A new feature');
    // Acceptance criteria left at the default "- [ ] " template -- no real text.
    await userEvent.click(screen.getByRole('button', { name: /create task/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Acceptance criteria required');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits notes once a concrete acceptance criterion is given', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    vi.mocked(fetchProjects).mockResolvedValue([
      { id: 'smart-invoice-workflow', name: 'Smart Invoice Workflow', path: '/tmp/smart-invoice-workflow', status: 'active', can_create_cards: true, blocked_card_reason: null },
    ]);
    vi.mocked(fetchTasks).mockResolvedValue([]);
    vi.mocked(fetchTaskPolicy).mockResolvedValue({ blocked_project_ids: [], blocked_project_reasons: {} });

    render(<TaskForm onSubmit={onSubmit} onCancel={vi.fn()} initialProjectId="smart-invoice-workflow" />);

    await waitFor(() => {
      expect(screen.getByLabelText(/task description/i)).toBeInTheDocument();
    });

    await userEvent.type(screen.getByLabelText(/task description/i), 'A new feature');
    await userEvent.type(screen.getByLabelText(/acceptance criteria/i), 'pytest tests/test_foo.py passes');
    await userEvent.click(screen.getByRole('button', { name: /create task/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      text: 'A new feature',
      notes: '- [ ] pytest tests/test_foo.py passes',
    });
  });
});
