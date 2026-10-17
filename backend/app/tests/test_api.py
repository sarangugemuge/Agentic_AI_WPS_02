try:
    import pytest
except ImportError:
    class _MockPytest:
        class mark:
            @staticmethod
            def asyncio(fn):
                return fn
    pytest = _MockPytest()

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Health endpoint returns 200 OK and expected structure."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "skillsync-api"
    assert "version" in data


@pytest.mark.asyncio
async def test_version_info(client: AsyncClient):
    """Version endpoint returns Phase 3 status and active test double mode."""
    response = await client.get("/api/version")
    assert response.status_code == 200
    data = response.json()
    assert data["phase"] == "Phase 3 — Backend API"
    assert data["test_doubles_active"] is True


@pytest.mark.asyncio
async def test_openapi_docs_available(client: AsyncClient):
    """FastAPI Swagger documentation endpoint is accessible."""
    response = await client.get("/docs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_repository_validation_valid(client: AsyncClient):
    """Valid repository URL should return valid=True."""
    response = await client.post(
        "/api/repositories/validate",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["owner"] == "octocat"
    assert data["repo"] == "Hello-World"
    assert data["is_accessible"] is True


@pytest.mark.asyncio
async def test_repository_validation_invalid_url(client: AsyncClient):
    """Invalid URL format returns 422 validation error."""
    response = await client.post(
        "/api/repositories/validate",
        json={"github_url": "not-a-valid-url"},
    )
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    assert data["error_code"] in ["UNPROCESSABLE_ENTITY", "VALIDATION_ERROR"]


@pytest.mark.asyncio
async def test_repository_validation_nonexistent(client: AsyncClient):
    """Nonexistent repository URL returns valid=False and accessible=False."""
    response = await client.post(
        "/api/repositories/validate",
        json={"github_url": "https://github.com/nonexistent/not-found-repo"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["is_accessible"] is False


@pytest.mark.asyncio
async def test_repository_crud_flow(client: AsyncClient):
    """Test full repository creation, retrieval, listing, and deletion."""
    # 1. Create repository
    create_res = await client.post(
        "/api/repositories",
        json={"github_url": "https://github.com/fastapi/fastapi"},
    )
    assert create_res.status_code == 201
    repo_data = create_res.json()
    repo_id = repo_data["id"]
    assert repo_data["github_owner"] == "fastapi"
    assert repo_data["repo_name"] == "fastapi"
    assert repo_data["full_name"] == "fastapi/fastapi"
    assert repo_data["default_branch"] == "main"

    # 2. Retrieve repository by ID
    get_res = await client.get(f"/api/repositories/{repo_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == repo_id

    # 3. List repositories
    list_res = await client.get("/api/repositories")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(r["id"] == repo_id for r in list_data["repositories"])

    # 4. Delete repository
    del_res = await client.delete(f"/api/repositories/{repo_id}")
    assert del_res.status_code == 204

    # 5. Verify 404 after deletion
    not_found_res = await client.get(f"/api/repositories/{repo_id}")
    assert not_found_res.status_code == 404
    assert not_found_res.json()["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_job_profile_skill_extraction_preview(client: AsyncClient):
    """Test previewing extracted skills from a raw job description."""
    payload = {
        "job_title": "Senior Python Backend Developer",
        "job_description": (
            "We are looking for a senior Python backend developer with strong FastAPI, "
            "SQLAlchemy, PostgreSQL, and Docker experience. Must write pytest tests."
        ),
    }
    response = await client.post("/api/job-profiles/extract-skills", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["job_title"] == payload["job_title"]
    assert "FastAPI" in data["extracted_skills"]
    assert "Python" in data["extracted_skills"]
    assert data["skill_count"] > 0


@pytest.mark.asyncio
async def test_job_profile_crud(client: AsyncClient):
    """Create, retrieve, and list job profiles."""
    payload = {
        "title": "Full Stack Engineer",
        "raw_description": (
            "Seeking a Full Stack Engineer experienced with React, Python, REST API design, "
            "and Docker container deployment in modern cloud environments."
        ),
        "company_context": "InnovateCorp",
    }
    create_res = await client.post("/api/job-profiles", json=payload)
    assert create_res.status_code == 201
    profile = create_res.json()
    profile_id = profile["id"]
    assert profile["title"] == payload["title"]
    assert len(profile["extracted_skills"]) > 0

    get_res = await client.get(f"/api/job-profiles/{profile_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == profile_id

    list_res = await client.get("/api/job-profiles")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1


@pytest.mark.asyncio
async def test_assessment_orchestrator_pipeline(client: AsyncClient):
    """
    Test the full 7-step assessment orchestrator:
    Validate input -> Analyze requirements -> Obtain repo evidence ->
    Compare skills -> Validate results -> Persist results -> Return assessment
    """
    # 1. Register a repository first
    repo_res = await client.post(
        "/api/repositories",
        json={"github_url": "https://github.com/myorg/skillsync-project"},
    )
    assert repo_res.status_code == 201
    repo_id = repo_res.json()["id"]

    # 2. Trigger an assessment with inline job details
    assess_payload = {
        "repository_id": repo_id,
        "job_title": "Backend Systems Architect",
        "job_description": (
            "Requirements: Strong background in Python, FastAPI, database design with SQLAlchemy, "
            "unit and integration testing using pytest, REST API architecture, and Docker."
        ),
        "company_context": "TechGrowth Inc.",
    }
    assess_res = await client.post("/api/assessments", json=assess_payload)
    assert assess_res.status_code == 201
    assessment = assess_res.json()
    assessment_id = assessment["id"]

    # Verify assessment structure and orchestrator results
    assert assessment["repository_id"] == repo_id
    assert assessment["status"] == "completed"
    assert assessment["overall_score"] is not None
    assert assessment["overall_score"] > 0
    assert "Assessment completed" in assessment["summary"]
    assert len(assessment["skill_findings"]) > 0

    # Verify skill findings and evidence citations
    fastapi_finding = next(
        (f for f in assessment["skill_findings"] if f["skill_name"] == "FastAPI"), None
    )
    assert fastapi_finding is not None
    assert fastapi_finding["status"] == "demonstrated"
    assert fastapi_finding["confidence_score"] > 0.8
    assert len(fastapi_finding["evidence_citations"]) > 0

    citation = fastapi_finding["evidence_citations"][0]
    assert citation["file_path"] is not None
    assert citation["start_line"] is not None
    assert citation["end_line"] is not None

    # 3. Retrieve assessment via GET /api/assessments/{id}
    fetch_res = await client.get(f"/api/assessments/{assessment_id}")
    assert fetch_res.status_code == 200
    assert fetch_res.json()["id"] == assessment_id

    # 4. Retrieve skill findings via GET /api/assessments/{id}/skills
    skills_res = await client.get(f"/api/assessments/{assessment_id}/skills")
    assert skills_res.status_code == 200
    assert len(skills_res.json()) == len(assessment["skill_findings"])

    # 5. Retrieve specific skill evidence via GET /api/assessments/{id}/skills/{skill_id}/evidence
    skill_id = fastapi_finding["id"]
    evidence_res = await client.get(f"/api/assessments/{assessment_id}/skills/{skill_id}/evidence")
    assert evidence_res.status_code == 200
    assert len(evidence_res.json()) > 0

    # 6. Retrieve repository assessment history via GET /api/repositories/{id}/assessments
    history_res = await client.get(f"/api/repositories/{repo_id}/assessments")
    assert history_res.status_code == 200
    history_data = history_res.json()
    assert history_data["total"] >= 1
    assert any(a["id"] == assessment_id for a in history_data["assessments"])


@pytest.mark.asyncio
async def test_assessment_validation_errors(client: AsyncClient):
    """Test assessment triggers with invalid repository or missing job info."""
    # Nonexistent repo ID
    res1 = await client.post(
        "/api/assessments",
        json={
            "repository_id": 99999,
            "job_title": "Engineer",
            "job_description": "Valid job description text with sufficient length for testing requirements.",
        },
    )
    assert res1.status_code == 404
    assert res1.json()["error_code"] == "NOT_FOUND"

    # Missing both job_profile_id and job description text
    res2 = await client.post(
        "/api/assessments",
        json={"repository_id": 1},
    )
    assert res2.status_code == 422
    assert res2.json()["error_code"] in ["VALIDATION_ERROR", "UNPROCESSABLE_ENTITY"]


@pytest.mark.asyncio
async def test_github_service_unavailable_handling(client: AsyncClient):
    """When GitHub service fails or times out, return 503 Service Unavailable."""
    from app.main import app
    from app.services.github_service import MockGitHubService
    from app.services.repository_service import RepositoryService, get_repository_service

    failing_github = MockGitHubService(simulate_timeout=True)
    failing_service = RepositoryService(github_service=failing_github)
    app.dependency_overrides[get_repository_service] = lambda: failing_service
    try:
        response = await client.post(
            "/api/repositories/validate",
            json={"github_url": "https://github.com/octocat/Hello-World"},
        )
        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "SERVICE_UNAVAILABLE"
    finally:
        app.dependency_overrides.pop(get_repository_service, None)


@pytest.mark.asyncio
async def test_ai_service_unavailable_handling(client: AsyncClient):
    """When AI service fails or times out during assessment, return 503 Service Unavailable."""
    from app.main import app
    from app.services.ai_service import MockAIService
    from app.services.orchestrator import AssessmentOrchestrator, get_orchestrator

    # Register a repo first
    repo_res = await client.post(
        "/api/repositories",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )
    repo_id = repo_res.json()["id"]

    failing_ai = MockAIService(simulate_timeout=True)
    failing_orchestrator = AssessmentOrchestrator(ai_service=failing_ai)
    app.dependency_overrides[get_orchestrator] = lambda: failing_orchestrator
    try:
        response = await client.post(
            "/api/assessments",
            json={
                "repository_id": repo_id,
                "job_title": "Developer",
                "job_description": "We need a skilled Python engineer with testing experience.",
            },
        )
        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "SERVICE_UNAVAILABLE"
    finally:
        app.dependency_overrides.pop(get_orchestrator, None)
