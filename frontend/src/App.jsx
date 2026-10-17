import React, { useState, useEffect } from 'react';
import './App.css';
import { Navbar } from './components/Navbar';
import { Footer } from './components/Footer';
import { ErrorBoundary } from './components/ErrorBoundary';
import { LandingPage } from './pages/LandingPage';
import { AssessPage } from './pages/AssessPage';
import { DashboardPage } from './pages/DashboardPage';
import { HistoryPage } from './pages/HistoryPage';

import { navigate } from './navigation';

// Simple URL state router supporting paths and query strings
function useLocationState() {
  const [location, setLocation] = useState({
    pathname: window.location.pathname,
    search: window.location.search,
  });

  useEffect(() => {
    const handlePopState = () => {
      setLocation({
        pathname: window.location.pathname,
        search: window.location.search,
      });
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  return location;
}


function NotFoundPage({ onNavigate }) {
  return (
    <main className="page animate-fade-in">
      <div className="container page-content text-center" style={{ padding: 'var(--space-16) 0' }}>
        <h1 className="text-6xl font-extrabold gradient-text">404</h1>
        <h2 className="text-2xl font-bold" style={{ marginTop: 'var(--space-4)' }}>
          Page Not Found
        </h2>
        <p className="text-muted" style={{ margin: 'var(--space-2) 0 var(--space-6)' }}>
          The requested page route does not exist.
        </p>
        <button
          className="btn btn-primary"
          onClick={() => onNavigate('/')}
          id="notfound-home-btn"
        >
          Return to Home
        </button>
      </div>
    </main>
  );
}

export default function App() {
  const { pathname, search } = useLocationState();
  const searchParams = new URLSearchParams(search);
  const assessmentId = searchParams.get('id');

  // Match active page component
  let CurrentPageComponent = NotFoundPage;
  if (pathname === '/') {
    CurrentPageComponent = LandingPage;
  } else if (pathname === '/assess') {
    CurrentPageComponent = AssessPage;
  } else if (pathname === '/dashboard') {
    CurrentPageComponent = DashboardPage;
  } else if (pathname === '/history') {
    CurrentPageComponent = HistoryPage;
  }

  return (
    <div className="app-layout">
      <Navbar currentPath={pathname} onNavigate={navigate} />
      <div className="page-wrapper">
        <ErrorBoundary>
          <CurrentPageComponent onNavigate={navigate} assessmentId={assessmentId} />
        </ErrorBoundary>
      </div>
      <Footer onNavigate={navigate} />
    </div>
  );
}
