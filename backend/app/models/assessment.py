"""Assessment model — one assessment run per repo + job profile combination."""
import enum
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Float, Integer, ForeignKey, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AssessmentStatus(str, enum.Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class TriggerEvent(str, enum.Enum):
    MANUAL = "manual"
    PUSH = "push"
    WEBHOOK = "webhook"


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    job_profile_id: Mapped[int] = mapped_column(ForeignKey("job_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_event: Mapped[TriggerEvent] = mapped_column(
        SAEnum(TriggerEvent), default=TriggerEvent.MANUAL
    )
    status: Mapped[AssessmentStatus] = mapped_column(
        SAEnum(AssessmentStatus), default=AssessmentStatus.PENDING, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(back_populates="assessments")  # noqa: F821
    job_profile: Mapped["JobProfile"] = relationship(back_populates="assessments")  # noqa: F821
    skill_findings: Mapped[list["SkillFinding"]] = relationship(  # noqa: F821
        back_populates="assessment", cascade="all, delete-orphan"
    )
    skill_gaps: Mapped[list["SkillGap"]] = relationship(  # noqa: F821
        back_populates="assessment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_assessments_repo_job", "repository_id", "job_profile_id"),
        Index("ix_assessments_repo_version", "repository_id", "version"),
    )

    def __repr__(self) -> str:
        return f"<Assessment {self.id} v{self.version} [{self.status}]>"
