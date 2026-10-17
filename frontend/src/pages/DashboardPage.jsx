import React, { useState, useEffect } from 'react';
import { api } from '../api';
import { GapSolverSection } from '../components/GapSolverSection';

export function DashboardPage({ onNavigate, assessmentId }) {
  const [assessmentsList, setAssessmentsList] = useState([]);
  const [currentAssessment, setCurrentAssessment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filter & Search states
  const [statusFilter, setStatusFilter] = useState('ALL'); // 'ALL' | 'demonstrated' | 'partially_demonstrated' | 'not_found' | 'manual_verification'
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedFindings, setExpandedFindings] = useState({});

  // Real-Time GitHub Synchronization States
  const [isSyncing, setIsSyncing] = useState(false);
  const [liveNotification, setLiveNotification] = useState(null);
  const [showWebhookModal, setShowWebhookModal] = useState(false);
  const [webhookDeliveries, setWebhookDeliveries] = useState([]);
  const [loadingDeliveries, setLoadingDeliveries] = useState(false);

  // Fetch assessments and select the target or latest one
  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const listRes = await api.getAssessments(0, 50);
        const list = listRes.assessments || [];
        if (!isMounted) return;
        setAssessmentsList(list);

        if (list.length === 0) {
          setLoading(false);
          return;
        }

        // Determine which assessment ID to load
        let targetId = assessmentId ? parseInt(assessmentId, 10) : null;
        if (!targetId || !list.some(a => a.id === targetId)) {
          targetId = list[0].id; // default to most recent
        }

        const fullAssessment = await api.getAssessment(targetId);
        if (isMounted) {
          setCurrentAssessment(fullAssessment);
          setLoading(false);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || 'Failed to load assessment results.');
          setLoading(false);
        }
      }
    }
    loadData();
    return () => { isMounted = false; };
  }, [assessmentId]);

  // Live SSE Real-Time Event Subscription
  useEffect(() => {
    const eventSource = api.subscribeToEvents((event) => {
      console.log('[SkillSync SSE]', event);

      if (event.event === 'sync_started') {
        setIsSyncing(true);
        setLiveNotification({
          type: 'info',
          title: '🔄 GitHub Code Push Detected',
          message: event.message || `Analyzing new commit ${event.commit_sha?.slice(0, 7)}...`,
        });
      } else if (event.event === 'sync_progress') {
        setLiveNotification({
          type: 'info',
          title: '⚡ Code Analysis in Progress',
          message: event.message,
        });
      } else if (event.event === 'assessment_completed') {
        setIsSyncing(false);
        const sign = event.delta > 0 ? '+' : '';
        setLiveNotification({
          type: 'success',
          title: `🎯 Assessment v${event.version} Completed Automatically!`,
          message: `Target Role: ${event.job_title} | Score: ${event.new_score}% (${sign}${event.delta}%) at commit ${event.commit_sha?.slice(0, 7)}. ${event.explanation || ''}`,
        });

        // Automatically fetch and display the fresh assessment without page reload
        if (event.assessment_id) {
          api.getAssessment(event.assessment_id).then((fresh) => {
            setCurrentAssessment(fresh);
            setAssessmentsList((prev) => {
              const exists = prev.some((a) => a.id === fresh.id);
              if (exists) {
                return prev.map((a) => (a.id === fresh.id ? fresh : a));
              }
              return [fresh, ...prev];
            });
          }).catch(console.error);
        }
      } else if (event.event === 'sync_completed') {
        setIsSyncing(false);
      }
    });

    return () => {
      eventSource.close();
    };
  }, []);

  async function handleManualSync() {
    if (!currentAssessment?.repository_id) return;
    setIsSyncing(true);
    try {
      await api.triggerRepositorySync(currentAssessment.repository_id);
      setLiveNotification({
        type: 'info',
        title: 'Sync Triggered',
        message: 'Synchronizing repository against latest GitHub commits and recalculating scores...',
      });
    } catch (err) {
      setIsSyncing(false);
      setLiveNotification({
        type: 'error',
        title: 'Sync Failed',
        message: err.message,
      });
    }
  }

  async function openWebhookSettings() {
    setShowWebhookModal(true);
    setLoadingDeliveries(true);
    try {
      const res = await api.getWebhookDeliveries(20);
      setWebhookDeliveries(res.deliveries || []);
    } catch (err) {
      console.error('Failed to load deliveries:', err);
    } finally {
      setLoadingDeliveries(false);
    }
  }

  // Switch to another assessment from dropdown
  async function handleSwitchAssessment(id) {
    if (!id || id === currentAssessment?.id) return;
    setLoading(true);
    setError(null);
    try {
      const full = await api.getAssessment(id);
      setCurrentAssessment(full);
      // Update browser URL without reload for shareability
      window.history.pushState({}, '', `/dashboard?id=${id}`);
    } catch (err) {
      setError(err.message || 'Failed to switch assessment.');
    } finally {
      setLoading(false);
    }
  }

  function toggleFindingExpand(id) {
    setExpandedFindings(prev => ({
      ...prev,
      [id]: !prev[id],
    }));
  }

  // Loading Skeleton State
  if (loading) {
    return (
      <main className="page animate-fade-in">
        <div className="container text-center" style={{ padding: 'var(--space-16) 0' }}>
          <div className="spinner-large" style={{ margin: '0 auto var(--space-4)' }} />
          <h2 className="text-xl font-semibold">Loading Assessment Dashboard...</h2>
          <p className="text-muted text-sm">Fetching verified skill findings, citations, and learning recommendations.</p>
        </div>
      </main>
    );
  }

  // Error State
  if (error) {
    return (
      <main className="page animate-fade-in">
        <div className="container" style={{ maxWidth: 650, padding: 'var(--space-12) 0' }}>
          <div className="alert alert-error">
            <div className="alert-icon">⚠️</div>
            <div className="alert-content">
              <strong>Error loading dashboard:</strong> {error}
            </div>
          </div>
          <div style={{ textAlign: 'center', marginTop: 'var(--space-6)' }}>
            <button className="btn btn-secondary" onClick={() => onNavigate('/assess')}>
              Start a New Assessment
            </button>
          </div>
        </div>
      </main>
    );
  }

  // Empty State (No assessments yet in DB)
  if (!currentAssessment) {
    return (
      <main className="page animate-fade-in">
        <div className="container text-center" style={{ maxWidth: 600, padding: 'var(--space-16) 0' }}>
          <div className="empty-state-icon" style={{ fontSize: '3rem', marginBottom: 'var(--space-4)' }}>📊</div>
          <h2 className="text-2xl font-bold">No Assessments Available Yet</h2>
          <p className="text-muted text-sm" style={{ margin: 'var(--space-2) 0 var(--space-6)' }}>
            Connect a GitHub repository and job description to generate your first evidence-backed assessment report.
          </p>
          <button className="btn btn-gradient btn-lg" onClick={() => onNavigate('/assess')}>
            Start Your First Assessment →
          </button>
        </div>
      </main>
    );
  }

  // Calculate statistics from current assessment findings
  const findings = currentAssessment.skill_findings || [];
  const totalFindings = findings.length;

  const demonstratedCount = findings.filter(f => f.status.toLowerCase() === 'demonstrated').length;
  const partialCount = findings.filter(f => f.status.toLowerCase() === 'partially_demonstrated').length;
  const notFoundCount = findings.filter(f => f.status.toLowerCase() === 'not_found').length;
  const manualCount = findings.filter(f => f.status.toLowerCase() === 'manual_verification').length;

  const totalCitations = findings.reduce((acc, f) => acc + (f.evidence_citations?.length || 0), 0);

  // Category Breakdown
  const categoryStats = {};
  findings.forEach(f => {
    const cat = f.category || 'General';
    if (!categoryStats[cat]) {
      categoryStats[cat] = { total: 0, demonstrated: 0, partial: 0 };
    }
    categoryStats[cat].total += 1;
    if (f.status.toLowerCase() === 'demonstrated') {
      categoryStats[cat].demonstrated += 1;
    } else if (f.status.toLowerCase() === 'partially_demonstrated') {
      categoryStats[cat].partial += 0.5;
    }
  });

  // Filter findings based on active tab and search query
  const filteredFindings = findings.filter(f => {
    const matchesStatus =
      statusFilter === 'ALL' || f.status.toLowerCase() === statusFilter.toLowerCase();
    const query = searchQuery.toLowerCase().trim();
    const matchesSearch =
      !query ||
      f.skill_name.toLowerCase().includes(query) ||
      (f.category && f.category.toLowerCase().includes(query)) ||
      (f.rationale && f.rationale.toLowerCase().includes(query));
    return matchesStatus && matchesSearch;
  });

  const overallScore = Math.round(currentAssessment.overall_score || 0);

  // Look for previous assessment version for the same repository to show before/after comparison
  const previousVersionAssessment = assessmentsList.find(
    (a) => a.repository_id === currentAssessment.repository_id && a.version === (currentAssessment.version - 1)
  );
  const scoreDelta = previousVersionAssessment
    ? Math.round(currentAssessment.overall_score || 0) - Math.round(previousVersionAssessment.overall_score || 0)
    : null;

  return (
    <main className="page animate-fade-in">
      <div className="container">
        {/* ── Top Bar: Assessment Switcher & Metadata ───────────── */}
        <div className="dashboard-topbar">
          <div className="dashboard-title-area">
            <div className="breadcrumbs text-xs text-muted">
              <span>SkillSync</span> &gt; <span>Assessments</span> &gt; <span>ID #{currentAssessment.id}</span>
            </div>
            <h1 className="dashboard-main-title">
              {currentAssessment.repository?.github_owner}/{currentAssessment.repository?.repo_name}
            </h1>
            <div className="dashboard-meta-row">
              <span className="badge badge-primary text-xs">
                Target Role: <strong>{currentAssessment.job_profile?.title}</strong>
              </span>
              <span className="badge badge-outline text-xs">
                Version <strong>v{currentAssessment.version || 1}</strong>
              </span>
              {currentAssessment.commit_sha && (
                <span className="badge badge-secondary text-xs font-mono">
                  Git SHA: {currentAssessment.commit_sha.slice(0, 7)}
                </span>
              )}
              <span className="text-xs text-muted">
                {new Date(currentAssessment.created_at).toLocaleString()}
              </span>
            </div>
          </div>

          {/* Assessment Selector Dropdown */}
          <div className="assessment-switcher">
            <label htmlFor="assessment-select" className="text-xs font-medium text-muted">
              Assessment Run:
            </label>
            <select
              id="assessment-select"
              className="form-select form-select-sm"
              value={currentAssessment.id}
              onChange={(e) => handleSwitchAssessment(parseInt(e.target.value, 10))}
            >
              {assessmentsList.map((a) => (
                <option key={a.id} value={a.id}>
                  #{a.id} — {a.repository?.repo_name || 'Repo'} (v{a.version || 1}, {Math.round(a.overall_score || 0)}%)
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Real-Time Live Notification Banner */}
        {liveNotification && (
          <div
            className={`alert alert-${liveNotification.type === 'error' ? 'error' : (liveNotification.type === 'success' ? 'success' : 'info')} animate-fade-in`}
            style={{
              marginBottom: 'var(--space-4)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              borderLeft: '4px solid var(--primary-color)',
            }}
          >
            <div>
              <strong>{liveNotification.title}:</strong> {liveNotification.message}
            </div>
            <button
              className="btn btn-xs btn-outline"
              onClick={() => setLiveNotification(null)}
              style={{ marginLeft: 'var(--space-4)' }}
            >
              ✕
            </button>
          </div>
        )}

        {/* ── Live GitHub Synchronization Bar ──────────────────────── */}
        <div
          className="card"
          style={{
            marginBottom: 'var(--space-6)',
            padding: 'var(--space-4) var(--space-6)',
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 'var(--space-4)',
            background: 'var(--surface-color)',
            border: '1px solid var(--border-color)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <span
              style={{
                display: 'inline-block',
                width: 12,
                height: 12,
                borderRadius: '50%',
                background: isSyncing ? '#f59e0b' : '#10b981',
                boxShadow: isSyncing ? '0 0 8px #f59e0b' : '0 0 8px #10b981',
              }}
            />
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                <span className="font-semibold text-sm">
                  {isSyncing ? 'Synchronizing with GitHub repository...' : 'Live GitHub Synchronization Active'}
                </span>
                <span className="badge badge-success text-xs">SSE Connected</span>
              </div>
              <span className="text-xs text-muted" style={{ display: 'block' }}>
                Latest Analyzed Commit:{' '}
                <strong className="font-mono">{currentAssessment.commit_sha ? currentAssessment.commit_sha.slice(0, 7) : 'HEAD'}</strong>
                {' • '}Scores dynamically recalculate when new code is pushed.
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <button
              className="btn btn-secondary btn-sm"
              onClick={handleManualSync}
              disabled={isSyncing}
              title="Pull latest commit and reassess now"
            >
              {isSyncing ? '🔄 Syncing Code...' : '⚡ Sync Repository Now'}
            </button>
            <button
              className="btn btn-outline btn-sm"
              onClick={openWebhookSettings}
              title="Configure GitHub webhook URL & secret"
            >
              ⚙️ Webhook Setup & Deliveries
            </button>
          </div>
        </div>

        {/* Failed Assessment Status Banner */}
        {currentAssessment.status === 'failed' && (
          <div className="alert alert-error animate-fade-in" style={{ marginBottom: 'var(--space-6)' }}>
            <div className="alert-icon">⚠️</div>
            <div className="alert-content">
              <strong>Assessment Pipeline Failed:</strong>{' '}
              {currentAssessment.error_message || 'The evaluation pipeline encountered an error during execution.'}
            </div>
          </div>
        )}

        {/* ── Before & After Assessment Progression (Persisted Backend Data) ── */}
        {previousVersionAssessment && (
          <div
            className="card animate-fade-in"
            style={{
              marginBottom: 'var(--space-6)',
              padding: 'var(--space-4) var(--space-6)',
              background: 'linear-gradient(135deg, rgba(23, 105, 210, 0.05) 0%, rgba(18, 184, 176, 0.05) 100%)',
              border: '1px solid var(--color-primary-light)',
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 'var(--space-4)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
              <div style={{ fontSize: '1.75rem' }}>📈</div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                  <span className="font-bold text-sm text-navy">
                    Before & After Reassessment Progression
                  </span>
                  <span className={`badge ${scoreDelta >= 0 ? 'badge-success' : 'badge-warning'} text-xs font-mono`}>
                    {scoreDelta >= 0 ? `+${scoreDelta}%` : `${scoreDelta}%`} Delta
                  </span>
                </div>
                <span className="text-xs text-muted" style={{ display: 'block', marginTop: '2px' }}>
                  Baseline <strong>v{previousVersionAssessment.version} ({Math.round(previousVersionAssessment.overall_score || 0)}%)</strong>
                  {' ➔ '}Current <strong>v{currentAssessment.version} ({Math.round(currentAssessment.overall_score || 0)}%)</strong>
                  {' • '}Scores updated via evidence verification and git sync.
                </span>
              </div>
            </div>

            <button
              className="btn btn-outline btn-sm"
              onClick={() => handleSwitchAssessment(previousVersionAssessment.id)}
            >
              Inspect v{previousVersionAssessment.version} Baseline →
            </button>
          </div>
        )}

        {/* ── Score & Overview Hero Card ─────────────────────────── */}
        <div className="card dashboard-hero-card">
          <div className="score-dial-column">
            <div className="score-dial">
              <svg className="score-dial-svg" viewBox="0 0 120 120">
                <circle
                  className="score-dial-bg"
                  cx="60"
                  cy="60"
                  r="52"
                  strokeWidth="10"
                />
                <circle
                  className="score-dial-fill"
                  cx="60"
                  cy="60"
                  r="52"
                  strokeWidth="10"
                  strokeDasharray={`${(overallScore / 100) * 326.7} 326.7`}
                />
              </svg>
              <div className="score-dial-content">
                <span className="score-dial-number">{overallScore}%</span>
                <span className="score-dial-label">Match Score</span>
              </div>
            </div>

            <div className="score-alignment-badge">
              {overallScore >= 80 ? (
                <span className="badge badge-success">High Role Alignment</span>
              ) : overallScore >= 50 ? (
                <span className="badge badge-warning">Moderate Role Alignment</span>
              ) : (
                <span className="badge badge-error">Skill Development Needed</span>
              )}
            </div>
          </div>

          <div className="score-summary-column">
            <h3 className="score-summary-title">Executive Skill Summary</h3>
            <p className="score-summary-text">
              {currentAssessment.summary ||
                `Analyzed ${totalFindings} competencies against repository artifacts. Codebase demonstrates ${demonstratedCount} verified skills with ${totalCitations} traceable citations.`}
            </p>

            {/* Quick KPI stats row */}
            <div className="kpi-grid">
              <div className="kpi-card kpi-demonstrated">
                <span className="kpi-num">{demonstratedCount}</span>
                <span className="kpi-lbl">Demonstrated</span>
              </div>
              <div className="kpi-card kpi-partial">
                <span className="kpi-num">{partialCount}</span>
                <span className="kpi-lbl">Partially Proven</span>
              </div>
              <div className="kpi-card kpi-not-found">
                <span className="kpi-num">{notFoundCount}</span>
                <span className="kpi-lbl">Not Found in Repo</span>
              </div>
              <div className="kpi-card kpi-citations">
                <span className="kpi-num">{totalCitations}</span>
                <span className="kpi-lbl">Code Citations</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Category Breakdown Progress Bars ───────────────────── */}
        {Object.keys(categoryStats).length > 0 && (
          <div className="card category-breakdown-card">
            <h3 className="section-heading">Domain Competency Breakdown</h3>
            <p className="text-muted text-xs" style={{ marginBottom: 'var(--space-4)' }}>
              Proportion of demonstrated skills across identified technical categories.
            </p>

            <div className="category-bars-grid">
              {Object.entries(categoryStats).map(([catName, stat]) => {
                const pct = Math.min(100, Math.round(((stat.demonstrated + stat.partial) / stat.total) * 100));
                return (
                  <div key={catName} className="category-bar-item">
                    <div className="category-bar-header">
                      <span className="font-semibold text-xs">{catName}</span>
                      <span className="text-xs text-muted font-mono">{pct}%</span>
                    </div>
                    <div className="progress-bar-bg">
                      <div
                        className="progress-bar-fill"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted font-mono" style={{ fontSize: '11px' }}>
                      {stat.demonstrated}/{stat.total} demonstrated
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Skill Gap Solver & Learning Roadmaps (Phase F) ────────── */}
        <GapSolverSection
          assessment={currentAssessment}
          onAssessmentUpdated={async (newAssessmentId) => {
            try {
              const listRes = await api.getAssessments(0, 50);
              const list = listRes.assessments || [];
              setAssessmentsList(list);
              if (newAssessmentId) {
                await handleSwitchAssessment(newAssessmentId);
              } else if (list.length > 0) {
                await handleSwitchAssessment(list[0].id);
              }
            } catch (err) {
              console.error('Failed to reload assessments after update:', err);
            }
          }}
        />

        {/* ── Skill Findings & Evidence Citations ────────────────── */}
        <div className="card findings-card">
          <div className="findings-header">
            <div>
              <h3 className="section-heading">Detailed Skill Findings & File Citations</h3>
              <p className="text-muted text-xs">
                Inspect rationale, limitations, and exact repository source code citations backing each skill rating.
              </p>
            </div>

            {/* Search Input */}
            <div className="findings-search">
              <input
                type="text"
                className="form-input form-input-sm"
                placeholder="Search skills or categories..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>

          {/* Filter Tabs */}
          <div className="findings-filter-tabs">
            <button
              className={`filter-tab ${statusFilter === 'ALL' ? 'active' : ''}`}
              onClick={() => setStatusFilter('ALL')}
            >
              All Skills ({totalFindings})
            </button>
            <button
              className={`filter-tab ${statusFilter === 'demonstrated' ? 'active' : ''}`}
              onClick={() => setStatusFilter('demonstrated')}
            >
              Demonstrated ({demonstratedCount})
            </button>
            <button
              className={`filter-tab ${statusFilter === 'partially_demonstrated' ? 'active' : ''}`}
              onClick={() => setStatusFilter('partially_demonstrated')}
            >
              Partial ({partialCount})
            </button>
            <button
              className={`filter-tab ${statusFilter === 'not_found' ? 'active' : ''}`}
              onClick={() => setStatusFilter('not_found')}
            >
              Not Found ({notFoundCount})
            </button>
            {manualCount > 0 && (
              <button
                className={`filter-tab ${statusFilter === 'manual_verification' ? 'active' : ''}`}
                onClick={() => setStatusFilter('manual_verification')}
              >
                Manual ({manualCount})
              </button>
            )}
          </div>

          {/* Findings List */}
          {filteredFindings.length === 0 ? (
            <div className="empty-findings-state text-center text-muted text-sm" style={{ padding: 'var(--space-8)' }}>
              No skills match the selected filter criteria.
            </div>
          ) : (
            <div className="findings-list">
              {filteredFindings.map((finding) => {
                const isExpanded = expandedFindings[finding.id];
                const citations = finding.evidence_citations || [];
                const statusLower = finding.status.toLowerCase();

                let statusBadgeClass = 'badge-secondary';
                let statusLabel = 'Not Found';
                if (statusLower === 'demonstrated') {
                  statusBadgeClass = 'badge-success';
                  statusLabel = 'Demonstrated';
                } else if (statusLower === 'partially_demonstrated') {
                  statusBadgeClass = 'badge-warning';
                  statusLabel = 'Partially Demonstrated';
                } else if (statusLower === 'manual_verification') {
                  statusBadgeClass = 'badge-outline';
                  statusLabel = 'Manual Verification';
                }

                return (
                  <div key={finding.id} className="finding-card card">
                    <div className="finding-top-row">
                      <div className="finding-title-col">
                        <div className="finding-title-group">
                          <h4 className="finding-skill-name font-bold text-base">{finding.skill_name}</h4>
                          {finding.category && (
                            <span className="badge badge-outline text-xs">{finding.category}</span>
                          )}
                          <span className={`badge ${statusBadgeClass} text-xs`}>
                            {statusLabel}
                          </span>
                        </div>
                        {finding.rationale && (
                          <p className="finding-rationale text-xs text-muted" style={{ marginTop: 'var(--space-2)' }}>
                            {finding.rationale}
                          </p>
                        )}
                      </div>

                      <div className="finding-score-col">
                        {finding.confidence_score !== null && (
                        <div className="confidence-pill" title="AI confidence score">
                            <span className="text-xs text-muted">Confidence:</span>
                            <span className="font-bold text-xs">{Math.round((finding.confidence_score || 0) * 100)}%</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Limitations & Next Steps */}
                    {(finding.limitations || finding.recommended_next_steps) && (
                      <div className="finding-meta-details">
                        {finding.limitations && (
                          <div className="meta-detail-item">
                            <span className="detail-tag text-xs font-semibold text-error">Missing Evidence:</span>
                            <span className="detail-text text-xs text-muted">{finding.limitations}</span>
                          </div>
                        )}
                        {finding.recommended_next_steps && (
                          <div className="meta-detail-item">
                            <span className="detail-tag text-xs font-semibold text-secondary">Next Step:</span>
                            <span className="detail-text text-xs text-muted">{finding.recommended_next_steps}</span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Citations Toggle Button */}
                    <div className="finding-citations-toggle-row">
                      <button
                        className="btn-link text-xs font-semibold"
                        onClick={() => toggleFindingExpand(finding.id)}
                      >
                        {isExpanded ? '▲ Hide Code Evidence' : `▼ View Code Evidence (${citations.length})`}
                      </button>
                    </div>

                    {/* Expandable Citations Drawer */}
                    {isExpanded && (
                      <div className="citations-drawer animate-fade-in">
                        {citations.length === 0 ? (
                          <p className="text-muted text-xs" style={{ fontStyle: 'italic' }}>
                            No specific source code files in this repository demonstrated this skill.
                          </p>
                        ) : (
                          citations.map((cit, cIdx) => (
                            <div key={cit.id || cIdx} className="citation-block">
                              <div className="citation-header">
                                <span className="citation-file-path font-mono text-xs">
                                  📄 {cit.file_path}
                                </span>
                                {cit.start_line && (
                                  <span className="citation-line-badge text-xs">
                                    Lines {cit.start_line}{cit.end_line ? `-${cit.end_line}` : ''}
                                  </span>
                                )}
                              </div>

                              {cit.code_snippet && (
                                <pre className="citation-snippet-box">
                                  <code>{cit.code_snippet}</code>
                                </pre>
                              )}

                              {cit.context_explanation && (
                                <p className="citation-explanation text-xs text-muted">
                                  <strong>Context:</strong> {cit.context_explanation}
                                </p>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Webhook Configuration & Audit Modal ────────────────────── */}
      {showWebhookModal && (
        <div
          className="modal-overlay animate-fade-in"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 'var(--space-4)',
          }}
          onClick={() => setShowWebhookModal(false)}
        >
          <div
            className="modal-content card"
            style={{
              maxWidth: 750,
              width: '100%',
              maxHeight: '85vh',
              overflowY: 'auto',
              background: 'var(--surface-color)',
              border: '1px solid var(--border-color)',
              padding: 'var(--space-6)',
              position: 'relative',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
              <h2 className="text-xl font-bold">GitHub Webhook Integration</h2>
              <button className="btn btn-xs btn-outline" onClick={() => setShowWebhookModal(false)}>
                ✕ Close
              </button>
            </div>

            <p className="text-sm text-muted" style={{ marginBottom: 'var(--space-4)' }}>
              Connect your GitHub repository to enable <strong>automatic synchronization</strong>. Whenever code is pushed, SkillSync analyzes new commits, extracts code evidence, and dynamically recalculates scores for all saved job profiles.
            </p>

            {/* Webhook Parameters Box */}
            <div className="card" style={{ background: 'var(--background-color)', padding: 'var(--space-4)', marginBottom: 'var(--space-6)', border: '1px solid var(--border-color)' }}>
              <div style={{ marginBottom: 'var(--space-3)' }}>
                <span className="text-xs text-muted font-semibold" style={{ display: 'block', textTransform: 'uppercase' }}>
                  1. Payload URL
                </span>
                <code className="text-sm font-mono" style={{ color: 'var(--primary-color)', userSelect: 'all' }}>
                  {(import.meta.env.VITE_API_BASE_URL
                    ? import.meta.env.VITE_API_BASE_URL.replace(/\/api\/?$/, '')
                    : window.location.origin.replace(':5173', ':8000'))}/api/webhooks/github
                </code>
              </div>

              <div style={{ marginBottom: 'var(--space-3)' }}>
                <span className="text-xs text-muted font-semibold" style={{ display: 'block', textTransform: 'uppercase' }}>
                  2. Content type
                </span>
                <code className="text-sm font-mono">application/json</code>
              </div>

              <div style={{ marginBottom: 'var(--space-3)' }}>
                <span className="text-xs text-muted font-semibold" style={{ display: 'block', textTransform: 'uppercase' }}>
                  3. Secret Token
                </span>
                <code className="text-sm font-mono" style={{ userSelect: 'all' }}>
                  skillsync-webhook-secret
                </code>
              </div>

              <div>
                <span className="text-xs text-muted font-semibold" style={{ display: 'block', textTransform: 'uppercase' }}>
                  4. Which events would you like to trigger this webhook?
                </span>
                <span className="text-sm">Select <strong>Just the push event</strong></span>
              </div>
            </div>

            {/* Webhook Deliveries Audit Table */}
            <h3 className="text-base font-semibold" style={{ marginBottom: 'var(--space-3)' }}>
              Recent Webhook Deliveries & Audit Log
            </h3>

            {loadingDeliveries ? (
              <p className="text-xs text-muted">Loading delivery records...</p>
            ) : webhookDeliveries.length === 0 ? (
              <div className="alert alert-info text-xs" style={{ padding: 'var(--space-3)' }}>
                No webhook deliveries received yet. Push a commit to your connected GitHub repository to see live deliveries appear here.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="table" style={{ width: '100%', fontSize: 'var(--text-xs)' }}>
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>Delivery ID</th>
                      <th>Commit SHA</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {webhookDeliveries.map((deliv) => (
                      <tr key={deliv.id}>
                        <td>
                          <span
                            className={`badge badge-${
                              deliv.status === 'processed'
                                ? 'success'
                                : deliv.status === 'queued'
                                ? 'primary'
                                : deliv.status === 'duplicate'
                                ? 'secondary'
                                : 'warning'
                            }`}
                          >
                            {deliv.status}
                          </span>
                        </td>
                        <td className="font-mono text-xs">{deliv.delivery_id ? deliv.delivery_id.slice(0, 16) : 'N/A'}</td>
                        <td className="font-mono text-xs">{deliv.commit_sha ? deliv.commit_sha.slice(0, 7) : 'HEAD'}</td>
                        <td className="text-muted text-xs">
                          {deliv.created_at ? new Date(deliv.created_at).toLocaleTimeString() : 'N/A'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
