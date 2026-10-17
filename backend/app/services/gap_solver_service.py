"""
Gap Solver Service — Business logic for skill gap remediation and roadmap planning.
Enforces Phase C guarantees:
- Reuses existing assessment and skill gap relationships.
- Updating step progress NEVER modifies official candidate scores or skill ratings.
- Zero data loss, robust validation, and isolated transaction scopes.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, BusinessValidationError
from app.models.assessment import Assessment
from app.models.skill_gap import SkillGap
from app.models.learning_plan import LearningPlan, LearningPlanStep, StepVerificationRecord
from app.services.ai_service import get_ai_service

logger = logging.getLogger("skillsync.services.gap_solver")

VALID_STEP_STATUSES = {
    "not_started",
    "in_progress",
    "evidence_submitted",
    "verified",
    "failed_verification",
}

# Standardized deterministic roadmap blueprints for canonical technical domains
DEFAULT_BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "default": {
        "title": "Practical Implementation Roadmap",
        "overview": "Implement a dedicated module with automated tests to produce verifiable repository code evidence.",
        "estimated_hours": 3.5,
        "steps": [
            {
                "title": "Architecture Setup & Interface Design",
                "instruction": "Define domain types, classes, and configuration schemas establishing the foundational structure.",
                "code_example": "# Domain model and interface\nclass ServiceInterface:\n    def execute(self, payload: dict) -> dict:\n        raise NotImplementedError",
                "expected_artifact": "A dedicated module defining core interfaces and dataclasses/models.",
            },
            {
                "title": "Core Implementation & Exception Handling",
                "instruction": "Implement the core logic with boundary checks, logging, and error propagation.",
                "code_example": "def process_data(items: list) -> list:\n    if not items:\n        raise ValueError('Items list cannot be empty')\n    return [item.strip() for item in items]",
                "expected_artifact": "Functional business logic module with error handling.",
            },
            {
                "title": "Automated Unit Tests & Verification",
                "instruction": "Write comprehensive automated unit tests verifying standard flows and edge cases.",
                "code_example": "def test_service_execution():\n    service = ServiceImplementation()\n    result = service.execute({'key': 'val'})\n    assert result is not None",
                "expected_artifact": "Test suite with high branch coverage.",
            },
        ],
    },
    "fastapi": {
        "title": "FastAPI Async API & Service Roadmap",
        "overview": "Develop production-ready asynchronous endpoints with Pydantic v2 schemas and dependency injection.",
        "estimated_hours": 4.0,
        "steps": [
            {
                "title": "Pydantic Schemas & Request Validation",
                "instruction": "Create strict request/response schemas with field validation and documentation examples.",
                "code_example": "from pydantic import BaseModel, Field\n\nclass ItemCreate(BaseModel):\n    title: str = Field(..., min_length=2, max_length=100)\n    price: float = Field(..., gt=0.0)",
                "expected_artifact": "app/schemas/ defining validated request/response models.",
            },
            {
                "title": "Async Router & Dependency Injection",
                "instruction": "Implement an APIRouter with async endpoint functions leveraging Depends() for services/sessions.",
                "code_example": "from fastapi import APIRouter, Depends\nrouter = APIRouter()\n\n@router.post('/items', status_code=201)\nasync def create_item(payload: ItemCreate, db=Depends(get_db)):\n    return await service.create(db, payload)",
                "expected_artifact": "app/api/routes/ with documented endpoints and status codes.",
            },
            {
                "title": "Integration Testing with AsyncClient",
                "instruction": "Write integration tests utilizing httpx.AsyncClient and pytest-asyncio covering status 201, 404, and 422.",
                "code_example": "@pytest.mark.asyncio\nasync def test_create_item_endpoint(client: AsyncClient):\n    res = await client.post('/api/items', json={'title': 'Test Item', 'price': 19.99})\n    assert res.status_code == 201",
                "expected_artifact": "tests/test_api_endpoints.py testing all router endpoints.",
            },
        ],
    },
    "docker": {
        "title": "Production Containerization Roadmap",
        "overview": "Create a multi-stage Dockerfile and Docker Compose orchestration configuration with security hardening.",
        "estimated_hours": 3.0,
        "steps": [
            {
                "title": "Multi-Stage Dockerfile",
                "instruction": "Write a multi-stage Dockerfile minimizing image size, creating a non-root user, and installing dependencies.",
                "code_example": "FROM python:3.11-slim AS builder\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n\nFROM python:3.11-slim\nRUN useradd -m appuser\nUSER appuser\nCOPY --from=builder /usr/local /usr/local\nCOPY . /app",
                "expected_artifact": "Dockerfile with multi-stage build and non-root execution.",
            },
            {
                "title": "Docker Compose Local Environment",
                "instruction": "Define a docker-compose.yml file configuring healthchecks, environment variables, and persistent volumes.",
                "code_example": "version: '3.8'\nservices:\n  web:\n    build: .\n    ports:\n      - '8000:8000'\n    healthcheck:\n      test: ['CMD', 'curl', '-f', 'http://localhost:8000/api/health']\n      interval: 10s",
                "expected_artifact": "docker-compose.yml with environment config and health checks.",
            },
            {
                "title": "Container CI Verification Script",
                "instruction": "Add a verification script or test to build and validate container health in local CI.",
                "code_example": "docker build -t app:test .\ndocker run --rm app:test pytest",
                "expected_artifact": "CI workflow step or script validating the built container.",
            },
        ],
    },
    "testing": {
        "title": "Automated Testing & Coverage Roadmap",
        "overview": "Establish a test suite with fixtures, unit tests, integration tests, and error boundary assertions.",
        "estimated_hours": 3.0,
        "steps": [
            {
                "title": "Pytest Fixtures & Test Harness",
                "instruction": "Configure conftest.py with isolated test fixtures, mock clients, and database isolation.",
                "code_example": "import pytest\nfrom httpx import AsyncClient, ASGITransport\n\n@pytest.fixture\nasync def client():\n    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:\n        yield ac",
                "expected_artifact": "tests/conftest.py defining reusable test fixtures.",
            },
            {
                "title": "Edge Case & Boundary Assertion Tests",
                "instruction": "Implement tests exercising invalid payloads, boundary values, empty lists, and error states.",
                "code_example": "def test_boundary_values():\n    assert validate_input('') == False\n    assert validate_input('a' * 1000) == False",
                "expected_artifact": "tests/test_validation.py validating edge-case scenarios.",
            },
            {
                "title": "CI Test Execution Configuration",
                "instruction": "Add pytest configuration (pytest.ini or pyproject.toml) enforcing coverage thresholds.",
                "code_example": "[pytest]\nasyncio_mode = auto\naddopts = --strict-markers -v",
                "expected_artifact": "pytest.ini or pyproject.toml config file.",
            },
        ],
    },
}


class GapSolverService:
    """Service providing skill gap roadmap planning and step progress tracking."""

    @staticmethod
    async def list_skill_gaps(db: AsyncSession, assessment_id: int) -> Dict[str, Any]:
        """List all identified skill gaps for an assessment, annotated with active plan status."""
        assess_stmt = select(Assessment).where(Assessment.id == assessment_id)
        assess_res = await db.execute(assess_stmt)
        assessment = assess_res.scalar_one_or_none()
        if not assessment:
            raise NotFoundError("Assessment", assessment_id)

        gaps_stmt = (
            select(SkillGap)
            .where(SkillGap.assessment_id == assessment_id)
            .options(selectinload(SkillGap.learning_plans))
            .order_by(SkillGap.priority.asc(), SkillGap.id.asc())
        )
        gaps_res = await db.execute(gaps_stmt)
        gaps = gaps_res.scalars().all()

        results = []
        for g in gaps:
            active_plan = next((p for p in g.learning_plans if p.status == "active"), None)
            results.append({
                "id": g.id,
                "assessment_id": g.assessment_id,
                "skill_name": g.skill_name,
                "category": g.category,
                "gap_severity": g.gap_severity,
                "description": g.description,
                "recommended_action": g.recommended_action,
                "priority": g.priority,
                "created_at": g.created_at,
                "active_plan_id": active_plan.id if active_plan else None,
                "active_plan_status": active_plan.status if active_plan else None,
            })

        return {
            "assessment_id": assessment_id,
            "total": len(results),
            "gaps": results,
        }

    @staticmethod
    async def create_or_get_learning_plan(
        db: AsyncSession,
        assessment_id: int,
        gap_id: int,
        difficulty_level: str = "intermediate",
        focus_areas: Optional[List[str]] = None,
    ) -> LearningPlan:
        """
        Retrieve an existing active plan for the gap, or generate and persist a new plan with ordered steps.
        Enforces ownership consistency between assessment_id and gap_id.
        Phase D Workflow:
        - Uses actual assessment findings and repository evidence.
        - Distinguishes 'not demonstrated' from candidate personal deficiency.
        - Generates rich roadmap with objectives, prerequisites, exercises, acceptance criteria,
          verification rubrics, and strictly verified canonical resources.
        - Validates against deterministic schema before persistence.
        """
        if difficulty_level is not None:
            norm_diff = difficulty_level.strip().lower()
            if norm_diff not in ("beginner", "intermediate", "advanced"):
                raise BusinessValidationError(
                    f"Invalid difficulty_level '{difficulty_level}'. Must be one of: 'beginner', 'intermediate', 'advanced'."
                )
            difficulty_level = norm_diff
        else:
            difficulty_level = "intermediate"

        # 1. Validate assessment and gap exist and belong together
        gap_stmt = select(SkillGap).where(SkillGap.id == gap_id)
        gap_res = await db.execute(gap_stmt)
        gap = gap_res.scalar_one_or_none()

        if not gap:
            raise NotFoundError("SkillGap", gap_id)

        if gap.assessment_id != assessment_id:
            raise BusinessValidationError(
                f"SkillGap #{gap_id} belongs to Assessment #{gap.assessment_id}, not Assessment #{assessment_id}."
            )

        # 2. Check for existing active plan (idempotency preservation)
        plan_stmt = (
            select(LearningPlan)
            .where(
                LearningPlan.skill_gap_id == gap_id,
                LearningPlan.status == "active",
            )
            .options(selectinload(LearningPlan.steps))
            .order_by(LearningPlan.version.desc())
        )
        plan_res = await db.execute(plan_stmt)
        existing_plan = plan_res.scalar_one_or_none()
        if existing_plan:
            logger.info(f"Returning existing active LearningPlan #{existing_plan.id} for SkillGap #{gap_id}.")
            return existing_plan

        # 3. Retrieve assessment context including findings, job profile, and repository
        assess_stmt = (
            select(Assessment)
            .where(Assessment.id == assessment_id)
            .options(
                selectinload(Assessment.job_profile),
                selectinload(Assessment.repository),
                selectinload(Assessment.skill_findings),
            )
        )
        assess_res = await db.execute(assess_stmt)
        assessment = assess_res.scalar_one_or_none()
        if not assessment:
            raise NotFoundError("Assessment", assessment_id)

        # 4. Extract evidence context and distinguish scope
        matching_finding = None
        if assessment.skill_findings:
            for f in assessment.skill_findings:
                if f.skill_name.lower() == gap.skill_name.lower():
                    matching_finding = f
                    break

        status_str = ""
        if matching_finding and matching_finding.status:
            status_str = getattr(matching_finding.status, "value", str(matching_finding.status)).lower()

        if status_str in ("not_found", "not_demonstrated") or not matching_finding:
            current_classification = "not_demonstrated"
            existing_evidence = "No source code or configuration files matching this skill were found in the current repository scope."
            missing_evidence = (
                matching_finding.limitations
                if matching_finding and matching_finding.limitations
                else f"No dedicated module, configuration, or automated tests demonstrate {gap.skill_name} in repository scope."
            )
        else:
            current_classification = "partially_demonstrated"
            existing_evidence = (
                matching_finding.rationale
                if matching_finding and matching_finding.rationale
                else f"Partial references to {gap.skill_name} were located in repository scope, but lacked comprehensive production implementation."
            )
            missing_evidence = (
                matching_finding.limitations
                if matching_finding and matching_finding.limitations
                else f"Lacks complete automated test suites or edge case coverage for {gap.skill_name}."
            )

        job_title = (
            assessment.job_profile.title
            if assessment.job_profile and assessment.job_profile.title
            else "Software Engineer"
        )
        job_req = (
            gap.description
            or (matching_finding.rationale if matching_finding else None)
            or f"Demonstrated proficiency in {gap.skill_name} required for {job_title} role."
        )
        repo_name = (
            assessment.repository.repo_name
            if assessment.repository and assessment.repository.repo_name
            else "candidate-repo"
        )

        # 5. Invoke AI Service for structured learning plan generation with safe fallback
        ai_service = get_ai_service()
        plan_output = await ai_service.generate_learning_plan(
            skill_name=gap.skill_name,
            category=gap.category,
            job_title=job_title,
            job_requirement_text=job_req,
            current_classification=current_classification,
            existing_evidence_summary=existing_evidence,
            missing_evidence_summary=missing_evidence,
            repo_name=repo_name,
            difficulty_level=difficulty_level or "intermediate",
            focus_areas=focus_areas,
        )

        # 6. Determine version number
        v_stmt = select(func.count(LearningPlan.id)).where(LearningPlan.skill_gap_id == gap_id)
        v_res = await db.execute(v_stmt)
        version_num = (v_res.scalar() or 0) + 1

        # 7. Persist LearningPlan with Phase D rich workflow fields
        new_plan = LearningPlan(
            skill_gap_id=gap.id,
            assessment_id=assessment_id,
            version=version_num,
            title=plan_output["title"],
            overview=plan_output["overview"],
            target_skill=gap.skill_name,
            difficulty_level=plan_output.get("difficulty_level", difficulty_level or "intermediate"),
            estimated_hours=float(plan_output.get("estimated_hours", 3.0)),
            status="active",
            objective=plan_output.get("objective"),
            concept_explanation=plan_output.get("concept_explanation"),
            prerequisites_json=json.dumps(plan_output.get("prerequisites", [])),
            current_classification=plan_output.get("current_classification", current_classification),
            existing_evidence_summary=plan_output.get("existing_evidence_summary", existing_evidence),
            missing_evidence_summary=plan_output.get("missing_evidence_summary", missing_evidence),
            repo_improvement_recommendation=plan_output.get("repo_improvement_recommendation"),
            verified_resources_json=json.dumps(plan_output.get("verified_resources", [])),
        )
        db.add(new_plan)
        await db.flush()  # assign new_plan.id

        # 8. Persist ordered LearningPlanSteps with rich fields
        for step_data in plan_output.get("steps", []):
            step = LearningPlanStep(
                plan_id=new_plan.id,
                step_number=step_data["step_number"],
                title=step_data["title"],
                instruction=step_data["instruction"],
                code_example=step_data.get("code_example"),
                expected_artifact=step_data.get("expected_artifact"),
                acceptance_criteria=step_data.get("acceptance_criteria"),
                exercise=step_data.get("exercise"),
                verification_rubric=step_data.get("verification_rubric"),
                status="not_started",
            )
            db.add(step)

        await db.commit()

        # Reload with steps
        reload_stmt = (
            select(LearningPlan)
            .where(LearningPlan.id == new_plan.id)
            .options(selectinload(LearningPlan.steps))
        )
        reloaded_res = await db.execute(reload_stmt)
        plan_with_steps = reloaded_res.scalar_one()

        logger.info(
            f"Created LearningPlan #{plan_with_steps.id} (v{version_num}) with {len(plan_with_steps.steps)} steps for gap '{gap.skill_name}'."
        )
        return plan_with_steps

    @staticmethod
    async def get_learning_plan(db: AsyncSession, plan_id: int) -> LearningPlan:
        """Retrieve a specific learning plan with its ordered steps."""
        stmt = (
            select(LearningPlan)
            .where(LearningPlan.id == plan_id)
            .options(selectinload(LearningPlan.steps))
        )
        res = await db.execute(stmt)
        plan = res.scalar_one_or_none()
        if not plan:
            raise NotFoundError("LearningPlan", plan_id)
        return plan

    @staticmethod
    async def update_step_progress(
        db: AsyncSession,
        step_id: int,
        status: Optional[str] = None,
        user_notes: Optional[str] = None,
        evidence_file_path: Optional[str] = None,
        evidence_commit_sha: Optional[str] = None,
    ) -> LearningPlanStep:
        """
        Update candidate notes, file path, commit SHA, and progress status on a step.
        Guarantees:
        - Validates allowed status values.
        - Never alters Assessment.overall_score or SkillFinding.status.
        """
        stmt = select(LearningPlanStep).where(LearningPlanStep.id == step_id)
        res = await db.execute(stmt)
        step = res.scalar_one_or_none()
        if not step:
            raise NotFoundError("LearningPlanStep", step_id)

        if status is not None:
            norm_status = status.strip().lower()
            if norm_status not in VALID_STEP_STATUSES:
                raise BusinessValidationError(
                    f"Invalid step status '{status}'. Must be one of: {sorted(list(VALID_STEP_STATUSES))}."
                )
            if norm_status == "evidence_submitted":
                active_path = evidence_file_path if evidence_file_path is not None else step.evidence_file_path
                clean_path = (active_path or "").strip()
                if not clean_path:
                    raise BusinessValidationError(
                        "An evidence file path is required when setting status to 'evidence_submitted'."
                    )
            step.status = norm_status

        if user_notes is not None:
            step.user_notes = user_notes.strip() if user_notes else None

        if evidence_file_path is not None:
            clean_fp = evidence_file_path.strip() if evidence_file_path else None
            if clean_fp:
                from app.services.evidence_verifier import EvidenceVerifier
                is_safe, path_err = EvidenceVerifier.validate_file_path(clean_fp)
                if not is_safe:
                    raise BusinessValidationError(path_err or "Invalid evidence file path.")
            step.evidence_file_path = clean_fp

        if evidence_commit_sha is not None:
            step.evidence_commit_sha = evidence_commit_sha.strip() if evidence_commit_sha else None

        await db.commit()
        await db.refresh(step)

        logger.info(f"Updated LearningPlanStep #{step.id} (Plan #{step.plan_id}): status='{step.status}'.")
        return step

    @staticmethod
    async def verify_step_evidence(
        db: AsyncSession,
        step_id: int,
        payload: Any,
    ) -> StepVerificationRecord:
        """
        Phase E Evidence-Based Verification and Reassessment:
        1. Retrieve original skill gap, learning-plan version, and acceptance criteria.
        2. Validate submitted evidence references, file paths, and user permissions.
        3. If authorized, inspect only the approved GitHub repository and relevant files.
           Do not access private repositories without explicit permission.
        4. Evaluate each rubric criterion against actual evidence.
           Distinguish verified, partially demonstrated, insufficient, and inaccessible.
        5. Record evidence found, locations, rubric findings, limitations, missing work, next action.
        6. Persist every verification result (immutable; never overwrite historical data).
        7. Insufficient evidence leaves gap unresolved and score unchanged.
        8. When evidence is sufficient, invoke existing assessment workflow under approved policy.
           Preserve before-and-after assessment records and explain classification changes.
        """
        from app.services.evidence_verifier import EvidenceVerifier
        from app.services.github_service import get_github_service

        # 1. Retrieve step with its plan, gap, assessment, repository, and job profile
        stmt = (
            select(LearningPlanStep)
            .where(LearningPlanStep.id == step_id)
            .options(
                selectinload(LearningPlanStep.learning_plan)
                .selectinload(LearningPlan.skill_gap),
                selectinload(LearningPlanStep.learning_plan)
                .selectinload(LearningPlan.assessment)
                .selectinload(Assessment.repository),
                selectinload(LearningPlanStep.learning_plan)
                .selectinload(LearningPlan.assessment)
                .selectinload(Assessment.job_profile),
                selectinload(LearningPlanStep.learning_plan)
                .selectinload(LearningPlan.assessment)
                .selectinload(Assessment.skill_findings),
            )
        )
        res = await db.execute(stmt)
        step = res.scalar_one_or_none()
        if not step:
            raise NotFoundError("LearningPlanStep", step_id)

        plan = step.learning_plan
        gap = plan.skill_gap
        orig_assessment = plan.assessment
        repo = orig_assessment.repository
        job_profile = orig_assessment.job_profile

        # 2. Extract and validate evidence references
        raw_evidence_path = getattr(payload, "evidence_file_path", None)
        if raw_evidence_path is not None:
            raw_evidence_path = raw_evidence_path.strip()
            if not raw_evidence_path:
                raw_evidence_path = None

        evidence_path = raw_evidence_path or step.evidence_file_path
        commit_sha = getattr(payload, "commit_sha", None) or step.evidence_commit_sha or repo.latest_commit_sha
        if commit_sha:
            commit_sha = str(commit_sha).strip()
        evidence_type = getattr(payload, "evidence_type", None) or "code_file"
        user_notes = getattr(payload, "user_notes", None)
        allow_private_repo = getattr(payload, "allow_private_repo", False)
        trigger_reassessment = getattr(payload, "trigger_reassessment", True)

        # Update candidate notes and references on step if provided
        if user_notes:
            step.user_notes = user_notes.strip()
        if raw_evidence_path:
            step.evidence_file_path = raw_evidence_path
        if commit_sha:
            step.evidence_commit_sha = commit_sha

        # Check for missing evidence file path - reject empty input
        if not evidence_path or not str(evidence_path).strip():
            raise BusinessValidationError(
                "An evidence file path is required for verification. Please specify a repository-relative path in 'evidence_file_path'."
            )

        # Validate file path safety (reject traversal / absolute paths)
        is_safe, path_err = EvidenceVerifier.validate_file_path(evidence_path)
        if not is_safe:
            raise BusinessValidationError(path_err or "Invalid evidence file path.")

        # 3. Validate permissions and private repository access
        github_service = get_github_service()
        repo_metadata = await github_service.get_repository_metadata(repo.github_owner, repo.repo_name)
        is_private = repo_metadata.get("is_private", False)

        if is_private and not allow_private_repo:
            logger.warning(
                f"[Phase E Security] Private repository '{repo.full_name}' inspection blocked: candidate has not granted explicit authorization."
            )
            rec = StepVerificationRecord(
                step_id=step.id,
                learning_plan_id=plan.id,
                original_assessment_id=orig_assessment.id,
                subsequent_assessment_id=None,
                verdict="inaccessible",
                rubric_score=0.0,
                feedback=f"Repository '{repo.full_name}' is private. Explicit candidate authorization is required to inspect private repositories.",
                strengths=None,
                missing_elements="Explicit authorization for private repository inspection.",
                limitations="Access refused: SkillSync never accesses private repositories without explicit user permission.",
                missing_work="Grant explicit permission by specifying allow_private_repo=True in verification request.",
                next_recommended_action="Set allow_private_repo=True if you authorize SkillSync to inspect this private repository.",
                evidence_type=evidence_type,
                evidence_source="github_repository",
                evidence_locations_json=json.dumps([{"file_path": evidence_path, "commit_sha": commit_sha}]),
                evidence_found_json=json.dumps([]),
                rubric_findings_json=json.dumps([{
                    "criterion": "Private Repository Authorization",
                    "status": "inaccessible",
                    "score": 0.0,
                    "notes": "Access refused without explicit permission.",
                }]),
                commit_sha=commit_sha,
                verified_file_path=evidence_path,
            )
            db.add(rec)
            step.status = "failed_verification"
            await db.commit()
            await db.refresh(rec)
            return rec

        # 4. Safely inspect repository evidence artifacts at target commit
        try:
            artifacts = await github_service.get_repository_evidence_artifacts(
                repo.github_owner, repo.repo_name, commit_sha=commit_sha
            )
        except Exception as exc:
            logger.error(f"[Phase E] Repository inspection failure for {repo.full_name}@{commit_sha}: {exc}", exc_info=True)
            rec = StepVerificationRecord(
                step_id=step.id,
                learning_plan_id=plan.id,
                original_assessment_id=orig_assessment.id,
                subsequent_assessment_id=None,
                verdict="inaccessible",
                rubric_score=0.0,
                feedback=f"Repository evidence artifacts could not be retrieved from GitHub: {str(exc)}",
                strengths=None,
                missing_elements="Accessible repository artifacts at commit.",
                limitations="GitHub API unavailable or commit identifier not found.",
                missing_work="Verify commit SHA and repository availability.",
                next_recommended_action="Check GitHub repository status and re-submit verification.",
                evidence_type=evidence_type,
                evidence_source="github_repository",
                evidence_locations_json=json.dumps([]),
                evidence_found_json=json.dumps([]),
                rubric_findings_json=json.dumps([{
                    "criterion": "Repository Availability",
                    "status": "inaccessible",
                    "score": 0.0,
                    "notes": str(exc),
                }]),
                commit_sha=commit_sha,
                verified_file_path=evidence_path,
            )
            db.add(rec)
            step.status = "failed_verification"
            await db.commit()
            await db.refresh(rec)
            return rec

        # 5. Locate requested evidence file in repository files
        repo_files = artifacts.get("files", [])
        norm_target = evidence_path.strip().replace("\\", "/").lower()
        target_file_record = None

        for f in repo_files:
            f_norm = f.get("path", "").strip().replace("\\", "/").lower()
            if f_norm == norm_target or f_norm.endswith("/" + norm_target):
                target_file_record = f
                break

        if not target_file_record:
            logger.info(f"[Phase E] Target file '{evidence_path}' not present in repository files at commit {commit_sha}.")
            rec = StepVerificationRecord(
                step_id=step.id,
                learning_plan_id=plan.id,
                original_assessment_id=orig_assessment.id,
                subsequent_assessment_id=None,
                verdict="inaccessible",
                rubric_score=0.0,
                feedback=f"Target evidence file '{evidence_path}' was not found in repository '{repo.full_name}' at commit {commit_sha}.",
                strengths=None,
                missing_elements=f"File '{evidence_path}' does not exist in repository files.",
                limitations="Repository file tree does not contain the specified file at this commit reference.",
                missing_work=f"Commit and push '{evidence_path}' to repository branch.",
                next_recommended_action="Check the relative file path spelling and ensure the file is committed to the repository.",
                evidence_type=evidence_type,
                evidence_source="github_repository",
                evidence_locations_json=json.dumps([{"file_path": evidence_path, "commit_sha": commit_sha}]),
                evidence_found_json=json.dumps([]),
                rubric_findings_json=json.dumps([{
                    "criterion": "Artifact Accessibility",
                    "status": "inaccessible",
                    "score": 0.0,
                    "notes": f"File '{evidence_path}' not found in repository artifacts.",
                }]),
                commit_sha=commit_sha,
                verified_file_path=evidence_path,
            )
            db.add(rec)
            step.status = "failed_verification"
            await db.commit()
            await db.refresh(rec)
            return rec

        # Collect evidence files (primary file + companion test files in repo)
        evidence_files_list = [target_file_record]
        for f in repo_files:
            if f != target_file_record and "test" in f.get("path", "").lower():
                evidence_files_list.append(f)

        # 6. Evaluate each rubric criterion against actual evidence
        eval_result = EvidenceVerifier.evaluate_rubric_against_evidence(
            target_skill=plan.target_skill,
            acceptance_criteria=step.acceptance_criteria,
            verification_rubric=step.verification_rubric,
            expected_artifact=step.expected_artifact or evidence_path,
            instruction=step.instruction,
            evidence_files=evidence_files_list,
            commit_sha=commit_sha,
            repo_name=repo.repo_name,
        )

        verdict = eval_result["verdict"]
        rubric_score = eval_result["rubric_score"]

        # 7. Update step status
        if verdict == "verified":
            step.status = "verified"
        elif verdict == "partially_demonstrated":
            step.status = "in_progress"
        else:
            step.status = "failed_verification"

        # 8. Reassessment Workflow (ONLY if verdict == 'verified' and trigger_reassessment)
        subsequent_assessment_id = None
        reassessment_explanation = None
        classification_change = None

        if verdict == "verified" and trigger_reassessment:
            logger.info(
                f"[Phase E Reassessment] Step #{step.id} verified (score: {rubric_score}%). "
                f"Invoking existing assessment pipeline for repository ID {repo.id}."
            )
            from app.services.orchestrator import AssessmentOrchestrator
            orchestrator = AssessmentOrchestrator(github_service=github_service)
            new_assessment = await orchestrator.run_assessment(
                db=db,
                repository_id=repo.id,
                job_profile_id=orig_assessment.job_profile_id,
                commit_sha=commit_sha,
            )
            subsequent_assessment_id = new_assessment.id

            # Determine before-and-after finding classification for the target skill
            orig_finding = next(
                (f for f in (orig_assessment.skill_findings or []) if f.skill_name.lower() == plan.target_skill.lower()),
                None,
            )
            orig_status = orig_finding.status.value if orig_finding else "not_found"

            new_finding = next(
                (f for f in (new_assessment.skill_findings or []) if f.skill_name.lower() == plan.target_skill.lower()),
                None,
            )
            new_status = new_finding.status.value if new_finding else "not_found"

            classification_change = f"{orig_status} -> {new_status}"
            reassessment_explanation = (
                f"Reassessment #{new_assessment.id} (v{new_assessment.version}) completed. "
                f"Candidate score: {orig_assessment.overall_score}% -> {new_assessment.overall_score}%. "
                f"Skill '{plan.target_skill}' classification updated: {classification_change}."
            )

            # If newly demonstrated, mark gap as resolved in new state
            if new_status.lower() == "demonstrated" and gap:
                gap.gap_severity = "resolved"

        # 9. Persist immutable StepVerificationRecord with full provenance
        rec = StepVerificationRecord(
            step_id=step.id,
            learning_plan_id=plan.id,
            original_assessment_id=orig_assessment.id,
            subsequent_assessment_id=subsequent_assessment_id,
            verdict=verdict,
            rubric_score=rubric_score,
            feedback=eval_result["feedback"],
            strengths=eval_result.get("strengths"),
            missing_elements=eval_result.get("missing_elements"),
            limitations=eval_result.get("limitations"),
            missing_work=eval_result.get("missing_work"),
            next_recommended_action=eval_result.get("next_recommended_action"),
            evidence_type=evidence_type,
            evidence_source="github_repository",
            evidence_locations_json=json.dumps(eval_result.get("evidence_locations", [])),
            evidence_found_json=json.dumps(eval_result.get("evidence_found", [])),
            rubric_findings_json=json.dumps(eval_result.get("rubric_findings", [])),
            reassessment_explanation=reassessment_explanation,
            classification_change=classification_change,
            commit_sha=commit_sha,
            verified_file_path=evidence_path,
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)

        logger.info(
            f"[Phase E Complete] Step #{step.id} verification #{rec.id} recorded. "
            f"Verdict: {verdict} ({rubric_score}%). Reassessment: {subsequent_assessment_id}."
        )
        return rec

    @staticmethod
    async def list_step_verifications(db: AsyncSession, step_id: int) -> List[StepVerificationRecord]:
        """Retrieve all historical verification records for a specific learning step."""
        stmt = (
            select(StepVerificationRecord)
            .where(StepVerificationRecord.step_id == step_id)
            .order_by(StepVerificationRecord.id.desc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_step_verification(db: AsyncSession, verification_id: int) -> StepVerificationRecord:
        """Retrieve a specific verification record by ID."""
        stmt = select(StepVerificationRecord).where(StepVerificationRecord.id == verification_id)
        res = await db.execute(stmt)
        rec = res.scalar_one_or_none()
        if not rec:
            raise NotFoundError("StepVerificationRecord", verification_id)
        return rec

