"""SkillFinding model — one finding per skill per assessment."""
import enum

from sqlalchemy import String, Text, Float, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SkillStatus(str, enum.Enum):
    DEMONSTRATED = "demonstrated"
    PARTIALLY_DEMONSTRATED = "partially_demonstrated"
    NOT_FOUND = "not_found"
    MANUAL_VERIFICATION = "manual_verification"


class SkillFinding(Base):
    __tablename__ = "skill_findings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id"), nullable=False, index=True
    )
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[SkillStatus] = mapped_column(
        SAEnum(SkillStatus), default=SkillStatus.NOT_FOUND
    )
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    assessment: Mapped["Assessment"] = relationship(back_populates="skill_findings")  # noqa: F821
    evidence_citations: Mapped[list["EvidenceCitation"]] = relationship(  # noqa: F821
        back_populates="skill_finding", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SkillFinding {self.skill_name} [{self.status}]>"
