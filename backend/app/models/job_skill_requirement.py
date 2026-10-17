"""JobSkillRequirement model — explicit and inferred skills extracted from a job description."""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobSkillRequirement(Base):
    __tablename__ = "job_skill_requirements"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    job_profile_id: Mapped[int] = mapped_column(
        ForeignKey("job_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    importance: Mapped[str] = mapped_column(
        String(50), default="required", nullable=False
    )  # "required", "preferred", "inferred"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    job_profile: Mapped["JobProfile"] = relationship(  # noqa: F821
        back_populates="skill_requirements"
    )

    __table_args__ = (
        Index("ix_job_skills_profile_skill", "job_profile_id", "skill_name"),
    )

    def __repr__(self) -> str:
        return f"<JobSkillRequirement {self.skill_name} [{self.importance}]>"
