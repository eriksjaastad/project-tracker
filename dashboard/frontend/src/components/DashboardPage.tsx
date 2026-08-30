import { useEffect, useState, useCallback } from 'react';
import { PageShell } from './PageShell';
import { CostPanel } from './CostPanel';
import { ShadowPricingPanel } from './ShadowPricingPanel';
import './DashboardPage.css';

interface GitHubData {
  user?: {
    login: string;
    name: string;
    avatar_url: string;
    public_repos: number;
    private_repos: number;
  };
  repos?: Array<{
    name: string;
    url: string;
    pushedAt: string;
    isPrivate: boolean;
    isArchived: boolean;
    description: string | null;
    stargazerCount: number;
    defaultBranchRef: { name: string } | null;
  }>;
  open_pull_requests?: Array<{
    title: string;
    number: number;
    url: string;
    author: { login: string };
    createdAt: string;
    headRefName: string;
    baseRefName: string;
    isDraft: boolean;
    reviewDecision: string;
    repository: { name: string };
    statusCheckRollup?: Array<{ state: string }>;
  }>;
  recent_commits?: Array<{
    repo: string;
    sha: string;
    message: string;
    author: string;
    date: string;
  }>;
  workflow_runs?: Array<{
    repo: string;
    name: string;
    status: string;
    conclusion: string | null;
    branch: string;
    created_at: string;
    url: string;
  }>;
  branches?: Array<{
    repo: string;
    name: string;
    protected: boolean;
  }>;
  fetch_errors?: string[];
  summary?: {
    total_repos: number;
    archived_repos: number;
    open_prs: number;
    draft_prs: number;
    recent_commit_count: number;
    repos_with_ci: number;
    failing_ci: number;
    fetch_errors: number;
  };
  fetched_at?: string;
  cached?: boolean;
  error?: string;
}

function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const ACTIVITY_LIMIT = 10;

function RecentActivity({ repos, commitsByRepo }: {
  repos: GitHubData['repos'] & Array<{ pushedAt: string }>;
  commitsByRepo: Record<string, GitHubData['recent_commits']>;
}) {
  const [expanded, setExpanded] = useState(false);
  const toggle = useCallback(() => setExpanded(e => !e), []);
  const visible = expanded ? repos : repos.slice(0, ACTIVITY_LIMIT);
  const hasMore = repos.length > ACTIVITY_LIMIT;

  return (
    <div className="dashboard-section">
      <h2>Recent Activity (7 days)</h2>
      <div className="activity-list">
        {visible.map((repo, i) => (
          <div key={i} className="activity-item">
            <span className="activity-repo">{repo.name}</span>
            <span className="activity-meta">{timeAgo(repo.pushedAt)}</span>
            <span className="activity-commits">
              {commitsByRepo[repo.name]?.length || 0} commits
            </span>
          </div>
        ))}
      </div>
      {hasMore && (
        <button className="expand-button" onClick={toggle}>
          {expanded ? 'Show less' : `Show all ${repos.length} repos`}
        </button>
      )}
    </div>
  );
}

export function DashboardPage() {
  const [data, setData] = useState<GitHubData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/github')
      .then(res => res.json())
      .then(d => {
        if (d.error) setError(d.error);
        else setData(d);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <PageShell title="Dashboard" subtitle="Loading GitHub data...">
        <div className="dashboard-loading">Fetching from GitHub API...</div>
      </PageShell>
    );
  }

  if (error) {
    return (
      <PageShell title="Dashboard" subtitle="GitHub integration">
        <div className="dashboard-error">Error: {error}</div>
      </PageShell>
    );
  }

  if (!data) return null;

  const { summary, repos, open_pull_requests, recent_commits, workflow_runs, branches, fetch_errors } = data;
  const fetchErrors = fetch_errors || [];

  // Group commits by repo
  const commitsByRepo: Record<string, typeof recent_commits> = {};
  for (const c of recent_commits || []) {
    if (!commitsByRepo[c.repo]) commitsByRepo[c.repo] = [];
    commitsByRepo[c.repo]!.push(c);
  }

  // Active repos (pushed in last 7 days, not archived)
  const activeRepos = (repos || [])
    .filter(r => !r.isArchived && r.pushedAt)
    .sort((a, b) => new Date(b.pushedAt).getTime() - new Date(a.pushedAt).getTime());

  // Failing CI — only show failures on main/master or branches with open PRs
  // (filters out stale failures on merged/closed branches)
  const openPrBranches = new Set(
    (open_pull_requests || []).map(pr => `${pr.repository?.name}:${pr.headRefName}`)
  );
  const failingRuns = (workflow_runs || [])
    .filter(r => {
      if (r.conclusion !== 'failure') return false;
      const isDefaultBranch = r.branch === 'main' || r.branch === 'master';
      const hasOpenPr = openPrBranches.has(`${r.repo}:${r.branch}`);
      return isDefaultBranch || hasOpenPr;
    })
    .slice(0, 10);

  // Stale branches (non-main, non-protected)
  const staleBranches = (branches || [])
    .filter(b => !b.protected && b.name !== 'main' && b.name !== 'master');

  // Group stale branches by repo
  const branchesByRepo: Record<string, string[]> = {};
  for (const b of staleBranches) {
    if (!branchesByRepo[b.repo]) branchesByRepo[b.repo] = [];
    branchesByRepo[b.repo].push(b.name);
  }

  return (
    <PageShell
      title="Dashboard"
      subtitle={`${summary?.total_repos} repos · ${summary?.recent_commit_count} commits this week · ${data.cached ? 'cached' : 'fresh'}${fetchErrors.length ? ` · ${fetchErrors.length} incomplete` : ''}`}
    >
      <div className="dashboard-grid">
        {/* API Cost Overview */}
        <CostPanel />

        {/* Shadow Pricing — subscription value */}
        <ShadowPricingPanel />

        {/* Summary Cards */}
        <div className="dashboard-summary">
          <div className="summary-card">
            <span className="summary-number">{summary?.total_repos}</span>
            <span className="summary-label">Repos</span>
          </div>
          <div className="summary-card">
            <span className="summary-number">{summary?.open_prs}</span>
            <span className="summary-label">Open PRs</span>
          </div>
          <div className="summary-card">
            <span className="summary-number">{summary?.recent_commit_count}</span>
            <span className="summary-label">Commits (7d)</span>
          </div>
          <div className="summary-card">
            <span className="summary-number">{summary?.repos_with_ci}</span>
            <span className="summary-label">Repos w/ CI</span>
          </div>
          <div className="summary-card highlight-bad">
            <span className="summary-number">{summary?.failing_ci}</span>
            <span className="summary-label">Failing CI</span>
          </div>
          <div className="summary-card">
            <span className="summary-number">{Object.keys(branchesByRepo).length}</span>
            <span className="summary-label">Repos w/ stale branches</span>
          </div>
          {fetchErrors.length > 0 && (
            <div className="summary-card highlight-bad">
              <span className="summary-number">{fetchErrors.length}</span>
              <span className="summary-label">Failed fetches</span>
            </div>
          )}
        </div>

        {/* Incomplete data — every number above is a floor, not a total, while
            this is non-empty. Without it the dashboard reports partial results
            as if they were complete, which is the same silent degradation as
            the bug that made this list necessary (#6749). */}
        {fetchErrors.length > 0 && (
          <div className="dashboard-section" role="alert">
            <h2>Incomplete data</h2>
            <p className="fetch-errors-note">
              GitHub data could not be retrieved for the following. Counts above exclude them,
              so treat every figure as a minimum.
            </p>
            <ul className="fetch-errors-list">
              {fetchErrors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Open PRs */}
        {open_pull_requests && open_pull_requests.length > 0 && (
          <div className="dashboard-section">
            <h2>Open Pull Requests</h2>
            <div className="pr-list">
              {open_pull_requests.map((pr, i) => (
                <div key={i} className="pr-item">
                  <a href={pr.url} target="_blank" rel="noopener noreferrer">
                    {pr.repository?.name}#{pr.number}
                  </a>
                  <span className="pr-title">{pr.title}</span>
                  <span className={`pr-badge ${pr.isDraft ? 'draft' : pr.reviewDecision?.toLowerCase() || 'pending'}`}>
                    {pr.isDraft ? 'Draft' : pr.reviewDecision || 'Pending'}
                  </span>
                  <span className="pr-meta">{timeAgo(pr.createdAt)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Activity */}
        <RecentActivity repos={activeRepos} commitsByRepo={commitsByRepo} />

        {/* Failing CI */}
        {failingRuns.length > 0 && (
          <div className="dashboard-section">
            <h2>Failing CI</h2>
            <div className="ci-list">
              {failingRuns.map((run, i) => (
                <div key={i} className="ci-item failing">
                  <a href={run.url} target="_blank" rel="noopener noreferrer">
                    {run.repo}
                  </a>
                  <span className="ci-name">{run.name}</span>
                  <span className="ci-branch">{run.branch}</span>
                  <span className="ci-meta">{timeAgo(run.created_at)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Stale Branches */}
        {Object.keys(branchesByRepo).length > 0 && (
          <div className="dashboard-section">
            <h2>Stale Branches ({staleBranches.length} across {Object.keys(branchesByRepo).length} repos)</h2>
            <div className="branch-list">
              {Object.entries(branchesByRepo)
                .sort((a, b) => b[1].length - a[1].length)
                .slice(0, 15)
                .map(([repo, branchNames]) => (
                  <div key={repo} className="branch-item">
                    <span className="branch-repo">{repo}</span>
                    <span className="branch-names">{branchNames.join(', ')}</span>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Raw data dump for exploration */}
        <details className="dashboard-section raw-data">
          <summary>Raw API Response ({JSON.stringify(data).length} bytes)</summary>
          <pre>{JSON.stringify(data, null, 2)}</pre>
        </details>
      </div>
    </PageShell>
  );
}
