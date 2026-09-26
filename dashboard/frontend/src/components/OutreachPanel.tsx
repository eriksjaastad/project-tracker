import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import './OutreachPanel.css';

interface OutreachContact {
  id: number;
  name: string;
  contacted_at: string | null;
  created_at: string;
}

const MINIMIZED_STORAGE_KEY = 'outreach-panel:minimized';

function readMinimized(): boolean {
  try {
    return window.localStorage.getItem(MINIMIZED_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function writeMinimized(minimized: boolean): void {
  try {
    window.localStorage.setItem(MINIMIZED_STORAGE_KEY, minimized ? '1' : '0');
  } catch {
    // Local storage is unavailable; the panel still works for this session.
  }
}

function errorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return fallback;
}

export function OutreachPanel() {
  const [contacts, setContacts] = useState<OutreachContact[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [minimized, setMinimized] = useState<boolean>(() => readMinimized());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState('');
  const editingIdRef = useRef<number | null>(null);
  editingIdRef.current = editingId;

  // Rows with an in-flight action request (Contacted / Replied / Delete). A
  // row's action buttons are disabled while one is running, and the handlers
  // drop duplicate clicks so a double-click can never send two requests.
  const [busyRows, setBusyRows] = useState<Set<number>>(() => new Set());
  const busyRowsRef = useRef<Set<number>>(new Set());

  // Rows with an in-flight rename. Other actions wait for the pending rename
  // instead of being blocked by it (see waitForPendingRename), but the name
  // still cannot enter edit mode again until the rename has landed.
  const [renamingRows, setRenamingRows] = useState<Set<number>>(() => new Set());
  const renamingRowsRef = useRef<Set<number>>(new Set());

  // The add form can only have one in-flight request at a time.
  const [addInFlight, setAddInFlight] = useState(false);
  const addInFlightRef = useRef(false);

  // Per-row serialization of mutating requests. A rename sent by blur-to-save
  // is kept here so a Contacted / Replied / Delete click on the same row can
  // wait for it before sending its own request; otherwise the two responses
  // race and whichever lands last wins, even if it is stale.
  const renamePromisesRef = useRef<Map<number, Promise<void>>>(new Map());

  function setRowBusy(id: number, busy: boolean): void {
    const next = new Set(busyRowsRef.current);
    if (busy) {
      next.add(id);
    } else {
      next.delete(id);
    }
    busyRowsRef.current = next;
    setBusyRows(next);
  }

  function setRowRenaming(id: number, renaming: boolean): void {
    const next = new Set(renamingRowsRef.current);
    if (renaming) {
      next.add(id);
    } else {
      next.delete(id);
    }
    renamingRowsRef.current = next;
    setRenamingRows(next);
  }

  async function waitForPendingRename(id: number): Promise<void> {
    const pendingRename = renamePromisesRef.current.get(id);
    if (!pendingRename) return;
    try {
      await pendingRename;
    } catch {
      // The rename already surfaced its own error; the action can still run.
    }
  }

  // Stable callback ref: React only invokes it when the edit input mounts or
  // unmounts, so focus + select happen once when a row enters edit mode instead
  // of on every render (which re-selected the text after each keystroke).
  const focusEditInput = useCallback((el: HTMLInputElement | null) => {
    if (el) {
      el.focus();
      el.select();
    }
  }, []);

  useEffect(() => {
    loadContacts();
  }, []);

  async function loadContacts() {
    try {
      const response = await fetch('/api/outreach/contacts');
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(errorMessage(payload, `Failed to load contacts (HTTP ${response.status})`));
      }
      const data = await response.json();
      setContacts(data.contacts || []);
      setError(null);
    } catch (err) {
      console.error('Failed to load outreach contacts:', err);
      setError(err instanceof Error ? err.message : 'Failed to load contacts');
    } finally {
      setLoading(false);
    }
  }

  // After a failed action the server is the only source of truth: show the
  // error, then re-fetch and render the server's list so the UI can never stay
  // out of step with the DB. If the reload also fails, keep the last list and
  // say so in the error.
  async function resyncAfterError(message: string): Promise<void> {
    try {
      const response = await fetch('/api/outreach/contacts');
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          errorMessage(payload, `Failed to reload contacts (HTTP ${response.status})`)
        );
      }
      const data = await response.json();
      setContacts(data.contacts || []);
    } catch (err) {
      console.error('Failed to reload outreach contacts after an error:', err);
      const reloadMessage = err instanceof Error ? err.message : 'Failed to reload contacts';
      setError(`${message} Could not reload contacts: ${reloadMessage}`);
    }
  }

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    if (addInFlightRef.current) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    addInFlightRef.current = true;
    setAddInFlight(true);
    try {
      const response = await fetch('/api/outreach/contacts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmed }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(errorMessage(payload, `Failed to add contact (HTTP ${response.status})`));
      }
      const data = await response.json();
      setContacts((prev) => [...(prev ?? []), data.contact]);
      setName('');
      setError(null);
    } catch (err) {
      console.error('Failed to add outreach contact:', err);
      const message = err instanceof Error ? err.message : 'Failed to add contact';
      setError(message);
      await resyncAfterError(message);
    } finally {
      addInFlightRef.current = false;
      setAddInFlight(false);
    }
  }

  function startEdit(contact: OutreachContact) {
    if (busyRowsRef.current.has(contact.id) || renamingRowsRef.current.has(contact.id)) return;
    editingIdRef.current = contact.id;
    setEditingId(contact.id);
    setEditingValue(contact.name);
    setError(null);
  }

  function cancelEdit() {
    editingIdRef.current = null;
    setEditingId(null);
  }

  function commitEdit() {
    const id = editingIdRef.current;
    if (id === null) return;
    const nextName = editingValue.trim();
    if (!nextName) {
      cancelEdit();
      return;
    }
    editingIdRef.current = null;
    setEditingId(null);
    renameContact(id, nextName);
  }

  function renameContact(id: number, nextName: string): Promise<void> {
    setRowRenaming(id, true);
    const promise = (async () => {
      try {
        const response = await fetch(`/api/outreach/contacts/${id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: nextName }),
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(errorMessage(payload, `Failed to rename contact (HTTP ${response.status})`));
        }
        const data = await response.json();
        setContacts((prev) =>
          (prev ?? []).map((contact) => (contact.id === id ? data.contact : contact))
        );
        setError(null);
      } catch (err) {
        console.error('Failed to rename outreach contact:', err);
        const message = err instanceof Error ? err.message : 'Failed to rename contact';
        setError(message);
        await resyncAfterError(message);
      } finally {
        setRowRenaming(id, false);
      }
    })();
    renamePromisesRef.current.set(id, promise);
    const cleanup = () => {
      if (renamePromisesRef.current.get(id) === promise) {
        renamePromisesRef.current.delete(id);
      }
    };
    void promise.then(cleanup, cleanup);
    return promise;
  }

  async function handleContacted(id: number) {
    if (busyRowsRef.current.has(id)) return;
    setRowBusy(id, true);
    try {
      await waitForPendingRename(id);
      const response = await fetch(`/api/outreach/contacts/${id}/contacted`, {
        method: 'POST',
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(errorMessage(payload, `Failed to mark contact (HTTP ${response.status})`));
      }
      const data = await response.json();
      setContacts((prev) =>
        (prev ?? []).map((contact) => (contact.id === id ? data.contact : contact))
      );
      setError(null);
    } catch (err) {
      console.error('Failed to mark outreach contact as contacted:', err);
      const message = err instanceof Error ? err.message : 'Failed to mark contact';
      setError(message);
      await resyncAfterError(message);
    } finally {
      setRowBusy(id, false);
    }
  }

  async function handleReplied(id: number) {
    if (busyRowsRef.current.has(id)) return;
    setRowBusy(id, true);
    try {
      await waitForPendingRename(id);
      const response = await fetch(`/api/outreach/contacts/${id}/replied`, {
        method: 'POST',
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(errorMessage(payload, `Failed to mark reply (HTTP ${response.status})`));
      }
      setContacts((prev) => (prev ?? []).filter((contact) => contact.id !== id));
      setError(null);
    } catch (err) {
      console.error('Failed to mark outreach contact as replied:', err);
      const message = err instanceof Error ? err.message : 'Failed to mark reply';
      setError(message);
      await resyncAfterError(message);
    } finally {
      setRowBusy(id, false);
    }
  }

  async function handleDelete(id: number) {
    if (busyRowsRef.current.has(id)) return;
    setRowBusy(id, true);
    try {
      await waitForPendingRename(id);
      const response = await fetch(`/api/outreach/contacts/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(errorMessage(payload, `Failed to delete contact (HTTP ${response.status})`));
      }
      setContacts((prev) => (prev ?? []).filter((contact) => contact.id !== id));
      setError(null);
    } catch (err) {
      console.error('Failed to delete outreach contact:', err);
      const message = err instanceof Error ? err.message : 'Failed to delete contact';
      setError(message);
      await resyncAfterError(message);
    } finally {
      setRowBusy(id, false);
    }
  }

  function toggleMinimized() {
    const next = !minimized;
    setMinimized(next);
    writeMinimized(next);
  }

  const uncontacted = (contacts ?? []).filter((contact) => contact.contacted_at === null);
  const contacted = (contacts ?? []).filter((contact) => contact.contacted_at !== null);

  return (
    <section className="outreach-panel" aria-label="People to contact">
      <h2 className="outreach-header">
        <button
          type="button"
          className="outreach-toggle"
          onClick={toggleMinimized}
          aria-expanded={!minimized}
        >
          <span className="outreach-chevron" aria-hidden="true">
            {minimized ? '▸' : '▾'}
          </span>
          People to contact
        </button>
      </h2>

      {!minimized && (
        <div className="outreach-body">
          {error && (
            <p role="alert" className="outreach-error">
              {error}
            </p>
          )}

          {loading && contacts === null ? (
            <p className="outreach-loading">Loading contacts...</p>
          ) : (
            <>
              {uncontacted.length > 0 && (
                <ul className="outreach-list" aria-label="Not contacted">
                  {uncontacted.map((contact) => (
                    <li key={contact.id} className="outreach-row">
                      {editingId === contact.id ? (
                        <input
                          type="text"
                          className="outreach-edit-input"
                          value={editingValue}
                          onChange={(event) => setEditingValue(event.target.value)}
                          onBlur={commitEdit}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') {
                              event.preventDefault();
                              commitEdit();
                            } else if (event.key === 'Escape') {
                              cancelEdit();
                            }
                          }}
                          ref={focusEditInput}
                          aria-label={`Edit name for ${contact.name}`}
                        />
                      ) : (
                        <button
                          type="button"
                          className="outreach-name"
                          onClick={() => startEdit(contact)}
                          disabled={
                            busyRows.has(contact.id) || renamingRows.has(contact.id)
                          }
                        >
                          {contact.name}
                        </button>
                      )}
                      <button
                        type="button"
                        className="outreach-action"
                        onClick={() => handleContacted(contact.id)}
                        disabled={busyRows.has(contact.id)}
                      >
                        Contacted
                      </button>
                      <button
                        type="button"
                        className="outreach-action outreach-action--danger"
                        onClick={() => handleDelete(contact.id)}
                        disabled={busyRows.has(contact.id)}
                      >
                        Delete
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <form className="outreach-add" onSubmit={handleAdd}>
                <input
                  type="text"
                  className="outreach-input"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Name or email"
                  aria-label="Name or email"
                />
                <button type="submit" className="outreach-add-btn" disabled={addInFlight}>
                  Add
                </button>
              </form>

              {contacted.length > 0 && (
                <ul className="outreach-list" aria-label="Contacted">
                  {contacted.map((contact) => (
                    <li key={contact.id} className="outreach-row outreach-row--contacted">
                      <span className="outreach-name">{contact.name}</span>
                      <button
                        type="button"
                        className="outreach-action"
                        onClick={() => handleReplied(contact.id)}
                        disabled={busyRows.has(contact.id)}
                      >
                        Replied
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
