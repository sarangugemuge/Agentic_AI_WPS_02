"""
Gap Solver API routes — Skill gap inspection, roadmap generation, and step progress tracking.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.gap_solver import (
    LearningPlanCreateRequest,
    LearningPlanResponse,
    LearningPlanStepResponse,
    SkillGapListResponse,
    StepProgressUpdateRequest,
    StepVerificationRequest,
    StepVerificationRecordResponse,
    StepVerificationListResponse,
)
from app.services.gap_solver_service import GapSolverService

router = APIRouter()


@router.get(
    "/assessments/{assessment_id}/gaps",
    response_model=SkillGapListResponse,
    summary="List skill gaps for an assessment",
    description="Retrieve all prioritized skill gaps identified during an assessment, annotated with active learning plan status.",
)
async def list_assessment_gaps(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
):
    """List skill gaps with learning roadmap metadata."""
    result = await GapSolverService.list_skill_gaps(db=db, assessment_id=assessment_id)
    return result


@router.post(
    "/assessments/{assessment_id}/gaps/{gap_id}/plan",
    response_model=LearningPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate or retrieve a learning plan",
    description="Creates a structured, actionable learning roadmap plan with ordered steps tailored to the identified skill gap.",
)
async def create_gap_learning_plan(
    assessment_id: int,
    gap_id: int,
    payload: LearningPlanCreateRequest = None,
    db: AsyncSession = Depends(get_db),
):
    """Generate or retrieve an active roadmap plan for a skill gap."""
    difficulty = payload.difficulty_level if payload else "intermediate"
    focus_areas = payload.focus_areas if payload else None

    plan = await GapSolverService.create_or_get_learning_plan(
        db=db,
        assessment_id=assessment_id,
        gap_id=gap_id,
        difficulty_level=difficulty,
        focus_areas=focus_areas,
    )
    return plan


@router.get(
    "/gaps/plans/{plan_id}",
    response_model=LearningPlanResponse,
    summary="Get learning plan details",
    description="Retrieve a specific persisted learning plan, its ordered steps, and current candidate progress.",
)
async def get_learning_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full learning plan with steps."""
    plan = await GapSolverService.get_learning_plan(db=db, plan_id=plan_id)
    return plan


@router.patch(
    "/gaps/plans/steps/{step_id}",
    response_model=LearningPlanStepResponse,
    summary="Update step progress",
    description=(
        "Update candidate notes, implementation details, or progress status on a step. "
        "Notice: Completing steps does not artificially modify the candidate assessment score."
    ),
)
async def update_step_progress(
    step_id: int,
    payload: StepProgressUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update step progress, notes, or file/commit references."""
    updated_step = await GapSolverService.update_step_progress(
        db=db,
        step_id=step_id,
        status=payload.status,
        user_notes=payload.user_notes,
        evidence_file_path=payload.evidence_file_path,
        evidence_commit_sha=payload.evidence_commit_sha,
    )
    return updated_step


@router.post(
    "/gaps/plans/steps/{step_id}/verify",
    response_model=StepVerificationRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify step code evidence",
    description=(
        "Phase E Evidence Verification: Inspects repository code artifacts at target commit, "
        "evaluates evidence against rubric and acceptance criteria, and safely triggers reassessment "
        "only when evidence is sufficient. Preserves immutable verification and assessment history."
    ),
)
async def verify_step_evidence(
    step_id: int,
    payload: StepVerificationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify submitted evidence against step rubric and acceptance criteria."""
    verification_record = await GapSolverService.verify_step_evidence(
        db=db,
        step_id=step_id,
        payload=payload,
    )
    return verification_record


@router.get(
    "/gaps/plans/steps/{step_id}/verifications",
    response_model=StepVerificationListResponse,
    summary="List verification history for a step",
    description="Retrieve all historical, immutable verification records for a learning step.",
)
async def list_step_verifications(
    step_id: int,
    db: AsyncSession = Depends(get_db),
):
    """List immutable verification history for a step."""
    records = await GapSolverService.list_step_verifications(db=db, step_id=step_id)
    return {
        "step_id": step_id,
        "total": len(records),
        "verifications": records,
    }


@router.get(
    "/gaps/verifications/{verification_id}",
    response_model=StepVerificationRecordResponse,
    summary="Get verification record details",
    description="Retrieve a specific immutable verification record by ID.",
)
async def get_verification_record(
    verification_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full details of a specific verification record."""
    record = await GapSolverService.get_step_verification(db=db, verification_id=verification_id)
    return record
