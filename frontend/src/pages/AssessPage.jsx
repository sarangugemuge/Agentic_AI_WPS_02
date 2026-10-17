import React, { useState, useEffect } from 'react';
import { api } from '../api';

export function AssessPage({ onNavigate }) {
  // Repository State
  const [repoMode, setRepoMode] = useState('new'); // 'new' | 'existing'
  const [existingRepos, setExistingRepos] = useState([]);
  const [selectedRepoId, setSelectedRepoId] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [validatingRepo, setValidatingRepo] = useState(false);
  const [validatedRepoInfo, setValidatedRepoInfo] = useState(null);
  const [repoError, setRepoError] = useState(null);

  // Job Profile State
  const [jobMode, setJobMode] = useState('new'); // 'new' | 'existing'
  const [existingProfiles, setExistingProfiles] = useState([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [jobTitle, setJobTitle] = useState('Full Stack Software Engineer');
  const [companyContext, setCompanyContext] = useState('');
  const [jobDescription, setJobDescription] = useState(
    'We are seeking a Full Stack Software Engineer proficient in Python, FastAPI, React, and Git. The candidate should be comfortable building RESTful APIs, writing automated unit tests with pytest, and deploying applications using Docker and modern CI/CD practices.'
  );
  const [extractingSkills, setExtractingSkills] = useState(false);
  const [extractedSkillsPreview, setExtractedSkillsPreview] = useState(null);
  const [jobError, setJobError] = useState(null);

  // Assessment Pipeline Execution State
  const [assessing, setAssessing] = useState(false);
  const [assessmentStep, setAssessmentStep] = useState(0); // 0 to 7
  const [assessmentResult, setAssessmentResult] = useState(null);
  const [pipelineError, setPipelineError] = useState(null);

  const pipelineSteps = [
    { num: 1, label: 'Validate Input', desc: 'Validating repository and target requirements' },
    { num: 2, label: 'Extract Skills', desc: 'Analyzing job description for required skills' },
    { num: 3, label: 'Gather Code Evidence', desc: 'Retrieving repository tree, README, and commit SHA' },
    { num: 4, label: 'AI Skill Matching', desc: 'Matching required competencies against code artifacts' },
    { num: 5, label: 'Verify Citations', desc: 'Executing anti-hallucination checks against real files' },
    { num: 6, label: 'Persist Results', desc: 'Saving versioned assessment, citations, and skill gaps' },
    { num: 7, label: 'Complete', desc: 'Assessment ready for inspection' },
  ];

  // Load existing repos and profiles on mount
  useEffect(() => {
    async function loadInitialData() {
      try {
        const [reposRes, profilesRes] = await Promise.allSettled([
          api.getRepositories(0, 50),
          api.getJobProfiles(0, 50),
        ]);
        if (reposRes.status === 'fulfilled') {
          setExistingRepos(reposRes.value.repositories || []);
        }
        if (profilesRes.status === 'fulfilled') {
          setExistingProfiles(profilesRes.value.job_profiles || []);
        }
      } catch (err) {
        console.error('Failed to load initial repos/profiles:', err);
      }
    }
    loadInitialData();
  }, []);

  // Validate GitHub repository URL
  async function handleValidateRepo() {
    if (!repoUrl || !repoUrl.trim()) {
      setRepoError('Please enter a GitHub repository URL.');
      return;
    }
    setValidatingRepo(true);
    setRepoError(null);
    setValidatedRepoInfo(null);

    try {
      const res = await api.validateRepository(repoUrl.trim());

      if (res.valid) {
        setValidatedRepoInfo(res);
      } else {
        setRepoError(res.message || 'Repository could not be validated.');
      }
    } catch (err) {
      setRepoError(err.message || 'Validation failed. Please verify the URL.');
    } finally {
      setValidatingRepo(false);
    }
  }

  // Preview Skill Extraction from Job Description
  async function handlePreviewSkills() {
    if (!jobTitle.trim()) {
      setJobError('Please provide a job title.');
      return;
    }
    if (!jobDescription.trim() || jobDescription.trim().length < 20) {
      setJobError('Job description must be at least 20 characters long.');
      return;
    }
    setExtractingSkills(true);
    setJobError(null);

    try {
      const res = await api.extractSkills(jobTitle.trim(), jobDescription.trim());
      setExtractedSkillsPreview(res.extracted_skills || []);
    } catch (err) {
      setJobError(err.message || 'Failed to extract skills preview.');
    } finally {
      setExtractingSkills(false);
    }
  }

  // Trigger Full Assessment Pipeline
  async function handleStartAssessment(e) {
    e.preventDefault();
    setPipelineError(null);
    setAssessmentResult(null);

    // 1. Determine Repository ID
    let repositoryId = null;
    if (repoMode === 'existing') {
      if (!selectedRepoId) {
        setRepoError('Please select a tracked repository.');
        return;
      }
      repositoryId = parseInt(selectedRepoId, 10);
    } else {
      if (!repoUrl.trim()) {
        setRepoError('Please enter a GitHub repository URL.');
        return;
      }
      // If not yet validated or already validated, register or get repo
      try {
        setValidatingRepo(true);
        const valRes = await api.validateRepository(repoUrl.trim());
        if (!valRes.valid) {
          setRepoError(valRes.message || 'Repository URL is invalid.');
          setValidatingRepo(false);
          return;
        }
        setValidatedRepoInfo(valRes);

        // Create or fetch repo from backend
        const createdRepo = await api.createRepository({
          github_url: repoUrl.trim(),
          github_owner: valRes.owner,
          repo_name: valRes.repo,
          default_branch: valRes.default_branch || 'main',
          description: valRes.description || '',
          language: valRes.language || 'Unknown',
        });
        repositoryId = createdRepo.id;
      } catch (err) {
        setRepoError(err.message || 'Failed to register repository.');
        setValidatingRepo(false);
        return;
      } finally {
        setValidatingRepo(false);
      }
    }

    // 2. Determine Job Profile Parameters
    let jobProfileId = null;
    let payloadJobTitle = null;
    let payloadJobDesc = null;
    let payloadCompany = null;

    if (jobMode === 'existing') {
      if (!selectedProfileId) {
        setJobError('Please select an existing job profile.');
        return;
      }
      jobProfileId = parseInt(selectedProfileId, 10);
    } else {
      if (!jobTitle.trim()) {
        setJobError('Please enter a job title.');
        return;
      }
      if (!jobDescription.trim() || jobDescription.trim().length < 20) {
        setJobError('Job description must be at least 20 characters long.');
        return;
      }
      payloadJobTitle = jobTitle.trim();
      payloadJobDesc = jobDescription.trim();
      payloadCompany = companyContext.trim() || null;
    }

    // 3. Begin Pipeline Animation & API Trigger
    setAssessing(true);
    setAssessmentStep(1);

    // Step simulation timers for transparent user feedback
    const stepTimer1 = setTimeout(() => setAssessmentStep(2), 700);
    const stepTimer2 = setTimeout(() => setAssessmentStep(3), 1600);
    const stepTimer3 = setTimeout(() => setAssessmentStep(4), 2800);
    const stepTimer4 = setTimeout(() => setAssessmentStep(5), 4200);

    try {
      const payload = {
        repository_id: repositoryId,
        job_profile_id: jobProfileId,
        job_title: payloadJobTitle,
        job_description: payloadJobDesc,
        company_context: payloadCompany,
      };

      const result = await api.triggerAssessment(payload);

      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      clearTimeout(stepTimer3);
      clearTimeout(stepTimer4);

      setAssessmentStep(6);
      setTimeout(() => {
        setAssessmentStep(7);
        setAssessmentResult(result);
        setAssessing(false);
      }, 500);

    } catch (err) {
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      clearTimeout(stepTimer3);
      clearTimeout(stepTimer4);
      setAssessing(false);
      setPipelineError(err.message || 'Assessment pipeline failed. Please try again.');
    }
  }

  return (
    <main className="page animate-fade-in">
      <div className="container">
        {/* Page Header */}
        <div className="page-header text-center">
          <span className="badge badge-primary">New Skill Assessment</span>
          <h1 className="page-title">Run Evidence-Backed Code Evaluation</h1>
          <p className="text-muted page-subtitle">
            Connect your repository and specify your target engineering role. SkillSync extracts
            skills, matches code artifacts, and delivers verified citations.
          </p>
        </div>

        {/* Global Pipeline Error Alert */}
        {pipelineError && (
          <div className="alert alert-error" role="alert" style={{ marginBottom: 'var(--space-6)' }}>
            <div className="alert-icon">⚠️</div>
            <div className="alert-content">
              <strong>Assessment Error:</strong> {pipelineError}
            </div>
            <button
              className="alert-close"
              onClick={() => setPipelineError(null)}
              aria-label="Dismiss alert"
            >
              ×
            </button>
          </div>
        )}

        {/* Assessment Progress Stepper Modal / Panel */}
        {assessing && (
          <div className="card assessment-progress-card animate-fade-in" style={{ marginBottom: 'var(--space-8)' }}>
            <div className="progress-header">
              <div className="spinner-large" />
              <div>
                <h3 className="font-semibold text-lg">AI Assessment Pipeline Running...</h3>
                <p className="text-muted text-sm">
                  {pipelineSteps[assessmentStep - 1]?.desc || 'Analyzing repository against job profile...'}
                </p>
              </div>
            </div>

            <div className="pipeline-stepper-bar">
              {pipelineSteps.map((s) => {
                const isComplete = assessmentStep > s.num;
                const isCurrent = assessmentStep === s.num;
                return (
                  <div
                    key={s.num}
                    className={`stepper-step ${isComplete ? 'completed' : isCurrent ? 'active' : 'pending'}`}
                  >
                    <div className="stepper-circle">
                      {isComplete ? '✓' : s.num}
                    </div>
                    <div className="stepper-label text-xs font-medium">{s.label}</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Assessment Completed Success Card */}
        {assessmentResult && (
          <div className="card assessment-success-card animate-fade-in" style={{ marginBottom: 'var(--space-8)' }}>
            <div className="success-header">
              <div className="success-badge">✓</div>
              <div>
                <h3 className="font-bold text-xl text-success">Assessment Successfully Completed!</h3>
                <p className="text-muted text-sm">
                  Evaluated <strong>{assessmentResult.repository?.github_owner}/{assessmentResult.repository?.repo_name}</strong> against{' '}
                  <strong>{assessmentResult.job_profile?.title}</strong> (Version {assessmentResult.version || 1}).
                </p>
              </div>
            </div>

            <div className="success-metrics-row">
              <div className="success-metric">
                <span className="metric-val gradient-text">{Math.round(assessmentResult.overall_score || 0)}%</span>
                <span className="metric-lbl">Overall Match Score</span>
              </div>
              <div className="success-metric">
                <span className="metric-val">{assessmentResult.skill_findings?.length || 0}</span>
                <span className="metric-lbl">Skills Evaluated</span>
              </div>
              <div className="success-metric">
                <span className="metric-val">
                  {assessmentResult.skill_findings?.reduce((acc, f) => acc + (f.evidence_citations?.length || 0), 0) || 0}
                </span>
                <span className="metric-lbl">File Citations</span>
              </div>
              <div className="success-metric">
                <span className="metric-val">{assessmentResult.skill_gaps?.length || 0}</span>
                <span className="metric-lbl">Identified Skill Gaps</span>
              </div>
            </div>

            <div className="success-actions">
              <button
                className="btn btn-gradient btn-lg"
                onClick={() => onNavigate(`/dashboard?id=${assessmentResult.id}`)}
              >
                Open Full Assessment Dashboard →
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setAssessmentResult(null);
                  setAssessmentStep(0);
                }}
              >
                Run Another Assessment
              </button>
            </div>
          </div>
        )}

        {/* Assessment Form Grid */}
        <form onSubmit={handleStartAssessment} className="assess-form-grid">
          {/* ── Left Column: Repository Connection ────────────────── */}
          <div className="card form-panel">
            <div className="panel-header">
              <span className="panel-step-badge">1</span>
              <div>
                <h2 className="panel-title">Repository Source</h2>
                <p className="text-muted text-xs">Target codebase to analyze for skill evidence</p>
              </div>
            </div>

            <div className="tab-pills" style={{ marginBottom: 'var(--space-4)' }}>
              <button
                type="button"
                className={`tab-pill ${repoMode === 'new' ? 'active' : ''}`}
                onClick={() => setRepoMode('new')}
              >
                GitHub URL
              </button>
              <button
                type="button"
                className={`tab-pill ${repoMode === 'existing' ? 'active' : ''}`}
                onClick={() => setRepoMode('existing')}
                disabled={existingRepos.length === 0}
              >
                Tracked Repos ({existingRepos.length})
              </button>
            </div>

            {repoMode === 'new' ? (
              <div className="form-group">
                <label className="form-label" htmlFor="repo-url-input">
                  GitHub Repository URL <span className="text-error">*</span>
                </label>
                <div className="input-with-button">
                  <input
                    id="repo-url-input"
                    type="url"
                    className={`form-input ${repoError ? 'form-input-error' : ''}`}
                    placeholder="https://github.com/owner/repository"
                    value={repoUrl}
                    onChange={(e) => {
                      setRepoUrl(e.target.value);
                      setRepoError(null);
                    }}
                    required
                  />
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={handleValidateRepo}
                    disabled={validatingRepo}
                  >
                    {validatingRepo ? 'Validating...' : 'Validate'}
                  </button>
                </div>
                <span className="form-helper text-xs text-muted">
                  Supports public GitHub repositories. Code is analyzed in read-only mode and never executed.
                </span>

                {repoError && (
                  <div className="form-feedback error text-xs" style={{ marginTop: 'var(--space-2)' }}>
                    ⚠️ {repoError}
                  </div>
                )}

                {/* Validated Repo Info Card */}
                {validatedRepoInfo && (
                  <div className="repo-info-card animate-fade-in" style={{ marginTop: 'var(--space-4)' }}>
                    <div className="repo-info-top">
                      <div>
                        <span className="font-semibold text-sm">
                          {validatedRepoInfo.owner}/{validatedRepoInfo.repo}
                        </span>
                        <span className="badge badge-success text-xs" style={{ marginLeft: 'var(--space-2)' }}>
                          ✓ Validated
                        </span>
                      </div>
                      <span className="text-xs text-muted">Branch: {validatedRepoInfo.default_branch || 'main'}</span>
                    </div>
                    {validatedRepoInfo.language && (
                      <div className="repo-info-details text-xs text-muted">
                        Primary Language: <strong>{validatedRepoInfo.language}</strong>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="form-group">
                <label className="form-label" htmlFor="repo-select">
                  Select Existing Repository <span className="text-error">*</span>
                </label>
                <select
                  id="repo-select"
                  className="form-select"
                  value={selectedRepoId}
                  onChange={(e) => setSelectedRepoId(e.target.value)}
                  required
                >
                  <option value="">-- Choose a tracked repository --</option>
                  {existingRepos.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.github_owner}/{r.repo_name} ({r.language || 'Code'})
                    </option>
                  ))}
                </select>
                <span className="form-helper text-xs text-muted">
                  Choose from repositories previously validated and tracked.
                </span>
              </div>
            )}
          </div>

          {/* ── Right Column: Target Job Description ──────────────── */}
          <div className="card form-panel">
            <div className="panel-header">
              <span className="panel-step-badge">2</span>
              <div>
                <h2 className="panel-title">Target Job Profile</h2>
                <p className="text-muted text-xs">Role specifications and required technical skills</p>
              </div>
            </div>

            <div className="tab-pills" style={{ marginBottom: 'var(--space-4)' }}>
              <button
                type="button"
                className={`tab-pill ${jobMode === 'new' ? 'active' : ''}`}
                onClick={() => setJobMode('new')}
              >
                New Job Description
              </button>
              <button
                type="button"
                className={`tab-pill ${jobMode === 'existing' ? 'active' : ''}`}
                onClick={() => setJobMode('existing')}
                disabled={existingProfiles.length === 0}
              >
                Saved Profiles ({existingProfiles.length})
              </button>
            </div>

            {jobMode === 'new' ? (
              <>
                <div className="form-row">
                  <div className="form-group flex-1">
                    <label className="form-label" htmlFor="job-title-input">
                      Target Role / Job Title <span className="text-error">*</span>
                    </label>
                    <input
                      id="job-title-input"
                      type="text"
                      className="form-input"
                      placeholder="e.g. Senior Backend Engineer"
                      value={jobTitle}
                      onChange={(e) => setJobTitle(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group flex-1">
                    <label className="form-label" htmlFor="company-context-input">
                      Company / Domain (Optional)
                    </label>
                    <input
                      id="company-context-input"
                      type="text"
                      className="form-input"
                      placeholder="e.g. Cloud SaaS / Fintech"
                      value={companyContext}
                      onChange={(e) => setCompanyContext(e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-group" style={{ marginTop: 'var(--space-3)' }}>
                  <div className="label-with-action">
                    <label className="form-label" htmlFor="job-desc-input">
                      Full Job Description <span className="text-error">*</span>
                    </label>
                    <button
                      type="button"
                      className="btn-link text-xs"
                      onClick={handlePreviewSkills}
                      disabled={extractingSkills}
                    >
                      {extractingSkills ? 'Extracting...' : '🔍 Preview Skills'}
                    </button>
                  </div>
                  <textarea
                    id="job-desc-input"
                    className={`form-textarea ${jobError ? 'form-input-error' : ''}`}
                    rows={6}
                    placeholder="Paste job posting text here (skills, responsibilities, requirements)..."
                    value={jobDescription}
                    onChange={(e) => {
                      setJobDescription(e.target.value);
                      setJobError(null);
                    }}
                    required
                  />
                  {jobError && (
                    <div className="form-feedback error text-xs" style={{ marginTop: 'var(--space-2)' }}>
                      ⚠️ {jobError}
                    </div>
                  )}
                </div>

                {/* Extracted Skills Preview Box */}
                {extractedSkillsPreview && (
                  <div className="skills-preview-box animate-fade-in">
                    <span className="text-xs font-semibold text-muted">
                      Extracted Requirements ({extractedSkillsPreview.length}):
                    </span>
                    <div className="tags-container" style={{ marginTop: 'var(--space-2)' }}>
                      {extractedSkillsPreview.map((skill) => (
                        <span key={skill} className="badge badge-primary text-xs">
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="form-group">
                <label className="form-label" htmlFor="profile-select">
                  Select Existing Job Profile <span className="text-error">*</span>
                </label>
                <select
                  id="profile-select"
                  className="form-select"
                  value={selectedProfileId}
                  onChange={(e) => setSelectedProfileId(e.target.value)}
                  required
                >
                  <option value="">-- Choose a job profile --</option>
                  {existingProfiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title} {p.company_context ? `(${p.company_context})` : ''} — {p.extracted_skills?.length || 0} skills
                    </option>
                  ))}
                </select>
                <span className="form-helper text-xs text-muted">
                  Use a saved profile with pre-extracted skills.
                </span>
              </div>
            )}
          </div>

          {/* ── Full Width Bottom Action ──────────────────────────── */}
          <div className="form-submit-row">
            <button
              type="submit"
              className="btn btn-gradient btn-lg btn-full"
              disabled={assessing || validatingRepo}
              id="assess-submit-btn"
            >
              {assessing ? 'Conducting Deep Skill Assessment...' : '⚡ Run SkillSync Assessment'}
            </button>
            <p className="text-center text-xs text-muted" style={{ marginTop: 'var(--space-2)' }}>
              Matches code artifacts, README, and commit revisions against required competencies with anti-hallucination checks.
            </p>
          </div>
        </form>
      </div>
    </main>
  );
}
