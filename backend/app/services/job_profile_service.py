"""
Job Profile Service — Handles parsing, skill extraction, and persistence of job descriptions.
"""
import logging
from typing import Any, List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, BusinessValidationError
from app.models.job_profile import JobProfile
from app.services.ai_service import get_ai_service

logger = logging.getLogger("skillsync.services.job_profile")


class JobProfileService:
    def __init__(self, ai_service: Any = None):
        self.ai_service = ai_service or get_ai_service()

    async def preview_extracted_skills(self, job_title: str, job_description: str) -> List[str]:
        """Extract skills from a raw job description without saving to the database."""
        if not job_title or not job_title.strip():
            raise BusinessValidationError("Job title cannot be empty.")
        if not job_description or len(job_description.strip()) < 20:
            raise BusinessValidationError("Job description must be at least 20 characters long.")

        return await self.ai_service.extract_skills(job_title, job_description)

    async def create_job_profile(
        self,
        db: AsyncSession,
        title: str,
        raw_description: str,
        company_context: Optional[str] = None,
    ) -> JobProfile:
        """Extract skills and persist a new JobProfile in the database."""
        if not title or not title.strip():
            raise BusinessValidationError("Job title is required.")
        if not raw_description or len(raw_description.strip()) < 20:
            raise BusinessValidationError("Job description must be at least 20 characters long.")

        skills = await self.ai_service.extract_skills(title, raw_description)

        profile = JobProfile(
            title=title.strip(),
            company_context=company_context.strip() if company_context else None,
            raw_description=raw_description.strip(),
        )
        profile.extracted_skills = skills

        db.add(profile)
        await db.flush()  # assign profile.id

        from app.models.job_skill_requirement import JobSkillRequirement
        for s in skills:
            req = JobSkillRequirement(
                job_profile_id=profile.id,
                skill_name=s,
                category="general",
                importance="required",
            )
            db.add(req)

        await db.commit()
        await db.refresh(profile)
        logger.info(f"Created JobProfile ID: {profile.id} with {len(skills)} extracted skills and requirements.")
        return profile


    async def get_job_profile(self, db: AsyncSession, job_profile_id: int) -> JobProfile:
        """Fetch job profile by ID or raise NotFoundError."""
        stmt = select(JobProfile).where(JobProfile.id == job_profile_id)
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()
        if not profile:
            raise NotFoundError("JobProfile", job_profile_id)
        return profile

    async def list_job_profiles(
        self, db: AsyncSession, skip: int = 0, limit: int = 50
    ) -> Tuple[List[JobProfile], int]:
        """List job profiles with pagination."""
        count_stmt = select(func.count(JobProfile.id))
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = select(JobProfile).order_by(JobProfile.id.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
        profiles = list(result.scalars().all())

        return profiles, total


def get_job_profile_service() -> JobProfileService:
    """FastAPI dependency provider for JobProfileService."""
    return JobProfileService()
