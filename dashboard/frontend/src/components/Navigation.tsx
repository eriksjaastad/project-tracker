import { NavLink, useLocation } from 'react-router-dom';
import './Navigation.css';

export function Navigation() {
  const location = useLocation();

  return (
    <nav className="navigation">
      <div className="navigation-container">
        <NavLink
          to="/"
          className={({ isActive }) =>
            `nav-link ${isActive || location.pathname === '/dashboard' ? 'active' : ''}`
          }
        >
          Dashboard
        </NavLink>
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
