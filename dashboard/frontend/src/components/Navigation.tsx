import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { fetchNavigation } from '../api';
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
