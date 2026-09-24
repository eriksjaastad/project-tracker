import { useEffect, useState } from 'react';
import { PageShell } from './PageShell';
import { Spinner } from './Spinner';
import { Notification } from './Notification';
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

export function JobsPage() {
  const [loading, setLoading] = useState(true);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    loadJobs();
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
                    <button
                      className="job-delete-btn"
                      onClick={() => handleDelete(job.id)}
                      aria-label={`Dismiss ${job.title}`}
                    >
                      ×
                    </button>
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
