"""
Job Profiles API routes — Parse job descriptions, preview skills, and manage job profiles.
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.job_profile import (
    JobProfileCreate,
    JobProfileResponse,
    JobProfileListResponse,
    SkillExtractionRequest,
    SkillExtractionResponse,
)
from app.services.job_profile_service import JobProfileService, get_job_profile_service

router = APIRouter()


@router.post(
    "/job-profiles/extract-skills",
    response_model=SkillExtractionResponse,
    summary="Preview skills from job description",
    description="Extracts key technical competencies and skills from raw job text without creating a database record.",
)
async def extract_skills_preview(
    payload: SkillExtractionRequest,
    job_service: JobProfileService = Depends(get_job_profile_service),
):
    skills = await job_service.preview_extracted_skills(
        job_title=payload.job_title,
        job_description=payload.job_description,
    )
    return SkillExtractionResponse(
        job_title=payload.job_title,
        extracted_skills=skills,
        skill_count=len(skills),
    )


@router.post(
    "/job-profiles",
    response_model=JobProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a job profile",
    description="Parses job description text, extracts required skills using the AI service, and persists the profile.",
)
async def create_job_profile(
    payload: JobProfileCreate,
    db: AsyncSession = Depends(get_db),
    job_service: JobProfileService = Depends(get_job_profile_service),
):
    profile = await job_service.create_job_profile(
        db=db,
        title=payload.resolved_title,
        raw_description=payload.resolved_description,
        company_context=payload.company_context,
    )
    return profile


@router.get(
    "/job-profiles",
    response_model=JobProfileListResponse,
    summary="List job profiles",
    description="Returns a paginated list of all created job profiles.",
)
async def list_job_profiles(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    job_service: JobProfileService = Depends(get_job_profile_service),
):
    profiles, total = await job_service.list_job_profiles(db, skip=skip, limit=limit)
    return JobProfileListResponse(
        job_profiles=[JobProfileResponse.model_validate(p) for p in profiles],
        total=total,
    )


@router.get(
    "/job-profiles/{job_profile_id}",
    response_model=JobProfileResponse,
    summary="Get job profile by ID",
    description="Retrieves a stored job profile and its extracted skills.",
)
async def get_job_profile(
    job_profile_id: int,
    db: AsyncSession = Depends(get_db),
    job_service: JobProfileService = Depends(get_job_profile_service),
):
    profile = await job_service.get_job_profile(db, job_profile_id)
    return profile
