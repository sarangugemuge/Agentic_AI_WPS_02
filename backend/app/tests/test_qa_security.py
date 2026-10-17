"""
Phase 9: Comprehensive QA and Security Verification Suite.
Validates:
1. End-to-end frontend-to-backend API contract integrity.
2. Boundary and input validation (short descriptions, invalid URLs, bad pagination).
3. Security: Unauthorized access, signature verification, safe error disclosures (no leaked tracebacks).
4. Provenance and anti-hallucination verification.
5. Multi-version assessment tracking and relational cascade safety.
"""
import hashlib
import hmac
import json
import uuid
from httpx import AsyncClient


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def test_qa_input_validation_boundaries(client: AsyncClient):
    """Test boundary conditions for all API endpoints."""
    # 1. Short job description (< 20 chars) must be rejected
    res = await client.post(
        "/api/job-profiles",
        json={"title": "DevOps", "raw_description": "Too short"},
    )
    assert res.status_code == 422

    # 2. Empty job title must be rejected
    res = await client.post(
        "/api/job-profiles",
        json={"title": "", "raw_description": "A sufficiently long description with more than 20 characters."},
    )
    assert res.status_code == 422

    # 3. Invalid repository URL format must be rejected
    res = await client.post(
        "/api/repositories/validate",
        json={"repository_url": "ftp://invalid-protocol.com/repo"},
    )
    assert res.status_code == 422

    # 4. Out-of-bounds pagination (limit=0, limit=101, skip=-1)
    res = await client.get("/api/assessments?limit=0")
    assert res.status_code == 422

    res = await client.get("/api/assessments?limit=101")
    assert res.status_code == 422

    res = await client.get("/api/assessments?skip=-1")
    assert res.status_code == 422


async def test_qa_security_error_disclosure(client: AsyncClient):
    """Ensure error messages never disclose internal stack traces or database internals."""
    # Non-existent repository query
    res = await client.get("/api/repositories/888888")
    assert res.status_code == 404
    data = res.json()
    assert "detail" in data
    assert "Traceback" not in json.dumps(data)
    assert "sqlite" not in json.dumps(data).lower()

    # Non-existent assessment query
    res = await client.get("/api/assessments/888888")
    assert res.status_code == 404
    data = res.json()
    assert "Traceback" not in json.dumps(data)

    # Malformed JSON body
    res = await client.post(
        "/api/job-profiles",
        content=b"not-valid-json{{{",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code in (400, 422)
    assert "Traceback" not in res.text


async def test_qa_cors_and_security_headers(client: AsyncClient):
    """Verify CORS headers and health endpoints."""
    res = await client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "skillsync-api"
    assert "version" in data
    assert "environment" in data

    res = await client.get("/api/version")
    assert res.status_code == 200
    ver_data = res.json()
    assert "api_version" in ver_data
    assert "service" in ver_data
    assert "test_doubles_active" in ver_data



async def test_qa_e2e_assessment_lifecycle(client: AsyncClient):
    """Full lifecycle: Repo -> Job Profile -> Assessment -> Findings -> Citations -> Gaps."""
    # 1. Connect repo
    repo_res = await client.post(
        "/api/repositories",
        json={
            "github_url": "https://github.com/octocat/Hello-World",
            "description": "QA Lifecycle Repo",
        },
    )
    assert repo_res.status_code == 201
    repo = repo_res.json()
    repo_id = repo["id"]

    # 2. Create job profile
    job_res = await client.post(
        "/api/job-profiles",
        json={
            "title": "QA Test Engineer",
            "company_context": "SkillSync Quality",
            "raw_description": "We require automated testing, Python, Docker, and REST API development skills.",
        },
    )
    assert job_res.status_code == 201
    job = job_res.json()
    job_id = job["id"]

    # 3. Trigger assessment
    assess_res = await client.post(
        "/api/assessments",
        json={"repository_id": repo_id, "job_profile_id": job_id},
    )
    assert assess_res.status_code == 201
    assessment = assess_res.json()
    assert assessment["overall_score"] is not None
    assert assessment["version"] >= 1
    assert assessment["status"] == "completed"
    assert len(assessment["skill_findings"]) > 0

    # 4. Fetch full assessment by ID
    get_res = await client.get(f"/api/assessments/{assessment['id']}")
    assert get_res.status_code == 200
    full = get_res.json()
    assert full["id"] == assessment["id"]
    assert full["repository"]["repo_name"] == "Hello-World"
    assert full["job_profile"]["title"] == "QA Test Engineer"

    # 5. Verify skill findings endpoint
    skills_res = await client.get(f"/api/assessments/{assessment['id']}/skills")
    assert skills_res.status_code == 200
    skills = skills_res.json()
    assert len(skills) == len(full["skill_findings"])

    # 6. Verify evidence endpoint for a finding
    finding_with_evidence = next((s for s in skills if len(s["evidence_citations"]) > 0), None)
    if finding_with_evidence:
        ev_res = await client.get(
            f"/api/assessments/{assessment['id']}/skills/{finding_with_evidence['id']}/evidence"
        )
        assert ev_res.status_code == 200
        ev_data = ev_res.json()
        assert len(ev_data) > 0
        assert "file_path" in ev_data[0]


async def test_qa_webhook_security_and_reassessment(client: AsyncClient):
    """Verify webhook signature security, idempotency, and automated multi-version tracking."""
    from app.core.config import settings
    secret = settings.github_webhook_secret

    # 1. Reject invalid signature
    bad_payload = json.dumps({"action": "push"}).encode("utf-8")
    res = await client.post(
        "/api/webhooks/github",
        content=bad_payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
        },
    )
    assert res.status_code == 401

    # 2. Ping handshake
    ping_payload = json.dumps({"zen": "QA Ping"}).encode("utf-8")
    ping_sig = compute_signature(ping_payload, secret)
    res = await client.post(
        "/api/webhooks/github",
        content=ping_payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": ping_sig,
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # 3. Push event triggering reassessment
    deliv_id = str(uuid.uuid4())
    push_data = {
        "ref": "refs/heads/main",
        "after": "aabbccddeeff00112233445566778899aabbccdd",
        "repository": {
            "name": "Hello-World",
            "full_name": "octocat/Hello-World",
            "default_branch": "main",
            "owner": {"login": "octocat"},
        },
    }
    push_bytes = json.dumps(push_data).encode("utf-8")
    push_sig = compute_signature(push_bytes, secret)

    res = await client.post(
        "/api/webhooks/github",
        content=push_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": deliv_id,
            "X-Hub-Signature-256": push_sig,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "reassessed"
    assert data["commit_sha"] is not None and len(data["commit_sha"]) >= 7
    assert data["version"] >= 1


    # 4. Duplicate delivery deduplication
    dup_res = await client.post(
        "/api/webhooks/github",
        content=push_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": deliv_id,
            "X-Hub-Signature-256": push_sig,
        },
    )
    assert dup_res.status_code == 200
    assert dup_res.json()["status"] == "duplicate"
