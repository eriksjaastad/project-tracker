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

  // Per-row serialization of mutating requests. A rename sent by blur-to-save
  // is kept here so a Contacted / Replied / Delete click on the same row can
  // wait for it before sending its own request; otherwise the two responses
  // race and whichever lands last wins, even if it is stale.
  const renamePromisesRef = useRef<Map<number, Promise<void>>>(new Map());
  // Per-row request sequence numbers. Every mutating request stamps the row;
  // a response is only applied when its sequence number is still the newest,
  // so a slow stale response can never overwrite fresher state.
  const requestSeqRef = useRef<Map<number, number>>(new Map());

  function nextRequestSeq(id: number): number {
    const seq = (requestSeqRef.current.get(id) ?? 0) + 1;
    requestSeqRef.current.set(id, seq);
    return seq;
  }

  function isLatestRequest(id: number, seq: number): boolean {
    return requestSeqRef.current.get(id) === seq;
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

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
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
      setError(err instanceof Error ? err.message : 'Failed to add contact');
    }
  }

  function startEdit(contact: OutreachContact) {
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
    const seq = nextRequestSeq(id);
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
        if (isLatestRequest(id, seq)) {
          setContacts((prev) =>
            (prev ?? []).map((contact) => (contact.id === id ? data.contact : contact))
          );
          setError(null);
        }
      } catch (err) {
        console.error('Failed to rename outreach contact:', err);
        if (isLatestRequest(id, seq)) {
          setError(err instanceof Error ? err.message : 'Failed to rename contact');
        }
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
    await waitForPendingRename(id);
    const seq = nextRequestSeq(id);
    try {
      const response = await fetch(`/api/outreach/contacts/${id}/contacted`, {
        method: 'POST',
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(errorMessage(payload, `Failed to mark contact (HTTP ${response.status})`));
      }
      const data = await response.json();
      if (isLatestRequest(id, seq)) {
        setContacts((prev) =>
          (prev ?? []).map((contact) => (contact.id === id ? data.contact : contact))
        );
        setError(null);
      }
    } catch (err) {
      console.error('Failed to mark outreach contact as contacted:', err);
      if (isLatestRequest(id, seq)) {
        setError(err instanceof Error ? err.message : 'Failed to mark contact');
      }
    }
  }

  async function handleReplied(id: number) {
    await waitForPendingRename(id);
    const seq = nextRequestSeq(id);
    try {
      const response = await fetch(`/api/outreach/contacts/${id}/replied`, {
        method: 'POST',
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(errorMessage(payload, `Failed to mark reply (HTTP ${response.status})`));
      }
      if (isLatestRequest(id, seq)) {
        setContacts((prev) => (prev ?? []).filter((contact) => contact.id !== id));
        setError(null);
      }
    } catch (err) {
      console.error('Failed to mark outreach contact as replied:', err);
      if (isLatestRequest(id, seq)) {
        setError(err instanceof Error ? err.message : 'Failed to mark reply');
      }
    }
  }

  async function handleDelete(id: number) {
    await waitForPendingRename(id);
    const seq = nextRequestSeq(id);
    try {
      const response = await fetch(`/api/outreach/contacts/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(errorMessage(payload, `Failed to delete contact (HTTP ${response.status})`));
      }
      if (isLatestRequest(id, seq)) {
        setContacts((prev) => (prev ?? []).filter((contact) => contact.id !== id));
        setError(null);
      }
    } catch (err) {
      console.error('Failed to delete outreach contact:', err);
      if (isLatestRequest(id, seq)) {
        setError(err instanceof Error ? err.message : 'Failed to delete contact');
      }
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
                        >
                          {contact.name}
                        </button>
                      )}
                      <button
                        type="button"
                        className="outreach-action"
                        onClick={() => handleContacted(contact.id)}
                      >
                        Contacted
                      </button>
                      <button
                        type="button"
                        className="outreach-action outreach-action--danger"
                        onClick={() => handleDelete(contact.id)}
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
                <button type="submit" className="outreach-add-btn">
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
