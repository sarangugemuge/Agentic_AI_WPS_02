"""SkillGap model — represents verified skill gaps and actionable recommendations for an assessment."""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SkillGap(Base):
    __tablename__ = "skill_gaps"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gap_severity: Mapped[str] = mapped_column(
        String(50), default="missing", nullable=False
    )  # "missing", "partially_demonstrated"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1 = highest priority
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    assessment: Mapped["Assessment"] = relationship(back_populates="skill_gaps")  # noqa: F821
    learning_plans: Mapped[list["LearningPlan"]] = relationship(  # noqa: F821
        back_populates="skill_gap", cascade="all, delete-orphan", order_by="LearningPlan.id.desc()"
    )

    __table_args__ = (
        Index("ix_skill_gaps_assessment_priority", "assessment_id", "priority"),
    )

    def __repr__(self) -> str:
        return f"<SkillGap {self.skill_name} [priority={self.priority}]>"
