"""
LearningPlan, LearningPlanStep, and StepVerificationRecord models.
Provides persistence for the Gap Solver extension.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import String, DateTime, Text, Float, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LearningPlan(Base):
    __tablename__ = "learning_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    skill_gap_id: Mapped[int] = mapped_column(
        ForeignKey("skill_gaps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_skill: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    difficulty_level: Mapped[str] = mapped_column(String(50), default="intermediate", nullable=False)
    estimated_hours: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    
    # Phase D Rich Guided Workflow Fields
    objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    concept_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prerequisites_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_classification: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    existing_evidence_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    missing_evidence_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    repo_improvement_recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_resources_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    skill_gap: Mapped["SkillGap"] = relationship(back_populates="learning_plans")  # noqa: F821
    assessment: Mapped["Assessment"] = relationship()  # noqa: F821
    steps: Mapped[List["LearningPlanStep"]] = relationship(
        back_populates="learning_plan",
        cascade="all, delete-orphan",
        order_by="LearningPlanStep.step_number",
    )
    verification_records: Mapped[List["StepVerificationRecord"]] = relationship(
        back_populates="learning_plan",
        foreign_keys="[StepVerificationRecord.learning_plan_id]",
        cascade="all, delete-orphan",
        order_by="StepVerificationRecord.id.desc()",
    )

    __table_args__ = (
        Index("ix_learning_plans_gap_version", "skill_gap_id", "version"),
        Index("ix_learning_plans_assessment", "assessment_id"),
    )

    def __repr__(self) -> str:
        return f"<LearningPlan #{self.id} '{self.title}' v{self.version} [{self.status}]>"


class LearningPlanStep(Base):
    __tablename__ = "learning_plan_steps"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("learning_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    code_example: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected_artifact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Phase D Rich Step Fields
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exercise: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_rubric: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    status: Mapped[str] = mapped_column(
        String(50), default="not_started", nullable=False
    )  # not_started, in_progress, evidence_submitted, verified, failed_verification
    user_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    evidence_commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    learning_plan: Mapped["LearningPlan"] = relationship(back_populates="steps")
    verification_records: Mapped[List["StepVerificationRecord"]] = relationship(
        back_populates="step",
        cascade="all, delete-orphan",
        order_by="StepVerificationRecord.id.desc()",
    )

    __table_args__ = (
        Index("ix_learning_plan_steps_plan_step", "plan_id", "step_number"),
    )

    def __repr__(self) -> str:
        return f"<LearningPlanStep #{self.step_number} in Plan #{self.plan_id} [{self.status}]>"


class StepVerificationRecord(Base):
    __tablename__ = "step_verification_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    step_id: Mapped[int] = mapped_column(
        ForeignKey("learning_plan_steps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    learning_plan_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("learning_plans.id", ondelete="CASCADE"), nullable=True, index=True
    )
    original_assessment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subsequent_assessment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verdict: Mapped[str] = mapped_column(
        String(50), default="insufficient_evidence", nullable=False
    )  # verified, partially_demonstrated, insufficient_evidence, inaccessible
    rubric_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strengths: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    missing_elements: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Phase E Rich Verification & Evidence Provenance Fields
    evidence_type: Mapped[str] = mapped_column(String(50), default="code_file", nullable=False)
    evidence_source: Mapped[str] = mapped_column(String(100), default="github_repository", nullable=False)
    evidence_locations_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_found_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rubric_findings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    limitations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    missing_work: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_recommended_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reassessment_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    classification_change: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    verified_file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    step: Mapped["LearningPlanStep"] = relationship(back_populates="verification_records")
    learning_plan: Mapped[Optional["LearningPlan"]] = relationship(
        back_populates="verification_records", foreign_keys=[learning_plan_id]
    )
    original_assessment: Mapped[Optional["Assessment"]] = relationship(
        foreign_keys=[original_assessment_id]
    )  # noqa: F821
    subsequent_assessment: Mapped[Optional["Assessment"]] = relationship(
        foreign_keys=[subsequent_assessment_id]
    )  # noqa: F821

    __table_args__ = (
        Index("ix_step_verification_records_step", "step_id"),
        Index("ix_step_verification_records_plan", "learning_plan_id"),
        Index("ix_step_verification_records_orig_assess", "original_assessment_id"),
        Index("ix_step_verification_records_subsequent_assess", "subsequent_assessment_id"),
    )

    def __repr__(self) -> str:
        return f"<StepVerificationRecord Step #{self.step_id} [{self.verdict} ({self.rubric_score}%)]>"
