"""
Assessments API routes — Trigger assessment runs, inspect results, and browse history.
"""
from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.models.assessment import Assessment
from app.models.repository import Repository
from app.models.skill_finding import SkillFinding
from app.schemas.assessment import (
    AssessmentCreate,
    AssessmentResponse,
    AssessmentListResponse,
    SkillFindingResponse,
)
from app.services.orchestrator import AssessmentOrchestrator, get_orchestrator

router = APIRouter()


@router.post(
    "/assessments",
    response_model=AssessmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger a skill assessment",
    description=(
        "Executes the assessment orchestrator pipeline:\n"
        "1. Validates repository and job profile input\n"
        "2. Analyzes job description requirements\n"
        "3. Gathers repository code evidence artifacts\n"
        "4. Compares code artifacts against required skills\n"
        "5. Validates findings and confidence scores\n"
        "6. Persists assessment, findings, and citations\n"
        "7. Returns complete assessment results"
    ),
)
async def trigger_assessment(
    payload: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    orchestrator: AssessmentOrchestrator = Depends(get_orchestrator),
):
    assessment = await orchestrator.run_assessment(
        db=db,
        repository_id=payload.repository_id,
        job_profile_id=payload.job_profile_id,
        job_title=payload.job_title,
        job_description=payload.job_description,
        company_context=payload.company_context,
    )
    return assessment


@router.get(
    "/assessments",
    response_model=AssessmentListResponse,
    summary="List assessments",
    description="Returns a paginated list of all assessments conducted across all repositories.",
)
async def list_assessments(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count(Assessment.id))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = (
        select(Assessment)
        .order_by(Assessment.id.desc())
        .offset(skip)
        .limit(limit)
        .options(
            selectinload(Assessment.job_profile),
            selectinload(Assessment.repository),
            selectinload(Assessment.skill_findings).selectinload(SkillFinding.evidence_citations),
            selectinload(Assessment.skill_gaps),
        )

    )
    result = await db.execute(stmt)
    assessments = list(result.scalars().all())

    return AssessmentListResponse(
        assessments=[AssessmentResponse.model_validate(a) for a in assessments],
        total=total,
    )


@router.get(
    "/assessments/{assessment_id}",
    response_model=AssessmentResponse,
    summary="Get assessment results",
    description="Fetch complete results for an assessment run, including job profile, score, summary, and all skill findings.",
)
async def get_assessment(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
    orchestrator: AssessmentOrchestrator = Depends(get_orchestrator),
):
    assessment = await orchestrator.step_7_return_assessment(db, assessment_id)
    return assessment


@router.get(
    "/assessments/{assessment_id}/skills",
    response_model=List[SkillFindingResponse],
    summary="Get assessment skill findings",
    description="Retrieves the detailed list of skill findings and confidence tiers for a specific assessment.",
)
async def get_assessment_skills(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
):
    # Verify assessment exists
    check_stmt = select(Assessment).where(Assessment.id == assessment_id)
    check_res = await db.execute(check_stmt)
    if not check_res.scalar_one_or_none():
        raise NotFoundError("Assessment", assessment_id)

    stmt = (
        select(SkillFinding)
        .where(SkillFinding.assessment_id == assessment_id)
        .options(selectinload(SkillFinding.evidence_citations))
        .order_by(SkillFinding.id.asc())
    )
    result = await db.execute(stmt)
    findings = list(result.scalars().all())
    return [SkillFindingResponse.model_validate(f) for f in findings]


@router.get(
    "/repositories/{repository_id}/assessments",
    response_model=AssessmentListResponse,
    summary="Get repository assessment history",
    description="List all historical assessment runs and scores for a specific repository.",
)
async def list_repository_assessments(
    repository_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    # Verify repository exists
    repo_stmt = select(Repository).where(Repository.id == repository_id)
    repo_res = await db.execute(repo_stmt)
    if not repo_res.scalar_one_or_none():
        raise NotFoundError("Repository", repository_id)

    count_stmt = select(func.count(Assessment.id)).where(Assessment.repository_id == repository_id)
    total_res = await db.execute(count_stmt)
    total = total_res.scalar_one()

    stmt = (
        select(Assessment)
        .where(Assessment.repository_id == repository_id)
        .order_by(Assessment.id.desc())
        .offset(skip)
        .limit(limit)
        .options(
            selectinload(Assessment.job_profile),
            selectinload(Assessment.repository),
            selectinload(Assessment.skill_findings).selectinload(SkillFinding.evidence_citations),
            selectinload(Assessment.skill_gaps),
        )

    )
    result = await db.execute(stmt)
    assessments = list(result.scalars().all())

    return AssessmentListResponse(
        assessments=[AssessmentResponse.model_validate(a) for a in assessments],
        total=total,
    )
