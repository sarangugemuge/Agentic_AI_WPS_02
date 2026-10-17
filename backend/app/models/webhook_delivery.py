"""WebhookDelivery model — tracks delivery IDs to prevent duplicate webhook processing."""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    delivery_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    repository_id: Mapped[int | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), default="push", nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="processed", nullable=False)  # "processed", "ignored", "duplicate", "failed"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    __table_args__ = (
        Index("ix_webhook_deliveries_repo_event", "repository_id", "event_type"),
    )

    def __repr__(self) -> str:
        return f"<WebhookDelivery {self.delivery_id} [{self.status}]>"
