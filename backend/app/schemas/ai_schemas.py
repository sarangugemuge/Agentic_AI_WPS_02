"""
AI Schemas — Structured outputs and prompt schemas for Gemini 2.0 Flash.
Enforces strict response formats, evidence cross-validation, and uncertainty modeling.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class ExtractedSkillItem(BaseModel):
    """A single skill extracted from a job description."""
    name: str = Field(..., description="Canonical name of the skill or technology (e.g. Python, Docker, PostgreSQL)")
    category: str = Field(..., description="Consistent category (e.g. Languages, Web Frameworks, Database, DevOps, QA & Testing, Architecture)")
    is_explicit: bool = Field(True, description="True if explicitly mentioned in text, False if inferred from context/responsibilities")
    importance: str = Field("required", description="'required' or 'preferred'")


class JobSkillExtractionResult(BaseModel):
    """Result of skill extraction from job text."""
    skills: List[ExtractedSkillItem]
    role_summary: str = Field(..., description="Brief one-sentence summary of the role focus")


class AIEvidenceCitation(BaseModel):
    """Code evidence citation matching an actual file in the repository."""
    file_path: str = Field(..., description="Relative file path in the repository (MUST exist in repository artifacts)")
    start_line: Optional[int] = Field(None, description="Starting line number in file")
    end_line: Optional[int] = Field(None, description="Ending line number in file")
    code_snippet: Optional[str] = Field(None, description="Verbatim code snippet demonstrating the skill")
    context_explanation: str = Field(..., description="Specific explanation of how this code proves the skill")


class AISkillFinding(BaseModel):
    """AI evaluation for a single skill."""
    skill_name: str
    category: str
    status: str = Field(
        ...,
        description="'demonstrated' (proven with code), 'partially_demonstrated' (partial or basic proof), 'not_found' (no evidence in repo), 'manual_verification' (needs human check)",
    )
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in this finding between 0.0 and 1.0")
    rationale: str = Field(..., description="Evidence-backed reasoning for the status")
    limitations: Optional[str] = Field(None, description="Scope boundaries of evidence (e.g., lack of tests, missing production configs)")
    recommended_next_steps: Optional[str] = Field(None, description="Actionable advice for the learner to strengthen this skill in their repo")
    evidence_citations: List[AIEvidenceCitation] = Field(default_factory=list)


class AIAssessmentOutput(BaseModel):
    """Structured assessment output from Gemini."""
    overall_score: float = Field(..., ge=0.0, le=100.0, description="Overall matching percentage score (0-100)")
    summary: str = Field(..., description="Comprehensive assessment summary synthesizing strengths and gaps")
    findings: List[AISkillFinding]
    skill_gaps: List[str] = Field(default_factory=list, description="List of critical missing or partially demonstrated skills")
    prioritized_learning_recommendations: List[str] = Field(
        default_factory=list,
        description="Prioritized, actionable projects or features the learner should build to fill gaps",
    )


# Re-export Gap Solver AI schemas for unified access
from app.schemas.gap_solver import (  # noqa: E402
    AILearningPlanOutput,
    AILearningPlanStepOutput,
    VerifiedResourceItem,
)
