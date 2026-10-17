"""
Pydantic schemas for Assessment and JobProfile requests and responses.
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, model_validator

from app.schemas.repository import RepositoryResponse


# ── Job Profile & Assessment Create Schemas ─────────────────────────

class AssessmentCreate(BaseModel):
    """Schema for triggering a new assessment."""
    repository_id: int = Field(..., description="ID of the tracked repository")
    job_profile_id: Optional[int] = Field(
        None,
        description="Optional ID of an existing job profile to assess against",
    )
    job_title: Optional[str] = Field(
        None,
        max_length=255,
        description="Job title / role if creating a new profile on the fly",
        examples=["Senior Backend Engineer"],
    )
    job_description: Optional[str] = Field(
        None,
        description="Full job description text if creating a new profile on the fly",
    )
    company_context: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional company name or context",
    )

    @model_validator(mode="after")
    def validate_requirements(self) -> "AssessmentCreate":
        if not self.job_profile_id and not (self.job_title and self.job_description):
            raise ValueError(
                "Either 'job_profile_id' or both 'job_title' and 'job_description' must be provided."
            )
        if self.job_description and len(self.job_description.strip()) < 20:
            raise ValueError("Job description must be at least 20 characters long.")
        return self


class JobProfileResponse(BaseModel):
    """Schema for a job profile embedded in an assessment response."""
    id: int
    title: str
    company_context: Optional[str]
    extracted_skills: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Skill Finding Schemas ────────────────────────────────────────────

class EvidenceCitationResponse(BaseModel):
    """Schema for an evidence citation."""
    id: int
    file_path: str
    start_line: Optional[int]
    end_line: Optional[int]
    commit_sha: Optional[str]
    code_snippet: Optional[str]
    context_explanation: Optional[str]

    model_config = {"from_attributes": True}


class SkillFindingResponse(BaseModel):
    """Schema for a single skill finding in an assessment."""
    id: int
    skill_name: str
    category: Optional[str]
    status: str
    confidence_score: Optional[float]
    rationale: Optional[str]
    limitations: Optional[str] = None
    recommended_next_steps: Optional[str] = None
    evidence_citations: List[EvidenceCitationResponse] = []

    model_config = {"from_attributes": True}


class SkillGapResponse(BaseModel):
    """Schema for an identified skill gap and actionable recommendation."""
    id: int
    skill_name: str
    category: Optional[str] = None
    gap_severity: str
    description: Optional[str] = None
    recommended_action: Optional[str] = None
    priority: int = 1
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Assessment Schemas ───────────────────────────────────────────────

class AssessmentResponse(BaseModel):
    """Full assessment response schema."""
    id: int
    repository_id: int
    job_profile_id: int
    version: int = 1
    commit_sha: Optional[str]
    overall_score: Optional[float]
    summary: Optional[str]
    trigger_event: str
    status: str
    error_message: Optional[str]
    created_at: datetime
    job_profile: Optional[JobProfileResponse] = None
    repository: Optional[RepositoryResponse] = None
    skill_findings: List[SkillFindingResponse] = []
    skill_gaps: List[SkillGapResponse] = []

    model_config = {"from_attributes": True}


class AssessmentListResponse(BaseModel):
    """Schema for a list of assessments."""
    assessments: List[AssessmentResponse]
    total: int



class AssessmentTriggerResponse(BaseModel):
    """Schema returned immediately when an assessment is triggered."""
    assessment_id: int
    status: str
    message: str
