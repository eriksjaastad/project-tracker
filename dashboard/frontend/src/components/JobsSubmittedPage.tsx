import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from './PageShell';
import { Spinner } from './Spinner';
import { Notification } from './Notification';
import './JobsSubmittedPage.css';

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

interface Submission {
  id: number;
  job_id: number;
  submitted_at: string;
  resume_path: string | null;
  cover_letter_path: string | null;
  notes: string | null;
}

interface JobSubmissionGroup {
  job: Job;
  submissions: Submission[];
}

export function JobsSubmittedPage() {
  const [loading, setLoading] = useState(true);
  const [jobGroups, setJobGroups] = useState<JobSubmissionGroup[]>([]);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    loadSubmissions();
  }, []);

  async function loadSubmissions() {
    try {
      const response = await fetch('/api/jobs/submissions');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setJobGroups(data.jobs || []);
    } catch (error) {
      console.error('Failed to load submissions:', error);
      setNotification({ message: 'Failed to load submissions', type: 'error' });
    } finally {
      setLoading(false);
    }
  }

  function formatSubmittedDate(isoDate: string): string {
    try {
      const date = new Date(isoDate);
      return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      }).format(date);
    } catch {
      return isoDate;
    }
  }

  return (
    <PageShell title="Submissions" subtitle="Job application history">
      {notification && (
        <Notification
          message={notification.message}
          type={notification.type}
          onClose={() => setNotification(null)}
        />
      )}

      {loading ? (
        <div className="submissions-loading">
          <Spinner size="large" />
        </div>
      ) : jobGroups.length === 0 ? (
        <div className="submissions-empty">
          <p>No submissions yet</p>
          <p className="submissions-empty-hint">
            <Link to="/jobs">Browse open listings</Link> to get started
          </p>
        </div>
      ) : (
        <div className="submissions-container">
          {jobGroups.map(({ job, submissions }) => (
            <div key={job.id} className="submission-group">
              <div className="submission-job-header">
                <div className="submission-job-main">
                  <h2 className="submission-company">{job.company}</h2>
                  <a
                    href={job.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="submission-job-title"
                  >
                    {job.title}
                  </a>
                  {job.location && (
                    <span className="submission-job-location">{job.location}</span>
                  )}
                  <span className="submission-job-category">{job.category}</span>
                  {job.deleted_at && (
                    <span className="submission-job-dismissed" title="Dismissed from open listings">
                      Dismissed
                    </span>
                  )}
                </div>
                <div className="submission-count">
                  {submissions.length} {submissions.length === 1 ? 'submission' : 'submissions'}
                </div>
              </div>

              <div className="submissions-list">
                {submissions.map((submission) => (
                  <div key={submission.id} className="submission-item">
                    <div className="submission-date">
                      {formatSubmittedDate(submission.submitted_at)}
                    </div>
                    {submission.notes && (
                      <div className="submission-notes">{submission.notes}</div>
                    )}
                    {(submission.resume_path || submission.cover_letter_path) && (
                      <div className="submission-attachments">
                        {submission.resume_path && (
                          <span className="submission-attachment">Resume: {submission.resume_path}</span>
                        )}
                        {submission.cover_letter_path && (
                          <span className="submission-attachment">
                            Cover letter: {submission.cover_letter_path}
                          </span>
                        )}
                      </div>
                    )}
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
