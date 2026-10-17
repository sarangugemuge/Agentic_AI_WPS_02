"""Repository model — tracks GitHub repositories added for assessment."""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    github_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    latest_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    webhook_secret_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    assessments: Mapped[list["Assessment"]] = relationship(  # noqa: F821
        back_populates="repository", cascade="all, delete-orphan"
    )
    commits: Mapped[list["CommitHistory"]] = relationship(  # noqa: F821
        back_populates="repository", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("github_owner", "repo_name", name="uq_repository_owner_repo"),
        Index("ix_repositories_owner_name", "github_owner", "repo_name"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.github_owner}/{self.repo_name}"

    def __repr__(self) -> str:
        return f"<Repository {self.full_name}>"
