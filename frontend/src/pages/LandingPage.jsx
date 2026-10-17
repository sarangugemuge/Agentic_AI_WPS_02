import React, { useState, useEffect } from 'react';
import { api } from '../api';

export function LandingPage({ onNavigate }) {
  const [stats, setStats] = useState({
    totalAssessments: 0,
    totalRepositories: 0,
    averageScore: 0,
    recentAssessments: [],
    loading: true,
  });

  useEffect(() => {
    let isMounted = true;
    async function loadStats() {
      try {
        const [assessRes, reposRes] = await Promise.allSettled([
          api.getAssessments(0, 5),
          api.getRepositories(0, 50),
        ]);

        const assessments = assessRes.status === 'fulfilled' ? assessRes.value.assessments || [] : [];
        const totalAssessments = assessRes.status === 'fulfilled' ? assessRes.value.total || assessments.length : 0;
        const totalRepos = reposRes.status === 'fulfilled' ? reposRes.value.total || 0 : 0;

        let avg = 0;
        if (assessments.length > 0) {
          const sum = assessments.reduce((acc, a) => acc + (a.overall_score || 0), 0);
          avg = Math.round(sum / assessments.length);
        }

        if (isMounted) {
          setStats({
            totalAssessments,
            totalRepositories: totalRepos,
            averageScore: avg,
            recentAssessments: assessments.slice(0, 3),
            loading: false,
          });
        }
      } catch (err) {
        console.error('Failed to load landing stats:', err);
        if (isMounted) setStats(s => ({ ...s, loading: false }));
      }
    }
    loadStats();
    return () => { isMounted = false; };
  }, []);

  return (
    <main className="page-landing animate-fade-in">
      {/* ── Hero Section ────────────────────────────────────────── */}
      <section className="hero">
        <div className="container hero-content">
          <div className="hero-badge">
            <span className="badge badge-primary">
              <span className="badge-pulse" />
              AI-Powered · Evidence-Backed Skill Assessment
            </span>
          </div>

          <h1 className="hero-title">
            Transform Code Into Proven Career Skills
          </h1>

          <p className="hero-subtitle">
            SkillSync analyzes your real GitHub repositories against target job descriptions.
            Get verified skill ratings, exact source file citations, and prioritized coaching
            to close technical gaps without AI hallucinations.
          </p>

          <div className="hero-actions">
            <button
              className="btn btn-gradient btn-lg"
              onClick={() => onNavigate('/assess')}
              id="hero-cta-primary"
            >
              Start Free Assessment
              <span className="btn-icon-right">→</span>
            </button>
            <button
              className="btn btn-secondary btn-lg"
              onClick={() => onNavigate('/dashboard')}
              id="hero-cta-secondary"
            >
              Explore Dashboard
            </button>
          </div>

          {/* Live Real-Data KPI Bar */}
          <div className="hero-stats">
            <div className="stat-item">
              <span className="stat-value gradient-text">
                {stats.loading ? '...' : stats.totalAssessments}
              </span>
              <span className="stat-label">Assessments Conducted</span>
            </div>
            <div className="stat-divider" />
            <div className="stat-item">
              <span className="stat-value gradient-text">
                {stats.loading ? '...' : stats.totalRepositories}
              </span>
              <span className="stat-label">Repositories Connected</span>
            </div>
            <div className="stat-divider" />
            <div className="stat-item">
              <span className="stat-value gradient-text">
                {stats.loading ? '...' : `${stats.averageScore}%`}
              </span>
              <span className="stat-label">Avg Candidate Match Score</span>
            </div>
            <div className="stat-divider" />
            <div className="stat-item">
              <span className="stat-value gradient-text">100%</span>
              <span className="stat-label">Verified Citations</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── 4-Step Career Coaching Workflow ────────────────────── */}
      <section className="workflow-section">
        <div className="container">
          <div className="section-header text-center">
            <span className="badge badge-secondary">How It Works</span>
            <h2 className="section-title">The Evidence-Based Assessment Pipeline</h2>
            <p className="section-subtitle">
              Traditional skill assessments rely on multiple-choice quizzes or unverifiable claims.
              SkillSync operates on tangible source code artifacts.
            </p>
          </div>

          <div className="workflow-grid">
            <div className="workflow-step-card card">
              <div className="step-number">01</div>
              <div className="step-icon-wrapper">
                <span className="step-icon">🔗</span>
              </div>
              <h3 className="step-title">Connect GitHub Repository</h3>
              <p className="step-description">
                Provide any public or permitted repository. SkillSync inspects directory trees,
                commit history, dependencies, and code structure. Source code is never executed.
              </p>
              <div className="step-tag">Untrusted Read-Only Mode</div>
            </div>

            <div className="workflow-step-card card">
              <div className="step-number">02</div>
              <div className="step-icon-wrapper">
                <span className="step-icon">📋</span>
              </div>
              <h3 className="step-title">Extract Job Requirements</h3>
              <p className="step-description">
                Paste any real job description. Gemini AI parses explicit requirements and inferred
                competencies, categorizing them into normalized skill domains.
              </p>
              <div className="step-tag">Normalized Taxonomy</div>
            </div>

            <div className="workflow-step-card card">
              <div className="step-number">03</div>
              <div className="step-icon-wrapper">
                <span className="step-icon">🛡️</span>
              </div>
              <h3 className="step-title">Anti-Hallucination Verification</h3>
              <p className="step-description">
                Our verification engine cross-references all AI citations against actual repository
                files. Invented paths and phantom code snippets are rejected.
              </p>
              <div className="step-tag">Strict Anti-Hallucination</div>
            </div>

            <div className="workflow-step-card card">
              <div className="step-number">04</div>
              <div className="step-icon-wrapper">
                <span className="step-icon">🎯</span>
              </div>
              <h3 className="step-title">Actionable Skill Gaps & Plan</h3>
              <p className="step-description">
                Receive 4-tier confidence classifications, line-level code citations, and a prioritized
                action plan detailing exact projects to build to bridge skill gaps.
              </p>
              <div className="step-tag">Prioritized Coaching</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Key Differentiators Grid ──────────────────────────── */}
      <section className="features-section">
        <div className="container">
          <div className="section-header text-center">
            <span className="badge badge-accent">Core Capabilities</span>
            <h2 className="section-title">Built for Real Career Growth</h2>
            <p className="section-subtitle">
              Engineered with provenance, reproducible versioning, and honest evaluation.
            </p>
          </div>

          <div className="features-grid">
            <div className="card feature-card">
              <div className="feature-icon">🔍</div>
              <h3 className="feature-title">Line-Level Evidence Citations</h3>
              <p className="feature-desc text-muted text-sm">
                Every demonstrated skill is backed by real file paths, line ranges, and verified code
                snippets from your repository. Show recruiters actual proof of competence.
              </p>
            </div>

            <div className="card feature-card">
              <div className="feature-icon">⚖️</div>
              <h3 className="feature-title">Honest Missing Evidence Distinction</h3>
              <p className="feature-desc text-muted text-sm">
                Missing repository evidence is never conflated with candidate deficiency. If a skill
                isn't in this repo, SkillSync transparently flags it as unobserved rather than failed.
              </p>
            </div>

            <div className="card feature-card">
              <div className="feature-icon">📈</div>
              <h3 className="feature-title">Multi-Version Progress Tracking</h3>
              <p className="feature-desc text-muted text-sm">
                Track skill evolution across Git commit revisions. Reassess with each push and
                observe your alignment score climb as you build requested features.
              </p>
            </div>

            <div className="card feature-card">
              <div className="feature-icon">🔒</div>
              <h3 className="feature-title">Owner-Controlled Local Storage</h3>
              <p className="feature-desc text-muted text-sm">
                Zero third-party hosted database lock-in. All assessment history, citations, and
                job profiles reside securely in your owner-controlled local database.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Recent Assessment Highlights ──────────────────────── */}
      {stats.recentAssessments.length > 0 && (
        <section className="recent-section">
          <div className="container">
            <div className="section-header text-center">
              <span className="badge badge-info">Live Activity</span>
              <h2 className="section-title">Recently Evaluated Repositories</h2>
            </div>

            <div className="recent-grid">
              {stats.recentAssessments.map((a) => (
                <div key={a.id} className="card recent-card">
                  <div className="recent-card-header">
                    <div>
                      <span className="recent-repo-name">
                        {a.repository?.github_owner}/{a.repository?.repo_name}
                      </span>
                      <span className="recent-version-badge">v{a.version || 1}</span>
                    </div>
                    <div className="recent-score-badge">
                      <span className="recent-score-num">{Math.round(a.overall_score || 0)}%</span>
                    </div>
                  </div>

                  <p className="recent-job-title text-sm font-medium">
                    {a.job_profile?.title || 'Target Role'}
                  </p>

                  <p className="recent-summary text-muted text-xs">
                    {a.summary ? (a.summary.length > 110 ? `${a.summary.slice(0, 110)}...` : a.summary) : 'Assessment completed successfully.'}
                  </p>

                  <div className="recent-card-footer">
                    <span className="text-muted text-xs">
                      {new Date(a.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                    </span>
                    <button
                      className="btn btn-secondary btn-xs"
                      onClick={() => onNavigate(`/dashboard?id=${a.id}`)}
                    >
                      View Report →
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ── Bottom Call to Action Banner ──────────────────────── */}
      <section className="cta-banner-section">
        <div className="container">
          <div className="cta-banner">
            <div className="cta-banner-content">
              <h2 className="cta-banner-title">Ready to Prove Your Technical Skills?</h2>
              <p className="cta-banner-desc">
                Evaluate your codebase against any software engineering role in under 60 seconds.
              </p>
            </div>
            <button
              className="btn btn-gradient btn-lg cta-banner-btn"
              onClick={() => onNavigate('/assess')}
            >
              Start Your Assessment
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
