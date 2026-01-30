import { NavLink } from 'react-router-dom';
import './Navigation.css';

export function Navigation() {
  return (
    <nav className="navigation">
      <div className="navigation-container">
        <div className="navigation-brand">
          <a href="/" className="navigation-title">
            Project Tracker
          </a>
        </div>
        <div className="navigation-links">
          <a href="/" className="nav-link">
            Dashboard
          </a>
          <NavLink
            to="/kanban"
            className={({ isActive }) =>
              `nav-link ${isActive ? 'active' : ''}`
            }
          >
            Kanban
          </NavLink>
          <a href="/graph" className="nav-link">
            Graph
          </a>
        </div>
      </div>
    </nav>
  );
}
