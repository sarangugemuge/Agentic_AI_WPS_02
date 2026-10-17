"""
Skills API routes — Evidence inspection for specific skill findings.
"""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.models.skill_finding import SkillFinding
from app.schemas.assessment import EvidenceCitationResponse

router = APIRouter()


@router.get(
    "/assessments/{assessment_id}/skills/{skill_id}/evidence",
    response_model=List[EvidenceCitationResponse],
    summary="Get skill evidence citations",
    description="Retrieve code evidence citations, line numbers, and file paths backing a specific skill finding.",
)
async def get_skill_evidence(
    assessment_id: int,
    skill_id: int,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(SkillFinding)
        .where(
            SkillFinding.id == skill_id,
            SkillFinding.assessment_id == assessment_id,
        )
        .options(selectinload(SkillFinding.evidence_citations))
    )
    result = await db.execute(stmt)
    finding = result.scalar_one_or_none()

    if not finding:
        raise NotFoundError("SkillFinding", f"id={skill_id} in assessment={assessment_id}")

    return [EvidenceCitationResponse.model_validate(c) for c in finding.evidence_citations]
