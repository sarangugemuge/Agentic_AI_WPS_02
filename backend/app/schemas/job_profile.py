"""
Pydantic schemas for JobProfile requests, extraction, and responses.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class JobProfileCreate(BaseModel):
    """Schema for creating a new job profile."""
    title: Optional[str] = Field(
        None,
        min_length=2,
        max_length=255,
        description="Job title, e.g. 'Senior Full-Stack Engineer'",
        examples=["Senior Backend Engineer"],
    )
    job_title: Optional[str] = Field(None, min_length=2, max_length=255, description="Alias for title")
    raw_description: Optional[str] = Field(
        None,
        min_length=20,
        description="Raw text of the job description or role requirements",
        examples=["We are looking for a Python and FastAPI engineer with PostgreSQL experience..."],
    )
    job_description: Optional[str] = Field(None, min_length=20, description="Alias for raw_description")
    company_context: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional company name or context",
        examples=["Acme Corp"],
    )

    @property
    def resolved_title(self) -> str:
        return (self.title or self.job_title or "").strip()

    @property
    def resolved_description(self) -> str:
        return (self.raw_description or self.job_description or "").strip()


class JobProfileResponse(BaseModel):
    """Schema for returning a job profile with extracted skills."""
    id: int
    title: str
    company_context: Optional[str] = None
    raw_description: str
    extracted_skills: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class JobProfileListResponse(BaseModel):
    """List of job profiles."""
    job_profiles: List[JobProfileResponse]
    total: int


class SkillExtractionRequest(BaseModel):
    """Schema for extracting skills from a raw job description without creating a profile."""
    job_title: str = Field(..., min_length=2, max_length=255)
    job_description: str = Field(..., min_length=20)


class SkillExtractionResponse(BaseModel):
    """Schema for previewing extracted skills from a job description."""
    job_title: str
    extracted_skills: List[str]
    skill_count: int
