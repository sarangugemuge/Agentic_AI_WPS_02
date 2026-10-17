import React from 'react';

/**
 * SkillSync React Error Boundary
 * Catches rendering exceptions in child component trees, displays an accessible
 * inline recovery UI, and prevents application-wide white-screen crashes.
 */
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary caught error]:', error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="container page-content"
          style={{ padding: 'var(--space-8) var(--space-4)' }}
          role="alert"
          aria-live="assertive"
        >
          <div
            className="card"
            style={{
              maxWidth: 720,
              margin: '0 auto',
              border: '1.5px solid var(--color-error)',
              borderRadius: 'var(--radius-lg)',
              padding: 'var(--space-6)',
              background: 'var(--color-white)',
              boxShadow: 'var(--shadow-lg)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
              <span style={{ fontSize: '2rem' }}>⚠️</span>
              <div>
                <h2 className="text-xl font-bold" style={{ color: 'var(--color-navy)', margin: 0 }}>
                  Something went wrong displaying this view
                </h2>
                <p className="text-xs text-muted" style={{ margin: '4px 0 0' }}>
                  A component rendering issue was safely caught. Navigation and entered data remain available.
                </p>
              </div>
            </div>

            <div
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-navy-10)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-3)',
                margin: 'var(--space-4) 0',
                fontSize: 'var(--font-size-xs)',
                fontFamily: 'monospace',
                color: 'var(--color-error-dark, #b91c1c)',
                maxHeight: 160,
                overflowY: 'auto',
              }}
            >
              {this.state.error?.message || 'An unexpected rendering error occurred.'}
            </div>

            <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
              <button
                className="btn btn-primary btn-sm"
                onClick={this.handleReset}
                id="error-boundary-retry-btn"
              >
                🔄 Try Again
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  this.handleReset();
                  if (typeof window !== 'undefined') window.location.href = '/dashboard';
                }}
                id="error-boundary-dashboard-btn"
              >
                📊 Go to Dashboard
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  this.handleReset();
                  if (typeof window !== 'undefined') window.location.href = '/';
                }}
                id="error-boundary-home-btn"
              >
                🏠 Return Home
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
