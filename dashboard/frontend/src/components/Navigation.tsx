import { NavLink } from 'react-router-dom';
import './Navigation.css';

export function Navigation() {
  return (
    <nav className="navigation">
      <div className="navigation-container">
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
    </nav>
  );
}
