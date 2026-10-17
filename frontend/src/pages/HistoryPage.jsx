import React, { useState, useEffect } from 'react';
import { api } from '../api';

export function HistoryPage({ onNavigate }) {
  const [assessments, setAssessments] = useState([]);
  const [repositories, setRepositories] = useState([]);
  const [selectedRepoFilter, setSelectedRepoFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    async function loadHistory() {
      setLoading(true);
      setError(null);
      try {
        const [assessRes, reposRes] = await Promise.allSettled([
          api.getAssessments(0, 100),
          api.getRepositories(0, 50),
        ]);

        if (assessRes.status === 'fulfilled') {
          if (isMounted) setAssessments(assessRes.value.assessments || []);
        } else {
          throw new Error('Failed to load assessment history.');
        }

        if (reposRes.status === 'fulfilled') {
          if (isMounted) setRepositories(reposRes.value.repositories || []);
        }
      } catch (err) {
        if (isMounted) setError(err.message || 'Error loading history.');
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadHistory();
    return () => { isMounted = false; };
  }, []);

  const filtered = assessments.filter((a) => {
    if (selectedRepoFilter === 'ALL') return true;
    return a.repository_id === parseInt(selectedRepoFilter, 10);
  });

  if (loading) {
    return (
      <main className="page animate-fade-in">
        <div className="container text-center" style={{ padding: 'var(--space-16) 0' }}>
          <div className="spinner-large" style={{ margin: '0 auto var(--space-4)' }} />
          <h2 className="text-xl font-semibold">Loading Assessment History...</h2>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="page animate-fade-in">
        <div className="container" style={{ maxWidth: 600, padding: 'var(--space-12) 0' }}>
          <div className="alert alert-error">
            <div className="alert-icon">⚠️</div>
            <div className="alert-content">{error}</div>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="page animate-fade-in">
      <div className="container">
        {/* Header */}
        <div className="page-header text-center">
          <span className="badge badge-info">Provenance & Versioning</span>
          <h1 className="page-title">Assessment History & Progression</h1>
          <p className="text-muted page-subtitle">
            Track skill evaluation records across Git commit revisions and target job profiles.
            All assessments are preserved in your owner-controlled database.
          </p>
        </div>

        {/* Repository Filter Bar */}
        {repositories.length > 0 && (
          <div className="history-filter-bar card">
            <div className="history-filter-label text-xs font-semibold text-muted">
              Filter by Repository:
            </div>
            <div className="history-filter-pills">
              <button
                className={`tab-pill ${selectedRepoFilter === 'ALL' ? 'active' : ''}`}
                onClick={() => setSelectedRepoFilter('ALL')}
              >
                All Repositories ({assessments.length})
              </button>
              {repositories.map((r) => (
                <button
                  key={r.id}
                  className={`tab-pill ${selectedRepoFilter === String(r.id) ? 'active' : ''}`}
                  onClick={() => setSelectedRepoFilter(String(r.id))}
                >
                  {r.repo_name}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* History List or Empty State */}
        {filtered.length === 0 ? (
          <div className="card text-center" style={{ padding: 'var(--space-12) var(--space-6)', marginTop: 'var(--space-6)' }}>
            <div style={{ fontSize: '2.5rem', marginBottom: 'var(--space-3)' }}>📅</div>
            <h3 className="text-lg font-bold">No Historical Assessments Found</h3>
            <p className="text-muted text-sm" style={{ margin: 'var(--space-2) 0 var(--space-6)' }}>
              {selectedRepoFilter === 'ALL'
                ? 'Run your first assessment to begin tracking your technical skill progress over time.'
                : 'No assessments have been recorded yet for the selected repository.'}
            </p>
            <button className="btn btn-gradient" onClick={() => onNavigate('/assess')}>
              Start an Assessment →
            </button>
          </div>
        ) : (
          <div className="history-timeline-list" style={{ marginTop: 'var(--space-6)' }}>
            {filtered.map((item) => {
              const score = Math.round(item.overall_score || 0);
              let scoreColor = 'var(--color-primary)';
              if (score >= 80) scoreColor = 'var(--color-success)';
              else if (score < 50) scoreColor = 'var(--color-error)';

              return (
                <div key={item.id} className="card history-item-card">
                  <div className="history-item-left">
                    <div className="history-version-badge">
                      <span className="font-bold text-sm">v{item.version || 1}</span>
                      <span className="text-xs text-muted">Run #{item.id}</span>
                    </div>

                    <div className="history-details-col">
                      <div className="history-title-row">
                        <span className="font-bold text-base">
                          {item.repository?.github_owner}/{item.repository?.repo_name}
                        </span>
                        <span className="badge badge-primary text-xs">
                          {item.job_profile?.title || 'Target Role'}
                        </span>
                        {item.commit_sha && (
                          <span className="badge badge-secondary text-xs font-mono">
                            Git: {item.commit_sha.slice(0, 7)}
                          </span>
                        )}
                        <span className="badge badge-outline text-xs">
                          Trigger: {item.trigger_event || 'manual'}
                        </span>
                      </div>

                      <p className="history-summary text-muted text-xs">
                        {item.summary || 'Assessment completed with verified skill findings.'}
                      </p>

                      <div className="history-date text-xs text-muted">
                        Recorded on {new Date(item.created_at).toLocaleString()}
                      </div>
                    </div>
                  </div>

                  <div className="history-item-right">
                    <div className="history-score-display">
                      <span className="history-score-num" style={{ color: scoreColor }}>
                        {score}%
                      </span>
                      <div className="history-score-bar-bg">
                        <div
                          className="history-score-bar-fill"
                          style={{ width: `${score}%`, backgroundColor: scoreColor }}
                        />
                      </div>
                    </div>

                    <button
                      className="btn btn-secondary btn-sm history-inspect-btn"
                      onClick={() => onNavigate(`/dashboard?id=${item.id}`)}
                    >
                      Inspect Report →
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
