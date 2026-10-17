/**
 * SkillSync Frontend API Client
 * Connects to the local FastAPI backend proxy at /api.
 */

// Resolve API base URL:
// - If VITE_API_BASE_URL is configured (e.g. https://skillsync-rfrh.onrender.com or with /api), ensure /api suffix
// - If in production (non-localhost) and not configured, default to the live Render backend (/api)
// - If local development, default to relative /api (handled by Vite proxy)
function resolveBaseUrl() {
  const envUrl = (import.meta.env.VITE_API_BASE_URL || '').trim();
  if (envUrl) {
    const stripped = envUrl.replace(/\/+$/, '');
    return stripped.endsWith('/api') ? stripped : `${stripped}/api`;
  }
  if (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return 'https://skillsync-rfrh.onrender.com/api';
  }
  return '/api';
}
const BASE_URL = resolveBaseUrl();

async function handleResponse(response) {
  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        if (typeof errJson.detail === 'string') {
          errorDetail = errJson.detail;
        } else if (Array.isArray(errJson.detail)) {
          errorDetail = errJson.detail.map(e => e.msg || e.message || JSON.stringify(e)).join(', ');
        } else {
          errorDetail = JSON.stringify(errJson.detail);
        }
      } else if (errJson.message) {
        errorDetail = errJson.message;
      }
    } catch {
      // response was not JSON
    }
    const err = new Error(errorDetail);
    err.status = response.status;
    throw err;
  }
  return response.json();
}

export const api = {
  // System
  async getHealth() {
    const res = await fetch(`${BASE_URL}/health`);
    return handleResponse(res);
  },

  async getVersion() {
    const res = await fetch(`${BASE_URL}/version`);
    return handleResponse(res);
  },

  // Repositories
  async validateRepository(url) {
    const res = await fetch(`${BASE_URL}/repositories/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ github_url: url, repository_url: url }),
    });
    return handleResponse(res);
  },

  async getRepositories(skip = 0, limit = 50) {
    const res = await fetch(`${BASE_URL}/repositories?skip=${skip}&limit=${limit}`);
    return handleResponse(res);
  },

  async getRepository(id) {
    const res = await fetch(`${BASE_URL}/repositories/${id}`);
    return handleResponse(res);
  },

  async createRepository(data) {
    const payload = typeof data === 'string'
      ? { github_url: data }
      : {
          github_url: data.github_url || (data.github_owner && data.repo_name ? `https://github.com/${data.github_owner}/${data.repo_name}` : undefined),
          ...data,
        };
    const res = await fetch(`${BASE_URL}/repositories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  },

  // Job Profiles
  async extractSkills(job_title, job_description) {
    const res = await fetch(`${BASE_URL}/job-profiles/extract-skills`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_title, job_description }),
    });
    return handleResponse(res);
  },

  async getJobProfiles(skip = 0, limit = 50) {
    const res = await fetch(`${BASE_URL}/job-profiles?skip=${skip}&limit=${limit}`);
    return handleResponse(res);
  },

  async getJobProfile(id) {
    const res = await fetch(`${BASE_URL}/job-profiles/${id}`);
    return handleResponse(res);
  },

  async createJobProfile(data) {
    const res = await fetch(`${BASE_URL}/job-profiles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return handleResponse(res);
  },

  // Assessments
  async triggerAssessment(payload) {
    const res = await fetch(`${BASE_URL}/assessments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  },

  async getAssessments(skip = 0, limit = 50) {
    const res = await fetch(`${BASE_URL}/assessments?skip=${skip}&limit=${limit}`);
    return handleResponse(res);
  },

  async getAssessment(id) {
    const res = await fetch(`${BASE_URL}/assessments/${id}`);
    return handleResponse(res);
  },

  async getAssessmentSkills(id) {
    const res = await fetch(`${BASE_URL}/assessments/${id}/skills`);
    return handleResponse(res);
  },

  async getRepositoryAssessments(repoId, skip = 0, limit = 50) {
    const res = await fetch(`${BASE_URL}/repositories/${repoId}/assessments?skip=${skip}&limit=${limit}`);
    return handleResponse(res);
  },

  // Webhooks & Live Synchronization
  async getRepositorySyncStatus(repoId) {
    const res = await fetch(`${BASE_URL}/repositories/${repoId}/sync-status`);
    return handleResponse(res);
  },

  async triggerRepositorySync(repoId) {
    const res = await fetch(`${BASE_URL}/repositories/${repoId}/sync`, {
      method: 'POST',
    });
    return handleResponse(res);
  },

  async getWebhookDeliveries(limit = 20) {
    const res = await fetch(`${BASE_URL}/webhooks/deliveries?limit=${limit}`);
    return handleResponse(res);
  },

  subscribeToEvents(onEvent, onError) {
    const eventSource = new EventSource(`${BASE_URL}/events`);

    const handleMsg = (e) => {
      try {
        const parsed = JSON.parse(e.data);
        if (onEvent) onEvent(parsed);
      } catch {
        // non-JSON message
      }
    };

    eventSource.addEventListener('connected', handleMsg);
    eventSource.addEventListener('sync_started', handleMsg);
    eventSource.addEventListener('sync_progress', handleMsg);
    eventSource.addEventListener('assessment_completed', handleMsg);
    eventSource.addEventListener('sync_completed', handleMsg);

    eventSource.onerror = (err) => {
      if (onError) onError(err);
    };

    return eventSource;
  },

  // Gap Solver & Learning Plans (Phases C, D, E)
  async getAssessmentGaps(assessmentId) {
    const res = await fetch(`${BASE_URL}/assessments/${assessmentId}/gaps`);
    return handleResponse(res);
  },

  async createOrGetLearningPlan(assessmentId, gapId, payload = {}) {
    const res = await fetch(`${BASE_URL}/assessments/${assessmentId}/gaps/${gapId}/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  },

  async getLearningPlan(planId) {
    const res = await fetch(`${BASE_URL}/gaps/plans/${planId}`);
    return handleResponse(res);
  },

  async updateStepProgress(stepId, payload) {
    const res = await fetch(`${BASE_URL}/gaps/plans/steps/${stepId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  },

  async verifyStepEvidence(stepId, payload) {
    const res = await fetch(`${BASE_URL}/gaps/plans/steps/${stepId}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  },

  async getStepVerifications(stepId) {
    const res = await fetch(`${BASE_URL}/gaps/plans/steps/${stepId}/verifications`);
    return handleResponse(res);
  },

  async getVerificationRecord(verificationId) {
    const res = await fetch(`${BASE_URL}/gaps/verifications/${verificationId}`);
    return handleResponse(res);
  },
};
