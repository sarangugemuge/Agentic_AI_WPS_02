# SkillSync — API Contract Documentation (Phase 3)

This document specifies the REST API contracts, request/response models, error handling, status codes, and assessment orchestration implemented in **Phase 3 — Backend API**.

---

## 1. Overview & Interactive Documentation

- **Base URL:** `http://localhost:8000/api`
- **Interactive Swagger UI:** `http://localhost:8000/docs`
- **ReDoc Documentation:** `http://localhost:8000/redoc`
- **Database:** Local SQLite via async SQLAlchemy (`sqlite+aiosqlite:///./skillsync.db`)
- **Active Test Doubles:** Clearly separated `MockGitHubService` and `MockAIService` in `app/services/` (preparing for real GitHub API in Phase 4 and Gemini AI in Phase 5).

---

## 2. Standard Error Response Schema

All domain exceptions and validation failures return consistent JSON envelopes:

```json
{
  "detail": "Description of the error",
  "error_code": "ERROR_CODE_IDENTIFIER",
  "status_code": 404,
  "details": null
}
```

### Standard Error Codes

| Status Code | Error Code | Description |
| :--- | :--- | :--- |
| **404 Not Found** | `NOT_FOUND` | The requested entity (Repository, Assessment, JobProfile) does not exist |
| **409 Conflict** | `CONFLICT` | Resource conflict or duplicate state |
| **422 Unprocessable Content** | `VALIDATION_ERROR` / `UNPROCESSABLE_ENTITY` | Input validation failure (malformed URL, missing required fields) |
| **503 Service Unavailable** | `SERVICE_UNAVAILABLE` | External dependency (GitHub, AI engine) timed out or is unreachable |
| **500 Server Error** | `INTERNAL_SERVER_ERROR` | Uncaught server exception |

---

## 3. System & Monitoring Endpoints

### `GET /api/health`
Health check for frontend connection and infrastructure probes.

- **Response:** `200 OK`
```json
{
  "status": "ok",
  "service": "skillsync-api",
  "version": "0.1.0",
  "environment": "development"
}
```

### `GET /api/version`
Service version and phase status information.

- **Response:** `200 OK`
```json
{
  "api_version": "0.1.0",
  "phase": "Phase 3 — Backend API",
  "service": "skillsync-api",
  "test_doubles_active": true
}
```

---

## 4. Repository Endpoints

### `POST /api/repositories/validate`
Validates whether a GitHub repository URL is properly formatted and accessible without saving it.

- **Request Body:**
```json
{
  "github_url": "https://github.com/fastapi/fastapi"
}
```
- **Response:** `200 OK`
```json
{
  "valid": true,
  "owner": "fastapi",
  "repo": "fastapi",
  "default_branch": "main",
  "message": "Repository 'fastapi/fastapi' is valid and accessible.",
  "is_accessible": true
}
```

### `POST /api/repositories`
Registers or updates a GitHub repository for tracking.

- **Request Body:**
```json
{
  "github_url": "https://github.com/octocat/Hello-World"
}
```
- **Response:** `201 Created`
```json
{
  "id": 1,
  "github_owner": "octocat",
  "repo_name": "Hello-World",
  "full_name": "octocat/Hello-World",
  "default_branch": "main",
  "latest_commit_sha": "a1b2c3d4e5f678901234567890abcdef12345678",
  "description": "Repository for Hello-World by octocat",
  "language": "Python",
  "created_at": "2026-10-16T18:00:00Z",
  "updated_at": "2026-10-16T18:00:00Z"
}
```

### `GET /api/repositories`
Lists all tracked repositories with pagination.

- **Query Parameters:** `skip` (default: 0), `limit` (default: 50)
- **Response:** `200 OK`
```json
{
  "repositories": [ ... ],
  "total": 1
}
```

### `GET /api/repositories/{repository_id}`
Retrieves repository metadata by ID.

- **Response:** `200 OK` or `404 Not Found`

### `DELETE /api/repositories/{repository_id}`
Deletes a tracked repository and its associated assessments.

- **Response:** `204 No Content`

---

## 5. Job Profile Endpoints

### `POST /api/job-profiles/extract-skills`
Previews extracted skills from raw job text without creating a database record.

- **Request Body:**
```json
{
  "job_title": "Senior Python Backend Developer",
  "job_description": "We need experience with Python, FastAPI, Docker, and PostgreSQL."
}
```
- **Response:** `200 OK`
```json
{
  "job_title": "Senior Python Backend Developer",
  "extracted_skills": ["Python", "FastAPI", "Docker", "PostgreSQL"],
  "skill_count": 4
}
```

### `POST /api/job-profiles`
Parses job description text, extracts required skills, and persists the profile.

- **Request Body:**
```json
{
  "title": "Backend Architect",
  "raw_description": "Experience in Python, FastAPI, and SQLAlchemy required.",
  "company_context": "Acme Corp"
}
```
- **Response:** `201 Created`
```json
{
  "id": 1,
  "title": "Backend Architect",
  "company_context": "Acme Corp",
  "raw_description": "Experience in Python, FastAPI, and SQLAlchemy required.",
  "extracted_skills": ["Python", "FastAPI", "SQLAlchemy"],
  "created_at": "2026-10-16T18:00:00Z"
}
```

### `GET /api/job-profiles` & `GET /api/job-profiles/{job_profile_id}`
List and retrieve job profiles.

---

## 6. Assessment Orchestration Endpoints

The assessment pipeline runs an explicit 7-step orchestrator:
1. **Validate Input:** Verifies repository exists and validates job requirements.
2. **Analyze Requirements:** Extracts key skills and competencies.
3. **Obtain Repository Evidence:** Fetches source code tree and artifacts.
4. **Compare Skills:** Matches repository evidence against required skills.
5. **Validate Results:** Enforces score bounds (0-100) and confidence tier sanity.
6. **Persist Results:** Atomically stores `Assessment`, `SkillFinding`, and `EvidenceCitation` rows.
7. **Return Assessment:** Loads relationships and returns complete structured response.

### `POST /api/assessments`
Triggers an assessment. Accepts either `job_profile_id` OR inline `job_title` + `job_description`.

- **Request Body (Inline Job Profile):**
```json
{
  "repository_id": 1,
  "job_title": "Backend Systems Architect",
  "job_description": "Requirements: Python, FastAPI, database design with SQLAlchemy, testing with pytest, REST API design.",
  "company_context": "TechGrowth Inc."
}
```
- **Response:** `201 Created`
```json
{
  "id": 1,
  "repository_id": 1,
  "job_profile_id": 1,
  "commit_sha": "a1b2c3d4e5f678901234567890abcdef12345678",
  "overall_score": 100.0,
  "summary": "Assessment completed against 5 required skills. Demonstrated 5/5 skills with verifiable code evidence. Overall competency match: 100.0%.",
  "trigger_event": "manual",
  "status": "completed",
  "error_message": null,
  "created_at": "2026-10-16T18:00:00Z",
  "job_profile": { ... },
  "skill_findings": [
    {
      "id": 1,
      "skill_name": "FastAPI",
      "category": "Web Frameworks",
      "status": "demonstrated",
      "confidence_score": 0.92,
      "rationale": "Strong repository evidence found for FastAPI across source files.",
      "evidence_citations": [
        {
          "id": 1,
          "file_path": "backend/app/main.py",
          "start_line": 1,
          "end_line": 15,
          "commit_sha": "a1b2c3d4e5f678901234567890abcdef12345678",
          "code_snippet": "from fastapi import FastAPI\napp = FastAPI()",
          "context_explanation": "Implementation of FastAPI demonstrated in backend/app/main.py."
        }
      ]
    }
  ]
}
```

### `GET /api/assessments/{assessment_id}`
Returns full assessment details, findings, and citations.

### `GET /api/assessments/{assessment_id}/skills`
Returns the list of skill findings for an assessment.

### `GET /api/assessments/{assessment_id}/skills/{skill_id}/evidence`
Returns code citations for a specific skill finding.

### `GET /api/repositories/{repository_id}/assessments`
Returns assessment history for a specific repository.

---

## 7. Automated Testing

To run the automated test suite without external dependencies:

```bash
cd backend
.venv\Scripts\python.exe -m app.tests.run_tests
```

13 test suites verify:
- Health check & version endpoints
- Swagger OpenAPI documentation endpoint availability
- Repository validation (valid, invalid URL, nonexistent)
- Repository CRUD operations
- Job Profile creation & skill preview
- 7-step Assessment Orchestrator execution
- Skill findings and file-level evidence citations
- Repository assessment history
- Validation error handling (`HTTP 422`)
- Graceful external service timeout & failure handling (`HTTP 503`)
