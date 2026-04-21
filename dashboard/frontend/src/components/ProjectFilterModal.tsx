import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Project } from '../types';
import { fetchProjects } from '../api';
import './ProjectFilterModal.css';

interface ProjectFilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentProject?: string;
}

type ProjectOption = Project & { task_count?: number };

const GROUP_TITLES: Record<string, string> = {
  AP: 'Auxesis Projects',
  AI: 'Auxesis Incubators',
};

export function ProjectFilterModal({
  isOpen,
  onClose,
  currentProject,
}: ProjectFilterModalProps) {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    let cancelled = false;

    async function loadProjects() {
      try {
        const data = await fetchProjects();
        if (!cancelled) {
          setProjects(data || []);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : 'Failed to load projects';
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadProjects();

    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const filteredProjects = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    const list = [...projects].sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
    );

    if (!query) {
      return list;
    }

    return list.filter((project) => {
      return (
        project.name.toLowerCase().includes(query) ||
        project.id.toLowerCase().includes(query)
      );
    });
  }, [projects, searchTerm]);

  const groupedProjects = useMemo(() => {
    const grouped = new Map<string, ProjectOption[]>();
    for (const project of filteredProjects) {
      const key = project.portfolio_group || 'default';
      const existing = grouped.get(key) || [];
      existing.push(project);
      grouped.set(key, existing);
    }

    const orderedKeys = [
      ...Object.keys(GROUP_TITLES).filter((key) => grouped.has(key)),
      ...Array.from(grouped.keys()).filter(
        (key) => key !== 'default' && !(key in GROUP_TITLES)
      ),
    ];
    if (grouped.has('default')) {
      orderedKeys.push('default');
    }

    return orderedKeys.map((key) => ({
      key,
      title: GROUP_TITLES[key] || 'Other Projects',
      projects: grouped.get(key) || [],
    }));
  }, [filteredProjects]);

  const handleSelect = (projectId?: string) => {
    if (!projectId) {
      navigate('/kanban');
    } else {
      navigate(`/kanban/${encodeURIComponent(projectId)}`);
    }
    onClose();
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="project-filter-modal-overlay" onClick={onClose}>
      <div
        className="project-filter-modal"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="project-filter-modal-header">
          <h2>Filter by Project</h2>
          <button
            className="project-filter-modal-close"
            onClick={onClose}
            aria-label="Close modal"
          >
            ×
          </button>
        </div>

        <input
          className="project-filter-search"
          type="text"
          placeholder="Search projects..."
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          autoFocus
        />

        {loading && <div className="project-filter-loading">Loading projects...</div>}
        {error && <div className="project-filter-error">{error}</div>}

        {!loading && !error && (
          <div className="project-filter-list">
            <button
              className={`project-filter-item ${!currentProject ? 'active' : ''}`}
              onClick={() => handleSelect()}
            >
              <span className="project-filter-name">All Projects</span>
            </button>

            {filteredProjects.length === 0 ? (
              <div className="project-filter-empty">No projects found</div>
            ) : (
              groupedProjects.map((group) => (
                <div key={group.key} className="project-filter-group">
                  {group.key !== 'default' && (
                    <div className="project-filter-group-title">
                      {group.projects[0]?.portfolio_label || `[${group.key}]`} {group.title}
                    </div>
                  )}
                  {group.projects.map((project) => (
                    <button
                      key={project.id}
                      className={`project-filter-item ${
                        currentProject === project.id ? 'active' : ''
                      }`}
                      onClick={() => handleSelect(project.id)}
                    >
                      <span className="project-filter-name-row">
                        {project.portfolio_label && (
                          <span className="project-filter-badge">{project.portfolio_label}</span>
                        )}
                        <span className="project-filter-name">{project.name}</span>
                      </span>
                      {typeof project.task_count === 'number' && (
                        <span className="project-filter-count">{project.task_count}</span>
                      )}
                    </button>
                  ))}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
