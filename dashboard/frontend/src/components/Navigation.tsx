import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { fetchNavigation, isAbortError } from '../api';
import type { NavigationItem, NavigationResponse } from '../types';
import './Navigation.css';

declare global {
  interface Window {
    __PT_NAVIGATION__?: NavigationResponse;
  }
}

function getInitialNavigation(): NavigationResponse {
  return window.__PT_NAVIGATION__ ?? { title: 'Project Tracker', items: [] };
}

function isNavigationItemActive(item: NavigationItem, pathname: string) {
  return item.match_prefixes.some(prefix => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function Navigation() {
  const location = useLocation();
  const [navigation, setNavigation] = useState<NavigationResponse>(() => getInitialNavigation());

  useEffect(() => {
    const controller = new AbortController();

    async function loadNavigation() {
      try {
        const data = await fetchNavigation(controller.signal);
        setNavigation(data);
      } catch (error) {
        if (isAbortError(error)) {
          return;
        }
        console.error('Failed to load navigation metadata:', error);
      }
    }

    loadNavigation();

    return () => {
      controller.abort();
    };
  }, []);

  return (
    <nav className="navigation">
      <div className="navigation-container">
        <div className="navigation-brand">
          <Link to="/dashboard" className="navigation-title">
            {navigation.title}
          </Link>
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
