"""EvidenceCitation model — file-level evidence backing each skill finding."""
from sqlalchemy import String, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EvidenceCitation(Base):
    __tablename__ = "evidence_citations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    skill_finding_id: Mapped[int] = mapped_column(
        ForeignKey("skill_findings.id"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    skill_finding: Mapped["SkillFinding"] = relationship(back_populates="evidence_citations")  # noqa: F821

    def __repr__(self) -> str:
        loc = f":{self.start_line}" if self.start_line else ""
        return f"<EvidenceCitation {self.file_path}{loc}>"
