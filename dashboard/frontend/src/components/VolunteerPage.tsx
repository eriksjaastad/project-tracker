import { useEffect, useState } from 'react';
import { PageShell } from './PageShell';
import { Spinner } from './Spinner';
import { Notification } from './Notification';
import { RankedListControls, TOP_LISTINGS } from './RankedListControls';
import './JobsPage.css';
import './VolunteerPage.css';

// Volunteer roles are `jobs` rows with kind='volunteer' (#101668605654102016).
// Dismiss and "Submitted" reuse the Jobs board's endpoints.
interface Role {
  id: number;
  company: string;
  title: string;
  url: string;
  location: string | null;
  posted_date: string | null;
  first_seen: string;
  volunteering_since: string | null;
  last_submitted_at?: string | null;
}

interface VolunteerData {
  current: Role[];
  applied: Role[];
  possible: Role[];
  possible_stale: Role[];
}

const EMPTY: VolunteerData = { current: [], applied: [], possible: [], possible_stale: [] };

function dateOnly(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10) : '';
}

function RoleLink({ role }: { role: Role }) {
  return (
    <a href={role.url} target="_blank" rel="noopener noreferrer" className="job-title">
      {role.title}
    </a>
  );
}

export function VolunteerPage() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<VolunteerData>(EMPTY);
  const [busy, setBusy] = useState<Set<number>>(new Set());
  const [showStale, setShowStale] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    loadRoles();
  }, []);

  async function loadRoles() {
    try {
      const response = await fetch('/api/volunteer');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const body = await response.json();
      setData({ ...EMPTY, ...body });
    } catch (error) {
      console.error('Failed to load volunteer roles:', error);
      setNotification({ message: 'Failed to load volunteer roles', type: 'error' });
    } finally {
      setLoading(false);
    }
  }

  // One request per role at a time; the row moves between sections only
  // after the server confirms, using the latest state rather than a snapshot.
  async function act(roleId: number, request: () => Promise<Response>,
    update: (prev: VolunteerData) => VolunteerData, success: string, failure: string) {
    if (busy.has(roleId)) {
      return;
    }
    setBusy(prev => new Set(prev).add(roleId));
    try {
      const response = await request();
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      setData(update);
      setNotification({ message: success, type: 'success' });
    } catch (error) {
      console.error(failure, error);
      setNotification({ message: failure, type: 'error' });
    } finally {
      setBusy(prev => {
        const next = new Set(prev);
        next.delete(roleId);
        return next;
      });
    }
  }

  function withoutPossible(prev: VolunteerData, roleId: number): VolunteerData {
    return {
      ...prev,
      possible: prev.possible.filter(role => role.id !== roleId),
      possible_stale: prev.possible_stale.filter(role => role.id !== roleId),
    };
  }

  function handleDelete(role: Role) {
    act(role.id, () => fetch(`/api/jobs/${role.id}`, { method: 'DELETE' }),
      prev => withoutPossible(prev, role.id),
      'Listing dismissed', 'Failed to dismiss listing');
  }

  function handleSubmitted(role: Role) {
    const submittedAt = new Date().toISOString();
    act(role.id, () => fetch(`/api/jobs/${role.id}/submissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    }),
    prev => ({
      ...withoutPossible(prev, role.id),
      applied: [{ ...role, last_submitted_at: submittedAt }, ...prev.applied],
    }),
    'Marked as applied', 'Failed to mark as applied');
  }

  function handleStarted(role: Role) {
    const since = new Date().toISOString();
    act(role.id, () => fetch(`/api/jobs/${role.id}/volunteering`, { method: 'POST' }),
      prev => ({
        ...prev,
        applied: prev.applied.filter(item => item.id !== role.id),
        current: [{ ...role, volunteering_since: since }, ...prev.current],
      }),
      'Marked as volunteering', 'Failed to mark as volunteering');
  }

  const visiblePossible = showStale ? [...data.possible, ...data.possible_stale] : data.possible;
  const shownPossible = showAll ? visiblePossible : visiblePossible.slice(0, TOP_LISTINGS);

  return (
    <PageShell title="Volunteer" subtitle="Where you volunteer, where you applied, and what to look at next">
      {notification && (
        <Notification
          message={notification.message}
          type={notification.type}
          onClose={() => setNotification(null)}
        />
      )}

      {loading ? (
        <div className="jobs-loading">
          <Spinner size="large" />
        </div>
      ) : (
        <div className="jobs-container">
          <section className="company-group" aria-label="Currently volunteering">
            <h2 className="company-name">Currently volunteering</h2>
            {data.current.length === 0 ? (
              <p className="volunteer-empty">Not volunteering anywhere yet</p>
            ) : (
              <div className="jobs-list">
                {data.current.map(role => (
                  <div key={role.id} className="job-row">
                    <div className="job-main">
                      <RoleLink role={role} />
                      <span className="job-location">{role.company}</span>
                      <span className="job-date">since {dateOnly(role.volunteering_since)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="company-group" aria-label="Applied">
            <h2 className="company-name">Applied</h2>
            {data.applied.length === 0 ? (
              <p className="volunteer-empty">No applications yet</p>
            ) : (
              <div className="jobs-list">
                {data.applied.map(role => (
                  <div key={role.id} className="job-row">
                    <div className="job-main">
                      <RoleLink role={role} />
                      <span className="job-location">{role.company}</span>
                      {role.last_submitted_at && (
                        <span className="job-date">applied {dateOnly(role.last_submitted_at)}</span>
                      )}
                    </div>
                    <div className="job-actions">
                      <button
                        className="job-submit-btn"
                        onClick={() => handleStarted(role)}
                        disabled={busy.has(role.id)}
                        aria-label={`Started volunteering at ${role.company}`}
                      >
                        {busy.has(role.id) ? '...' : 'Started volunteering'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="company-group" aria-label="Possible">
            <h2 className="company-name">Possible</h2>
            <RankedListControls
              shownCount={shownPossible.length}
              visibleCount={visiblePossible.length}
              staleCount={data.possible_stale.length}
              showStale={showStale}
              onToggleStale={() => setShowStale(prev => !prev)}
              onShowAll={() => setShowAll(true)}
            />
            {visiblePossible.length === 0 ? (
              <p className="volunteer-empty">No open volunteer listings</p>
            ) : (
              <div className="jobs-list">
                {shownPossible.map(role => (
                  <div key={role.id} className="job-row">
                    <div className="job-main">
                      <RoleLink role={role} />
                      <span className="job-location">{role.company}</span>
                      {role.location && <span className="job-location">{role.location}</span>}
                      {role.posted_date && <span className="job-date">{role.posted_date}</span>}
                    </div>
                    <div className="job-actions">
                      <button
                        className="job-submit-btn"
                        onClick={() => handleSubmitted(role)}
                        disabled={busy.has(role.id)}
                        aria-label={`Mark ${role.title} as submitted`}
                        title="Record that you applied"
                      >
                        {busy.has(role.id) ? '...' : 'Submitted'}
                      </button>
                      <button
                        className="job-delete-btn"
                        onClick={() => handleDelete(role)}
                        disabled={busy.has(role.id)}
                        aria-label={`Dismiss ${role.title}`}
                      >
                        ×
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </PageShell>
  );
}
