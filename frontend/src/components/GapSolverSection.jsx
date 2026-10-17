import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api';

/**
 * Safely parse bullet lists whether backend sends a newline-delimited string,
 * an array of strings, or null/undefined.
 * Prevents TypeError: .map is not a function when verdict strings arrive from API.
 */
function formatBulletItems(val) {
  if (!val) return [];
  if (Array.isArray(val)) return val.map(String).filter(Boolean);
  if (typeof val === 'string') {
    return val
      .split('\n')
      .map((line) => line.trim().replace(/^[-*•]\s*/, ''))
      .filter(Boolean);
  }
  return [String(val)];
}

/**
 * StepWorkspace: Individual Step Workspace (Keyed by step.id)
 * Handles step details, hands-on exercise, reference code, notes/evidence form,
 * deterministic rubric verification, and audit history.
 */
function StepWorkspace({
  step,
  assessmentCommitSha,
  onSaveProgress,
  onReloadPlan,
  onAssessmentUpdated,
  currentStepIndex,
  totalSteps,
  onPrevStep,
  onNextStep,
}) {
  const [stepNotes, setStepNotes] = useState(step.user_notes || '');
  const [stepFilePath, setStepFilePath] = useState(step.evidence_file_path || '');
  const [stepCommitSha, setStepCommitSha] = useState(step.evidence_commit_sha || assessmentCommitSha || '');
  const [savingProgress, setSavingProgress] = useState(false);
  const [stepSaveMessage, setStepSaveMessage] = useState(null);

  // Field-specific validation errors (Bug 2)
  const [filePathError, setFilePathError] = useState(null);
  const [commitShaError, setCommitShaError] = useState(null);

  // Evidence Verification State
  const [verifying, setVerifying] = useState(false);
  const [allowPrivateRepo, setAllowPrivateRepo] = useState(false);
  const [verificationResult, setVerificationResult] = useState(null);
  const [verificationError, setVerificationError] = useState(null);

  // Verification Audit History
  const [stepVerifications, setStepVerifications] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [showHistoryTab, setShowHistoryTab] = useState(false);

  // Copied code feedback
  const [copiedCode, setCopiedCode] = useState(false);

  useEffect(() => {
    let isMounted = true;
    async function fetchHistory() {
      if (!step?.id) return;
      setLoadingHistory(true);
      try {
        const res = await api.getStepVerifications(step.id);
        if (isMounted) setStepVerifications(res.verifications || []);
      } catch {
        if (isMounted) setStepVerifications([]);
      } finally {
        if (isMounted) setLoadingHistory(false);
      }
    }
    fetchHistory();
    return () => { isMounted = false; };
  }, [step?.id]);

  // Bug 2: Validate inputs before saving progress
  async function handleSave(newStatus = null) {
    setFilePathError(null);
    setCommitShaError(null);
    setStepSaveMessage(null);

    const targetStatus = newStatus || step.status;
    const cleanPath = (stepFilePath || '').trim();
    const cleanSha = (stepCommitSha || '').trim();
    const cleanNotes = (stepNotes || '').trim();

    // Required evidence file path check when marking evidence submitted
    if (targetStatus === 'evidence_submitted' && !cleanPath) {
      setFilePathError('Evidence file path is required to mark evidence as submitted.');
      return;
    }

    // Path safety validation if provided
    if (cleanPath) {
      if (cleanPath.includes('..')) {
        setFilePathError("Directory traversal ('..') is not permitted in evidence file paths.");
        return;
      }
      if (cleanPath.startsWith('/') || cleanPath.startsWith('\\') || (cleanPath.length > 1 && cleanPath[1] === ':')) {
        setFilePathError('Absolute file paths are not permitted. Please use repository-relative paths (e.g. src/auth.py).');
        return;
      }
    }

    // Commit SHA validation if provided
    if (cleanSha && !/^[0-9a-zA-Z_\-./]{1,40}$/.test(cleanSha)) {
      setCommitShaError('Commit SHA contains invalid characters or exceeds 40 characters.');
      return;
    }

    setSavingProgress(true);
    try {
      await onSaveProgress(step.id, targetStatus, cleanNotes, cleanPath || null, cleanSha || null);
      setStepSaveMessage({
        type: 'success',
        text: 'Step progress, notes, and evidence references saved successfully.',
      });
    } catch (err) {
      setStepSaveMessage({
        type: 'error',
        text: err.message || 'Failed to save progress.',
      });
    } finally {
      setSavingProgress(false);
    }
  }

  // Bug 2 & Bug 3: Validate required inputs and safely process verification response
  async function handleVerify() {
    setFilePathError(null);
    setCommitShaError(null);
    setVerificationError(null);

    const cleanPath = (stepFilePath || '').trim();
    const cleanSha = (stepCommitSha || '').trim();
    const cleanNotes = (stepNotes || '').trim();

    // Bug 2: Validate required evidence file path
    if (!cleanPath) {
      setFilePathError('Evidence file path is required for verification. Specify a repository-relative path (e.g. src/auth.py).');
      return;
    }

    if (cleanPath.includes('..')) {
      setFilePathError("Directory traversal ('..') is not permitted in evidence file paths.");
      return;
    }

    if (cleanPath.startsWith('/') || cleanPath.startsWith('\\') || (cleanPath.length > 1 && cleanPath[1] === ':')) {
      setFilePathError('Absolute file paths are not permitted. Please use repository-relative paths.');
      return;
    }

    if (cleanSha && !/^[0-9a-zA-Z_\-./]{1,40}$/.test(cleanSha)) {
      setCommitShaError('Commit SHA contains invalid characters or exceeds 40 characters.');
      return;
    }

    setVerifying(true);
    setVerificationResult(null);

    try {
      const payload = {
        evidence_file_path: cleanPath,
        commit_sha: cleanSha || null,
        user_notes: cleanNotes || null,
        allow_private_repo: allowPrivateRepo,
        trigger_reassessment: true,
      };

      const record = await api.verifyStepEvidence(step.id, payload);
      setVerificationResult(record);

      // Refresh verification history
      try {
        const historyRes = await api.getStepVerifications(step.id);
        setStepVerifications(historyRes.verifications || []);
      } catch {
        // non-critical history fetch
      }

      // Refresh learning plan to update step status
      if (onReloadPlan) {
        await onReloadPlan();
      }

      // If reassessment was triggered, notify parent
      if ((record.reassessment_triggered || record.subsequent_assessment_id) && record.subsequent_assessment_id) {
        if (onAssessmentUpdated) {
          onAssessmentUpdated(record.subsequent_assessment_id);
        }
      }
    } catch (err) {
      setVerificationError(err.message || 'Evidence verification encountered an error.');
    } finally {
      setVerifying(false);
    }
  }

  function handleCopyCode(code) {
    if (!code) return;
    navigator.clipboard.writeText(code).then(() => {
      setCopiedCode(true);
      setTimeout(() => setCopiedCode(false), 2000);
    });
  }

  // Bug 3 Safe Property Extraction
  const verdict = verificationResult?.verdict || verificationResult?.verification_status || 'unverified';
  const rubricScore = Math.round(verificationResult?.rubric_score ?? verificationResult?.score_percent ?? 0);
  const strengthsList = formatBulletItems(verificationResult?.strengths);
  const missingWorkList = formatBulletItems(verificationResult?.missing_work);
  const rubricFindings = Array.isArray(verificationResult?.rubric_findings) ? verificationResult.rubric_findings : [];
  const verifiedDate = verificationResult?.verified_at || verificationResult?.created_at;

  return (
    <div className="gap-active-step-panel card" style={{ padding: 'var(--space-6)', border: '1px solid var(--color-navy-20)' }}>
      {/* Step Title & Status Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
        <div>
          <span className="badge badge-outline text-xs">
            Step #{step.step_number}
          </span>
          <h3 className="text-xl font-bold" style={{ marginTop: 'var(--space-1)' }}>
            {step.title}
          </h3>
        </div>

        {/* Quick status actions */}
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          {step.status !== 'in_progress' && step.status !== 'verified' && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => handleSave('in_progress')}
              disabled={savingProgress}
              id="start-step-btn"
            >
              ▶ Mark In Progress
            </button>
          )}
          {step.status !== 'evidence_submitted' && step.status !== 'verified' && (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => handleSave('evidence_submitted')}
              disabled={savingProgress}
              id="complete-step-btn"
            >
              ✓ Mark Evidence Submitted
            </button>
          )}
        </div>
      </div>

      {/* Step Explanation */}
      <div style={{ marginTop: 'var(--space-4)' }}>
        <h4 className="text-xs font-semibold text-navy text-uppercase">Concepts & Implementation Strategy</h4>
        <p className="text-sm text-navy-80" style={{ marginTop: 'var(--space-1)', lineHeight: '1.6' }}>
          {step.instruction || step.explanation}
        </p>
      </div>

      {/* Hands-on Exercise & Expected Artifact */}
      {(step.exercise || step.exercise_prompt) && (
        <div
          className="card"
          style={{
            marginTop: 'var(--space-4)',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-navy-10)',
            padding: 'var(--space-4)',
          }}
        >
          <span className="badge badge-warning text-xs">Hands-on Technical Exercise</span>
          <p className="text-sm font-medium" style={{ marginTop: 'var(--space-2)', color: 'var(--color-navy)' }}>
            {step.exercise || step.exercise_prompt}
          </p>

          {step.expected_artifact && (
            <div style={{ marginTop: 'var(--space-3)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <span className="text-xs font-semibold text-navy">Expected Code Artifact:</span>
              <code className="text-xs font-mono font-bold" style={{ color: 'var(--color-primary)' }}>
                {step.expected_artifact}
              </code>
            </div>
          )}
        </div>
      )}

      {/* Reference Code Example */}
      {step.code_example && (
        <div style={{ marginTop: 'var(--space-4)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-1)' }}>
            <span className="text-xs font-semibold text-navy text-uppercase">
              Reference Implementation Example
            </span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => handleCopyCode(step.code_example)}
              style={{ fontSize: '11px', padding: '2px 8px' }}
              id="copy-code-example-btn"
            >
              {copiedCode ? '✓ Copied!' : '📋 Copy Code'}
            </button>
          </div>
          <pre
            className="citation-snippet-box"
            style={{
              background: '#0d1117',
              color: '#c9d1d9',
              padding: 'var(--space-4)',
              borderRadius: 'var(--radius-md)',
              overflowX: 'auto',
              fontSize: '12px',
              fontFamily: 'monospace',
              lineHeight: '1.5',
            }}
          >
            <code>{step.code_example}</code>
          </pre>
        </div>
      )}

      {/* Acceptance Criteria Checklist */}
      {(() => {
        let criteriaList = [];
        if (Array.isArray(step.acceptance_criteria)) {
          criteriaList = step.acceptance_criteria;
        } else if (typeof step.acceptance_criteria === 'string' && step.acceptance_criteria.trim()) {
          try {
            const parsed = JSON.parse(step.acceptance_criteria);
            criteriaList = Array.isArray(parsed) ? parsed : [step.acceptance_criteria];
          } catch {
            criteriaList = [step.acceptance_criteria];
          }
        }
        if (criteriaList.length === 0) return null;
        return (
          <div style={{ marginTop: 'var(--space-4)' }}>
            <h4 className="text-xs font-semibold text-navy text-uppercase" style={{ marginBottom: 'var(--space-2)' }}>
              Acceptance Criteria (Verified by Rubric)
            </h4>
            <ul style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              {criteriaList.map((crit, cIdx) => (
                <li
                  key={cIdx}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 'var(--space-2)',
                    fontSize: 'var(--font-size-xs)',
                    color: 'var(--color-navy-80)',
                  }}
                >
                  <span style={{ color: 'var(--color-primary)', fontWeight: 'bold' }}>✓</span>
                  <span>{crit}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })()}

      {/* ── Candidate Notes & Evidence Submission Form ── */}
      <div
        className="card"
        style={{
          marginTop: 'var(--space-6)',
          border: '1px solid var(--color-navy-20)',
          background: 'var(--color-surface)',
          padding: 'var(--space-5)',
        }}
      >
        <h4 className="text-sm font-bold text-navy">
          Record Progress & Submit Evidence References
        </h4>
        <p className="text-xs text-muted" style={{ marginBottom: 'var(--space-3)' }}>
          Document your architecture choices and point to the repository file where your code is committed.
        </p>

        {stepSaveMessage && (
          <div
            className={`alert alert-${stepSaveMessage.type === 'error' ? 'error' : 'success'}`}
            style={{ marginBottom: 'var(--space-3)', padding: 'var(--space-2) var(--space-3)', fontSize: 'var(--font-size-xs)' }}
            role="status"
          >
            {stepSaveMessage.text}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-3)' }}>
          <div className="form-group">
            <label className="form-label text-xs font-semibold" htmlFor="evidence-file-input">
              Evidence File Path in Repo: <span className="text-error">*</span>
            </label>
            <input
              id="evidence-file-input"
              type="text"
              className={`form-input form-input-sm font-mono ${filePathError ? 'input-error' : ''}`}
              placeholder="e.g. k8s/deployment.yaml or src/auth.py"
              value={stepFilePath}
              onChange={(e) => {
                setStepFilePath(e.target.value);
                if (filePathError) setFilePathError(null);
              }}
              aria-invalid={Boolean(filePathError)}
              aria-describedby={filePathError ? 'file-path-error-msg' : undefined}
            />
            {filePathError && (
              <span id="file-path-error-msg" className="text-xs text-error font-medium" style={{ display: 'block', marginTop: '4px' }}>
                {filePathError}
              </span>
            )}
          </div>

          <div className="form-group">
            <label className="form-label text-xs font-semibold" htmlFor="evidence-commit-input">
              Target Commit SHA (Optional):
            </label>
            <input
              id="evidence-commit-input"
              type="text"
              className={`form-input form-input-sm font-mono ${commitShaError ? 'input-error' : ''}`}
              placeholder={assessmentCommitSha || 'HEAD'}
              value={stepCommitSha}
              onChange={(e) => {
                setStepCommitSha(e.target.value);
                if (commitShaError) setCommitShaError(null);
              }}
              aria-invalid={Boolean(commitShaError)}
              aria-describedby={commitShaError ? 'commit-sha-error-msg' : undefined}
            />
            {commitShaError && (
              <span id="commit-sha-error-msg" className="text-xs text-error font-medium" style={{ display: 'block', marginTop: '4px' }}>
                {commitShaError}
              </span>
            )}
          </div>
        </div>

        <div className="form-group" style={{ marginTop: 'var(--space-3)' }}>
          <label className="form-label text-xs font-semibold" htmlFor="user-notes-input">
            Your Implementation Notes & Reflection:
          </label>
          <textarea
            id="user-notes-input"
            className="form-input form-input-sm"
            rows={3}
            placeholder="Record key design trade-offs, security considerations, or verification test results..."
            value={stepNotes}
            onChange={(e) => setStepNotes(e.target.value)}
          />
        </div>

        <div style={{ marginTop: 'var(--space-3)', display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => handleSave()}
            disabled={savingProgress}
            id="save-notes-btn"
          >
            {savingProgress ? 'Saving...' : '💾 Save Notes & Evidence References'}
          </button>
        </div>
      </div>

      {/* ── Evidence Verification & Reassessment Action ── */}
      <div
        className="card"
        style={{
          marginTop: 'var(--space-4)',
          border: '1px solid var(--color-primary-light)',
          background: 'var(--color-white)',
          padding: 'var(--space-5)',
        }}
        id="evidence-verification-panel"
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <span className="badge badge-primary text-xs">Phase E Verification</span>
              <span className="text-xs text-muted">Deterministic Rubric Evaluation</span>
            </div>
            <h4 className="text-base font-bold text-navy" style={{ marginTop: 'var(--space-1)' }}>
              Verify Code Evidence & Trigger Reassessment
            </h4>
          </div>

          <button
            className="btn btn-gradient btn-sm"
            onClick={handleVerify}
            disabled={verifying}
            id="verify-evidence-btn"
          >
            {verifying ? (
              <>
                <span className="spinner-small" style={{ marginRight: '6px' }} />
                Verifying Code Evidence...
              </>
            ) : (
              '🔬 Verify Evidence & Reassess'
            )}
          </button>
        </div>

        <p className="text-xs text-muted" style={{ marginTop: 'var(--space-2)' }}>
          SkillSync inspects your repository code at the specified commit, evaluates each rubric criterion,
          detects placeholders/stubs, and automatically reassesses your score when evidence is verified.
        </p>

        {/* Explicit permission checkbox for private repositories */}
        <div style={{ marginTop: 'var(--space-3)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <input
            type="checkbox"
            id="allow-private-repo-check"
            checked={allowPrivateRepo}
            onChange={(e) => setAllowPrivateRepo(e.target.checked)}
          />
          <label htmlFor="allow-private-repo-check" className="text-xs text-navy-80" style={{ cursor: 'pointer' }}>
            Authorize inspection of private repository code for this evidence verification check
          </label>
        </div>

        {/* Verification Error Alert */}
        {verificationError && (
          <div className="alert alert-error animate-fade-in" style={{ marginTop: 'var(--space-4)' }} role="alert">
            <div className="alert-icon">⚠️</div>
            <div className="alert-content">
              <strong>Verification Failed:</strong> {verificationError}
            </div>
          </div>
        )}

        {/* ── Actual Verification Results & Rubric Findings (Bug 3 Safe Rendering) ── */}
        {verificationResult && (
          <div
            className="card animate-fade-in"
            style={{
              marginTop: 'var(--space-4)',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-navy-20)',
              padding: 'var(--space-4)',
            }}
            id="verification-results-card"
          >
            {/* Verdict Status Banner */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                <span
                  className={`badge text-xs font-bold ${
                    verdict === 'verified'
                      ? 'badge-success'
                      : verdict === 'partially_demonstrated'
                      ? 'badge-warning'
                      : verdict === 'inaccessible' || verdict === 'inaccessible_resource'
                      ? 'badge-warning'
                      : 'badge-error'
                  }`}
                  style={{ padding: '4px 10px', fontSize: '12px' }}
                >
                  {verdict.toUpperCase().replace(/_/g, ' ')}
                </span>
                <span className="text-xs font-semibold text-navy">
                  Rubric Score: <strong>{rubricScore}%</strong>
                </span>
              </div>

              <span className="text-xs text-muted font-mono">
                Verified at {verifiedDate ? new Date(verifiedDate).toLocaleTimeString() : 'Just now'}
              </span>
            </div>

            {/* Reassessment Banner if triggered */}
            {(verificationResult.subsequent_assessment_id || verificationResult.reassessment_triggered) && (
              <div
                className="alert alert-success animate-fade-in"
                style={{ marginTop: 'var(--space-3)', padding: 'var(--space-3)' }}
                id="reassessment-success-banner"
              >
                <div className="alert-icon">🎯</div>
                <div className="alert-content">
                  <strong>Assessment Reevaluated!</strong>{' '}
                  {verificationResult.reassessment_explanation ||
                    'Evidence satisfied acceptance criteria. Competency rating updated.'}
                  {verificationResult.classification_change && (
                    <div style={{ marginTop: '4px', fontSize: 'var(--font-size-xs)' }}>
                      Classification update:{' '}
                      <strong className="badge badge-success text-xs font-mono">
                        {verificationResult.classification_change}
                      </strong>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Inaccessible Resource State */}
            {(verdict === 'inaccessible' || verdict === 'inaccessible_resource') && (
              <div className="alert alert-warning animate-fade-in" style={{ marginTop: 'var(--space-3)' }}>
                <div className="alert-icon">🔒</div>
                <div className="alert-content">
                  <strong>Resource Inaccessible:</strong> SkillSync could not read the specified evidence file or commit.
                  Please ensure the file exists in your repository branch/commit and that private repo inspection is enabled if applicable.
                </div>
              </div>
            )}

            {/* Rubric Findings Checklist */}
            {rubricFindings.length > 0 && (
              <div style={{ marginTop: 'var(--space-4)' }}>
                <span className="text-xs font-semibold text-navy text-uppercase" style={{ display: 'block', marginBottom: 'var(--space-2)' }}>
                  Rubric Evaluation Breakdown:
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  {rubricFindings.map((item, rfIdx) => {
                    const isPassed = item.passed === true || item.status === 'verified';
                    const detailText = item.details || item.notes || item.evidence;
                    return (
                      <div
                        key={rfIdx}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: 'var(--space-2)',
                          padding: 'var(--space-2) var(--space-3)',
                          background: isPassed ? 'var(--color-success-bg)' : 'var(--color-error-bg)',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: 'var(--font-size-xs)',
                        }}
                      >
                        <span style={{ fontWeight: 'bold', color: isPassed ? 'var(--color-success)' : 'var(--color-error)' }}>
                          {isPassed ? '✓' : '✗'}
                        </span>
                        <div style={{ flex: 1 }}>
                          <strong style={{ color: 'var(--color-navy)' }}>{item.criterion || 'Criterion'}</strong>
                          {detailText && (
                            <p style={{ margin: '2px 0 0', color: 'var(--color-navy-60)' }}>
                              {detailText}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Strengths & Missing Work (Bug 3 fix: formatBulletItems avoids calling .map on strings) */}
            <div style={{ marginTop: 'var(--space-3)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 'var(--space-3)' }}>
              {strengthsList.length > 0 && (
                <div style={{ padding: 'var(--space-3)', background: 'var(--color-white)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-navy-10)' }}>
                  <span className="text-xs font-semibold text-success" style={{ display: 'block', marginBottom: '4px' }}>
                    Verified Strengths:
                  </span>
                  <ul className="text-xs text-navy-80" style={{ paddingLeft: 'var(--space-3)', listStyle: 'disc' }}>
                    {strengthsList.map((str, sIdx) => (
                      <li key={sIdx}>{str}</li>
                    ))}
                  </ul>
                </div>
              )}

              {missingWorkList.length > 0 && (
                <div style={{ padding: 'var(--space-3)', background: 'var(--color-white)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-navy-10)' }}>
                  <span className="text-xs font-semibold text-error" style={{ display: 'block', marginBottom: '4px' }}>
                    Missing Evidence / Work Remaining:
                  </span>
                  <ul className="text-xs text-navy-80" style={{ paddingLeft: 'var(--space-3)', listStyle: 'disc' }}>
                    {missingWorkList.map((miss, mIdx) => (
                      <li key={mIdx}>{miss}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Next Recommended Action */}
            {verificationResult.next_recommended_action && (
              <div style={{ marginTop: 'var(--space-3)', padding: 'var(--space-3)', background: 'var(--color-info-bg)', borderRadius: 'var(--radius-sm)' }}>
                <span className="text-xs font-semibold text-primary" style={{ display: 'block' }}>
                  Next Recommended Action:
                </span>
                <p className="text-xs text-navy" style={{ marginTop: '2px' }}>
                  {verificationResult.next_recommended_action}
                </p>
              </div>
            )}
          </div>
        )}

        {/* ── Verification Audit History Drawer ─────────── */}
        <div style={{ marginTop: 'var(--space-4)', borderTop: '1px solid var(--color-navy-10)', paddingTop: 'var(--space-3)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <button
              className="btn-link text-xs font-semibold"
              onClick={() => setShowHistoryTab(!showHistoryTab)}
              id="toggle-verification-history-btn"
            >
              {showHistoryTab
                ? '▲ Hide Past Verification Records'
                : `▼ View Verification Audit History (${stepVerifications.length})`}
            </button>
            {loadingHistory && <span className="text-xs text-muted">Refreshing...</span>}
          </div>

          {showHistoryTab && (
            <div className="animate-fade-in" style={{ marginTop: 'var(--space-3)' }}>
              {stepVerifications.length === 0 ? (
                <p className="text-xs text-muted" style={{ fontStyle: 'italic' }}>
                  No previous verification attempts recorded for this step.
                </p>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table className="table" style={{ width: '100%', fontSize: 'var(--font-size-xs)' }}>
                    <thead>
                      <tr>
                        <th>Status</th>
                        <th>Score</th>
                        <th>Evidence Location</th>
                        <th>Commit SHA</th>
                        <th>Reassessed?</th>
                        <th>Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stepVerifications.map((rec) => {
                        const statusVal = rec.verdict || rec.verification_status || 'unverified';
                        const scoreVal = Math.round(rec.rubric_score ?? rec.score_percent ?? 0);
                        const fileVal = rec.verified_file_path || rec.evidence_file_path || 'None';
                        const shaVal = rec.commit_sha ? rec.commit_sha.slice(0, 7) : 'HEAD';
                        const reassessedVal = Boolean(rec.subsequent_assessment_id || rec.reassessment_triggered);
                        const dateVal = rec.verified_at || rec.created_at;
                        return (
                          <tr key={rec.id}>
                            <td>
                              <span
                                className={`badge text-xs ${
                                  statusVal === 'verified'
                                    ? 'badge-success'
                                    : statusVal === 'partially_demonstrated'
                                    ? 'badge-warning'
                                    : 'badge-error'
                                }`}
                              >
                                {statusVal.replace(/_/g, ' ')}
                              </span>
                            </td>
                            <td className="font-mono">{scoreVal}%</td>
                            <td className="font-mono">{fileVal}</td>
                            <td className="font-mono">{shaVal}</td>
                            <td>
                              {reassessedVal ? (
                                <span className="badge badge-success text-xs">Yes</span>
                              ) : (
                                <span className="text-muted">No</span>
                              )}
                            </td>
                            <td className="text-muted">{dateVal ? new Date(dateVal).toLocaleDateString() : 'N/A'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Stepper Navigation Footer: Previous & Next Buttons */}
      <div
        style={{
          marginTop: 'var(--space-6)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 'var(--space-3)',
        }}
      >
        <button
          className="btn btn-secondary btn-sm"
          onClick={onPrevStep}
          disabled={currentStepIndex === 0}
          id="prev-step-btn"
        >
          ← Previous Step
        </button>

        <span className="text-xs font-mono text-muted">
          Step {currentStepIndex + 1} of {totalSteps}
        </span>

        <button
          className="btn btn-secondary btn-sm"
          onClick={onNextStep}
          disabled={currentStepIndex === totalSteps - 1}
          id="next-step-btn"
        >
          Next Step →
        </button>
      </div>
    </div>
  );
}

/**
 * SkillSync Gap Solver & Learning Roadmap Component (Phase F)
 */
export function GapSolverSection({ assessment, onAssessmentUpdated }) {
  // Gaps state
  const [gaps, setGaps] = useState([]);
  const [loadingGaps, setLoadingGaps] = useState(true);
  const [gapsError, setGapsError] = useState(null);

  // Active Plan & Modal state
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [planError, setPlanError] = useState(null);
  const [planSuccessMessage, setPlanSuccessMessage] = useState(null);
  const [generatingGapId, setGeneratingGapId] = useState(null);
  const [difficultyByGap, setDifficultyByGap] = useState({});

  // Active Step Navigation (one step at a time)
  const [currentStepIndex, setCurrentStepIndex] = useState(0);

  // Bug 1: React Ref to auto-scroll generated result into visible viewport
  const planContainerRef = useRef(null);

  // Load skill gaps for current assessment
  useEffect(() => {
    let isMounted = true;
    async function fetchGaps() {
      if (!assessment?.id) return;
      setLoadingGaps(true);
      setGapsError(null);
      try {
        const res = await api.getAssessmentGaps(assessment.id);
        if (isMounted) {
          setGaps(res.gaps || res.skill_gaps || []);
          setLoadingGaps(false);
        }
      } catch (err) {
        if (isMounted) {
          if (assessment?.skill_gaps && assessment.skill_gaps.length > 0) {
            setGaps(assessment.skill_gaps);
          } else {
            setGapsError(err.message || 'Failed to load skill gaps.');
          }
          setLoadingGaps(false);
        }
      }
    }
    fetchGaps();
    return () => { isMounted = false; };
  }, [assessment?.id, assessment?.skill_gaps]);

  // Bug 1: Smoothly scroll generated learning plan result into view after render
  useEffect(() => {
    if (selectedPlan && planContainerRef.current) {
      const timer = setTimeout(() => {
        if (planContainerRef.current) {
          planContainerRef.current.scrollIntoView({
            behavior: 'smooth',
            block: 'start',
          });
        }
      }, 80);
      return () => clearTimeout(timer);
    }
  }, [selectedPlan]);

  // Open existing plan or generate new plan
  async function handleOpenOrCreatePlan(gap) {
    // Prevent duplicate submissions while generation is in progress (Bug 1)
    if (generatingGapId || loadingPlan) return;

    setPlanError(null);
    setPlanSuccessMessage(null);
    setGeneratingGapId(gap.id);
    setLoadingPlan(true);

    try {
      let plan;
      if (gap.active_plan_id) {
        plan = await api.getLearningPlan(gap.active_plan_id);
      } else {
        const difficulty = difficultyByGap[gap.id] || 'intermediate';
        plan = await api.createOrGetLearningPlan(assessment.id, gap.id, {
          difficulty_level: difficulty,
        });
        // Refresh gaps list to update active_plan_id
        try {
          const refreshed = await api.getAssessmentGaps(assessment.id);
          setGaps(refreshed.gaps || refreshed.skill_gaps || []);
        } catch {
          // non-critical gaps list refresh
        }
      }
      setSelectedPlan(plan);
      setCurrentStepIndex(0);
      // Bug 1: Display success message only after the request succeeds
      setPlanSuccessMessage(
        `Learning roadmap for "${plan.target_skill || gap.skill_name}" generated successfully! Explore your step-by-step guidance below.`
      );
    } catch (err) {
      // Bug 1: Display helpful error message if generation fails
      setPlanError(err.message || 'Failed to load or generate learning plan.');
    } finally {
      setLoadingPlan(false);
      setGeneratingGapId(null);
    }
  }

  // Reload active plan from backend
  async function reloadPlan(planId) {
    if (!planId) return;
    try {
      const plan = await api.getLearningPlan(planId);
      setSelectedPlan(plan);
    } catch (err) {
      console.error('Error reloading plan:', err);
    }
  }

  // Save Step Progress callback
  async function handleSaveStepProgress(stepId, status, userNotes, evidenceFilePath, evidenceCommitSha) {
    const updated = await api.updateStepProgress(stepId, {
      status,
      user_notes: userNotes,
      evidence_file_path: evidenceFilePath,
      evidence_commit_sha: evidenceCommitSha,
    });

    // Update local state in selectedPlan
    setSelectedPlan((prev) => {
      if (!prev) return prev;
      const newSteps = prev.steps.map((s) => (s.id === updated.id ? { ...s, ...updated } : s));
      const completedCount = newSteps.filter((s) => s.status === 'evidence_submitted' || s.status === 'completed' || s.status === 'verified').length;
      const newPercent = Math.round((completedCount / newSteps.length) * 100);
      return {
        ...prev,
        steps: newSteps,
        progress_percent: newPercent,
      };
    });
  }

  // Find matching finding limitations for a gap
  function getGapLimitations(gap) {
    const finding = assessment?.skill_findings?.find(
      (f) => f.skill_name?.toLowerCase() === gap.skill_name?.toLowerCase()
    );
    if (finding?.limitations) return finding.limitations;
    return 'Repository artifacts did not demonstrate required production patterns for this competency.';
  }

  // Get matching finding rationale
  function getGapRationale(gap) {
    const finding = assessment?.skill_findings?.find(
      (f) => f.skill_name?.toLowerCase() === gap.skill_name?.toLowerCase()
    );
    if (finding?.rationale) return finding.rationale;
    return gap.description || 'Essential competency for target job profile.';
  }

  const currentStep = selectedPlan?.steps?.[currentStepIndex] || null;

  return (
    <div className="card gap-solver-card" id="gap-solver-section">
      {/* ── Section Header ─────────────────────────────────────── */}
      <div className="gap-solver-header">
        <div className="gap-solver-title-group">
          <div className="gap-solver-badge-row">
            <span className="badge badge-primary text-xs">Close Your Skill Gaps</span>
            <span className="badge badge-outline text-xs">Evidence-Backed Coaching</span>
          </div>
          <h2 className="section-heading" style={{ marginTop: 'var(--space-2)' }}>
            Skill Gap Solver & Learning Roadmaps
          </h2>
          <p className="text-muted text-sm">
            Actionable, step-by-step roadmaps generated from your job profile requirements. Practice real
            exercises, submit code evidence, and verify your implementation with deterministic rubrics.
          </p>
        </div>
      </div>

      {/* ── Loading State ───────────────────────────────────────── */}
      {loadingGaps && (
        <div className="gap-solver-loading text-center" style={{ padding: 'var(--space-8)' }}>
          <div className="spinner-large" style={{ margin: '0 auto var(--space-3)' }} />
          <p className="text-sm font-semibold">Analyzing identified skill gaps & active roadmaps...</p>
        </div>
      )}

      {/* ── Error State ─────────────────────────────────────────── */}
      {!loadingGaps && gapsError && (
        <div className="alert alert-error" style={{ margin: 'var(--space-4) 0' }}>
          <div className="alert-icon">⚠️</div>
          <div className="alert-content">
            <strong>Unable to load skill gaps:</strong> {gapsError}
          </div>
        </div>
      )}

      {/* ── Empty State: No Gaps (All Skills Demonstrated!) ─────── */}
      {!loadingGaps && !gapsError && gaps.length === 0 && (
        <div className="gap-solver-empty-state text-center" style={{ padding: 'var(--space-8) 0' }}>
          <div style={{ fontSize: '3rem', marginBottom: 'var(--space-2)' }}>🎉</div>
          <h3 className="text-lg font-bold">No Skill Gaps Detected!</h3>
          <p className="text-muted text-sm" style={{ maxWidth: 500, margin: 'var(--space-2) auto' }}>
            Your repository demonstrates verified evidence across all identified competencies for{' '}
            <strong>{assessment?.job_profile?.title || 'the target profile'}</strong>.
          </p>
          <span className="badge badge-success text-xs" style={{ marginTop: 'var(--space-2)' }}>
            100% Competencies Addressed
          </span>
        </div>
      )}

      {/* ── Gaps List Grid ──────────────────────────────────────── */}
      {!loadingGaps && !gapsError && gaps.length > 0 && (
        <div className="gap-solver-grid" style={{ marginTop: 'var(--space-4)' }}>
          {gaps.map((gap, idx) => {
            const limitations = getGapLimitations(gap);
            const rationale = getGapRationale(gap);
            const isGenerating = generatingGapId === gap.id;
            const hasPlan = Boolean(gap.active_plan_id || gap.has_active_plan);
            const selectedDiff = difficultyByGap[gap.id] || 'intermediate';

            return (
              <div key={gap.id || idx} className="gap-card card" id={`gap-card-${gap.id}`}>
                <div className="gap-card-header">
                  <div className="gap-card-priority-badge">
                    #{gap.priority || idx + 1} Priority
                  </div>
                  <div className="gap-card-tags">
                    {gap.category && (
                      <span className="badge badge-outline text-xs">{gap.category}</span>
                    )}
                    <span
                      className={`badge text-xs ${
                        gap.gap_severity === 'missing' ? 'badge-error' : 'badge-warning'
                      }`}
                    >
                      {gap.gap_severity === 'missing' ? 'Not Found in Repo' : 'Partially Demonstrated'}
                    </span>
                  </div>
                </div>

                <h3 className="gap-card-title text-base font-bold" style={{ marginTop: 'var(--space-2)' }}>
                  {gap.skill_name}
                </h3>

                {/* Job Relevance & Requirement Rationale */}
                <div className="gap-card-section" style={{ marginTop: 'var(--space-2)' }}>
                  <span className="text-xs font-semibold text-navy" style={{ display: 'block' }}>
                    Job Relevance & Rationale:
                  </span>
                  <p className="text-xs text-muted" style={{ marginTop: '2px' }}>
                    {rationale}
                  </p>
                </div>

                {/* Evidence Limitations */}
                <div className="gap-card-section gap-limitations-box" style={{ marginTop: 'var(--space-2)' }}>
                  <span className="text-xs font-semibold text-error" style={{ display: 'block' }}>
                    Evidence Limitations:
                  </span>
                  <p className="text-xs text-muted" style={{ marginTop: '2px' }}>
                    {limitations}
                  </p>
                  <p className="text-xs text-muted" style={{ marginTop: '4px', fontStyle: 'italic', fontSize: '11px' }}>
                    *Note: Reflects repository scope limitations observed during code analysis, not a personal capability deficit.
                  </p>
                </div>

                {/* Plan Progress or Generator Footer */}
                <div className="gap-card-footer" style={{ marginTop: 'var(--space-4)' }}>
                  {hasPlan ? (
                    <div className="gap-plan-status-box">
                      <div className="gap-plan-status-top">
                        <span className="badge badge-success text-xs">
                          {gap.active_plan_status ? gap.active_plan_status.replace(/_/g, ' ') : 'Roadmap Active'}
                        </span>
                        {gap.active_plan_progress_percent !== undefined && (
                          <span className="text-xs font-mono font-semibold">
                            {Math.round(gap.active_plan_progress_percent)}% Done
                          </span>
                        )}
                      </div>
                      <button
                        className="btn btn-primary btn-sm btn-full"
                        style={{ marginTop: 'var(--space-2)' }}
                        onClick={() => handleOpenOrCreatePlan(gap)}
                        disabled={isGenerating || Boolean(generatingGapId)}
                        id={`open-plan-btn-${gap.id}`}
                      >
                        {isGenerating ? (
                          <>
                            <span className="spinner-small" style={{ marginRight: '6px' }} />
                            Loading Roadmap...
                          </>
                        ) : (
                          'Continue Learning Plan →'
                        )}
                      </button>
                    </div>
                  ) : (
                    <div className="gap-plan-generate-box">
                      <div className="gap-difficulty-select-row" style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
                        <select
                          className="form-select form-select-sm"
                          value={selectedDiff}
                          onChange={(e) =>
                            setDifficultyByGap((prev) => ({
                              ...prev,
                              [gap.id]: e.target.value,
                            }))
                          }
                          disabled={Boolean(generatingGapId)}
                          aria-label="Select learning roadmap difficulty"
                        >
                          <option value="beginner">Beginner Level</option>
                          <option value="intermediate">Intermediate Level</option>
                          <option value="advanced">Advanced Level</option>
                        </select>
                      </div>
                      <button
                        className="btn btn-gradient btn-sm btn-full"
                        onClick={() => handleOpenOrCreatePlan(gap)}
                        disabled={isGenerating || Boolean(generatingGapId)}
                        id={`generate-plan-btn-${gap.id}`}
                      >
                        {isGenerating ? (
                          <>
                            <span className="spinner-small" style={{ marginRight: '6px' }} />
                            Generating Learning Plan...
                          </>
                        ) : (
                          '🚀 Generate Learning Plan'
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Active Learning Plan Result Container (Bug 1: In-Page Auto-Scrolled View) ── */}
      {(loadingPlan || selectedPlan || planError) && (
        <section
          ref={planContainerRef}
          id="active-learning-plan-section"
          className="card gap-plan-container animate-fade-in"
          aria-label={selectedPlan ? `Learning plan for ${selectedPlan.target_skill}` : 'Learning roadmap'}
          style={{
            marginTop: 'var(--space-6)',
            border: '1.5px solid var(--color-primary-light)',
            borderRadius: 'var(--radius-lg)',
            background: 'var(--color-white)',
            padding: 'var(--space-6)',
            boxShadow: 'var(--shadow-md)',
            scrollMarginTop: 'calc(var(--navbar-height, 64px) + 24px)',
          }}
        >
          {/* Header */}
          <div className="gap-plan-top-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                <span className="badge badge-primary text-xs">
                  Target Skill: <strong>{selectedPlan?.target_skill || 'Remediation'}</strong>
                </span>
                <span className="badge badge-outline text-xs" style={{ textTransform: 'capitalize' }}>
                  {selectedPlan?.difficulty_level || 'Intermediate'}
                </span>
                <span className="badge badge-success text-xs">
                  Status: {selectedPlan?.status?.replace(/_/g, ' ') || 'Active'}
                </span>
              </div>
              <h2 className="text-2xl font-bold" style={{ marginTop: 'var(--space-2)' }}>
                {selectedPlan?.title || 'Learning Roadmap'}
              </h2>
            </div>

            {selectedPlan && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setSelectedPlan(null)}
                aria-label="Close roadmap view"
                id="close-plan-section-btn"
              >
                ✕ Close Roadmap
              </button>
            )}
          </div>

          {/* Success Banner (Bug 1: Shown only after successful generation) */}
          {planSuccessMessage && (
            <div
              className="alert alert-success animate-fade-in"
              style={{ marginTop: 'var(--space-4)', padding: 'var(--space-3)' }}
              id="plan-generation-success-alert"
              role="status"
            >
              <div className="alert-icon">✓</div>
              <div className="alert-content">
                <strong>Success!</strong> {planSuccessMessage}
              </div>
            </div>
          )}

          {/* Loading Indicator inside container if still running */}
          {loadingPlan && (
            <div className="text-center" style={{ padding: 'var(--space-8)' }} id="plan-generation-loading-indicator">
              <div className="spinner-large" style={{ margin: '0 auto var(--space-4)' }} />
              <h3 className="text-lg font-semibold">Generating Your Structured Learning Plan...</h3>
              <p className="text-muted text-sm" style={{ maxWidth: 540, margin: 'var(--space-2) auto 0' }}>
                Synthesizing repository scope limitations, official documentation, hands-on exercises,
                and acceptance criteria.
              </p>
            </div>
          )}

          {/* Error Banner (Bug 1) */}
          {planError && (
            <div
              className="alert alert-error animate-fade-in"
              style={{ marginTop: 'var(--space-4)' }}
              id="plan-generation-error-alert"
              role="alert"
            >
              <div className="alert-icon">⚠️</div>
              <div className="alert-content">
                <strong>Plan Generation Failed:</strong> {planError}
              </div>
            </div>
          )}

          {/* Plan Body */}
          {!loadingPlan && selectedPlan && (
            <div className="gap-plan-body" style={{ marginTop: 'var(--space-4)' }}>
              {/* ── Effort Estimate & Overview Banner ───────────── */}
              <div
                className="card"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-navy-10)',
                  padding: 'var(--space-4)',
                  marginBottom: 'var(--space-4)',
                }}
              >
                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-2)' }}>
                  {/* Explicitly labeled effort estimate */}
                  <div className="effort-estimate-badge" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                    <span style={{ fontSize: '1.25rem' }}>⏱️</span>
                    <div>
                      <span className="text-xs text-muted" style={{ display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Estimated Effort (Estimate Only)
                      </span>
                      <span className="text-sm font-bold text-navy">
                        ~{selectedPlan.estimated_hours || 3.0} Hours{' '}
                        <span className="text-xs text-muted font-normal">
                          (Subject to prior familiarity; not a strict timeline)
                        </span>
                      </span>
                    </div>
                  </div>

                  {/* Overall Progress */}
                  <div style={{ minWidth: 160 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--font-size-xs)', marginBottom: '4px' }}>
                      <span className="font-semibold text-muted">Plan Progress</span>
                      <span className="font-mono font-bold text-primary">{Math.round(selectedPlan.progress_percent || 0)}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: 6 }}>
                      <div
                        className="progress-bar-fill"
                        style={{ width: `${Math.min(100, selectedPlan.progress_percent || 0)}%` }}
                      />
                    </div>
                  </div>
                </div>

                <p className="text-xs text-muted" style={{ marginTop: 'var(--space-3)' }}>
                  {selectedPlan.overview}
                </p>

                {/* Scope Limitation Notice */}
                {selectedPlan.scope_limitations && (
                  <div
                    style={{
                      marginTop: 'var(--space-3)',
                      padding: 'var(--space-2) var(--space-3)',
                      background: 'var(--color-info-bg)',
                      borderLeft: '3px solid var(--color-primary)',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: 'var(--font-size-xs)',
                      color: 'var(--color-navy-80)',
                    }}
                  >
                    <strong>Scope Limitation Context:</strong> {selectedPlan.scope_limitations}
                  </div>
                )}

                {/* Prerequisites & Canonical Official Resources */}
                <div style={{ marginTop: 'var(--space-4)', display: 'flex', flexWrap: 'wrap', gap: 'var(--space-6)' }}>
                  {/* Prerequisites */}
                  {selectedPlan.prerequisites && selectedPlan.prerequisites.length > 0 && (
                    <div style={{ flex: 1, minWidth: 200 }}>
                      <span className="text-xs font-semibold text-navy" style={{ display: 'block', marginBottom: '4px' }}>
                        Prerequisites:
                      </span>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                        {selectedPlan.prerequisites.map((req, rIdx) => (
                          <span key={rIdx} className="badge badge-outline text-xs">
                            {req}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Official Canonical Resources */}
                  {selectedPlan.canonical_resources && selectedPlan.canonical_resources.length > 0 && (
                    <div style={{ flex: 1.5, minWidth: 250 }}>
                      <span className="text-xs font-semibold text-navy" style={{ display: 'block', marginBottom: '4px' }}>
                        Verified Official Resources:
                      </span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        {selectedPlan.canonical_resources.map((res, cIdx) => (
                          <a
                            key={cIdx}
                            href={res.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-primary font-medium"
                            style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                            id={`resource-link-${cIdx}`}
                          >
                            <span>↗ {res.title}</span>
                            <span className="text-muted" style={{ fontSize: '11px' }}>
                              ({res.resource_type || 'docs'})
                            </span>
                          </a>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* ── Stepper Navigation Tabs (One Step at a Time) ── */}
              <div className="gap-stepper-container" style={{ marginBottom: 'var(--space-4)' }}>
                <div className="gap-stepper-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2)' }}>
                  <span className="text-xs font-semibold text-muted text-uppercase">
                    Learning Steps (Navigate Step-by-Step)
                  </span>
                  <span className="text-xs font-mono font-bold text-navy">
                    Step {currentStepIndex + 1} of {selectedPlan.steps?.length || 0}
                  </span>
                </div>

                <div className="gap-steps-nav" style={{ display: 'flex', gap: 'var(--space-2)', overflowX: 'auto', paddingBottom: 'var(--space-2)' }}>
                  {selectedPlan.steps?.map((step, sIdx) => {
                    const isActive = sIdx === currentStepIndex;
                    let badgeClass = 'badge-secondary';
                    let statusIcon = '○';

                    if (step.status === 'verified') {
                      badgeClass = 'badge-success';
                      statusIcon = '✓';
                    } else if (step.status === 'evidence_submitted' || step.status === 'completed') {
                      badgeClass = 'badge-primary';
                      statusIcon = '✓';
                    } else if (step.status === 'in_progress') {
                      badgeClass = 'badge-warning';
                      statusIcon = '●';
                    } else if (step.status === 'failed_verification') {
                      badgeClass = 'badge-error';
                      statusIcon = '⚠';
                    }

                    return (
                      <button
                        key={step.id || sIdx}
                        className={`btn ${isActive ? 'btn-primary' : 'btn-ghost'} btn-sm gap-step-btn`}
                        onClick={() => setCurrentStepIndex(sIdx)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 'var(--space-2)',
                          borderRadius: 'var(--radius-lg)',
                          padding: 'var(--space-2) var(--space-4)',
                          border: isActive ? '1.5px solid var(--color-primary)' : '1px solid var(--color-navy-10)',
                          background: isActive ? 'var(--color-info-bg)' : 'var(--color-white)',
                          color: isActive ? 'var(--color-primary-dark)' : 'var(--color-navy)',
                        }}
                        id={`step-tab-${step.step_number || sIdx + 1}`}
                      >
                        <span style={{ fontWeight: 'bold' }}>{statusIcon} Step {step.step_number || sIdx + 1}</span>
                        <span
                          className={`badge ${badgeClass} text-xs`}
                          style={{ padding: '2px 6px', fontSize: '10px' }}
                        >
                          {step.status?.replace(/_/g, ' ')}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* ── Active Step Detailed Workspace ─────────────── */}
              {currentStep && (
                <StepWorkspace
                  key={currentStep.id}
                  step={currentStep}
                  assessmentCommitSha={assessment?.commit_sha ? assessment.commit_sha.slice(0, 7) : ''}
                  onSaveProgress={handleSaveStepProgress}
                  onReloadPlan={() => reloadPlan(selectedPlan.id)}
                  onAssessmentUpdated={onAssessmentUpdated}
                  currentStepIndex={currentStepIndex}
                  totalSteps={selectedPlan.steps?.length || 1}
                  onPrevStep={() => setCurrentStepIndex((prev) => Math.max(0, prev - 1))}
                  onNextStep={() => setCurrentStepIndex((prev) => Math.min((selectedPlan.steps?.length || 1) - 1, prev + 1))}
                />
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
