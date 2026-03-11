import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { fetchNavigation } from '../api';
import type { NavigationItem, NavigationResponse } from '../types';
import './Navigation.css';

const FALLBACK_NAVIGATION: NavigationResponse = {
  title: 'Project Tracker',
  items: [
    {
      id: 'dashboard',
      label: 'Dashboard',
      href: '/dashboard',
      match_prefixes: ['/dashboard', '/project'],
      navigation_type: 'document',
    },
    {
      id: 'kanban',
      label: 'Kanban',
      href: '/kanban',
      match_prefixes: ['/kanban'],
      navigation_type: 'spa',
    },
    {
      id: 'agentic',
      label: 'Agentic',
      href: '/agentic',
      match_prefixes: ['/agentic'],
      navigation_type: 'spa',
    },
    {
      id: 'graph',
      label: 'Graph',
      href: '/graph',
      match_prefixes: ['/graph'],
      navigation_type: 'document',
    },
  ],
};

function isNavigationItemActive(item: NavigationItem, pathname: string) {
  return item.match_prefixes.some(prefix => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function Navigation() {
  const location = useLocation();
  const [navigation, setNavigation] = useState<NavigationResponse>(FALLBACK_NAVIGATION);

  useEffect(() => {
    let cancelled = false;

    async function loadNavigation() {
      try {
        const data = await fetchNavigation();
        if (!cancelled) {
          setNavigation(data);
        }
      } catch (error) {
        console.error('Failed to load navigation metadata:', error);
      }
    }

    loadNavigation();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <nav className="navigation">
      <div className="navigation-container">
        <div className="navigation-brand">
          <a href="/dashboard" className="navigation-title">
            {navigation.title}
          </a>
        </div>
        <div className="navigation-links">
          {navigation.items.map((item) => {
            const className = `nav-link ${
              isNavigationItemActive(item, location.pathname) ? 'active' : ''
            }`;

            if (item.navigation_type === 'spa') {
              return (
                <Link key={item.id} to={item.href} className={className}>
                  {item.label}
                </Link>
              );
            }

            return (
              <a key={item.id} href={item.href} className={className}>
                {item.label}
              </a>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
