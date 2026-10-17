"""
Automated Test Suite for SkillSync Gap Solver (Phase C & Phase D: Learning-Plan Generation & Guided Workflow).
Verifies:
1. Listing skill gaps for an assessment.
2. Generating structured, ordered learning plans with steps and rich Phase D fields.
3. Distinction of 'not demonstrated' from candidate deficiency.
4. Schema validation against deterministic AILearningPlanOutput schema.
5. Strict verification of canonical learning resource URLs (no fabricated links).
6. Plan idempotency (re-fetching returns the active plan).
7. Updating step progress and notes.
8. Error handling (invalid statuses, non-existent entities, mismatched IDs).
9. CRITICAL RULE: Progress updates never automatically improve candidate scores or ratings.
"""
import pytest
from httpx import AsyncClient

from app.schemas.gap_solver import AILearningPlanOutput, AILearningPlanStepOutput
from app.services.ai_service import sanitize_verified_resources, ALLOWED_DOC_DOMAINS
from pydantic import ValidationError


@pytest.mark.asyncio
async def test_gap_solver_full_lifecycle(client: AsyncClient):
    """
    Test complete Phase C & D Gap Solver workflow:
    1. Setup repo, job profile, and assessment.
    2. List identified skill gaps.
    3. Generate a structured learning plan with ordered steps and rich Phase D fields.
    4. Retrieve persisted plan.
    5. Update step progress and candidate notes.
    6. Verify assessment score is NOT modified by step completion.
    """
    # 1. Setup repository
    repo_res = await client.post(
        "/api/repositories",
        json={"github_url": "https://github.com/myorg/skillsync-project"},
    )
    assert repo_res.status_code == 201
    repo_id = repo_res.json()["id"]

    # 2. Setup job profile with skills that will have gaps
    prof_res = await client.post(
        "/api/job-profiles",
        json={
            "title": "Cloud Backend Engineer",
            "raw_description": (
                "Seeking an engineer proficient in Python, FastAPI, Docker, and Kubernetes. "
                "Must write automated unit tests and manage cloud deployments."
            ),
        },
    )
    assert prof_res.status_code == 201
    prof_id = prof_res.json()["id"]

    # 3. Trigger initial assessment
    assess_res = await client.post(
        "/api/assessments",
        json={"repository_id": repo_id, "job_profile_id": prof_id},
    )
    assert assess_res.status_code == 201
    assessment = assess_res.json()
    assess_id = assessment["id"]
    initial_score = assessment["overall_score"]
    assert len(assessment["skill_gaps"]) > 0

    target_gap = assessment["skill_gaps"][0]
    gap_id = target_gap["id"]
    gap_skill = target_gap["skill_name"]

    # 4. List gaps via Gap Solver endpoint
    gaps_list_res = await client.get(f"/api/assessments/{assess_id}/gaps")
    assert gaps_list_res.status_code == 200
    gaps_data = gaps_list_res.json()
    assert gaps_data["assessment_id"] == assess_id
    assert gaps_data["total"] >= 1
    found_gap = next((g for g in gaps_data["gaps"] if g["id"] == gap_id), None)
    assert found_gap is not None
    assert found_gap["active_plan_id"] is None  # No plan generated yet

    # 5. Generate learning plan for the gap
    plan_create_res = await client.post(
        f"/api/assessments/{assess_id}/gaps/{gap_id}/plan",
        json={"difficulty_level": "intermediate"},
    )
    assert plan_create_res.status_code == 201
    plan_data = plan_create_res.json()
    assert plan_data["skill_gap_id"] == gap_id
    assert plan_data["assessment_id"] == assess_id
    assert plan_data["target_skill"] == gap_skill
    assert plan_data["status"] == "active"
    assert len(plan_data["steps"]) >= 3
    plan_id = plan_data["id"]

    # Phase D Rich Field Verifications
    assert plan_data["objective"] is not None and len(plan_data["objective"]) > 10
    assert plan_data["concept_explanation"] is not None and len(plan_data["concept_explanation"]) > 10
    assert isinstance(plan_data["prerequisites"], list)
    assert len(plan_data["prerequisites"]) >= 1
    assert plan_data["current_classification"] in ("not_demonstrated", "partially_demonstrated")
    assert plan_data["existing_evidence_summary"] is not None
    assert plan_data["missing_evidence_summary"] is not None
    assert plan_data["repo_improvement_recommendation"] is not None
    assert isinstance(plan_data["verified_resources"], list)
    assert len(plan_data["verified_resources"]) >= 1

    # Verify that resource URLs belong strictly to verified canonical documentation domains
    for res in plan_data["verified_resources"]:
        assert any(domain in res["url"] for domain in ALLOWED_DOC_DOMAINS), f"Unverified resource URL: {res['url']}"

    # Verify steps are ordered 1..N and contain Phase D fields
    step_numbers = [s["step_number"] for s in plan_data["steps"]]
    assert step_numbers == list(range(1, len(step_numbers) + 1))
    first_step = plan_data["steps"][0]
    assert first_step["status"] == "not_started"
    assert first_step["acceptance_criteria"] is not None and len(first_step["acceptance_criteria"]) > 5
    assert first_step["exercise"] is not None and len(first_step["exercise"]) > 5
    assert first_step["verification_rubric"] is not None and len(first_step["verification_rubric"]) > 5
    step_id = first_step["id"]

    # 6. Idempotency check: Calling plan generation again returns the active plan
    second_plan_res = await client.post(
        f"/api/assessments/{assess_id}/gaps/{gap_id}/plan",
        json={"difficulty_level": "intermediate"},
    )
    assert second_plan_res.status_code == 201
    assert second_plan_res.json()["id"] == plan_id

    # 7. Retrieve plan by ID
    get_plan_res = await client.get(f"/api/gaps/plans/{plan_id}")
    assert get_plan_res.status_code == 200
    retrieved_plan = get_plan_res.json()
    assert retrieved_plan["id"] == plan_id
    assert len(retrieved_plan["steps"]) == len(plan_data["steps"])
    assert retrieved_plan["objective"] == plan_data["objective"]
    assert retrieved_plan["concept_explanation"] == plan_data["concept_explanation"]
    assert retrieved_plan["prerequisites"] == plan_data["prerequisites"]
    assert len(retrieved_plan["verified_resources"]) == len(plan_data["verified_resources"])

    # 8. List gaps again — now active_plan_id must be populated
    gaps_list_res2 = await client.get(f"/api/assessments/{assess_id}/gaps")
    found_gap2 = next((g for g in gaps_list_res2.json()["gaps"] if g["id"] == gap_id), None)
    assert found_gap2["active_plan_id"] == plan_id
    assert found_gap2["active_plan_status"] == "active"

    # 9. Update step progress to in_progress with notes
    update_step_res = await client.patch(
        f"/api/gaps/plans/steps/{step_id}",
        json={
            "status": "in_progress",
            "user_notes": "Setting up core interfaces and base dataclasses.",
            "evidence_file_path": "app/services/core.py",
        },
    )
    assert update_step_res.status_code == 200
    updated_step = update_step_res.json()
    assert updated_step["id"] == step_id
    assert updated_step["status"] == "in_progress"
    assert updated_step["user_notes"] == "Setting up core interfaces and base dataclasses."
    assert updated_step["evidence_file_path"] == "app/services/core.py"

    # 10. Mark step as verified
    verify_step_res = await client.patch(
        f"/api/gaps/plans/steps/{step_id}",
        json={"status": "verified"},
    )
    assert verify_step_res.status_code == 200
    assert verify_step_res.json()["status"] == "verified"

    # 11. CRITICAL RULE VERIFICATION:
    # A completed or verified learning step must NEVER automatically change the candidate's assessment score!
    check_assess_res = await client.get(f"/api/assessments/{assess_id}")
    assert check_assess_res.status_code == 200
    current_assessment = check_assess_res.json()
    assert current_assessment["overall_score"] == initial_score, (
        f"Score mutated! Expected {initial_score}, got {current_assessment['overall_score']}"
    )


@pytest.mark.asyncio
async def test_gap_solver_validation_and_errors(client: AsyncClient):
    """Test validation boundaries and error conditions."""
    # 1. Non-existent assessment gaps
    res = await client.get("/api/assessments/999999/gaps")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

    # 2. Non-existent gap plan creation
    res2 = await client.post("/api/assessments/1/gaps/999999/plan")
    assert res2.status_code == 404

    # 3. Non-existent learning plan retrieval
    res3 = await client.get("/api/gaps/plans/999999")
    assert res3.status_code == 404

    # 4. Invalid step status update
    res4 = await client.patch(
        "/api/gaps/plans/steps/1",
        json={"status": "invalid_bogus_status"},
    )
    assert res4.status_code in (404, 422)


@pytest.mark.asyncio
async def test_phase_d_scope_distinction(client: AsyncClient):
    """
    Test Phase D requirement 1:
    Distinguish 'not demonstrated in repository' from 'candidate lacks the skill'.
    """
    # Setup repository and profile with a skill with zero code evidence (e.g., Kubernetes)
    repo_res = await client.post(
        "/api/repositories",
        json={"github_url": "https://github.com/myorg/demo-scope-distinction"},
    )
    repo_id = repo_res.json()["id"]

    prof_res = await client.post(
        "/api/job-profiles",
        json={
            "title": "Site Reliability Engineer",
            "raw_description": "Requires deep Kubernetes and Docker cluster orchestration experience.",
        },
    )
    prof_id = prof_res.json()["id"]

    assess_res = await client.post(
        "/api/assessments",
        json={"repository_id": repo_id, "job_profile_id": prof_id},
    )
    assessment = assess_res.json()
    assess_id = assessment["id"]

    # Target Kubernetes gap (should be NOT_FOUND in repo files)
    k8s_gap = next((g for g in assessment["skill_gaps"] if "kubernetes" in g["skill_name"].lower()), None)
    assert k8s_gap is not None

    plan_res = await client.post(
        f"/api/assessments/{assess_id}/gaps/{k8s_gap['id']}/plan",
        json={"difficulty_level": "intermediate"},
    )
    assert plan_res.status_code == 201
    plan = plan_res.json()

    # Must classify as not_demonstrated
    assert plan["current_classification"] == "not_demonstrated"
    # Overview or scope notes must clarify that absence in repo is repo boundary, not deficit
    assert "scope" in plan["overview"].lower() or "repository" in plan["overview"].lower()
    assert plan["existing_evidence_summary"] is not None
    assert "no " in plan["existing_evidence_summary"].lower() or "not" in plan["existing_evidence_summary"].lower()


def test_phase_d_schema_validation_and_sanitizer():
    """
    Test Phase D requirements 3 and 4:
    - Deterministic schema validation for AILearningPlanOutput.
    - Strict verification and rejection of unverified/fabricated URLs.
    """
    # 1. Valid plan payload satisfies schema
    valid_payload = {
        "title": "FastAPI Async Architecture Roadmap",
        "overview": "Comprehensive plan to implement async endpoints in candidate repository.",
        "objective": "Build production-ready FastAPI endpoints with automated validation.",
        "concept_explanation": "FastAPI utilizes async coroutines and Pydantic schemas for high performance.",
        "prerequisites": ["Python 3.10+", "AsyncIO basics"],
        "difficulty_level": "intermediate",
        "estimated_hours": 4.0,
        "current_classification": "not_demonstrated",
        "existing_evidence_summary": "No FastAPI endpoints in repository scope.",
        "missing_evidence_summary": "Need async router and integration tests.",
        "repo_improvement_recommendation": "Add app/api/ router module.",
        "verified_resources": [
            {"title": "FastAPI Docs", "url": "https://fastapi.tiangolo.com/"}
        ],
        "steps": [
            {
                "step_number": 1,
                "title": "Setup Pydantic Schemas",
                "instruction": "Define request and response schemas using Pydantic v2 BaseModel.",
                "code_example": "class Item(BaseModel): name: str",
                "expected_artifact": "app/schemas/item.py",
                "acceptance_criteria": "Schemas reject invalid types with 422.",
                "exercise": "Create an Item schema with positive price validation.",
                "verification_rubric": "Code inherits from BaseModel with field validation.",
            }
        ],
    }
    validated = AILearningPlanOutput.model_validate(valid_payload)
    assert validated.title == "FastAPI Async Architecture Roadmap"
    assert len(validated.steps) == 1

    # 2. Invalid schema payload (missing required title, negative hours) raises ValidationError
    invalid_payload = valid_payload.copy()
    invalid_payload["estimated_hours"] = -5.0
    with pytest.raises(ValidationError):
        AILearningPlanOutput.model_validate(invalid_payload)

    # 3. URL Sanitizer rejects fabricated external links and keeps canonical documentation
    fabricated_resources = [
        {"title": "Fake Course", "url": "https://fakecourses.xyz/learn-fastapi"},
        {"title": "Random Blog", "url": "http://random-blog.net/python-tricks"},
        {"title": "FastAPI Official", "url": "https://fastapi.tiangolo.com/tutorial/"},
    ]
    sanitized = sanitize_verified_resources(fabricated_resources, "fastapi")
    # Only the official documentation must remain!
    assert len(sanitized) == 1
    assert sanitized[0]["url"] == "https://fastapi.tiangolo.com/tutorial/"
    assert "fakecourses.xyz" not in [r["url"] for r in sanitized]
    assert "random-blog.net" not in [r["url"] for r in sanitized]

    # 4. If all provided URLs are invalid, fallback to canonical documentation for that skill
    all_fake = [{"title": "Fake", "url": "https://suspicious-site.co/course"}]
    fallback_sanitized = sanitize_verified_resources(all_fake, "docker")
    assert len(fallback_sanitized) >= 1
    assert all("docker.com" in r["url"] for r in fallback_sanitized)


@pytest.mark.asyncio
async def test_gap_solver_empty_and_required_input_validation(client: AsyncClient):
    """
    Test Bug 2 validation requirements:
    - Empty or whitespace-only difficulty_level is safely defaulted or invalid values rejected with 422.
    - Setting step status to 'evidence_submitted' without an evidence file path returns 422.
    - Verification requests with empty or whitespace-only evidence_file_path return 422.
    """
    repo_res = await client.post(
        "/api/repositories",
        json={"github_url": "https://github.com/myorg/validation-boundaries-repo"},
    )
    repo_id = repo_res.json()["id"]

    prof_res = await client.post(
        "/api/job-profiles",
        json={"title": "DevOps Architect", "raw_description": "Kubernetes and Python required."},
    )
    prof_id = prof_res.json()["id"]

    assess_res = await client.post(
        "/api/assessments",
        json={"repository_id": repo_id, "job_profile_id": prof_id},
    )
    assess_id = assess_res.json()["id"]
    gap_id = assess_res.json()["skill_gaps"][0]["id"]

    # 1. Invalid difficulty level is rejected with 422
    bad_diff_res = await client.post(
        f"/api/assessments/{assess_id}/gaps/{gap_id}/plan",
        json={"difficulty_level": "impossible_difficulty_level"},
    )
    assert bad_diff_res.status_code == 422
    assert "difficulty_level" in bad_diff_res.json()["detail"].lower()

    # Create a valid plan
    plan_res = await client.post(
        f"/api/assessments/{assess_id}/gaps/{gap_id}/plan",
        json={"difficulty_level": "intermediate"},
    )
    assert plan_res.status_code == 201
    step_id = plan_res.json()["steps"][0]["id"]

    # 2. Cannot set status to 'evidence_submitted' without providing evidence file path
    no_path_res = await client.patch(
        f"/api/gaps/plans/steps/{step_id}",
        json={"status": "evidence_submitted", "evidence_file_path": "   "},
    )
    assert no_path_res.status_code == 422
    assert "evidence file path is required" in no_path_res.json()["detail"].lower()

    # 3. Verification request with empty or whitespace-only evidence file path returns 422
    empty_verify_res = await client.post(
        f"/api/gaps/plans/steps/{step_id}/verify",
        json={"evidence_file_path": "   "},
    )
    assert empty_verify_res.status_code == 422
    assert "evidence file path is required" in empty_verify_res.json()["detail"].lower()
