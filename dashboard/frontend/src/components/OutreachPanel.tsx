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

export const OUTREACH_REQUEST_TIMEOUT_MS = 20000;
const OUTREACH_TIMEOUT_MESSAGE = 'Request timed out — reloading contacts';

// Every contacts request goes through this helper so a fetch that never settles
// (server hang, stalled connection, laptop sleep mid-request) cannot block the
// panel-wide queue forever. The controller aborts after the timeout, the timer
// is always cleared, and an abort caused by the timeout surfaces as the
// ordinary timeout error the call sites already know how to display.
function fetchWithTimeout(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), OUTREACH_REQUEST_TIMEOUT_MS);
  try {
    return fetch(input, { ...init, signal: controller.signal })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          throw new Error(OUTREACH_TIMEOUT_MESSAGE);
        }
        throw error;
      })
      .finally(() => clearTimeout(timer));
  } catch (error) {
    clearTimeout(timer);
    throw error;
  }
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

  // ONE panel-wide request queue. Every server interaction (the initial load,
  // add, rename, contacted, replied, delete, and the post-error resync GET) is
  // enqueued here and runs strictly one after another. queueRef holds a promise
  // chain; each new task is appended with `.then(run, run)` so a failed task can
  // never break the chain for the tasks queued behind it.
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const [queueDepth, setQueueDepth] = useState(0);

  // Rows with a queued/in-flight Contacted / Replied / Delete action. Used to
  // de-duplicate accidental double-clicks and to disable the row's buttons.
  const [busyRows, setBusyRows] = useState<Set<number>>(() => new Set());
  const busyRowsRef = useRef<Set<number>>(new Set());

  // Rows with a queued/in-flight rename. Ordering between a rename and another
  // action on the same row is guaranteed by the queue, but the row still cannot
  // enter edit mode again until its rename has landed.
  const [renamingRows, setRenamingRows] = useState<Set<number>>(() => new Set());
  const renamingRowsRef = useRef<Set<number>>(new Set());

  // The add form can only have one queued/in-flight request at a time.
  const [addInFlight, setAddInFlight] = useState(false);
  const addInFlightRef = useRef(false);

  const enqueue = useCallback((task: () => Promise<void>): Promise<void> => {
    setQueueDepth((depth) => depth + 1);
    const run = async (): Promise<void> => {
      try {
        await task();
      } finally {
        setQueueDepth((depth) => depth - 1);
      }
    };
    // The rejection handler also runs the next task, so one failed task can
    // never break the chain. Tasks handle their own errors internally, so run
    // only rejects if something truly unexpected escapes.
    const next = queueRef.current.then(run, run);
    queueRef.current = next;
    return next;
  }, []);

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
    void enqueue(async () => {
      try {
        const response = await fetchWithTimeout('/api/outreach/contacts');
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
    });
  }, [enqueue]);

  // After a failed action the server is the only source of truth: show the
  // error, then re-fetch and render the server's list so the UI can never stay
  // out of step with the DB. The GET is itself enqueued, so by the time it runs
  // no other request is in flight and its full replace is truthful. If the
  // reload also fails, keep the last list and say so in the error.
  const resyncAfterError = useCallback(
    (message: string): void => {
      void enqueue(async () => {
        try {
          const response = await fetchWithTimeout('/api/outreach/contacts');
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
      });
    },
    [enqueue]
  );

  function handleAdd(event: FormEvent): void {
    event.preventDefault();
    if (addInFlightRef.current) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    addInFlightRef.current = true;
    setAddInFlight(true);
    void enqueue(async () => {
      try {
        const response = await fetchWithTimeout('/api/outreach/contacts', {
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
        resyncAfterError(message);
      } finally {
        addInFlightRef.current = false;
        setAddInFlight(false);
      }
    });
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

  function renameContact(id: number, nextName: string): void {
    setRowRenaming(id, true);
    void enqueue(async () => {
      try {
        const response = await fetchWithTimeout(`/api/outreach/contacts/${id}`, {
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
        resyncAfterError(message);
      } finally {
        setRowRenaming(id, false);
      }
    });
  }

  function handleContacted(id: number): void {
    if (busyRowsRef.current.has(id)) return;
    setRowBusy(id, true);
    void enqueue(async () => {
      try {
        const response = await fetchWithTimeout(`/api/outreach/contacts/${id}/contacted`, {
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
        resyncAfterError(message);
      } finally {
        setRowBusy(id, false);
      }
    });
  }

  function handleReplied(id: number): void {
    if (busyRowsRef.current.has(id)) return;
    setRowBusy(id, true);
    void enqueue(async () => {
      try {
        const response = await fetchWithTimeout(`/api/outreach/contacts/${id}/replied`, {
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
        resyncAfterError(message);
      } finally {
        setRowBusy(id, false);
      }
    });
  }

  function handleDelete(id: number): void {
    if (busyRowsRef.current.has(id)) return;
    setRowBusy(id, true);
    void enqueue(async () => {
      try {
        const response = await fetchWithTimeout(`/api/outreach/contacts/${id}`, {
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
        resyncAfterError(message);
      } finally {
        setRowBusy(id, false);
      }
    });
  }

  function toggleMinimized() {
    const next = !minimized;
    setMinimized(next);
    writeMinimized(next);
  }

  const uncontacted = (contacts ?? []).filter((contact) => contact.contacted_at === null);
  const contacted = (contacts ?? []).filter((contact) => contact.contacted_at !== null);
  const queueBusy = queueDepth > 0;

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
        {queueBusy && <span className="outreach-saving">Saving…</span>}
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
