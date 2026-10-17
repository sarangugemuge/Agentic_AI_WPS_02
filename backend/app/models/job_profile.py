"""Job profile model — stores a parsed job description with extracted skills."""
import json
from datetime import datetime, timezone
from typing import List

from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobProfile(Base):
    __tablename__ = "job_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_skills_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    assessments: Mapped[list["Assessment"]] = relationship(  # noqa: F821
        back_populates="job_profile"
    )
    skill_requirements: Mapped[list["JobSkillRequirement"]] = relationship(  # noqa: F821
        back_populates="job_profile", cascade="all, delete-orphan"
    )

    @property
    def extracted_skills(self) -> List[str]:
        if self.extracted_skills_json:
            try:
                return json.loads(self.extracted_skills_json)
            except Exception:
                return []
        return []

    @extracted_skills.setter
    def extracted_skills(self, skills: List[str]) -> None:
        self.extracted_skills_json = json.dumps(skills)

    def __repr__(self) -> str:
        return f"<JobProfile {self.title}>"
