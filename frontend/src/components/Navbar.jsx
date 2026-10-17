import React, { useState, useEffect } from 'react';
import { api } from '../api';

export function Navbar({ currentPath, onNavigate }) {
  const [backendOnline, setBackendOnline] = useState(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    let isMounted = true;
    async function checkHealth() {
      try {
        const res = await api.getHealth();
        if (isMounted) setBackendOnline(res.status === 'ok');
      } catch {
        if (isMounted) setBackendOnline(false);
      }
    }
    checkHealth();
    const timer = setInterval(checkHealth, 30000);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, []);

  const navItems = [
    { label: 'Home', path: '/' },
    { label: 'Assess', path: '/assess' },
    { label: 'Dashboard', path: '/dashboard' },
    { label: 'History', path: '/history' },
  ];

  function handleNav(path) {
    setMobileMenuOpen(false);
    onNavigate(path);
  }

  return (
    <header className="navbar">
      <div className="container navbar-inner">
        {/* Brand */}
        <button
          className="navbar-brand"
          onClick={() => handleNav('/')}
          aria-label="SkillSync Home"
        >
          <img
            src="/logo.png"
            alt="SkillSync Logo"
            className="navbar-logo"
          />
          <span className="navbar-wordmark">SkillSync</span>
        </button>

        {/* Desktop Navigation */}
        <nav className="navbar-desktop-nav" aria-label="Main Navigation">
          <ul className="navbar-links">
            {navItems.map((item) => (
              <li key={item.path}>
                <button
                  className={`navbar-link ${currentPath === item.path ? 'active' : ''}`}
                  onClick={() => handleNav(item.path)}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {/* Status Pill & Primary Action */}
        <div className="navbar-actions">
          <div
            className={`status-pill ${backendOnline ? 'online' : backendOnline === false ? 'offline' : 'checking'}`}
            title={backendOnline ? 'Backend API connected' : 'Backend API connecting...'}
          >
            <span className="status-dot" />
            <span className="status-text text-xs">
              {backendOnline ? 'API Connected' : backendOnline === false ? 'API Offline' : 'Connecting...'}
            </span>
          </div>

          <button
            className="btn btn-gradient btn-sm navbar-cta-btn"
            onClick={() => handleNav('/assess')}
            id="navbar-cta-assess"
          >
            Start Assessment
          </button>

          {/* Mobile hamburger button */}
          <button
            className="mobile-menu-toggle"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle navigation menu"
            aria-expanded={mobileMenuOpen}
          >
            <span className={`hamburger-bar ${mobileMenuOpen ? 'open' : ''}`} />
            <span className={`hamburger-bar ${mobileMenuOpen ? 'open' : ''}`} />
            <span className={`hamburger-bar ${mobileMenuOpen ? 'open' : ''}`} />
          </button>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="mobile-nav-drawer animate-fade-in">
          <ul className="mobile-nav-links">
            {navItems.map((item) => (
              <li key={item.path}>
                <button
                  className={`mobile-nav-link ${currentPath === item.path ? 'active' : ''}`}
                  onClick={() => handleNav(item.path)}
                >
                  {item.label}
                </button>
              </li>
            ))}
            <li className="mobile-cta-item">
              <button
                className="btn btn-gradient btn-full"
                onClick={() => handleNav('/assess')}
              >
                Start Assessment
              </button>
            </li>
          </ul>
        </div>
      )}
    </header>
  );
}
