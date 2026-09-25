import { useEffect, useState } from 'react';
import { PageShell } from './PageShell';
import { Spinner } from './Spinner';
import { Notification } from './Notification';
import { JobStatsChart } from './JobStatsChart';
import { CategoryTable } from './CategoryTable';
import './JobsPage.css';

interface Job {
  id: number;
  company: string;
  title: string;
  url: string;
  location: string | null;
  posted_date: string | null;
  first_seen: string;
  category: string;
  source: string;
  deleted_at: string | null;
  raw: string | null;
}

interface CompanyGroup {
  company: string;
  jobs: Job[];
}

interface JobStats {
  jobs_per_day: Array<{ date: string; count: number }>;
  submissions_per_day: Array<{ date: string; count: number }>;
  categories: Array<{ category: string; count: number }>;
}

export function JobsPage() {
  const [loading, setLoading] = useState(true);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<JobStats | null>(null);
  const [statsError, setStatsError] = useState(false);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [queuingPrompts, setQueuingPrompts] = useState<Set<number>>(new Set());

  useEffect(() => {
    loadJobs();
    loadStats();
  }, []);

  async function loadJobs() {
    try {
      const response = await fetch('/api/jobs');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setJobs(data.jobs || []);
    } catch (error) {
      console.error('Failed to load jobs:', error);
      setNotification({ message: 'Failed to load jobs', type: 'error' });
    } finally {
      setLoading(false);
    }
  }

  async function loadStats() {
    try {
      const response = await fetch('/api/jobs/stats');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Failed to load job stats:', error);
      setStatsError(true);
    }
  }

  async function handleDelete(jobId: number) {
    try {
      const response = await fetch(`/api/jobs/${jobId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      setJobs(jobs.filter(job => job.id !== jobId));
      setNotification({ message: 'Job dismissed', type: 'success' });
    } catch (error) {
      console.error('Failed to delete job:', error);
      setNotification({ message: 'Failed to dismiss job', type: 'error' });
    }
  }

  async function handleQueuePrompt(jobId: number) {
    setQueuingPrompts(prev => new Set(prev).add(jobId));
    try {
      const response = await fetch(`/api/jobs/${jobId}/agent-prompt`, {
        method: 'POST',
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(data.detail || `HTTP ${response.status}`);
      }
      setNotification({ message: 'Agent prompt queued successfully', type: 'success' });
    } catch (error) {
      console.error('Failed to queue agent prompt:', error);
      const message = error instanceof Error ? error.message : 'Failed to queue agent prompt';
      setNotification({ message, type: 'error' });
    } finally {
      setQueuingPrompts(prev => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    }
  }

  const companyGroups: CompanyGroup[] = jobs.reduce((groups, job) => {
    const existingGroup = groups.find(g => g.company === job.company);
    if (existingGroup) {
      existingGroup.jobs.push(job);
    } else {
      groups.push({ company: job.company, jobs: [job] });
    }
    return groups;
  }, [] as CompanyGroup[]);

  return (
    <PageShell title="Jobs" subtitle="Open job listings">
      {notification && (
        <Notification
          message={notification.message}
          type={notification.type}
          onClose={() => setNotification(null)}
        />
      )}

      {stats && !statsError && (
        <>
          <JobStatsChart stats={stats} />
          <CategoryTable categories={stats.categories} />
        </>
      )}

      {loading ? (
        <div className="jobs-loading">
          <Spinner size="large" />
        </div>
      ) : jobs.length === 0 ? (
        <div className="jobs-empty">
          <p>No open job listings</p>
        </div>
      ) : (
        <div className="jobs-container">
          {companyGroups.map(group => (
            <div key={group.company} className="company-group">
              <h2 className="company-name">{group.company}</h2>
              <div className="jobs-list">
                {group.jobs.map(job => (
                  <div key={job.id} className="job-row">
                    <div className="job-main">
                      <a
                        href={job.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="job-title"
                      >
                        {job.title}
                      </a>
                      {job.location && (
                        <span className="job-location">{job.location}</span>
                      )}
                      {job.posted_date && (
                        <span className="job-date">{job.posted_date}</span>
                      )}
                      <span className="job-category">{job.category}</span>
                    </div>
                    <div className="job-actions">
                      <button
                        className="job-agent-btn"
                        onClick={() => handleQueuePrompt(job.id)}
                        disabled={queuingPrompts.has(job.id)}
                        aria-label={`Queue agent prompt for ${job.title}`}
                        title="Queue agent to tailor resume and cover letter"
                      >
                        {queuingPrompts.has(job.id) ? '...' : '🤖'}
                      </button>
                      <button
                        className="job-delete-btn"
                        onClick={() => handleDelete(job.id)}
                        aria-label={`Dismiss ${job.title}`}
                      >
                        ×
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </PageShell>
  );
}
