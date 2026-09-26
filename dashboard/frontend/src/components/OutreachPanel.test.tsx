import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { OutreachPanel } from './OutreachPanel';

globalThis.fetch = vi.fn() as typeof fetch;

interface Contact {
  id: number;
  name: string;
  contacted_at: string | null;
  created_at: string;
}

interface StoredContact extends Contact {
  replied_at?: string | null;
  deleted_at?: string | null;
}

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

interface MockOutreachApi {
  patchCalls: Array<{ id: number; name: string }>;
  contactedCalls: number[];
  deleteCalls: number[];
  resolvePatch: (index?: number) => void;
}

function mockOutreachApi(
  initial: Contact[] = [],
  options: { deferPatch?: boolean } = {}
): MockOutreachApi {
  const contacts: StoredContact[] = initial.map((contact) => ({ ...contact }));
  let nextId = contacts.reduce((max, contact) => Math.max(max, contact.id), 0) + 1;
  const patchCalls: Array<{ id: number; name: string }> = [];
  const contactedCalls: number[] = [];
  const deleteCalls: number[] = [];
  const deferredPatches: Array<{ resolve: (response: Response) => void; response: Response }> = [];

  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const url =
      typeof input === 'string' ? input : input instanceof Request ? input.url : String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : null;

    if (url === '/api/outreach/contacts') {
      if (method === 'GET') {
        const active = contacts.filter((contact) => !contact.deleted_at && !contact.replied_at);
        const uncontacted = active
          .filter((contact) => !contact.contacted_at)
          .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id);
        const contacted = active
          .filter((contact) => contact.contacted_at)
          .sort(
            (a, b) =>
              (a.contacted_at ?? '').localeCompare(b.contacted_at ?? '') || a.id - b.id
          );
        return jsonResponse({
          contacts: [...uncontacted, ...contacted].map((contact) => ({
            id: contact.id,
            name: contact.name,
            contacted_at: contact.contacted_at,
            created_at: contact.created_at,
          })),
        });
      }
      if (method === 'POST') {
        const name = String(body?.name ?? '').trim();
        if (!name) return jsonResponse({ detail: 'Name is required' }, 400);
        const contact: StoredContact = {
          id: nextId++,
          name,
          contacted_at: null,
          created_at: `2026-09-26T10:00:${String(nextId).padStart(2, '0')}+00:00`,
        };
        contacts.push(contact);
        return jsonResponse({ contact }, 201);
      }
    }

    const match = url.match(/^\/api\/outreach\/contacts\/(\d+)(?:\/(contacted|replied))?$/);
    if (match) {
      const id = Number(match[1]);
      const action = match[2];
      const index = contacts.findIndex((contact) => contact.id === id);
      if (index === -1 || contacts[index].deleted_at) {
        return jsonResponse({ detail: 'Contact not found' }, 404);
      }
      const contact = contacts[index];

      if (method === 'PATCH') {
        const name = String(body?.name ?? '').trim();
        if (!name) return jsonResponse({ detail: 'Name is required' }, 400);
        if (contact.contacted_at || contact.replied_at) {
          return jsonResponse({ detail: 'Invalid name or contact state' }, 409);
        }
        contact.name = name;
        patchCalls.push({ id, name });
        if (options.deferPatch) {
          // Snapshot the row exactly as the rename response would look when the
          // server processed it: the new name, still uncontacted. The caller
          // decides when this response lands, simulating a slow PATCH racing a
          // fast Contacted/Delete request.
          const response = jsonResponse({ contact: { ...contact } }, 200);
          let resolve!: (value: Response) => void;
          const promise = new Promise<Response>((res) => {
            resolve = res;
          });
          deferredPatches.push({ resolve, response });
          return promise;
        }
        return jsonResponse({ contact }, 200);
      }
      if (method === 'DELETE') {
        deleteCalls.push(id);
        contact.deleted_at = '2026-09-26T11:00:00+00:00';
        return jsonResponse({ contact }, 200);
      }
      if (method === 'POST' && action === 'contacted') {
        contactedCalls.push(id);
        if (contact.contacted_at || contact.replied_at) {
          return jsonResponse({ detail: 'Contact cannot be marked contacted' }, 409);
        }
        contact.contacted_at = '2026-09-26T11:00:00+00:00';
        return jsonResponse({ contact }, 200);
      }
      if (method === 'POST' && action === 'replied') {
        if (!contact.contacted_at) {
          return jsonResponse({ detail: 'Contact cannot be marked replied' }, 409);
        }
        contact.replied_at = '2026-09-26T12:00:00+00:00';
        return jsonResponse({ contact }, 200);
      }
    }

    throw new Error(`Unexpected fetch: ${method} ${url}`);
  });

  return {
    patchCalls,
    contactedCalls,
    deleteCalls,
    resolvePatch: (index = 0) => {
      const deferred = deferredPatches[index];
      if (!deferred) {
        throw new Error(`No deferred PATCH #${index}`);
      }
      deferred.resolve(deferred.response);
    },
  };
}

function isBefore(element: Element, other: Element): boolean {
  return Boolean(element.compareDocumentPosition(other) & Node.DOCUMENT_POSITION_FOLLOWING);
}

function uncontactedList(): HTMLElement {
  return screen.getByRole('list', { name: 'Not contacted' });
}

function contactedList(): HTMLElement {
  return screen.getByRole('list', { name: 'Contacted' });
}

describe('OutreachPanel', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
  });

  it('adds a contact via the Add button above the input', async () => {
    mockOutreachApi([]);
    render(<OutreachPanel />);

    const input = (await screen.findByLabelText('Name or email')) as HTMLInputElement;
    fireEvent.change(input, { target: { value: ' Alice ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => {
      expect(within(uncontactedList()).getByText('Alice')).toBeInTheDocument();
    });
    expect(input.value).toBe('');
    expect(isBefore(uncontactedList(), input)).toBe(true);
    expect(
      vi.mocked(fetch).mock.calls.some(
        ([, init]) => (init?.method ?? 'GET').toUpperCase() === 'POST'
      )
    ).toBe(true);
  });

  it('adds a contact when Enter is pressed in the input', async () => {
    const user = userEvent.setup();
    mockOutreachApi([]);
    render(<OutreachPanel />);

    const input = (await screen.findByLabelText('Name or email')) as HTMLInputElement;
    await user.type(input, 'Bob{enter}');

    await waitFor(() => {
      expect(within(uncontactedList()).getByText('Bob')).toBeInTheDocument();
    });
    expect(input.value).toBe('');
  });

  it('keeps uncontacted rows above the input and contacted rows below it', async () => {
    mockOutreachApi([
      { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
      { id: 2, name: 'Bob', contacted_at: '2026-09-26T10:00:00+00:00', created_at: '2026-09-26T08:00:00+00:00' },
    ]);
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    const input = screen.getByLabelText('Name or email');

    expect(within(uncontactedList()).getByText('Alice')).toBeInTheDocument();
    expect(within(contactedList()).getByText('Bob')).toBeInTheDocument();
    expect(isBefore(uncontactedList(), input)).toBe(true);
    expect(isBefore(input, contactedList())).toBe(true);
  });

  it('edits a name in place and saves on blur via PATCH', async () => {
    mockOutreachApi([
      { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
    ]);
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    fireEvent.click(screen.getByRole('button', { name: 'Alice' }));

    const editInput = screen.getByLabelText('Edit name for Alice') as HTMLInputElement;
    expect(document.activeElement).toBe(editInput);
    expect(editInput.value).toBe('Alice');
    expect(editInput.selectionStart).toBe(0);
    expect(editInput.selectionEnd).toBe('Alice'.length);

    fireEvent.change(editInput, { target: { value: 'Alicia' } });
    fireEvent.blur(editInput);

    await waitFor(() => {
      expect(screen.getByText('Alicia')).toBeInTheDocument();
    });
    expect(screen.queryByLabelText('Edit name for Alice')).not.toBeInTheDocument();
    expect(
      vi.mocked(fetch).mock.calls.some(
        ([, init]) => (init?.method ?? 'GET').toUpperCase() === 'PATCH'
      )
    ).toBe(true);
  });

  it('types a full rename character by character and saves it on blur', async () => {
    const user = userEvent.setup();
    mockOutreachApi([
      { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
    ]);
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    await user.click(screen.getByRole('button', { name: 'Alice' }));

    const editInput = screen.getByLabelText('Edit name for Alice') as HTMLInputElement;
    expect(editInput.selectionStart).toBe(0);
    expect(editInput.selectionEnd).toBe('Alice'.length);

    // Clear the pre-selected text, then type character by character. The old
    // inline-ref bug re-selected the value after every keystroke, so each
    // character replaced the previous one and only the last character survived.
    await user.clear(editInput);
    await user.type(editInput, 'Alpha Renamed');
    await user.tab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Alpha Renamed' })).toBeInTheDocument();
    });
    const patchCalls = vi.mocked(fetch).mock.calls.filter(
      ([, init]) => (init?.method ?? 'GET').toUpperCase() === 'PATCH'
    );
    expect(patchCalls).toHaveLength(1);
    const [, patchInit] = patchCalls[0];
    expect(JSON.parse(String(patchInit?.body))).toEqual({ name: 'Alpha Renamed' });
  });

  it('keeps both characters when typing right after entering edit mode', async () => {
    const user = userEvent.setup();
    mockOutreachApi([
      { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
    ]);
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    await user.click(screen.getByRole('button', { name: 'Alice' }));

    const editInput = screen.getByLabelText('Edit name for Alice') as HTMLInputElement;
    await user.clear(editInput);
    await user.type(editInput, 'xy');

    expect(editInput.value).toBe('xy');
  });

  it('cancels the edit on Escape and restores the old value', async () => {
    mockOutreachApi([
      { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
    ]);
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    fireEvent.click(screen.getByRole('button', { name: 'Alice' }));

    const editInput = screen.getByLabelText('Edit name for Alice') as HTMLInputElement;
    fireEvent.change(editInput, { target: { value: 'Changed' } });
    fireEvent.keyDown(editInput, { key: 'Escape' });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Alice' })).toBeInTheDocument();
    });
    expect(screen.queryByLabelText('Edit name for Alice')).not.toBeInTheDocument();
    expect(
      vi.mocked(fetch).mock.calls.some(
        ([, init]) => (init?.method ?? 'GET').toUpperCase() === 'PATCH'
      )
    ).toBe(false);
  });

  it('rejects an empty rename on blur and restores the old value', async () => {
    mockOutreachApi([
      { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
    ]);
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    fireEvent.click(screen.getByRole('button', { name: 'Alice' }));

    const editInput = screen.getByLabelText('Edit name for Alice') as HTMLInputElement;
    fireEvent.change(editInput, { target: { value: '   ' } });
    fireEvent.blur(editInput);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Alice' })).toBeInTheDocument();
    });
    expect(
      vi.mocked(fetch).mock.calls.some(
        ([, init]) => (init?.method ?? 'GET').toUpperCase() === 'PATCH'
      )
    ).toBe(false);
  });

  it('serializes rename and Contacted so a late PATCH response cannot revert the row', async () => {
    const user = userEvent.setup();
    const api = mockOutreachApi(
      [
        { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
      ],
      { deferPatch: true }
    );
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    await user.click(screen.getByRole('button', { name: 'Alice' }));

    const editInput = screen.getByLabelText('Edit name for Alice') as HTMLInputElement;
    await user.clear(editInput);
    await user.type(editInput, 'Alicia');
    // Clicking Contacted blurs the edit input first, so the PATCH rename and
    // the POST /contacted fire back to back. The POST response resolves
    // immediately; the PATCH response stays pending until the end.
    await user.click(screen.getByRole('button', { name: 'Contacted' }));

    await waitFor(() => {
      expect(api.patchCalls).toHaveLength(1);
    });
    expect(api.patchCalls[0].name).toBe('Alicia');

    // The POST /contacted must wait for the pending rename instead of racing it.
    expect(api.contactedCalls).toHaveLength(0);

    // The slow PATCH (still uncontacted, with the new name) lands last.
    api.resolvePatch();

    await waitFor(() => {
      expect(api.contactedCalls).toHaveLength(1);
      expect(within(contactedList()).getByText('Alicia')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Replied' })).toBeInTheDocument();
    });
    expect(screen.queryByText('Alice')).not.toBeInTheDocument();
    const row = within(contactedList()).getByText('Alicia').closest('li');
    expect(row).toHaveClass('outreach-row--contacted');
  });

  it('serializes rename and Delete so a late PATCH response cannot resurrect the row', async () => {
    const user = userEvent.setup();
    const api = mockOutreachApi(
      [
        { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
      ],
      { deferPatch: true }
    );
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    await user.click(screen.getByRole('button', { name: 'Alice' }));

    const editInput = screen.getByLabelText('Edit name for Alice') as HTMLInputElement;
    await user.clear(editInput);
    await user.type(editInput, 'Alicia');
    await user.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(api.patchCalls).toHaveLength(1);
    });
    expect(api.patchCalls[0].name).toBe('Alicia');

    // The DELETE must wait for the pending rename instead of racing it.
    expect(api.deleteCalls).toHaveLength(0);
    api.resolvePatch();

    await waitFor(() => {
      expect(api.deleteCalls).toHaveLength(1);
      expect(screen.queryByText('Alicia')).not.toBeInTheDocument();
    });
    expect(screen.queryByText('Alice')).not.toBeInTheDocument();
  });

  it('moves a row below the input and shows Replied after Contacted', async () => {
    mockOutreachApi([
      { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
    ]);
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    fireEvent.click(screen.getByRole('button', { name: 'Contacted' }));

    await waitFor(() => {
      expect(within(contactedList()).getByText('Alice')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Replied' })).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Not contacted' })).not.toBeInTheDocument();
  });

  it('removes the row when Replied is clicked', async () => {
    mockOutreachApi([
      { id: 1, name: 'Alice', contacted_at: '2026-09-26T10:00:00+00:00', created_at: '2026-09-26T09:00:00+00:00' },
    ]);
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    fireEvent.click(screen.getByRole('button', { name: 'Replied' }));

    await waitFor(() => {
      expect(screen.queryByText('Alice')).not.toBeInTheDocument();
    });
  });

  it('removes the row when Delete is clicked', async () => {
    mockOutreachApi([
      { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
    ]);
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(screen.queryByText('Alice')).not.toBeInTheDocument();
    });
  });

  it('shows an error and keeps the list when an action fails', async () => {
    mockOutreachApi([
      { id: 1, name: 'Alice', contacted_at: null, created_at: '2026-09-26T09:00:00+00:00' },
    ]);
    render(<OutreachPanel />);

    await screen.findByText('Alice');
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Failed to add contact' }),
    } as Response);

    fireEvent.change(screen.getByLabelText('Name or email'), { target: { value: 'Bob' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to add contact');
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });

  it('still renders the input when the initial load fails', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Failed to load contacts' }),
    } as Response);
    render(<OutreachPanel />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load contacts');
    expect(screen.getByLabelText('Name or email')).toBeInTheDocument();
  });

  it('minimizes and restores from localStorage', async () => {
    mockOutreachApi([]);
    const { unmount } = render(<OutreachPanel />);

    await screen.findByLabelText('Name or email');
    fireEvent.click(screen.getByRole('button', { name: /People to contact/ }));

    await waitFor(() => {
      expect(screen.queryByLabelText('Name or email')).not.toBeInTheDocument();
    });
    expect(window.localStorage.getItem('outreach-panel:minimized')).toBe('1');

    unmount();
    render(<OutreachPanel />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /People to contact/ })).toHaveAttribute(
        'aria-expanded',
        'false'
      );
    });
    expect(screen.queryByLabelText('Name or email')).not.toBeInTheDocument();
  });
});
