"""
Pydantic schemas for SkillSync Gap Solver requests, responses, and AI generation contracts.
Enforces Phase D deterministic structured output validation.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
import json

from pydantic import BaseModel, Field, field_validator, model_validator


VALID_STEP_STATUSES = {
    "not_started",
    "in_progress",
    "evidence_submitted",
    "verified",
    "failed_verification",
}


class LearningPlanCreateRequest(BaseModel):
    """Request payload to initiate or regenerate a learning plan for a skill gap."""
    difficulty_level: Optional[str] = Field("intermediate", description="Target difficulty: beginner, intermediate, advanced")
    focus_areas: Optional[List[str]] = Field(None, description="Optional focus areas or specializations")

    @field_validator("difficulty_level")
    @classmethod
    def validate_difficulty_level(cls, v: Optional[str]) -> str:
        if v is None:
            return "intermediate"
        v_clean = v.strip().lower()
        if not v_clean:
            return "intermediate"
        if v_clean not in ("beginner", "intermediate", "advanced"):
            raise ValueError(f"Invalid difficulty_level '{v}'. Must be one of: 'beginner', 'intermediate', 'advanced'.")
        return v_clean


class VerifiedResourceItem(BaseModel):
    """Verified official documentation resource link (never fabricated)."""
    title: str = Field(..., description="Title of official documentation resource")
    url: str = Field(..., description="Verified canonical documentation URL")


class AILearningPlanStepOutput(BaseModel):
    """Structured AI output schema for an individual learning plan step."""
    step_number: int = Field(..., ge=1, description="Sequential 1-indexed step number")
    title: str = Field(..., min_length=3, description="Concise, actionable step title")
    instruction: str = Field(..., min_length=10, description="Clear, detailed implementation instructions")
    code_example: Optional[str] = Field(None, description="Syntactically valid illustrative code pattern")
    expected_artifact: Optional[str] = Field(None, description="Expected repository file or artifact produced")
    acceptance_criteria: Optional[str] = Field(None, description="Deterministic criteria required to verify this step")
    exercise: Optional[str] = Field(None, description="Hands-on coding exercise")
    verification_rubric: Optional[str] = Field(None, description="Rubric for evaluating code evidence")


class AILearningPlanOutput(BaseModel):
    """
    Deterministic AI structured output schema for learning plan generation.
    Validated by Gemini structured output response_schema before database persistence.
    """
    title: str = Field(..., min_length=5, description="Clear title for the learning plan")
    overview: str = Field(..., min_length=20, description="Comprehensive overview of the gap and remediation roadmap")
    objective: str = Field(..., min_length=15, description="Clear learning objective for mastering the skill")
    concept_explanation: str = Field(..., min_length=20, description="Deep concept explanation of the underlying technology")
    prerequisites: List[str] = Field(default_factory=list, description="Foundational prerequisites needed before starting")
    difficulty_level: str = Field("intermediate", description="Target difficulty: beginner, intermediate, advanced")
    estimated_hours: float = Field(3.0, gt=0, le=50.0, description="Estimated total hours to complete plan")
    current_classification: str = Field(
        ..., description="Assessment status: 'not_demonstrated' or 'partially_demonstrated'"
    )
    existing_evidence_summary: str = Field(
        ..., description="Summary of existing repository evidence or lack thereof"
    )
    missing_evidence_summary: str = Field(
        ..., description="Specific elements missing to satisfy the job requirement"
    )
    repo_improvement_recommendation: str = Field(
        ..., description="Concrete, actionable improvement for candidate's actual repository"
    )
    verified_resources: List[VerifiedResourceItem] = Field(
        default_factory=list, description="Strictly verified canonical documentation links"
    )
    steps: List[AILearningPlanStepOutput] = Field(
        ..., min_length=1, description="Ordered sequential implementation steps"
    )


class LearningPlanStepResponse(BaseModel):
    """Schema for an individual ordered learning step."""
    id: int
    plan_id: int
    step_number: int
    title: str
    instruction: str
    code_example: Optional[str] = None
    expected_artifact: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    exercise: Optional[str] = None
    verification_rubric: Optional[str] = None
    status: str
    user_notes: Optional[str] = None
    evidence_file_path: Optional[str] = None
    evidence_commit_sha: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StepProgressUpdateRequest(BaseModel):
    """Schema for updating candidate notes or progress status on a step."""
    status: Optional[str] = Field(
        None,
        description="Updated step status: not_started, in_progress, evidence_submitted, verified, failed_verification",
    )
    user_notes: Optional[str] = Field(None, description="Candidate reflection or implementation notes")
    evidence_file_path: Optional[str] = Field(None, max_length=1000, description="Relative file path in repository")
    evidence_commit_sha: Optional[str] = Field(None, max_length=40, description="Commit SHA containing work")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip().lower()
            return v_clean if v_clean else None
        return v

    @field_validator("user_notes")
    @classmethod
    def validate_user_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip()
            return v_clean if v_clean else None
        return v

    @field_validator("evidence_file_path")
    @classmethod
    def validate_file_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip()
            return v_clean if v_clean else None
        return v

    @field_validator("evidence_commit_sha")
    @classmethod
    def validate_commit_sha(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip()
            return v_clean if v_clean else None
        return v


class LearningPlanResponse(BaseModel):
    """Full schema for a persisted learning roadmap plan with ordered steps."""
    id: int
    skill_gap_id: int
    assessment_id: int
    version: int
    title: str
    overview: Optional[str] = None
    target_skill: str
    difficulty_level: str
    estimated_hours: float
    status: str
    objective: Optional[str] = None
    concept_explanation: Optional[str] = None
    prerequisites: List[str] = []
    current_classification: Optional[str] = None
    existing_evidence_summary: Optional[str] = None
    missing_evidence_summary: Optional[str] = None
    repo_improvement_recommendation: Optional[str] = None
    verified_resources: List[VerifiedResourceItem] = []
    created_at: datetime
    updated_at: datetime
    steps: List[LearningPlanStepResponse] = []

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def parse_orm_fields(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            prereqs_raw = getattr(data, "prerequisites_json", None)
            prereqs = []
            if prereqs_raw:
                try:
                    prereqs = json.loads(prereqs_raw) if isinstance(prereqs_raw, str) else prereqs_raw
                except Exception:
                    prereqs = []

            res_raw = getattr(data, "verified_resources_json", None)
            resources = []
            if res_raw:
                try:
                    loaded = json.loads(res_raw) if isinstance(res_raw, str) else res_raw
                    resources = [VerifiedResourceItem(**r) if isinstance(r, dict) else r for r in loaded]
                except Exception:
                    resources = []

            return {
                "id": data.id,
                "skill_gap_id": data.skill_gap_id,
                "assessment_id": data.assessment_id,
                "version": data.version,
                "title": data.title,
                "overview": data.overview,
                "target_skill": data.target_skill,
                "difficulty_level": data.difficulty_level,
                "estimated_hours": data.estimated_hours,
                "status": data.status,
                "objective": data.objective,
                "concept_explanation": data.concept_explanation,
                "prerequisites": prereqs,
                "current_classification": data.current_classification,
                "existing_evidence_summary": data.existing_evidence_summary,
                "missing_evidence_summary": data.missing_evidence_summary,
                "repo_improvement_recommendation": data.repo_improvement_recommendation,
                "verified_resources": resources,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "steps": getattr(data, "steps", []),
            }
        return data

    @classmethod
    def from_orm_plan(cls, plan: Any) -> "LearningPlanResponse":

        """Helper to safely construct response from ORM entity, deserializing JSON fields."""
        prereqs = []
        if getattr(plan, "prerequisites_json", None):
            try:
                prereqs = json.loads(plan.prerequisites_json)
            except Exception:
                prereqs = []

        resources = []
        if getattr(plan, "verified_resources_json", None):
            try:
                raw_res = json.loads(plan.verified_resources_json)
                resources = [VerifiedResourceItem(**r) for r in raw_res]
            except Exception:
                resources = []

        return cls(
            id=plan.id,
            skill_gap_id=plan.skill_gap_id,
            assessment_id=plan.assessment_id,
            version=plan.version,
            title=plan.title,
            overview=plan.overview,
            target_skill=plan.target_skill,
            difficulty_level=plan.difficulty_level,
            estimated_hours=plan.estimated_hours,
            status=plan.status,
            objective=plan.objective,
            concept_explanation=plan.concept_explanation,
            prerequisites=prereqs,
            current_classification=plan.current_classification,
            existing_evidence_summary=plan.existing_evidence_summary,
            missing_evidence_summary=plan.missing_evidence_summary,
            repo_improvement_recommendation=plan.repo_improvement_recommendation,
            verified_resources=resources,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            steps=[LearningPlanStepResponse.model_validate(s) for s in getattr(plan, "steps", [])],
        )


class SkillGapDetailResponse(BaseModel):
    """Schema for an identified skill gap with learning plan status."""
    id: int
    assessment_id: int
    skill_name: str
    category: Optional[str] = None
    gap_severity: str
    description: Optional[str] = None
    recommended_action: Optional[str] = None
    priority: int = 1
    created_at: datetime
    active_plan_id: Optional[int] = None
    active_plan_status: Optional[str] = None

    model_config = {"from_attributes": True}


class SkillGapListResponse(BaseModel):
    """Schema for listing all identified gaps for a specific assessment."""
    assessment_id: int
    total: int
    gaps: List[SkillGapDetailResponse]


class RubricFindingItem(BaseModel):
    """Evaluation result for an individual rubric criterion."""
    criterion: str
    status: str  # "verified", "partially_demonstrated", "insufficient", "inaccessible"
    score: float  # 0.0 to 100.0
    evidence: Optional[str] = None
    notes: Optional[str] = None


class StepVerificationRequest(BaseModel):
    """Payload to request evidence-based verification of a learning step."""
    evidence_file_path: Optional[str] = Field(None, max_length=1000, description="Relative file path in repository")
    evidence_file_paths: Optional[List[str]] = Field(None, description="Optional multiple relative file paths submitted as evidence")
    commit_sha: Optional[str] = Field(None, max_length=40, description="Specific commit SHA to inspect")
    evidence_type: Optional[str] = Field("code_file", description="Type of evidence: code_file, test_file, commit, pull_request")
    user_notes: Optional[str] = Field(None, description="Candidate context or explanation on evidence")
    allow_private_repo: Optional[bool] = Field(False, description="Explicit authorization to inspect private repository if applicable")
    trigger_reassessment: Optional[bool] = Field(True, description="Whether to trigger reassessment workflow if verification succeeds")

    @field_validator("evidence_file_path")
    @classmethod
    def validate_evidence_file_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip()
            return v_clean if v_clean else None
        return v

    @field_validator("commit_sha")
    @classmethod
    def validate_commit_sha(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip()
            return v_clean if v_clean else None
        return v

    @field_validator("user_notes")
    @classmethod
    def validate_user_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip()
            return v_clean if v_clean else None
        return v


class StepVerificationRecordResponse(BaseModel):
    """Complete schema for an immutable step verification result with full provenance."""
    id: int
    step_id: int
    learning_plan_id: Optional[int] = None
    original_assessment_id: Optional[int] = None
    subsequent_assessment_id: Optional[int] = None
    verdict: str  # verified, partially_demonstrated, insufficient_evidence, inaccessible
    rubric_score: float = 0.0
    feedback: Optional[str] = None
    strengths: Optional[str] = None
    missing_elements: Optional[str] = None
    limitations: Optional[str] = None
    missing_work: Optional[str] = None
    next_recommended_action: Optional[str] = None
    evidence_type: str = "code_file"
    evidence_source: str = "github_repository"
    evidence_locations: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_found: List[str] = Field(default_factory=list)
    rubric_findings: List[RubricFindingItem] = Field(default_factory=list)
    reassessment_explanation: Optional[str] = None
    classification_change: Optional[str] = None
    commit_sha: Optional[str] = None
    verified_file_path: Optional[str] = None
    verified_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def parse_orm_fields(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            locs_raw = getattr(data, "evidence_locations_json", None)
            locs = []
            if locs_raw:
                try:
                    locs = json.loads(locs_raw) if isinstance(locs_raw, str) else locs_raw
                except Exception:
                    locs = []

            found_raw = getattr(data, "evidence_found_json", None)
            found = []
            if found_raw:
                try:
                    found = json.loads(found_raw) if isinstance(found_raw, str) else found_raw
                except Exception:
                    found = []

            rubric_raw = getattr(data, "rubric_findings_json", None)
            rubric = []
            if rubric_raw:
                try:
                    loaded = json.loads(rubric_raw) if isinstance(rubric_raw, str) else rubric_raw
                    rubric = [RubricFindingItem(**r) if isinstance(r, dict) else r for r in loaded]
                except Exception:
                    rubric = []

            return {
                "id": data.id,
                "step_id": data.step_id,
                "learning_plan_id": getattr(data, "learning_plan_id", None),
                "original_assessment_id": getattr(data, "original_assessment_id", None),
                "subsequent_assessment_id": getattr(data, "subsequent_assessment_id", None),
                "verdict": data.verdict,
                "rubric_score": data.rubric_score,
                "feedback": data.feedback,
                "strengths": data.strengths,
                "missing_elements": data.missing_elements,
                "limitations": getattr(data, "limitations", None),
                "missing_work": getattr(data, "missing_work", None),
                "next_recommended_action": getattr(data, "next_recommended_action", None),
                "evidence_type": getattr(data, "evidence_type", "code_file") or "code_file",
                "evidence_source": getattr(data, "evidence_source", "github_repository") or "github_repository",
                "evidence_locations": locs,
                "evidence_found": found,
                "rubric_findings": rubric,
                "reassessment_explanation": getattr(data, "reassessment_explanation", None),
                "classification_change": getattr(data, "classification_change", None),
                "commit_sha": data.commit_sha,
                "verified_file_path": data.verified_file_path,
                "verified_at": data.verified_at,
            }
        return data


class StepVerificationListResponse(BaseModel):
    """Schema for listing all immutable verification records for a learning step."""
    step_id: int
    total: int
    verifications: List[StepVerificationRecordResponse] = Field(default_factory=list)


RubricFindingItem.model_rebuild()
StepVerificationRequest.model_rebuild()
StepVerificationRecordResponse.model_rebuild()
StepVerificationListResponse.model_rebuild()

