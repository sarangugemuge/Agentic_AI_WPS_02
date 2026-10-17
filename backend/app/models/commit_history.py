"""CommitHistory model — records repository commit revisions, timestamps, and authors for reproducibility."""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CommitHistory(Base):
    __tablename__ = "commit_history"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(  # noqa: F821
        back_populates="commits"
    )

    __table_args__ = (
        UniqueConstraint("repository_id", "commit_sha", name="uq_repo_commit"),
        Index("ix_commit_history_repo_committed", "repository_id", "committed_at"),
    )

    def __repr__(self) -> str:
        return f"<CommitHistory {self.commit_sha[:7]} in repo {self.repository_id}>"
